# modules/help.py
# Compact help system with individual command lookups and private message support.

import re
import time
from .base import SimpleCommandModule

def setup(bot, config):
    """Initializes the Help module."""
    return Help(bot, config)

class Help(SimpleCommandModule):
    """Provides a list of commands and help for specific commands."""
    name = "help"
    version = "3.0.1"
    description = "Provides a list of commands and help for specific commands."
    
    def __init__(self, bot, config):
        """Initializes the module's state and registers commands."""
        super().__init__(bot)
        
        self.COOLDOWN_SECONDS = config.get("cooldown_seconds", 10.0)

        # State for tracking usage statistics
        self.set_state("help_requests", self.get_state("help_requests", 0))
        self.set_state("command_lookups", self.get_state("command_lookups", 0))
        self.set_state("last_help_time", self.get_state("last_help_time", {}))
        self.save_state()
        
    def _register_commands(self):
        """Registers the help-related commands."""
        self.register_command(r"^\s*!help\s*$", self._cmd_help_public,
                              name="help", description="Show available commands.")
        self.register_command(r"^\s*!help\s+(\S+)\s*$", self._cmd_help_command_public,
                              name="help command", description="Show help for a specific command.")

    def _get_all_commands(self, is_admin: bool):
        """
        Dynamically builds a dictionary of commands from all loaded modules,
        respecting the user's admin status.
        """
        all_commands = {}
        for module_instance in self.bot.pm.plugins.values():
            if hasattr(module_instance, "_commands"):
                for cmd_info in module_instance._commands.values():
                    # Skip commands that are admin-only if the user is not an admin
                    if cmd_info.get("admin_only") and not is_admin:
                        continue
                    
                    cmd_name = cmd_info.get("name")
                    if cmd_name:
                        all_commands[cmd_name] = {
                            "description": cmd_info.get("description", "No description available."),
                            "admin_only": cmd_info.get("admin_only", False)
                        }
        return all_commands

    def _get_command_list(self, is_admin: bool) -> str:
        """Builds a clean, comma-separated list of primary commands."""
        commands_dict = self._get_all_commands(is_admin)
        
        # Get the unique base command for each entry (e.g., 'hunt' from 'hunt top')
        primary_commands = sorted(list({name.split(" ")[0] for name in commands_dict.keys()}))
        
        # Add an asterisk to commands that have at least one admin-only subcommand
        display_names = []
        for cmd in primary_commands:
            is_any_admin = any(
                info.get("admin_only") 
                for name, info in commands_dict.items() 
                if name.startswith(cmd)
            )
            display_names.append(f"{cmd}*" if is_admin and is_any_admin else cmd)
            
        return ", ".join(display_names)

    def _get_command_help(self, command: str, is_admin: bool) -> list[str]:
        """Gets help for a specific command, including its subcommands."""
        command = command.lower().strip("!")
        all_commands = self._get_all_commands(is_admin)
        
        # Find all commands that match the base command (e.g., 'hunt' matches 'hunt score')
        matches = {
            name: info['description']
            for name, info in all_commands.items()
            if name == command or name.startswith(command + " ")
        }
        
        if not matches:
            return []

        # Format the help lines for output
        return [f"!{name}: {matches[name]}" for name in sorted(matches.keys())]

    def _update_stats(self, username: str, is_lookup: bool = False):
        """Updates usage statistics."""
        if is_lookup:
            self.set_state("command_lookups", self.get_state("command_lookups", 0) + 1)
        else:
            self.set_state("help_requests", self.get_state("help_requests", 0) + 1)
        
        # Update cooldown timestamp
        last_times = self.get_state("last_help_time", {})
        last_times[username.lower()] = time.time()
        self.set_state("last_help_time", last_times)
        self.save_state()

    # --- Public Channel Command Handlers ---

    def _cmd_help_public(self, connection, event, msg, username, match):
        """Handles !help in a channel by sending a PM."""
        self._handle_help_request(username, is_admin=self.bot.is_admin(event.source))
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you a list of my commands privately.")
        return True

    def _cmd_help_command_public(self, connection, event, msg, username, match):
        """Handles !help <command> in a channel by sending a PM."""
        command = match.group(1)
        is_admin = self.bot.is_admin(event.source)
        
        help_lines = self._get_command_help(command, is_admin)
        if help_lines:
            self._handle_help_request(username, command, is_admin)
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you the details for that command privately.")
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but I am not familiar with that command.")
        return True

    # --- Private Message Handler ---

    def on_privmsg(self, connection, event):
        """Handles help requests sent via private message."""
        msg = event.arguments[0].strip() if event.arguments else ""
        username = event.source.nick
        is_admin = self.bot.is_admin(event.source)
        
        # Check for 'help <command>'
        help_command_match = re.match(r"^\s*help\s+(\S+)\s*$", msg, re.IGNORECASE)
        if help_command_match:
            command = help_command_match.group(1)
            self._handle_help_request(username, command, is_admin)
            return True

        # Check for general 'help'
        if re.match(r"^\s*help\s*$", msg, re.IGNORECASE):
            self._handle_help_request(username, is_admin=is_admin)
            return True
        
        return False

    # --- Core Logic for Sending Help ---

    def _handle_help_request(self, username: str, command: str = None, is_admin: bool = False):
        """Core logic to generate and send help text to a user via PM."""
        last_times = self.get_state("last_help_time", {})
        if time.time() - last_times.get(username.lower(), 0) < self.COOLDOWN_SECONDS:
            return # Enforce cooldown silently in PM

        if command:
            # Specific command help
            help_lines = self._get_command_help(command, is_admin)
            if help_lines:
                for line in help_lines:
                    self.safe_privmsg(username, line)
            else:
                self.safe_privmsg(username, f"I am not familiar with the command '{command}'.")
            self._update_stats(username, is_lookup=True)
        else:
            # General command list
            cmd_list = self._get_command_list(is_admin)
            self.safe_privmsg(username, f"Available commands: {cmd_list}")
            
            note = " (commands marked with * have admin-only subcommands)" if is_admin else ""
            self.safe_privmsg(username, f"Use 'help <command>' for more details.{note}")
            self._update_stats(username, is_lookup=False)

