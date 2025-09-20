# modules/help.py
# Compact help system with individual command lookups using ModuleBase
import re
import time
import sys
import functools
from typing import Optional, Dict, Any, List, Callable, Union
from .base import SimpleCommandModule, ResponseModule, admin_required

def setup(bot, config):
    return Help(bot, config)

class Help(SimpleCommandModule):
    name = "help"
    version = "2.4.0" # version bumped for refactor
    description = "Provides a list of commands and help for specific commands."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.COOLDOWN_SECONDS = config.get("cooldown_seconds", 10.0)

        self.set_state("help_requests", self.get_state("help_requests", 0))
        self.set_state("command_lookups", self.get_state("command_lookups", 0))
        self.set_state("users_helped", self.get_state("users_helped", []))
        self.set_state("last_help_time", self.get_state("last_help_time", {}))
        self.save_state()
        
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_NL_HELP = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what\s+(?:can\s+you\s+do|commands)|help\s+me|show\s+me\s+(?:the\s+)?commands)\b",
            re.IGNORECASE
        )
        
    def _register_commands(self):
        self.register_command(r"^\s*!help\s+stats\s*$", self._cmd_stats,
                              name="help stats", admin_only=True, description="Show help module statistics.")
        self.register_command(r"^\s*!help\s*$", self._cmd_help,
                              name="help", description="Show available commands.")
        self.register_command(r"^\s*!help\s+(\S+)\s*$", self._cmd_help_command,
                              name="help command", description="Show help for a specific command.")

    def _get_all_commands(self, is_admin: bool) -> Dict[str, Dict[str, Any]]:
        """Dynamically builds a dictionary of commands from all loaded modules."""
        all_commands = {}
        for module_instance in self.bot.pm.plugins.values():
            if hasattr(module_instance, "_commands"):
                for cmd_info in module_instance._commands.values():
                    if cmd_info.get("admin_only") and not is_admin:
                        continue
                    
                    cmd_name = cmd_info.get("name")
                    if cmd_name:
                        all_commands[cmd_name] = {
                            "description": cmd_info.get("description", "No description available."),
                            "admin_only": cmd_info.get("admin_only", False)
                        }
        return all_commands

    def _can_give_help(self, username: str) -> bool:
        if self.COOLDOWN_SECONDS <= 0: return True
        now = time.time()
        last_times = self.get_state("last_help_time", {})
        last_time = last_times.get(username.lower(), 0)
        return now - last_time >= self.COOLDOWN_SECONDS

    def _mark_help_given(self, username: str, is_command_lookup: bool = False):
        last_times = self.get_state("last_help_time", {})
        last_times[username.lower()] = time.time()
        self.set_state("last_help_time", last_times)
        if is_command_lookup:
            self.set_state("command_lookups", self.get_state("command_lookups", 0) + 1)
        else:
            self.set_state("help_requests", self.get_state("help_requests", 0) + 1)
        users = self.get_state("users_helped", [])
        username_lower = username.lower()
        if username_lower not in users:
            users.append(username_lower)
            self.set_state("users_helped", users)
        self.save_state()

    def _get_command_list(self, is_admin: bool) -> str:
        """Builds a clean list of primary commands."""
        commands_dict = self._get_all_commands(is_admin)
        primary_commands = set()
        for name in commands_dict.keys():
            primary_command = name.split(" ")[0]
            primary_commands.add(primary_command)
        
        command_names = []
        for cmd in sorted(list(primary_commands)):
            is_any_admin = False
            if is_admin:
                for name, info in commands_dict.items():
                    if name.startswith(cmd) and info.get("admin_only"):
                        is_any_admin = True
                        break
            
            display_name = cmd
            if is_any_admin:
                display_name += "*"
            command_names.append(display_name)
            
        return ", ".join(command_names)

    def _get_command_help(self, command: str, is_admin: bool) -> List[str]:
        """Gets help for a specific command, including subcommands."""
        command = command.lower().strip("!")
        all_commands = self._get_all_commands(is_admin)
        
        matches = {}
        for name, info in all_commands.items():
            if name == command or name.startswith(command + " "):
                matches[name] = info['description']
        
        if not matches:
            return []

        help_lines = []
        for name in sorted(matches.keys()):
            help_lines.append(f"!{name}: {matches[name]}")
        
        return help_lines

    def on_ambient_message(self, connection, event, msg, username):
        if not self._can_give_help(username):
            return False
            
        if self.RE_NL_HELP.search(msg):
            self._cmd_help(connection, event, msg, username, None)
            return True
        
        return False

    def on_privmsg(self, connection, event):
        """private message handler."""
        msg = event.arguments[0] if event.arguments else ""
        username = event.source.split('!')[0]
        is_admin = self.bot.is_admin(username)

        if not self._can_give_help(username):
            return False

        # Check for 'help <command>' first
        help_command_match = re.match(r"^\s*help\s+(\S+)\s*$", msg, re.IGNORECASE)
        if help_command_match:
            command = help_command_match.group(1)
            help_lines = self._get_command_help(command, is_admin)
            
            if help_lines:
                for line in help_lines:
                    self.safe_privmsg(username, line)
                self._mark_help_given(username, is_command_lookup=True)
            else:
                cmd_list = self._get_command_list(is_admin)
                self.safe_privmsg(username, f"Unknown command. Available commands: {cmd_list}")
            return True

        # Check for general 'help' second
        help_simple_match = re.match(r"^\s*help\s*$", msg, re.IGNORECASE)
        if help_simple_match:
            cmd_list = self._get_command_list(is_admin)
            self.safe_privmsg(username, f"Available commands: {cmd_list}")
            self.safe_privmsg(username, "Use 'help <command>' for details on a specific command.")
            self._mark_help_given(username)
            return True

        return False

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        help_requests = stats.get("help_requests", 0)
        command_lookups = stats.get("command_lookups", 0)
        unique_users = len(stats.get("users_helped", []))
        self.safe_reply(connection, event, f"Help stats: {help_requests} general requests, {command_lookups} command lookups from {unique_users} unique users.")
        return True

    def _cmd_help(self, connection, event, msg, username, match):
        """Handles the general !help command by sending all info privately."""
        is_admin = self.bot.is_admin(username)
        cmd_list = self._get_command_list(is_admin)
        
        # Send all help text privately
        self.safe_privmsg(username, f"Available commands: {cmd_list}")
        
        available_note = " (admin commands are marked with *)" if is_admin else ""
        self.safe_privmsg(username, f"Use '!help <command>' for more details on a specific command.{available_note}")
        
        # Send a confirmation to the channel
        self.safe_reply(connection, event, f"{username}, I have sent you a list of my available commands privately.")
        
        self._mark_help_given(username)
        return True

    def _cmd_help_command(self, connection, event, msg, username, match):
        """Handles getting help for a specific command by sending it privately."""
        is_admin = self.bot.is_admin(username)
        command = match.group(1)
        help_lines = self._get_command_help(command, is_admin)
        
        if help_lines:
            # Send the detailed help privately
            for line in help_lines:
                self.safe_privmsg(username, line)
            
            # Send a confirmation to the channel
            self.safe_reply(connection, event, f"{username}, I have sent you the details for that command privately.")
            self._mark_help_given(username, is_command_lookup=True)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I don't know that command.")
        return True
