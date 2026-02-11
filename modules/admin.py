# modules/admin.py
from typing import Any
# Administrative bot controls with dynamic configuration management.
import re
import time
import sys
import yaml
from pathlib import Path
from .base import SimpleCommandModule, admin_required

def setup(bot: Any) -> "Admin":
    return Admin(bot)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "4.0.0" # Removed runtime config editing (config.yaml is source of truth)
    description = "Administrative bot controls."

    def __init__(self, bot):
        super().__init__(bot)
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}

    def _register_commands(self):
        self.register_command(r"^\s*!admin(?:\s+(.*))?$", self._cmd_admin_master,
                              name="admin", admin_only=True, description="Main admin command. Use '!admin help' for subcommands.")
        self.register_command(r"^\s*!reload\s*$", lambda c, e, m, u, ma: self._cmd_reload(c, e, u),
                              name="reload", admin_only=True, description="Alias for '!admin reload'.")
        self.register_command(r"^\s*!say(?:\s+(#\S+))?\s+(.+)$", self._cmd_say_alias,
                              name="say", admin_only=True, description="Alias for '!admin say'.")
        self.register_command(r"^\s*!emergency\s+quit(?:\s+(.+))?\s*$", self._cmd_emergency_quit,
                              name="emergency quit", admin_only=True, description="Emergency shutdown.")
        self.register_command(r"^\s*!pass\s+(.+)$", self._cmd_authenticate,
                              name="pass", admin_only=True, description="Authenticate as super admin (IM only).")
        self.register_command(r"^\s*!kill\s*$", self._cmd_kill,
                              name="kill", admin_only=True, description="Shutdown bot without restart.")

    # --- Private Message Handler ---

    def on_privmsg(self, connection, event):
        """Handle private messages by dispatching to command system."""
        msg = event.arguments[0]
        username = event.source.nick
        # Dispatch to the command system just like public messages
        return self._dispatch_commands(connection, event, msg, username)

    # --- Master Command Handler ---

    def _cmd_admin_master(self, connection, event, msg, username, match):
        args_str = (match.group(1) or "").strip()

        if not args_str:
            self.safe_reply(connection, event, "Please specify an admin command. Use '!admin help' for a list.")
            return True

        args = args_str.split()
        subcommand = args[0].lower()

        if subcommand == "reload":
            return self._cmd_reload(connection, event, username)
        elif subcommand == "load" and len(args) > 1:
            return self._cmd_load(connection, event, username, args[1])
        elif subcommand == "unload" and len(args) > 1:
            return self._cmd_unload(connection, event, username, args[1])
        elif subcommand == "config" and len(args) > 1 and args[1].lower() == "reload":
            return self._cmd_config_reload(connection, event, username)
        elif subcommand == "modules":
             return self._cmd_list_modules(connection, event, username)
        elif subcommand == "join" and len(args) > 1:
            return self._cmd_join(connection, event, username, args[1])
        elif subcommand == "part" and len(args) > 1:
            return self._cmd_part(connection, event, username, args[1], " ".join(args[2:]))
        elif subcommand == "say" and len(args) > 1:
            target = args[1] if args[1].startswith('#') else event.target
            message = " ".join(args[2:]) if args[1].startswith('#') else " ".join(args[1:])
            return self._cmd_say(connection, event, username, target, message)
        elif subcommand == "debug":
            if len(args) == 2:
                return self._cmd_debug_toggle(connection, event, username, args[1])
            elif len(args) == 3:
                return self._cmd_module_debug_toggle(connection, event, username, args[1], args[2])
            else:
                return self._usage(connection, event, "debug <on|off> [module_name]")
        elif subcommand == "help":
            return self._cmd_help(connection, event, username)
        else:
            self.safe_reply(connection, event, f"Unknown admin command. Use '!admin help'.")
            return True

    def _usage(self, connection, event, command_args):
        self.safe_reply(connection, event, f"Usage: !admin {command_args}")
        return True

    # --- Helper Methods ---

    def _require_super_admin(self, connection, event, username):
        """
        Check if user is authenticated as super admin. If not, send helpful message.

        Returns:
            True if user is super admin, False otherwise
        """
        nick = event.source.split('!')[0]
        if not self.bot.is_super_admin(nick, event_source=str(event.source)):
            # Check if password auth is enabled
            password_hash = self.bot.config.get("core", {}).get("super_admin_password_hash", "")
            if password_hash and password_hash.strip():
                self.safe_privmsg(username, "This command requires super admin authentication. Please authenticate with: /msg me !pass <password>")
            else:
                self.safe_reply(connection, event, "Super admin authentication is not configured.")
            return False
        return True

    # --- Subcommand Logic ---

    def _cmd_authenticate(self, connection, event, msg, username, match):
        """Handle !pass <password> command for super admin authentication."""
        # Only allow in private message
        if not event.target.startswith(self.bot.connection.get_nickname()):
            # Quietly ignore in public channels for security
            return True

        password = match.group(1).strip()

        # Rate limiting: track failed attempts by hostname (nicks can be changed freely)
        nick = event.source.split('!')[0]
        try:
            host = event.source.split('@')[1]
        except IndexError:
            host = nick.lower()
        rate_key = host.lower()

        if not hasattr(self, '_auth_attempts'):
            self._auth_attempts = {}

        # Clean up old attempts (older than 5 minutes)
        current_time = time.time()
        self._auth_attempts = {k: v for k, v in self._auth_attempts.items() if current_time - v["last_attempt"] < 300}

        # Check rate limit (max 5 attempts per 5 minutes)
        if rate_key in self._auth_attempts:
            attempts = self._auth_attempts[rate_key]
            if attempts["count"] >= 5:
                self.safe_privmsg(username, "Too many authentication attempts. Please wait 5 minutes before trying again.")
                return True

        # Attempt authentication
        if self.bot.authenticate_super_admin(nick, password):
            # Success - clear failed attempts
            if rate_key in self._auth_attempts:
                del self._auth_attempts[rate_key]

            session_hours = self.bot.config.get("core", {}).get("super_admin_session_hours", 1)
            self.safe_privmsg(username, f"Authentication successful. Super admin privileges granted for {session_hours} hour(s).")
        else:
            # Failed - record attempt
            if rate_key not in self._auth_attempts:
                self._auth_attempts[rate_key] = {"count": 0, "last_attempt": 0}

            self._auth_attempts[rate_key]["count"] += 1
            self._auth_attempts[rate_key]["last_attempt"] = current_time

            remaining = 5 - self._auth_attempts[rate_key]["count"]
            if remaining > 0:
                self.safe_privmsg(username, f"Authentication failed. {remaining} attempt(s) remaining before rate limit.")
            else:
                self.safe_privmsg(username, "Authentication failed. Rate limit exceeded. Please wait 5 minutes.")

        return True

    def _cmd_reload(self, connection, event, username):
        if not self._require_super_admin(connection, event, username):
            return True
        loaded = self.bot.core_reload_plugins()
        self.safe_reply(connection, event, f"Modules reloaded: {', '.join(sorted(loaded))}")
        return True

    def _cmd_load(self, connection, event, username, module_name):
        if not self._require_super_admin(connection, event, username):
            return True
        if self.bot.pm.load_module(module_name):
            self.safe_reply(connection, event, f"Module '{module_name}' loaded successfully.")
        else:
            self.safe_reply(connection, event, f"Failed to load module '{module_name}'. Please check the debug.log file for specific errors (e.g., a missing API key or an uninstalled library).")
        return True

    def _cmd_unload(self, connection, event, username, module_name):
        if not self._require_super_admin(connection, event, username):
            return True
        if self.bot.pm.unload_module(module_name):
            self.safe_reply(connection, event, f"Module '{module_name}' unloaded successfully.")
        else:
            self.safe_reply(connection, event, f"Failed to unload module '{module_name}'. It may not be loaded.")
        return True

    def _cmd_config_reload(self, connection, event, username):
        if not self._require_super_admin(connection, event, username):
            return True
        if self.bot.core_reload_config():
            self.safe_reply(connection, event, "Configuration reloaded from config.yaml. Modules NOT reloaded (use !admin reload for that).")
        else:
            self.safe_reply(connection, event, "Error reloading configuration.")
        return True

    def _cmd_list_modules(self, connection, event, username):
        loaded_modules = sorted(list(self.bot.pm.plugins.keys()))
        self.safe_reply(connection, event, f"Loaded modules ({len(loaded_modules)}): {', '.join(loaded_modules)}")
        return True

    def _cmd_join(self, connection, event, username, room):
        self.bot.connection.join(room)
        self.safe_reply(connection, event, f"Joined {room}.")
        return True

    def _cmd_part(self, connection, event, username, room, msg):
        if room in self.bot.joined_channels:
            self.bot.connection.part(room, msg or "Leaving per request.")
            self.safe_reply(connection, event, f"Left {room}.")
        else:
            self.safe_reply(connection, event, f"I am not in {room}.")
        return True

    def _cmd_say(self, connection, event, username, target, message):
        # Sanitize newlines to prevent IRC protocol injection
        message = message.replace('\r', '').replace('\n', ' ')
        self.bot.connection.privmsg(target, message)
        return True
        
    def _cmd_say_alias(self, connection, event, msg, username, match):
        target, message = match.groups()
        return self._cmd_say(connection, event, username, target or event.target, message)

    def _cmd_debug_toggle(self, connection, event, username, state: str):
        state_bool = state.lower() in ['on', 'true', '1', 'enable']
        self.bot.set_debug_mode(state_bool)
        self.safe_reply(connection, event, f"Debug mode is now {'ON' if state_bool else 'OFF'}.")
        return True

    def _cmd_module_debug_toggle(self, connection, event, username, module_name: str, state: str):
        state_bool = state.lower() in ['on', 'true', '1', 'enable']

        if module_name not in self.bot.pm.plugins:
            self.safe_reply(connection, event, f"Module '{module_name}' is not loaded.")
            return True

        self.bot.set_module_debug(module_name, state_bool)
        self.safe_reply(connection, event, f"Debug mode for '{module_name}' is now {'ON' if state_bool else 'OFF'}.")
        return True
        
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        if not self._require_super_admin(connection, event, username):
            return True
        self.bot.connection.quit(match.group(1) or "Emergency quit.")
        return True

    def _cmd_kill(self, connection, event, msg, username, match):
        self.bot.connection.quit("Killed by admin.")
        sys.exit(42)

    def _cmd_help(self, connection, event, username):
        # Check if super admin auth is enabled
        password_hash = self.bot.config.get("core", {}).get("super_admin_password_hash", "")
        super_admin_enabled = bool(password_hash and password_hash.strip())

        help_lines = [
            "=== Admin Commands ==="
        ]

        if super_admin_enabled:
            help_lines.extend([
                "",
                "SUPER ADMIN COMMANDS (require password authentication):",
                "!pass <password> - Authenticate as super admin (use in /msg only)",
                "!admin reload - Reload all modules from disk.",
                "!admin load <module> - Load a specific module by name.",
                "!admin unload <module> - Unload a specific module by name.",
                "!admin config reload - Reload config.yaml (without reloading modules).",
                "!emergency quit [message] - Emergency shutdown.",
                "",
                "REGULAR ADMIN COMMANDS (hostname verification only):",
            ])
        else:
            help_lines.append("")

        help_lines.extend([
            "!admin modules - List all currently loaded modules.",
            "!admin join <#channel> - Join a channel.",
            "!admin part <#channel> [message] - Leave a channel.",
            "!say [#channel] <message> - Make the bot speak.",
            "!admin debug <on|off> - Toggle verbose file logging.",
            "!admin debug <module_name> <on|off> - Toggle debug for specific module.",
            "!kill - Shutdown bot without auto-restart.",
            "",
            "NOTE: Configuration is now read from config.yaml only.",
            "To change settings, edit config.yaml and use !admin config reload."
        ])

        self.safe_reply(connection, event, "I have sent you the admin command list privately.")
        for line in help_lines:
            self.safe_privmsg(username, line)
        return True

