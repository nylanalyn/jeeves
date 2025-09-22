# modules/admin.py
# Enhanced admin conveniences with state management.
import re
import time
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Admin(bot, config)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "2.5.0"
    description = "Administrative bot controls."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}
        
        # Initialize state for command usage tracking
        self.set_state("commands_used", self.get_state("commands_used", {}))
        self.save_state()

    def _register_commands(self):
        # Module and Config Management
        self.register_command(r"^\s*!reload\s*$", self._cmd_reload,
                              name="reload", admin_only=True, description="Reload all modules from disk.")
        self.register_command(r"^\s*!config\s+reload\s*$", self._cmd_config_reload,
                              name="config reload", admin_only=True, description="Reload the bot's config.yaml file.")

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
        
        # Stats
        self.register_command(r"^\s*!admin\s+stats\s*$", self._cmd_stats,
                              name="admin stats", admin_only=True, description="Show usage statistics for admin commands.")

    def _update_stats(self, command_name: str):
        """Increments the usage count for a given command."""
        stats = self.get_state("commands_used", {})
        stats[command_name] = stats.get(command_name, 0) + 1
        self.set_state("commands_used", stats)
        self.save_state()

    # --- Command Handlers ---
    def _cmd_reload(self, connection, event, msg, username, match):
        loaded_modules = self.bot.pm.load_all()
        self.safe_reply(connection, event, f"Reloaded. Modules loaded: {', '.join(sorted(loaded_modules))}")
        return True

    def _cmd_config_reload(self, connection, event, msg, username, match):
        if self.bot.reload_config_and_notify_modules():
            self.safe_reply(connection, event, "Configuration file reloaded.")
        else:
            self.safe_reply(connection, event, "There was an error reloading the configuration.")
        return True

    def _cmd_join(self, connection, event, msg, username, match):
        room_to_join = match.group(1)
        self.bot.connection.join(room_to_join)
        self.safe_reply(connection, event, f"Joined {room_to_join}.")
        return True

    def _cmd_part(self, connection, event, msg, username, match):
        room_to_part, part_msg = match.groups()
        if room_to_part in self.bot.joined_channels:
            self.bot.connection.part(room_to_part, part_msg or "Leaving per request.")
            self.safe_reply(connection, event, f"Left {room_to_part}.")
        else:
            self.safe_reply(connection, event, f"I am not in {room_to_part}.")
        return True
    
    def _cmd_channels(self, connection, event, msg, username, match):
        channels_list = ", ".join(sorted(list(self.bot.joined_channels)))
        self.safe_reply(connection, event, f"I am currently in these channels: {channels_list}")
        return True

    def _cmd_say(self, connection, event, msg, username, match):
        target_room, message = match.groups()
        target = target_room or event.target
        self.bot.connection.privmsg(target, message)
        return True

    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        quit_msg = match.group(1)
        self.bot.connection.quit(quit_msg or "Emergency quit.")
        return True
    
    def _cmd_nick(self, connection, event, msg, username, match):
        new_nick = match.group(1)
        self.bot.connection.nick(new_nick)
        self.safe_reply(connection, event, f"Nickname changed to {new_nick}.")
        return True
        
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state("commands_used", {})
        if not stats:
            self.safe_reply(connection, event, "No admin commands have been used yet.")
            return True
        
        # Format the stats for display
        stats_str = ", ".join([f"{cmd}: {count}" for cmd, count in sorted(stats.items())])
        self.safe_reply(connection, event, f"Admin command usage: {stats_str}")
        return True

