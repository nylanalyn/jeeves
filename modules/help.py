# modules/help.py
# Compact help system with individual command lookups
import re
import time
import sys
import functools
from typing import Optional, Dict, Any, List, Callable, Union
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Help(bot, config)

class Help(SimpleCommandModule):
    name = "help"
    version = "2.4.0"
    description = "Provides a list of commands and help for specific commands."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.COOLDOWN_SECONDS = config.get("cooldown_seconds", 10.0)
        self.set_state("last_help_time", self.get_state("last_help_time", {}))
        self.save_state()
        
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_NL_HELP = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what\s+(?:can\s+you\s+do|commands)|help\s*me|show\s+me\s+(?:the\s+)?commands)\b",
            re.IGNORECASE
        )
        
    def _register_commands(self):
        self.register_command(r"^\s*!help\s*$", self._cmd_help,
                              name="help", description="Show available commands.")
        self.register_command(r"^\s*!help\s+(\S+)\s*$", self._cmd_help_command,
                              name="help command", description="Show help for a specific command.")

    def _get_all_commands(self, is_admin: bool) -> Dict[str, Dict[str, Any]]:
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
        return now - last_times.get(username.lower(), 0) >= self.COOLDOWN_SECONDS

    def _mark_help_given(self, username: str):
        last_times = self.get_state("last_help_time", {})
        last_times[username.lower()] = time.time()
        self.set_state("last_help_time", last_times)
        self.save_state()

    def _get_command_list_str(self, is_admin: bool) -> str:
        commands_dict = self._get_all_commands(is_admin)
        primary_commands = sorted(list({name.split(" ")[0] for name in commands_dict}))
        
        display_names = []
        for cmd in primary_commands:
            is_any_admin = False
            if is_admin:
                if any(info.get("admin_only") for name, info in commands_dict.items() if name.startswith(cmd)):
                    is_any_admin = True
            display_names.append(f"{cmd}{'*' if is_any_admin else ''}")
            
        return ", ".join(display_names)

    def _get_command_help_lines(self, command: str, is_admin: bool) -> List[str]:
        command = command.lower().strip("!")
        all_commands = self._get_all_commands(is_admin)
        
        matches = {name: info['description'] for name, info in all_commands.items() if name == command or name.startswith(command + " ")}
        
        return [f"!{name}: {desc}" for name, desc in sorted(matches.items())]

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if self._can_give_help(username) and self.RE_NL_HELP.search(msg):
            self._send_help_privately(connection, event, username)
            return True
        return False

    def on_privmsg(self, connection, event):
        msg, username = event.arguments[0], event.source.nick
        if not self._can_give_help(username): return

        is_admin = self.bot.is_admin(username)
        help_cmd_match = re.match(r"^\s*help\s+(\S+)\s*$", msg, re.IGNORECASE)
        
        if help_cmd_match:
            command = help_cmd_match.group(1)
            help_lines = self._get_command_help_lines(command, is_admin)
            if help_lines:
                for line in help_lines: self.safe_privmsg(username, line)
            else:
                self.safe_privmsg(username, f"Unknown command. Available: {self._get_command_list_str(is_admin)}")
            self._mark_help_given(username)
        elif re.match(r"^\s*help\s*$", msg, re.IGNORECASE):
            self.safe_privmsg(username, f"Available commands: {self._get_command_list_str(is_admin)}")
            self.safe_privmsg(username, "Use 'help <command>' for details.")
            self._mark_help_given(username)

    def _send_help_privately(self, connection, event, username):
        is_admin = self.bot.is_admin(username)
        cmd_list = self._get_command_list_str(is_admin)
        
        self.safe_privmsg(username, f"Available commands: {cmd_list}")
        note = " (admin commands are marked with *)" if is_admin else ""
        self.safe_privmsg(username, f"Use '!help <command>' for more details.{note}")
        
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you a list of my commands privately.")
        self._mark_help_given(username)

    def _cmd_help(self, connection, event, msg, username, match):
        if not self._can_give_help(username): return True
        self._send_help_privately(connection, event, username)
        return True

    def _cmd_help_command(self, connection, event, msg, username, match):
        if not self._can_give_help(username): return True
        is_admin = self.bot.is_admin(username)
        command = match.group(1)
        help_lines = self._get_command_help_lines(command, is_admin)
        
        if help_lines:
            for line in help_lines: self.safe_privmsg(username, line)
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you the details for that command privately.")
        else:
            self.safe_reply(connection, event, f"I'm afraid I don't know that command, {self.bot.title_for(username)}.")
        
        self._mark_help_given(username)
        return True

