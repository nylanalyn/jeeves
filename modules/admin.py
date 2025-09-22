# modules/admin.py
# Enhanced admin conveniences with state management and data migration.
import re
import time
import sys
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Admin(bot, config)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "2.5.0"
    description = "Administrative bot controls."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        self._migrate_state() # Ensure state is in the new format
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}

    def _migrate_state(self):
        """
        Checks for old, top-level state data and migrates it into a nested 'stats' dictionary.
        This is a one-time operation per old state file.
        """
        current_state = self.get_state()
        # Check for a key that only exists in the old format
        if "commands_used" in current_state:
            print(f"[{self.name}] Detected old state format. Migrating...", file=sys.stderr)
            new_stats = {
                "commands_used": current_state.get("commands_used", 0),
                "last_used": current_state.get("last_used", None),
                "channels_joined": current_state.get("channels_joined", 0),
                "emergency_uses": current_state.get("emergency_uses", 0),
            }
            # Create the new nested structure
            self.set_state("stats", new_stats)
            
            # Clean up old top-level keys
            for key in ["commands_used", "last_used", "channels_joined", "emergency_uses", "last_command"]:
                current_state.pop(key, None)
            
            # Update the cache with the cleaned state before saving
            self._state_cache = current_state
            self._state_cache["stats"] = new_stats
            self.save_state(force=True)
            print(f"[{self.name}] Migration complete.", file=sys.stderr)


    def _register_commands(self):
        # Module and Config Management
        self.register_command(r"^\s*!reload\s*$", self._cmd_reload,
                              name="reload", admin_only=True, description="Reload all modules from disk.")
        self.register_command(r"^\s*!config\s+reload\s*$", self._cmd_config_reload,
                              name="config reload", admin_only=True, description="Reload the bot's config.yaml file.")
        self.register_command(r"^\s*!admin\s+stats\s*$", self._cmd_stats,
                              name="admin stats", admin_only=True, description="Show admin command usage stats.")

        # Channel Management
        self.register_command(r"^\s*!join\s+(#\S+)\s*$", self._cmd_join,
                              name="join", admin_only=True, description="Join a channel. Usage: !join #channel")
        self.register_command(r"^\s*!part\s+(#\S+)(?:\s+(.+))?\s*$", self._cmd_part,
                              name="part", admin_only=True, description="Leave a channel. Usage: !part #channel [message]")
        self.register_command(r"^\s*!channels\s*$", self._cmd_channels,
                              name="channels", admin_only=True, description="List all channels I'm in.")
        self.register_command(r"^\s*!say(?:\s+(#\S+))?\s+(.+)$", self._cmd_say,
                              name="say", admin_only=True, description="Make the bot say something. Usage: !say [#channel] <message>")
        
        # Emergency Controls
        self.register_command(r"^\s*!emergency\s+quit(?:\s+(.+))?\s*$", self._cmd_emergency_quit,
                              name="emergency quit", admin_only=True, description="Emergency shutdown. Usage: !emergency quit [message]")
        self.register_command(r"^\s*!nick\s+(\S+)\s*$", self._cmd_nick,
                              name="nick", admin_only=True, description="Change bot nickname. Usage: !nick <newnick>")

    def _update_stats(self, command_name):
        """Updates and saves the admin command usage statistics."""
        stats = self.get_state("stats", {"commands_used": 0, "last_used": None})
        stats["commands_used"] = stats.get("commands_used", 0) + 1
        stats["last_used"] = time.time()
        self.set_state("stats", stats)
        self.save_state()

    # --- Command Handlers ---
    @admin_required
    def _cmd_reload(self, connection, event, msg, username, match):
        self._update_stats("reload")
        loaded_modules = self.bot.pm.load_all()
        self.safe_reply(connection, event, f"Reloaded. Modules loaded: {', '.join(sorted(loaded_modules))}")
        return True

    @admin_required
    def _cmd_config_reload(self, connection, event, msg, username, match):
        self._update_stats("config reload")
        if self.bot.reload_config_and_notify_modules():
            self.safe_reply(connection, event, "Configuration file reloaded.")
        else:
            self.safe_reply(connection, event, "There was an error reloading the configuration.")
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state("stats", {})
        last_used_time = stats.get("last_used")
        last_used_str = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(last_used_time)) if last_used_time else "never"
        
        response = (f"Admin stats: {stats.get('commands_used', 0)} commands used. "
                    f"Last used: {last_used_str}.")
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_join(self, connection, event, msg, username, match):
        self._update_stats("join")
        room_to_join = match.group(1)
        self.bot.connection.join(room_to_join)
        self.safe_reply(connection, event, f"Joined {room_to_join}.")
        return True

    @admin_required
    def _cmd_part(self, connection, event, msg, username, match):
        self._update_stats("part")
        room_to_part, part_msg = match.groups()
        if room_to_part in self.bot.joined_channels:
            self.bot.connection.part(room_to_part, part_msg or "Leaving per request.")
            self.safe_reply(connection, event, f"Left {room_to_part}.")
        else:
            self.safe_reply(connection, event, f"I am not in {room_to_part}.")
        return True
    
    @admin_required
    def _cmd_channels(self, connection, event, msg, username, match):
        self._update_stats("channels")
        channels_list = ", ".join(sorted(list(self.bot.joined_channels)))
        self.safe_reply(connection, event, f"I am currently in these channels: {channels_list}")
        return True

    @admin_required
    def _cmd_say(self, connection, event, msg, username, match):
        self._update_stats("say")
        target_room, message = match.groups()
        target = target_room or event.target
        self.bot.connection.privmsg(target, message)
        return True

    @admin_required
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        self._update_stats("emergency quit")
        quit_msg = match.group(1)
        self.bot.connection.quit(quit_msg or "Emergency quit.")
        return True
    
    @admin_required
    def _cmd_nick(self, connection, event, msg, username, match):
        self._update_stats("nick")
        new_nick = match.group(1)
        self.bot.connection.nick(new_nick)
        self.safe_reply(connection, event, f"Nickname changed to {new_nick}.")
        return True

