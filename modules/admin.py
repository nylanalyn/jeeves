# modules/admin.py
# Enhanced admin conveniences using the ModuleBase framework
import re
import time
import threading
import functools
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
    version = "2.1.0"
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
        # ... (same join logic) ...
        return True

    @admin_required
    def _cmd_part(self, connection, event, msg, username, match):
        room_to_part, part_msg = match.groups()
        # ... (same part logic) ...
        return True
    
    @admin_required
    def _cmd_channels(self, connection, event, msg, username, match):
        # ... (same channels logic) ...
        return True

    @admin_required
    def _cmd_say(self, connection, event, msg, username, match):
        target_room, message = match.groups()
        # ... (same say logic) ...
        return True

    @admin_required
    def _cmd_adv_cancel(self, connection, event, msg, username, match):
        # ... (same adventure cancel logic) ...
        return True

    @admin_required
    def _cmd_adv_shorten(self, connection, event, msg, username, match):
        value = match.group(1)
        delta_secs = int(value)
        # ... (same shorten logic) ...
        return True
        
    @admin_required
    def _cmd_adv_extend(self, connection, event, msg, username, match):
        value = match.group(1)
        delta_secs = int(value)
        # ... (same extend logic) ...
        return True
    
    @admin_required
    def _cmd_adv_status(self, connection, event, msg, username, match):
        # ... (same adventure status logic) ...
        return True

    @admin_required
    def _cmd_emergency_quit(self, connection, event, msg, username, match):
        quit_msg = match.group(1)
        # ... (same quit logic) ...
        return True
    
    @admin_required
    def _cmd_nick(self, connection, event, msg, username, match):
        new_nick = match.group(1)
        # ... (same nick logic) ...
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
    def _get_adventure_state_for_room(self, room: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        # ... (same helper logic) ...
        pass
    
    def _format_time_remaining(self, seconds: int) -> str:
        # ... (same helper logic) ...
        pass
    
    def _handle_join(self, connection, event, room_to_join: str):
        # ... (same helper logic) ...
        pass
        
    def _handle_part(self, connection, event, room_to_part: str, part_message: Optional[str] = None):
        # ... (same helper logic) ...
        pass
    
    def _handle_channels_list(self, connection, room: str):
        # ... (same helper logic) ...
        pass
    
    def _handle_say(self, connection, event, target_room: Optional[str], message: str):
        # ... (same helper logic) ...
        pass
        
    def _handle_emergency_quit(self, connection, quit_message: Optional[str]):
        # ... (same helper logic) ...
        pass
        
    def _handle_nick_change(self, connection, new_nick: str):
        # ... (same helper logic) ...
        pass