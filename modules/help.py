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
    version = "4.1.0" # Added configurable web reference link
    description = "Provides a list of commands and help for specific commands."
    
    def __init__(self, bot, config):
        """Initializes the module's state and registers commands."""
        super().__init__(bot, config)
        self.set_state("last_help_time", self.get_state("last_help_time", {}))
        self.save_state()

    def _register_commands(self):
        """Registers the help-related commands."""
        self.register_command(r"^\s*!help\s*$", self._cmd_help_public,
                              name="help", description="Show available commands.")
        self.register_command(r"^\s*!help\s+(\S+)\s*$", self._cmd_help_command_public,
                              name="help command", description="Show help for a specific command.")

    def _get_all_commands(self, is_admin: bool):
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
                            "description": cmd_info.get("description", "No description."),
                            "admin_only": cmd_info.get("admin_only", False)
                        }
        return all_commands

    def _get_command_list(self, is_admin: bool) -> str:
        """Builds a clean, comma-separated list of primary commands."""
        commands_dict = self._get_all_commands(is_admin)
        primary_commands = sorted(list({name.split(" ")[0] for name in commands_dict.keys()}))
        
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
        """Gets help for a specific command and its subcommands."""
        command = command.lower().strip("!")
        all_commands = self._get_all_commands(is_admin)
        
        matches = {
            name: info['description']
            for name, info in all_commands.items()
            if name == command or name.startswith(command + " ")
        }
        
        if not matches:
            return []
        return [f"!{name}: {desc}" for name, desc in sorted(matches.items())]
        
    def _construct_public_reply(self, base_message: str, channel: str) -> str:
        """Constructs the public reply, adding the reference URL if it's configured."""
        reference_url = self.get_config_value("reference_url", channel)
        if reference_url:
            return f"{base_message} For a comprehensive public reference, you may also consult the household records at: {reference_url}"
        return base_message

    def _cmd_help_public(self, connection, event, msg, username, match):
        """Handles !help in a channel by sending a PM."""
        self._handle_help_request(username, event.source)
        base_msg = f"{self.bot.title_for(username)}, I have sent you a list of my commands privately."
        reply = self._construct_public_reply(base_msg, event.target)
        self.safe_reply(connection, event, reply)
        return True

    def _cmd_help_command_public(self, connection, event, msg, username, match):
        """Handles !help <command> in a channel by sending a PM."""
        command = match.group(1)
        is_admin = self.bot.is_admin(event.source)
        
        help_lines = self._get_command_help(command, is_admin)
        if help_lines:
            self._handle_help_request(username, event.source, command)
            base_msg = f"{self.bot.title_for(username)}, I have sent you the details for that command privately."
            reply = self._construct_public_reply(base_msg, event.target)
            self.safe_reply(connection, event, reply)
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I am not familiar with that command.")
        return True

    def on_privmsg(self, connection, event):
        """Handles help requests sent via private message."""
        msg = event.arguments[0].strip() if event.arguments else ""
        username = event.source.nick
        
        help_command_match = re.match(r"^\s*help\s+(\S+)\s*$", msg, re.IGNORECASE)
        if help_command_match:
            command = help_command_match.group(1)
            self._handle_help_request(username, event.source, command)
            return True

        if re.match(r"^\s*help\s*$", msg, re.IGNORECASE):
            self._handle_help_request(username, event.source)
            return True
        return False

    def _handle_help_request(self, username: str, source: str, command: str = None):
        """Core logic to generate and send help text to a user via PM."""
        user_id = self.bot.get_user_id(username)
        is_admin = self.bot.is_admin(source)
        
        cooldown = self.get_config_value("cooldown_seconds", default=10.0)
        if not self.check_user_cooldown(username, "help_request", cooldown):
            return

        if command:
            help_lines = self._get_command_help(command, is_admin)
            if help_lines:
                for line in help_lines:
                    self.safe_privmsg(username, line)
            else:
                self.safe_privmsg(username, f"I am not familiar with the command '{command}'.")
        else:
            cmd_list = self._get_command_list(is_admin)
            self.safe_privmsg(username, f"Available commands: {cmd_list}")
            note = " (commands marked with * have admin-only subcommands)" if is_admin else ""
            self.safe_privmsg(username, f"Use 'help <command>' for more details.{note}")
        
        last_times = self.get_state("last_help_time", {})
        last_times[user_id] = time.time()
        self.set_state("last_help_time", last_times)
        self.save_state()

