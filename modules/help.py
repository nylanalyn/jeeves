# modules/help.py
# Compact help system with individual command lookups and private message support.

import re
import time
from typing import Any, Dict, List, Optional
from .base import SimpleCommandModule

def setup(bot: Any) -> 'Help':
    """Initializes the Help module."""
    return Help(bot)

class Help(SimpleCommandModule):
    """Provides a list of commands and help for specific commands."""
    name = "help"
    version = "4.1.1" # Corrected __init__ call
    description = "Provides a list of commands and help for specific commands."
    
    def __init__(self, bot: Any) -> None:
        """Initializes the module's state and registers commands."""
        super().__init__(bot)
        self.set_state("last_help_time", self.get_state("last_help_time", {}))
        self.save_state()

    def _register_commands(self) -> None:
        """Registers the help-related commands."""
        self.register_command(r"^\s*!help\s*$", self._cmd_help_public,
                              name="help", description="Show available commands.")
        self.register_command(r"^\s*!help\s+(\S+)\s*$", self._cmd_help_command_public,
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

    def _get_command_help(self, command: str, is_admin: bool) -> List[str]:
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
            return f"{base_message} If you need more ink on the case, thumb through the public files: {reference_url}"
        return base_message

    def _cmd_help_public(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Handles !help in a channel by sending a PM."""
        self._handle_help_request(username, event.source)
        base_msg = f"Check your private wire, {self.bot.title_for(username)}—the command roster's waiting there."
        reply = self._construct_public_reply(base_msg, event.target)
        self.safe_reply(connection, event, reply)
        return True

    def _cmd_help_command_public(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Handles !help <command> in a channel by sending a PM."""
        command = match.group(1)
        is_admin = self.bot.is_admin(event.source)

        help_lines = self._get_command_help(command, is_admin)
        if help_lines:
            self._handle_help_request(username, event.source, command)
            base_msg = f"Details on `{command}` are on your private line, {self.bot.title_for(username)}."
            reply = self._construct_public_reply(base_msg, event.target)
            self.safe_reply(connection, event, reply)
        else:
            self.safe_reply(connection, event, f"Can't find that command in my files, {self.bot.title_for(username)}.")
        return True

    def on_privmsg(self, connection: Any, event: Any) -> bool:
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

    def _handle_help_request(self, username: str, source: str, command: Optional[str] = None) -> None:
        """Core logic to generate and send help text to a user via PM."""
        user_id = self.bot.get_user_id(username)
        is_admin = self.bot.is_admin(source)

        cooldown = self.get_config_value("cooldown_seconds", default=10.0)
        if not self.check_user_cooldown(username, "help_request", cooldown):
            self.log_debug(f"Help request from {username} blocked by cooldown")
            return

        if command:
            help_lines = self._get_command_help(command, is_admin)
            if help_lines:
                for line in help_lines:
                    self.safe_privmsg(username, line)
            else:
                self.safe_privmsg(username, f"No entry for '{command}' in the casebook.")
        else:
            all_commands = self._get_all_commands(is_admin)
            self.log_debug(f"Help request: found {len(all_commands)} commands for user {username} (admin={is_admin})")
            cmd_list = self._get_command_list(is_admin)
            self.log_debug(f"Help request: command list length = {len(cmd_list)} bytes")
            
            # Split command list into chunks that fit IRC's 512-byte limit
            # Account for the prefix text and some safety margin
            prefix = "Available leads: "
            max_length = 400  # Conservative limit to account for IRC overhead
            
            if len(prefix + cmd_list) <= max_length:
                self.safe_privmsg(username, f"{prefix}{cmd_list}")
            else:
                # Split into multiple messages
                commands = cmd_list.split(", ")
                chunks = []
                current_chunk = []
                current_length = len(prefix)
                
                for cmd in commands:
                    cmd_length = len(cmd) + 2  # +2 for ", "
                    if current_length + cmd_length > max_length and current_chunk:
                        chunks.append(", ".join(current_chunk))
                        current_chunk = [cmd]
                        current_length = len(prefix) + len(cmd)
                    else:
                        current_chunk.append(cmd)
                        current_length += cmd_length
                
                if current_chunk:
                    chunks.append(", ".join(current_chunk))
                
                # Send the chunks
                for i, chunk in enumerate(chunks):
                    if i == 0:
                        self.safe_privmsg(username, f"{prefix}{chunk}")
                    else:
                        self.safe_privmsg(username, chunk)
            
            note = " (commands marked with * have admin-only subcommands)" if is_admin else ""
            self.safe_privmsg(username, f"Ask 'help <command>' for the deep dive.{note}")

        # Record cooldown after successfully sending help
        self.record_user_cooldown(username, "help_request")

        last_times = self.get_state("last_help_time", {})
        last_times[user_id] = time.time()
        self.set_state("last_help_time", last_times)
        self.save_state()
