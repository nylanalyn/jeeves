# modules/memos.py
# Memo delivery with butler flair — with per-user memo cap
import re
import functools
import time 
import random
from datetime import datetime, timezone
from typing import Optional
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot):
    return Memos(bot)

class Memos(SimpleCommandModule):
    name = "memos"
    version = "2.1.0"
    description = "Provides memo functionality for leaving messages for users."
    
    MAX_DELIVER_PER_BURST = 3
    MAX_PENDING_PER_USER = 3

    ACKS = [
        "Indeed, {title}; I shall make a precise note of it.",
        "Very good, {title}. Your message is recorded.",
        "Quite so, {title}; I shall see that it is delivered.",
        "At once, {title}. I have filed the memorandum.",
        "Consider it noted and queued with care, {title}.",
    ]

    DELIVER_LINES = [
        "Ah, {to}! {from_} left you a message; {says}: {text}",
        "{to}, a note from {from_}: {text}",
        "Message for {to} from {from_}: {text}",
    ]

    def __init__(self, bot):
        super().__init__(bot)
        self.set_state("pending", self.get_state("pending", {}))
        self.set_state("created_count", self.get_state("created_count", 0))
        self.set_state("delivered_count", self.get_state("delivered_count", 0))
        self.set_state("last_delivered_at", self.get_state("last_delivered_at", None))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!memo\s+(\S+)\s+(.+)$", self._cmd_memo,
                              description="Leave a message for someone. Usage: !memo <nick> <message>")
        self.register_command(r"^\s*!memos\s+mine\s*$", self._cmd_memos_mine,
                              description="Show your pending messages.")
        self.register_command(r"^\s*!memos\s+stats\s*$", self._cmd_stats,
                              admin_only=True, description="Show memo statistics.")

    # --- main handler ---
    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True

        key = self._norm(username)
        bucket = self._bucket(key)
        if not bucket:
            return False

        to_deliver = bucket[:self.MAX_DELIVER_PER_BURST]
        remainder  = bucket[self.MAX_DELIVER_PER_BURST:]

        for item in to_deliver:
            line = self._deliver_line(username, item.get("from","?"), item.get("text",""))
            self.safe_reply(connection, event, line)

        if remainder:
            self.safe_reply(connection, event, f"{username}, there are {len(remainder)} additional memo(s); say '!memos mine' to review them.")

        self.set_state("delivered_count", self.get_state("delivered_count") + len(to_deliver))
        self.set_state("last_delivered_at", datetime.now(UTC).isoformat())
        self.save_state()

        self._set_bucket(key, remainder)
        return True

    # --- helpers ---
    def _norm(self, nick: str) -> str:
        return nick.strip().lower()

    def _bucket(self, nick_lower: str):
        return self.get_state("pending", {}).get(nick_lower, [])

    def _set_bucket(self, nick_lower: str, items):
        pending = self.get_state("pending", {})
        if items:
            pending[nick_lower] = items
        else:
            pending.pop(nick_lower, None)
        self.set_state("pending", pending)
        self.save_state()

    def _ack(self, username: str) -> str:
        return random.choice(self.ACKS).format(title=self.bot.title_for(username))

    def _third_person_says(self, pronouns: str) -> str:
        p = (pronouns or "").lower()
        if p.startswith("he"): return "he says"
        if p.startswith("she"): return "she says"
        if p.startswith("it"): return "it says"
        return "they say"

    def _deliver_line(self, to_user: str, from_user: str, text: str) -> str:
        pron = self.bot.pronouns_for(from_user)
        says = self._third_person_says(pron)
        tmpl = random.choice(self.DELIVER_LINES)
        return tmpl.format(to=to_user, from_=from_user, text=text, says=says)
    
    # --- Command handlers ---
    def _cmd_memo(self, connection, event, msg, username, match):
        room = event.target
        to_nick, text = match.group(1), match.group(2).strip()
        if not text:
            self.safe_reply(connection, event, f"{username}, I require a message to record.")
            return True

        key = self._norm(to_nick)
        bucket = self._bucket(key)
        if len(bucket) >= self.MAX_PENDING_PER_USER:
            self.safe_reply(connection, event, f"{username}, {to_nick} already has {self.MAX_PENDING_PER_USER} memos queued; I cannot accept more.")
            return True

        bucket.append({
            "from": username,
            "text": text,
            "when": datetime.now(UTC).isoformat(),
            "room": room,
        })
        self._set_bucket(key, bucket)

        self.set_state("created_count", self.get_state("created_count") + 1)
        self.save_state()
        self.safe_reply(connection, event, f"{username}, {self._ack(username)}")
        return True

    def _cmd_memos_mine(self, connection, event, msg, username, match):
        room = event.target
        key = self._norm(username)
        bucket = self._bucket(key)
        if not bucket:
            self.safe_reply(connection, event, f"{username}, there are no memos awaiting you.")
            return True
        shown = bucket[:self.MAX_DELIVER_PER_BURST]
        more = len(bucket) - len(shown)
        for item in shown:
            when = (item.get("when") or "")[:16]
            self.safe_reply(connection, event, f"{username}, from {item.get('from','?')} ({when}): {item.get('text','')}")
        if more > 0:
            self.safe_reply(connection, event, f"{username}, …and {more} more memo(s) queued.")
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        room = event.target
        total_pending = sum(len(v) for v in self.get_state("pending", {}).values())
        self.safe_reply(connection, event,
                        f"Memos stats: pending={total_pending}, created={self.get_state('created_count',0)}, delivered={self.get_state('delivered_count',0)}, last_delivery={self.get_state('last_delivered_at','never')}")
        return True