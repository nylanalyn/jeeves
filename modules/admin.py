# modules/admin.py
# Enhanced admin conveniences without base class dependency
import re
import time
import threading
from typing import Optional, Tuple, Dict, Any

def setup(bot): 
    return Admin(bot)

class Admin:
    name = "admin"
    version = "2.0.0"
    
    # Compiled regex patterns for better performance
    RE_JOIN = re.compile(r"^\s*!join\s+(#\S+)\s*$", re.IGNORECASE)
    RE_PART = re.compile(r"^\s*!part\s+(#\S+)(?:\s+(.+))?\s*$", re.IGNORECASE)
    RE_SAY = re.compile(r"^\s*!say(?:\s+(#\S+))?\s+(.+)$", re.IGNORECASE)
    RE_CHANNELS = re.compile(r"^\s*!channels\s*$", re.IGNORECASE)
    
    # Adventure controls with better validation
    RE_ADV_CANCEL = re.compile(r"^\s*!adventure\s+cancel\s*$", re.IGNORECASE)
    RE_ADV_SHORTEN = re.compile(r"^\s*!adventure\s+shorten\s+(\d{1,4})([smh])?\s*$", re.IGNORECASE)
    RE_ADV_EXTEND = re.compile(r"^\s*!adventure\s+extend\s+(\d{1,4})([smh])?\s*$", re.IGNORECASE)
    RE_ADV_STATUS = re.compile(r"^\s*!adventure\s+status\s*$", re.IGNORECASE)
    
    # Emergency controls
    RE_EMERGENCY_QUIT = re.compile(r"^\s*!emergency\s+quit(?:\s+(.+))?\s*$", re.IGNORECASE)
    RE_NICK_CHANGE = re.compile(r"^\s*!nick\s+(\S+)\s*$", re.IGNORECASE)

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("commands_used", 0)
        self.st.setdefault("last_used", None)
        self.st.setdefault("channels_joined", 0)
        self.st.setdefault("emergency_uses", 0)
        
        self._command_cache = {}
        self._last_channel_list = 0
        
        # Ensure bot has joined_channels tracking
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = {self.bot.primary_channel}
        
        bot.save()

    def on_load(self):
        """Initialize admin module state."""
        pass

    def on_unload(self):
        """Cleanup on module unload."""
        self._command_cache.clear()

    def _is_admin_command(self, msg: str) -> bool:
        """Quick check if message is an admin command (with caching)."""
        msg_lower = msg.lower().strip()
        if msg_lower in self._command_cache:
            return self._command_cache[msg_lower]
        
        is_admin_cmd = any([
            self.RE_JOIN.match(msg), self.RE_PART.match(msg), self.RE_SAY.match(msg),
            self.RE_CHANNELS.match(msg), self.RE_ADV_CANCEL.match(msg),
            self.RE_ADV_SHORTEN.match(msg), self.RE_ADV_EXTEND.match(msg),
            self.RE_ADV_STATUS.match(msg), self.RE_EMERGENCY_QUIT.match(msg),
            self.RE_NICK_CHANGE.match(msg)
        ])
        
        if len(self._command_cache) < 100:
            self._command_cache[msg_lower] = is_admin_cmd
        
        return is_admin_cmd

    def _update_usage_stats(self, command: str):
        """Track command usage statistics."""
        self.st["commands_used"] = self.st.get("commands_used", 0) + 1
        self.st["last_used"] = time.time()
        self.st["last_command"] = command
        self.bot.save()

    # ---- Adventure management helpers ----
    def _get_adventure_state_for_room(self, room: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        """Get adventure state for a specific room."""
        state = self.bot.get_module_state("adventure")
        current = state.get("current")
        
        if current and current.get("room") == room:
            return state, current
        return state, None

    def _format_time_remaining(self, seconds: int) -> str:
        """Format seconds into human readable time."""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        else:
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m"

    def _parse_time_unit(self, value: str, unit: Optional[str]) -> int:
        """Parse time value with optional unit (s/m/h), default seconds."""
        multiplier = {"s": 1, "m": 60, "h": 3600}.get((unit or "s").lower(), 1)
        return int(value) * multiplier

    # ---- Adventure command handlers ----
    def _handle_adventure_cancel(self, connection, room: str):
        """Cancel active adventure in the room."""
        state, current = self._get_adventure_state_for_room(room)
        
        if not current:
            connection.privmsg(room, "There is no active adventure in this room.")
            return
            
        options = current.get("options", ("?", "?"))
        state["current"] = None
        
        # Update adventure module state
        adventure_st = self.bot.get_module_state("adventure")
        adventure_st["current"] = None
        self.bot.save()
        
        connection.privmsg(room, f"Very good. The adventure ({options[0]} vs {options[1]}) has been canceled.")

    def _handle_adventure_status(self, connection, room: str):
        """Show current adventure status."""
        state, current = self._get_adventure_state_for_room(room)
        
        if not current:
            connection.privmsg(room, "No active adventure in this room.")
            return
            
        now = time.time()
        close_epoch = float(current.get("close_epoch", now))
        remaining = max(0, int(close_epoch - now))
        
        options = current.get("options", ("?", "?"))
        votes_1 = current.get("votes_1", []) 
        votes_2 = current.get("votes_2", [])
        
        vote_counts = [len(votes_1), len(votes_2)]
        
        time_str = self._format_time_remaining(remaining)
        connection.privmsg(room, 
            f"Adventure: \"{options[0]}\" ({vote_counts[0]} votes) vs \"{options[1]}\" ({vote_counts[1]} votes) - {time_str} remaining")

    def _handle_adventure_time_adjust(self, connection, room: str, delta_secs: int, mode: str):
        """Adjust adventure timing (shorten/extend)."""
        state, current = self._get_adventure_state_for_room(room)
        
        if not current:
            connection.privmsg(room, "There is no active adventure in this room.")
            return

        now = time.time()
        close_epoch = float(current.get("close_epoch", now))
        remaining = max(0, int(close_epoch - now))

        # Calculate new remaining time
        if mode == "shorten":
            new_remaining = remaining - delta_secs
        else:  # extend
            new_remaining = remaining + delta_secs

        # Enforce reasonable bounds: 5s minimum, 2 hours maximum
        new_remaining = max(5, min(new_remaining, 2 * 3600))
        
        # Update state
        current["close_epoch"] = now + new_remaining
        adventure_st = self.bot.get_module_state("adventure")
        adventure_st["current"] = current
        self.bot.save()

        action = "shortened" if mode == "shorten" else "extended"
        time_str = self._format_time_remaining(new_remaining)
        connection.privmsg(room, f"Adventure timer {action} to {time_str} remaining.")

    # ---- Channel management ----
    def _handle_join(self, connection, event, room_to_join: str):
        """Handle channel join with error handling."""
        current_room = event.target
        
        try:
            if room_to_join in self.bot.joined_channels:
                connection.privmsg(current_room, f"I am already attending {room_to_join}.")
                return
                
            connection.join(room_to_join)
            self.bot.joined_channels.add(room_to_join)
            
            # Send greeting to new room (with delay to ensure join completes)
            def delayed_greeting():
                time.sleep(1)
                try:
                    connection.privmsg(room_to_join, "At your service; I shall attend here as well.")
                except Exception:
                    pass
                    
            threading.Timer(1.0, delayed_greeting).start()
            
            username = event.source.split('!')[0]
            connection.privmsg(current_room, 
                f"Now attending {room_to_join}, {self.bot.title_for(username)}.")
            
            self.st["channels_joined"] = self.st.get("channels_joined", 0) + 1
            self.bot.save()
                
        except Exception as e:
            connection.privmsg(current_room, f"Unable to join {room_to_join}: {str(e)}")

    def _handle_part(self, connection, event, room_to_part: str, part_message: Optional[str] = None):
        """Handle channel part with optional message."""
        current_room = event.target
        message = part_message or "As you wish."
        
        # Prevent parting from primary channel
        if room_to_part == self.bot.primary_channel:
            connection.privmsg(current_room, "I cannot part from my primary channel.")
            return
            
        try:
            if room_to_part not in self.bot.joined_channels:
                connection.privmsg(current_room, f"I am not currently attending {room_to_part}.")
                return
                
            connection.part(room_to_part, message)
            self.bot.joined_channels.discard(room_to_part)
            connection.privmsg(current_room, f"I have departed from {room_to_part}.")
            
        except Exception as e:
            connection.privmsg(current_room, f"Unable to part from {room_to_part}: {str(e)}")

    def _handle_channels_list(self, connection, room: str):
        """List currently joined channels with rate limiting."""
        now = time.time()
        if now - self._last_channel_list < 10:  # 10 second cooldown
            connection.privmsg(room, "Please wait before requesting the channel list again.")
            return
            
        self._last_channel_list = now
        
        if not self.bot.joined_channels:
            connection.privmsg(room, "I am not currently attending any channels.")
            return
            
        channels = sorted(self.bot.joined_channels)
        
        if len(channels) == 1:
            primary_mark = " (primary)" if channels[0] == self.bot.primary_channel else ""
            connection.privmsg(room, f"Currently attending: {channels[0]}{primary_mark}")
        else:
            channel_list = ", ".join(
                f"{ch}{' (primary)' if ch == self.bot.primary_channel else ''}" 
                for ch in channels
            )
            connection.privmsg(room, f"Currently attending {len(channels)} channels: {channel_list}")

    def _handle_say(self, connection, event, target_room: Optional[str], message: str):
        """Handle say command with validation."""
        current_room = event.target
        final_room = target_room or current_room
        
        # Validate target room
        if target_room and target_room not in self.bot.joined_channels:
            connection.privmsg(current_room, f"I am not attending {target_room}.")
            return
            
        try:
            connection.privmsg(final_room, message)
            if target_room and target_room != current_room:
                connection.privmsg(current_room, f"Message delivered to {target_room}.")
        except Exception as e:
            connection.privmsg(current_room, f"Unable to send message: {str(e)}")

    # ---- Emergency commands ----
    def _handle_emergency_quit(self, connection, quit_message: Optional[str]):
        """Handle emergency quit command."""
        message = quit_message or "Emergency shutdown requested"
        self.st["emergency_uses"] = self.st.get("emergency_uses", 0) + 1
        self.bot.save()
        
        try:
            connection.quit(message)
        except Exception:
            connection.disconnect()

    def _handle_nick_change(self, connection, new_nick: str):
        """Handle nickname change."""
        try:
            connection.nick(new_nick)
            self.bot.nickname = new_nick
        except Exception as e:
            connection.privmsg(self.bot.primary_channel, f"Unable to change nick: {str(e)}")

    # ---- Main message handler ----
    def on_pubmsg(self, connection, event, msg: str, username: str) -> bool:
        """Handle public messages - optimized with early returns."""
        
        # Quick rejection for non-admin commands
        if not self._is_admin_command(msg):
            return False
            
        # Security check - silent denial for non-admins
        if not self.bot.is_admin(username):
            return True  # Silent denial

        # Track command usage
        self._update_usage_stats(msg.split()[0] if msg else "unknown")

        room = event.target

        # Adventure controls
        if self.RE_ADV_CANCEL.match(msg):
            self._handle_adventure_cancel(connection, room)
            return True

        if self.RE_ADV_STATUS.match(msg):
            self._handle_adventure_status(connection, room)
            return True

        # Adventure time adjustments
        for pattern, mode in [(self.RE_ADV_SHORTEN, "shorten"), (self.RE_ADV_EXTEND, "extend")]:
            match = pattern.match(msg)
            if match:
                value, unit = match.groups()
                delta_secs = self._parse_time_unit(value, unit)
                self._handle_adventure_time_adjust(connection, room, delta_secs, mode)
                return True

        # Channel management
        match = self.RE_JOIN.match(msg)
        if match:
            self._handle_join(connection, event, match.group(1))
            return True

        match = self.RE_PART.match(msg)
        if match:
            room_to_part, part_msg = match.groups()
            self._handle_part(connection, event, room_to_part, part_msg)
            return True

        if self.RE_CHANNELS.match(msg):
            self._handle_channels_list(connection, room)
            return True

        # Say command
        match = self.RE_SAY.match(msg)
        if match:
            target_room, message = match.groups()
            self._handle_say(connection, event, target_room, message)
            return True

        # Emergency controls
        match = self.RE_EMERGENCY_QUIT.match(msg)
        if match:
            quit_msg = match.group(1)
            self._handle_emergency_quit(connection, quit_msg)
            return True

        match = self.RE_NICK_CHANGE.match(msg)
        if match:
            new_nick = match.group(1)
            self._handle_nick_change(connection, new_nick)
            return True

        return False