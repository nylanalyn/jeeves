# modules/admin.py
# Enhanced admin conveniences using the ModuleBase framework
import re
import time
import threading
import functools
import sys
from typing import Optional, Tuple, Dict, Any
from .base import SimpleCommandModule

def setup(bot): 
    return Admin(bot)

def admin_required(func):
    @functools.wraps(func)
    def wrapper(self, connection, event, msg, username, *args, **kwargs):
        if not self.bot.is_admin(username):
            return False
        return func(self, connection, event, msg, username, *args, **kwargs)
    return wrapper

class Admin(SimpleCommandModule):
    name = "admin"
    version = "2.2.0"
    description = "Administrative bot controls."
    
    def __init__(self, bot):
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
        # Channel Management
        self.register_command(r"^\s*!join\s+(#\S+)\s*$", self._cmd_join,
                              admin_only=True, description="Join a channel. Usage: !join #channel")
        self.register_command(r"^\s*!part\s+(#\S+)(?:\s+(.+))?\s*$", self._cmd_part,
                              admin_only=True, description="Leave a channel. Usage: !part #channel [message]")
        self.register_command(r"^\s*!channels\s*$", self._cmd_channels,
                              admin_only=True, description="List all channels I'm in.")
        self.register_command(r"^\s*!say(?:\s+(#\S+))?\s+(.+)$", self._cmd_say,
                              admin_only=True, description="Make the bot say something. Usage: !say [#channel] <message>")

        # Adventure Controls (requires adventure.py)
        self.register_command(r"^\s*!adventure\s+cancel\s*$", self._cmd_adv_cancel,
                              admin_only=True, description="Cancel the current adventure.")
        self.register_command(r"^\s*!adventure\s+shorten\s+(\d+)\s*$", self._cmd_adv_shorten,
                              admin_only=True, description="Shorten adventure timer by N seconds.")
        self.register_command(r"^\s*!adventure\s+extend\s+(\d+)\s*$", self._cmd_adv_extend,
                              admin_only=True, description="Extend adventure timer by N seconds.")
        self.register_command(r"^\s*!adventure\s+status\s*$", self._cmd_adv_status,
                              admin_only=True, description="Show current adventure status.")
        
        # Emergency Controls
        self.register_command(r"^\s*!emergency\s+quit(?:\s+(.+))?\s*$", self._cmd_emergency_quit,
                              admin_only=True, description="Emergency shutdown. Usage: !emergency quit [message]")
        self.register_command(r"^\s*!nick\s+(\S+)\s*$", self._cmd_nick,
                              admin_only=True, description="Change bot nickname. Usage: !nick <newnick>")
        
        # Admin Stats
        self.register_command(r"^\s*!admin\s+stats\s*$", self._cmd_stats,
                              admin_only=True, description="Show admin command usage stats.")

    def on_pubmsg(self, connection, event, msg, username):
        # Let the base class handle all registered commands
        handled = super().on_pubmsg(connection, event, msg, username)
        
        if handled:
            # Update admin module-specific stats
            self.update_state({"commands_used": self.get_state("commands_used") + 1, "last_used": time.time()})
            self.save_state()
            
        return handled

    # --- Command Handlers ---
    @admin_required
    def _cmd_join(self, connection, event, msg, username, match):
        room_to_join = match.group(1)
        print(f"[admin] DEBUG: Handling !join command for room: {room_to_join}", file=sys.stderr)
        try:
            self.bot.connection.join(room_to_join)
            self.safe_reply(connection, event, f"Joined {room_to_join}.")
            self.set_state("channels_joined", self.get_state("channels_joined", 0) + 1)
            self.save_state()
            print(f"[admin] DEBUG: Successfully joined {room_to_join}", file=sys.stderr)
        except Exception as e:
            self.safe_reply(connection, event, f"Error joining {room_to_join}: {e}")
            self._record_error(f"Error joining channel: {e}")
            print(f"[admin] DEBUG: Failed to join {room_to_join} with error: {e}", file=sys.stderr)
        return True

    @admin_required
    def _cmd_part(self, connection, event, msg, username, match):
        room_to_part, part_msg = match.groups()
        print(f"[admin] DEBUG: Handling !part command for room: {room_to_part}", file=sys.stderr)
        if room_to_part in self.bot.joined_channels:
            try:
                self.bot.connection.part(room_to_part, part_msg or "Leaving per request.")
                self.safe_reply(connection, event, f"Left {room_to_part}.")
                self.set_state("channels_joined", self.get_state("channels_joined", 0) - 1)
                self.save_state()
                print(f"[admin] DEBUG: Successfully parted {room_to_part}", file=sys.stderr)
            except Exception as e:
                self.safe_reply(connection, event, f"Error leaving {room_to_part}: {e}")
                self._record_error(f"Error leaving channel: {e}")
                print(f"[admin] DEBUG: Failed to part {room_to_part} with error: {e}", file=sys.stderr)
        else:
            self.safe_reply(connection, event, f"I am not in {room_to_part}.")
            print(f"[admin] DEBUG: Not in channel {room_to_part}", file=sys.stderr)
        return True
    
    @admin_required
    def _cmd_channels(self, connection, event, msg, username, match):
        print(f"[admin] DEBUG: Handling !channels command", file=sys.stderr)
        channels_list = ", ".join(sorted(list(self.bot.joined_channels)))
        self.safe_reply(connection, event, f"I am currently in these channels: {channels_list}")
        return True

    @admin_required
    def _cmd_say(self, connection, event, msg, username, match):
        target_room, message = match.groups()
        print(f"[admin] DEBUG: Handling !say command for target: {target_room}", file=sys.stderr)
        target = target_room or event.target
        self.bot.connection.privmsg(target, message)
        return True

    @admin_required
    def _cmd_adv_cancel(self, connection, event, msg, username, match):
        print(f"[admin] DEBUG: Handling !adventure cancel command", file=sys.stderr)
        adventure_plugin = self.bot.pm.plugins.get("adventure")
        if adventure_plugin:
            adventure_state = self._get_adventure_state_for_room(event.target)
            if adventure_state:
                adventure_plugin._close_adventure_round()
                self.safe_reply(connection, event, "Adventure has been cancelled.")
            else:
                self.safe_reply(connection, event, "There is no adventure to cancel.")
        else:
            self.safe_reply(connection, event, "Adventure module is not loaded.")
        return True

    @admin_required
    def _cmd_adv_shorten(self, connection, event, msg, username, match):
        value = match.group(1)
        delta_secs = int(value)
        print(f"[admin] DEBUG: Handling !adventure shorten command by {delta_secs}s", file=sys.stderr)
        adventure_plugin = self.bot.pm.plugins.get("adventure")
        if adventure_plugin:
            adventure_state = self._get_adventure_state_for_room(event.target)
            if adventure_state:
                new_close_time = float(adventure_state.get("close_epoch", 0)) - delta_secs
                adventure_state["close_epoch"] = new_close_time
                self.bot.update_module_state("adventure", {"current": adventure_state})
                self.safe_reply(connection, event, f"Adventure timer shortened by {delta_secs} seconds.")
            else:
                self.safe_reply(connection, event, "There is no adventure to modify.")
        else:
            self.safe_reply(connection, event, "Adventure module is not loaded.")
        return True
        
    @admin_required
    def _cmd_adv_extend(self, connection, event, msg, username, match):
        value = match.group(1)
        delta_secs = int(value)
        print(f"[admin] DEBUG: Handling !adventure extend command by {delta_secs}s", file=sys.stderr)
        adventure_plugin = self.bot.pm.plugins.get("adventure")
        if adventure_plugin:
            adventure_state = self._get_adventure_state_for_room(event.target)
            if adventure_state:
                new_close_time = float(adventure_state.get("close_epoch", 0)) + delta_secs
                adventure_state["close_epoch"] = new_close_time
                self.bot.update_module_state("adventure", {"current": adventure_state})
                self.safe_reply(connection, event, f"Adventure timer extended by {delta_secs} seconds.")
            else:
                self.safe_reply(connection, event, "There is no adventure to modify.")
        else:
            self.safe_reply(connection, event, "Adventure module is not loaded.")
        return True
    
    @admin_required
    def _cmd_adv_status(self, connection, event, msg, username, match):
        print(f"[admin] DEBUG: Handling !adventure status command", file=sys.stderr)
        adventure_plugin = self.bot.pm.plugins.get("adventure")
        if adventure_plugin:
            adventure_state = self._get_adventure_state_for_room(event.target)
            if adventure_state:
                options = adventure_state["options"]
                close_time = float(adventure_state.get("close_epoch", 0))
                secs_left = max(0, int(close_time - time.time()))
                self.safe_reply(connection, event, f"Adventure in progress: 1. {options[0]} or 2. {options[1]} — {secs_left}s left.")
            else:
                self.safe_reply(connection, event, "There is no adventure in progress in this channel.")
        else:
            self.safe_reply(connection, event, "Adventure module is not loaded.")
        return True

    @admin_required
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        quit_msg = match.group(1)
        self.bot.connection.quit(quit_msg or "Emergency quit.")
        return True
    
    @admin_required
    def _cmd_nick(self, connection, event, msg, username, match):
        new_nick = match.group(1)
        try:
            self.bot.connection.nick(new_nick)
            self.safe_reply(connection, event, f"Nickname changed to {new_nick}.")
        except Exception as e:
            self.safe_reply(connection, event, f"Failed to change nick: {e}")
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
        
    # --- Helper methods (same as before) ---
    def _get_adventure_state_for_room(self, room: str) -> Optional[Dict[str, Any]]:
        adventure_plugin = self.bot.pm.plugins.get("adventure")
        if adventure_plugin and hasattr(adventure_plugin, "get_state"):
            current_adventure = adventure_plugin.get_state("current")
            if current_adventure and current_adventure.get("room") == room:
                return current_adventure
        return None