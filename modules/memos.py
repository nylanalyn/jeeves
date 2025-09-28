# modules/memos.py
# Memo delivery with butler flair.
import re
import random
from datetime import datetime, timezone
from typing import Optional
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Memos(bot, config)

class Memos(SimpleCommandModule):
    name = "memos"
    version = "3.1.0" # Added channel-specific memo delivery
    description = "Provides memo functionality for leaving messages for users."

    ACKS = [ "Indeed, {title}; I shall make a note of it.", "Very good, {title}. Your message is recorded.", "Quite so, {title}; I shall see that it is delivered." ]
    DELIVER_LINES = [ "Ah, {to}! {from_} left you a message; {says}: {text}", "{to}, a note from {from_}: {text}", "Message for {to} from {from_}: {text}" ]

    def __init__(self, bot, config):
        super().__init__(bot)
        
        # --- State Migration Logic ---
        pending_memos = self.get_state("pending", {})
        # Check if the first key is likely a user_id (non-channel) to detect old format
        first_key = next(iter(pending_memos), None)
        if first_key and not first_key.startswith('#'):
            self.log_debug("Old memo state format detected. Migrating memos...")
            new_pending = { self.bot.primary_channel: pending_memos }
            self.set_state("pending", new_pending)
            self.log_debug(f"Migrated memos for {len(pending_memos)} users to default channel {self.bot.primary_channel}.")
        else:
            self.set_state("pending", pending_memos)
        # --- End Migration Logic ---
        
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!memo\s+(\S+)\s+(.+)$", self._cmd_memo, name="memo", description="Leave a message for someone.")
        self.register_command(r"^\s*!note\s+(\S+)\s+(.+)$", self._cmd_memo, name="note", description="Alias for !memo.")
        self.register_command(r"^\s*!tell\s+(\S+)\s+(.+)$", self._cmd_memo, name="tell", description="Alias for !memo.")
        self.register_command(r"^\s*!memos\s+mine\s*$", self._cmd_memos_mine, name="memos mine", description="Show your pending messages.")

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target): return False

        user_id = self.bot.get_user_id(username)
        channel = event.target
        pending = self.get_state("pending", {})
        
        # Only look for memos in the current channel
        channel_memos = pending.get(channel, {})
        bucket = channel_memos.get(user_id, [])
        
        if not bucket:
            return False
            
        max_deliver = self.get_config_value("max_deliver_per_burst", channel, default=3)
        to_deliver = bucket[:max_deliver]
        remainder = bucket[max_deliver:]
        
        for item in to_deliver:
            line = self._deliver_line(username, item.get("from","?"), item.get("text",""))
            self.safe_reply(connection, event, line)
            
        if remainder:
            self.safe_reply(connection, event, f"{username}, there are {len(remainder)} additional memo(s) for you in this channel; say '!memos mine' to review them.")
        
        if remainder:
            pending[channel][user_id] = remainder
        else:
            del pending[channel][user_id]
            if not pending[channel]: # Clean up empty channel dict
                del pending[channel]

        self.set_state("pending", pending)
        self.save_state()
        return True # Memos were delivered, so we can consider the event handled.

    def _third_person_says(self, from_user: str) -> str:
        pron = self.bot.pronouns_for(from_user).lower()
        if pron.startswith("he"): return "he says"
        if pron.startswith("she"): return "she says"
        if pron.startswith("it"): return "it says"
        return "they say"

    def _deliver_line(self, to_user: str, from_user: str, text: str) -> str:
        says = self._third_person_says(from_user)
        tmpl = random.choice(self.DELIVER_LINES)
        return tmpl.format(to=to_user, from_=from_user, text=text, says=says)

    def _cmd_memo(self, connection, event, msg, username, match):
        to_nick, text = match.group(1), match.group(2).strip()
        channel = event.target
        if not text:
            return True

        to_user_id = self.bot.get_user_id(to_nick)
        pending = self.get_state("pending", {})
        
        channel_memos = pending.setdefault(channel, {})
        bucket = channel_memos.setdefault(to_user_id, [])
        
        max_pending = self.get_config_value("max_pending_per_user", channel, default=3)
        if len(bucket) >= max_pending:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {to_nick} already has {max_pending} memos queued in this channel.")
            return True
            
        bucket.append({
            "from": username, 
            "text": text, 
            "when": self.bot.get_utc_time(),
        })
        
        self.set_state("pending", pending)
        self.save_state()
        self.safe_reply(connection, event, random.choice(self.ACKS).format(title=self.bot.title_for(username)))
        return True

    def _cmd_memos_mine(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        pending = self.get_state("pending", {})
        all_user_memos = []

        # Collect memos from all channels for the user
        for channel, channel_memos in pending.items():
            if user_id in channel_memos:
                for memo in channel_memos[user_id]:
                    memo_with_context = memo.copy()
                    memo_with_context['channel'] = channel
                    all_user_memos.append(memo_with_context)
        
        if not all_user_memos:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, there are no memos awaiting you.")
            return True
        
        max_deliver = self.get_config_value("max_deliver_per_burst", event.target, default=3)
        shown = all_user_memos[:max_deliver]
        more = len(all_user_memos) - len(shown)
        
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your pending memos:")
        for item in shown:
            when = (item.get("when") or "")[:16].replace("T", " ")
            self.safe_privmsg(username, f"- From {item.get('from','?')} (in {item.get('channel')} at {when} UTC): {item.get('text','')}")
            
        if more > 0:
            self.safe_privmsg(username, f"…and {more} more memo(s) queued.")
        
        self.safe_reply(connection, event, "I have sent you the details privately.")
        return True

