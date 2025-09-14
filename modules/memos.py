# modules/memos.py
# Memo delivery with butler flair — with per-user memo cap - Already correctly targets rooms

import re
from datetime import datetime, timezone

UTC = timezone.utc

def setup(bot):
    return Memos(bot)

class Memos:
    name = "memos"
    version = "1.0.2"
    MAX_DELIVER_PER_BURST = 3   # deliver at most 3 memos inline
    MAX_PENDING_PER_USER = 3    # cap: each recipient may only have 3 memos waiting

    RE_STORE = re.compile(r"^\s*!memo\s+(\S+)\s+(.+)$", re.IGNORECASE)
    RE_MINE  = re.compile(r"^\s*!memos\s+mine\s*$", re.IGNORECASE)
    RE_STATS = re.compile(r"^\s*!memos\s+stats\s*$", re.IGNORECASE)

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
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        self.st.setdefault("pending", {})
        self.st.setdefault("created_count", 0)
        self.st.setdefault("delivered_count", 0)
        self.st.setdefault("last_delivered_at", None)
        bot.save()

    # --- helpers ---
    def _norm(self, nick: str) -> str:
        return nick.strip().lower()

    def _bucket(self, nick_lower: str):
        return self.st.get("pending", {}).get(nick_lower, [])

    def _set_bucket(self, nick_lower: str, items):
        pending = self.st.get("pending", {})
        if items:
            pending[nick_lower] = items
        else:
            pending.pop(nick_lower, None)
        self.st["pending"] = pending
        self.bot.save()

    def _ack(self, username: str) -> str:
        import random
        return random.choice(self.ACKS).format(title=self.bot.title_for(username))

    def _third_person_says(self, pronouns: str) -> str:
        p = (pronouns or "").lower()
        if p.startswith("he"): return "he says"
        if p.startswith("she"): return "she says"
        if p.startswith("it"): return "it says"
        return "they say"

    def _deliver_line(self, to_user: str, from_user: str, text: str) -> str:
        import random
        pron = self.bot.pronouns_for(from_user)
        says = self._third_person_says(pron)
        tmpl = random.choice(self.DELIVER_LINES)
        return tmpl.format(to=to_user, from_=from_user, text=text, says=says)

    # --- main handler ---
    def on_pubmsg(self, connection, event, msg, username):
        room = event.target

        # Store memo
        m = self.RE_STORE.match(msg)
        if m:
            to_nick, text = m.group(1), m.group(2).strip()
            if not text:
                connection.privmsg(room, f"{username}, I require a message to record.")
                return True

            key = self._norm(to_nick)
            bucket = self._bucket(key)

            # Enforce cap
            if len(bucket) >= self.MAX_PENDING_PER_USER:
                connection.privmsg(room, f"{username}, {to_nick} already has {self.MAX_PENDING_PER_USER} memos queued; I cannot accept more.")
                return True

            bucket.append({
                "from": username,
                "text": text,
                "when": datetime.now(UTC).isoformat(),
                "room": room,
            })
            self._set_bucket(key, bucket)

            self.st["created_count"] = self.st.get("created_count", 0) + 1
            self.bot.save()

            connection.privmsg(room, f"{username}, {self._ack(username)}")
            return True

        # List your own memos
        if self.RE_MINE.match(msg):
            key = self._norm(username)
            bucket = self._bucket(key)
            if not bucket:
                connection.privmsg(room, f"{username}, there are no memos awaiting you.")
                return True
            shown = bucket[:self.MAX_DELIVER_PER_BURST]
            more = len(bucket) - len(shown)
            for item in shown:
                when = (item.get("when") or "")[:16]
                connection.privmsg(room, f"{username}, from {item.get('from','?')} ({when}): {item.get('text','')}")
            if more > 0:
                connection.privmsg(room, f"{username}, …and {more} more memo(s) queued.")
            return True

        # Stats (admin)
        if self.bot.is_admin(username) and self.RE_STATS.match(msg):
            total_pending = sum(len(v) for v in self.st.get("pending", {}).values())
            connection.privmsg(
                room,
                f"Memos stats: pending={total_pending}, created={self.st.get('created_count',0)}, delivered={self.st.get('delivered_count',0)}, last_delivery={self.st.get('last_delivered_at','never')}"
            )
            return True

        # Delivery trigger
        key = self._norm(username)
        bucket = self._bucket(key)
        if not bucket:
            return False

        to_deliver = bucket[:self.MAX_DELIVER_PER_BURST]
        remainder  = bucket[self.MAX_DELIVER_PER_BURST:]

        for item in to_deliver:
            line = self._deliver_line(username, item.get("from","?"), item.get("text",""))
            connection.privmsg(room, line)

        if remainder:
            connection.privmsg(room, f"{username}, there are {len(remainder)} additional memo(s); say '!memos mine' to review them.")

        self.st["delivered_count"] = self.st.get("delivered_count", 0) + len(to_deliver)
        self.st["last_delivered_at"] = datetime.now(UTC).isoformat()
        self.bot.save()

        self._set_bucket(key, remainder)
        return True