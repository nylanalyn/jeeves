# modules/admin.py
# Enhanced admin conveniences using the ModuleBase framework
import re
import time
import threading
import functools
import sys
from typing import Optional, Tuple, Dict, Any
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Admin(bot, config)

class Admin(SimpleCommandModule):
    name = "admin"
    version = "2.4.0" # version bumped
    description = "Administrative bot controls."
    
    def __init__(self, bot, config):
        super().__init__(bot)
        # Initialize state
        self.set_state("commands_used", self.get_state("commands_used", 0))
        self.set_state("last_used", self.get_state("last_used", None))
        self.set_state("channels_joined", self.get_state("channels_joined", 0))
        self.set_state("emergency_uses", self.get_state("emergency_uses", 0))
        self.save_state()

        # Ensure bot has joined_channels tracking
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}

    def _register_commands(self):
        # Module Management
        self.register_command(r"^\s*!reload\s*$", self._cmd_reload,
                              name="reload", admin_only=True, description="Reload all modules from disk.")

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
        
        # Admin Stats
        self.register_command(r"^\s*!admin\s+stats\s*$", self._cmd_stats,
                              name="admin stats", admin_only=True, description="Show admin command usage stats.")

    def _dispatch_commands(self, connection, event, msg, username):
        # Override to update stats after a command is handled
        handled = super()._dispatch_commands(connection, event, msg, username)
        
        if handled:
            self.update_state({"commands_used": self.get_state("commands_used") + 1, "last_used": time.time()})
            self.save_state()
            
        return handled

    # --- Command Handlers ---
    @admin_required
    def _cmd_reload(self, connection, event, msg, username, match):
        loaded_modules = self.bot.pm.load_all()
        self.safe_reply(connection, event, f"Reloaded. Modules loaded: {', '.join(sorted(loaded_modules))}")
        return True

    @admin_required
    def _cmd_join(self, connection, event, msg, username, match):
        room_to_join = match.group(1)
        self.bot.connection.join(room_to_join)
        self.safe_reply(connection, event, f"Joined {room_to_join}.")
        self.set_state("channels_joined", self.get_state("channels_joined", 0) + 1)
        self.save_state()
        return True

    @admin_required
    def _cmd_part(self, connection, event, msg, username, match):
        room_to_part, part_msg = match.groups()
        if room_to_part in self.bot.joined_channels:
            self.bot.connection.part(room_to_part, part_msg or "Leaving per request.")
            self.safe_reply(connection, event, f"Left {room_to_part}.")
            self.set_state("channels_joined", self.get_state("channels_joined", 0) - 1)
            self.save_state()
        else:
            self.safe_reply(connection, event, f"I am not in {room_to_part}.")
        return True
    
    @admin_required
    def _cmd_channels(self, connection, event, msg, username, match):
        channels_list = ", ".join(sorted(list(self.bot.joined_channels)))
        self.safe_reply(connection, event, f"I am currently in these channels: {channels_list}")
        return True

    @admin_required
    def _cmd_say(self, connection, event, msg, username, match):
        target_room, message = match.groups()
        target = target_room or event.target
        self.bot.connection.privmsg(target, message)
        return True

    @admin_required
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        quit_msg = match.group(1)
        self.bot.connection.quit(quit_msg or "Emergency quit.")
        return True
    
    @admin_required
    def _cmd_nick(self, connection, event, msg, username, match):
        new_nick = match.group(1)
        self.bot.connection.nick(new_nick)
        self.safe_reply(connection, event, f"Nickname changed to {new_nick}.")
        return True
    
    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        lines = [
            f"Admin stats: commands_used={stats.get('commands_used', 0)}, "
            f"last_used={time.strftime('%Y-%m-%d %H:%M:%S', time.gmtime(stats.get('last_used', 0))) if stats.get('last_used') else 'never'}",
            f"channels_joined={stats.get('channels_joined', 0)}, emergency_uses={stats.get('emergency_uses', 0)}"
        ]
        self.safe_reply(connection, event, "; ".join(lines))
        return True

