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
    version = "3.0.1" # Initialization fix
    description = "Provides memo functionality for leaving messages for users."

    ACKS = [ "Indeed, {title}; I shall make a note of it.", "Very good, {title}. Your message is recorded.", "Quite so, {title}; I shall see that it is delivered." ]
    DELIVER_LINES = [ "Ah, {to}! {from_} left you a message; {says}: {text}", "{to}, a note from {from_}: {text}", "Message for {to} from {from_}: {text}" ]

    def __init__(self, bot, config):
        self.on_config_reload(config)
        super().__init__(bot)
        
        self.set_state("pending", self.get_state("pending", {}))
        self.save_state()

    def on_config_reload(self, config):
        memos_config = config.get(self.name, config)
        self.MAX_DELIVER_PER_BURST = memos_config.get("max_deliver_per_burst", 3)
        self.MAX_PENDING_PER_USER = memos_config.get("max_pending_per_user", 3)

    def _register_commands(self):
        self.register_command(r"^\s*!memo\s+(\S+)\s+(.+)$", self._cmd_memo, name="memo", description="Leave a message for someone.")
        self.register_command(r"^\s*!note\s+(\S+)\s+(.+)$", self._cmd_memo, name="note", description="Alias for !memo.")
        self.register_command(r"^\s*!tell\s+(\S+)\s+(.+)$", self._cmd_memo, name="tell", description="Alias for !memo.")
        self.register_command(r"^\s*!memos\s+mine\s*$", self._cmd_memos_mine, name="memos mine", description="Show your pending messages.")

    def on_ambient_message(self, connection, event, msg, username):
        user_id = self.bot.get_user_id(username)
        pending = self.get_state("pending", {})
        bucket = pending.get(user_id, [])
        
        if not bucket:
            return False
            
        to_deliver = bucket[:self.MAX_DELIVER_PER_BURST]
        remainder = bucket[self.MAX_DELIVER_PER_BURST:]
        
        for item in to_deliver:
            line = self._deliver_line(username, item.get("from","?"), item.get("text",""))
            self.safe_reply(connection, event, line)
            
        if remainder:
            self.safe_reply(connection, event, f"{username}, there are {len(remainder)} additional memo(s); say '!memos mine' to review them.")
        
        if remainder:
            pending[user_id] = remainder
        else:
            pending.pop(user_id, None)
        
        self.set_state("pending", pending)
        self.save_state()
        return True

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
        if not text:
            return True

        to_user_id = self.bot.get_user_id(to_nick)
        pending = self.get_state("pending")
        bucket = pending.get(to_user_id, [])
        
        if len(bucket) >= self.MAX_PENDING_PER_USER:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {to_nick} already has {self.MAX_PENDING_PER_USER} memos queued.")
            return True
            
        bucket.append({
            "from": username, 
            "text": text, 
            "when": self.bot.get_utc_time(),
        })
        pending[to_user_id] = bucket
        
        self.set_state("pending", pending)
        self.save_state()
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {random.choice(self.ACKS).format(title=self.bot.title_for(username))}")
        return True

    def _cmd_memos_mine(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        bucket = self.get_state("pending", {}).get(user_id, [])
        
        if not bucket:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, there are no memos awaiting you.")
            return True
            
        shown = bucket[:self.MAX_DELIVER_PER_BURST]
        more = len(bucket) - len(shown)
        
        for item in shown:
            when = (item.get("when") or "")[:16]
            self.safe_reply(connection, event, f"{username}, from {item.get('from','?')} ({when}): {item.get('text','')}")
            
        if more > 0:
            self.safe_reply(connection, event, f"{username}, …and {more} more memo(s) queued.")
        return True

