# modules/admin.py
# Enhanced admin conveniences with a robust, single-handler command structure.
import re
import time
import sys
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Admin(bot, config)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "2.6.0" # Refactored to a single robust command handler
    description = "Administrative bot controls."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}

    def _register_commands(self):
        # Master command for all admin functions
        self.register_command(r"^\s*!admin(?:\s+(.*))?$", self._cmd_admin_master,
                              name="admin", admin_only=True, description="Main admin command. Use '!admin help' for subcommands.")
        # Alias for convenience
        self.register_command(r"^\s*!reload\s*$", self._cmd_reload_alias,
                              name="reload", admin_only=True, description="Alias for '!admin reload'.")
        
        # Emergency command remains top-level for critical access
        self.register_command(r"^\s*!emergency\s+quit(?:\s+(.+))?\s*$", self._cmd_emergency_quit,
                              name="emergency quit", admin_only=True, description="Emergency shutdown.")

    def _update_stats(self, command_name):
        """Updates and saves the admin command usage statistics."""
        stats = self.get_state("stats", {"commands_used": 0, "last_used": None})
        stats["commands_used"] = stats.get("commands_used", 0) + 1
        stats["last_used"] = time.time()
        self.set_state("stats", stats)
        self.save_state()

    # --- Master Command Handler ---

    def _cmd_admin_master(self, connection, event, msg, username, match):
        """The single entry point for all '!admin' commands."""
        args_str = (match.group(1) or "").strip()
        
        if not args_str:
            self.safe_reply(connection, event, "Please specify an admin command. Use '!admin help' for a list.")
            return True

        args = args_str.split()
        subcommand = args[0].lower()
        
        # Route to the appropriate handler
        if subcommand == "reload":
            return self._cmd_reload(connection, event, username)
        elif subcommand == "config" and len(args) > 1 and args[1].lower() == "reload":
            return self._cmd_config_reload(connection, event, username)
        elif subcommand == "stats":
            return self._cmd_stats(connection, event, username)
        elif subcommand == "join" and len(args) > 1:
            return self._cmd_join(connection, event, username, args[1])
        elif subcommand == "part" and len(args) > 1:
            part_msg = " ".join(args[2:]) if len(args) > 2 else ""
            return self._cmd_part(connection, event, username, args[1], part_msg)
        elif subcommand == "channels":
            return self._cmd_channels(connection, event, username)
        elif subcommand == "say" and len(args) > 1:
            target = args[1] if args[1].startswith('#') else event.target
            message = " ".join(args[2:]) if args[1].startswith('#') else " ".join(args[1:])
            return self._cmd_say(connection, event, username, target, message)
        elif subcommand == "nick" and len(args) > 1:
            return self._cmd_nick(connection, event, username, args[1])
        elif subcommand == "help":
            return self._cmd_help(connection, event, username)
        else:
            self.safe_reply(connection, event, f"Unknown admin command or incorrect usage. Use '!admin help'.")
            return True

    def _cmd_reload_alias(self, connection, event, msg, username, match):
        """Alias for !admin reload."""
        return self._cmd_reload(connection, event, username)

    # --- Subcommand Logic ---
    
    @admin_required
    def _cmd_reload(self, connection, event, username):
        self._update_stats("reload")
        loaded_modules = self.bot.pm.load_all()
        self.safe_reply(connection, event, f"Reloaded. Modules loaded: {', '.join(sorted(loaded_modules))}")
        return True

    @admin_required
    def _cmd_config_reload(self, connection, event, username):
        self._update_stats("config reload")
        if self.bot.reload_config_and_notify_modules():
            self.safe_reply(connection, event, "Configuration file reloaded.")
        else:
            self.safe_reply(connection, event, "There was an error reloading the configuration.")
        return True

    @admin_required
    def _cmd_stats(self, connection, event, username):
        stats = self.get_state("stats", {})
        last_used_time = stats.get("last_used")
        last_used_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(last_used_time)) if last_used_time else "never"
        response = (f"Admin stats: {stats.get('commands_used', 0)} commands used. "
                    f"Last used: {last_used_str}.")
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_join(self, connection, event, username, room_to_join):
        self._update_stats("join")
        self.bot.connection.join(room_to_join)
        self.safe_reply(connection, event, f"Joined {room_to_join}.")
        return True

    @admin_required
    def _cmd_part(self, connection, event, username, room_to_part, part_msg):
        self._update_stats("part")
        if room_to_part in self.bot.joined_channels:
            self.bot.connection.part(room_to_part, part_msg or "Leaving per request.")
            self.safe_reply(connection, event, f"Left {room_to_part}.")
        else:
            self.safe_reply(connection, event, f"I am not in {room_to_part}.")
        return True
    
    @admin_required
    def _cmd_channels(self, connection, event, username):
        self._update_stats("channels")
        channels_list = ", ".join(sorted(list(self.bot.joined_channels)))
        self.safe_reply(connection, event, f"I am currently in these channels: {channels_list}")
        return True

    @admin_required
    def _cmd_say(self, connection, event, username, target, message):
        self._update_stats("say")
        self.bot.connection.privmsg(target, message)
        return True

    @admin_required
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        self._update_stats("emergency quit")
        quit_msg = match.group(1)
        self.bot.connection.quit(quit_msg or "Emergency quit.")
        return True
    
    @admin_required
    def _cmd_nick(self, connection, event, username, new_nick):
        self._update_stats("nick")
        self.bot.connection.nick(new_nick)
        self.safe_reply(connection, event, f"Nickname changed to {new_nick}.")
        return True

    @admin_required
    def _cmd_help(self, connection, event, username):
        """Displays admin-specific help."""
        help_lines = [
            "!admin reload - Reload all modules from disk (!reload also works).",
            "!admin config reload - Reload the bot's config.yaml file.",
            "!admin stats - Show admin command usage stats.",
            "!admin join <#channel> - Join a channel.",
            "!admin part <#channel> [message] - Leave a channel.",
            "!admin channels - List all channels I'm in.",
            "!admin say [#channel] <message> - Make the bot say something.",
            "!admin nick <newnick> - Change bot nickname.",
            "!emergency quit [message] - Emergency shutdown."
        ]
        
        self.safe_reply(connection, event, f"--- {self.name.capitalize()} Commands ---")
        for line in help_lines:
            self.safe_privmsg(username, line)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you the details privately.")
        return True

