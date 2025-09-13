# modules/admin.py
# Admin conveniences: !join, !part, !say, and adventure controls (cancel/shorten/extend).
import re
import time

def setup(bot): return Admin(bot)

class Admin:
    name = "admin"

    RE_JOIN = re.compile(r"^\s*!join\s+(#\S+)\s*$", re.IGNORECASE)
    RE_PART = re.compile(r"^\s*!part\s+(#\S+)\s*$", re.IGNORECASE)
    # !say #room Hello world (room optional: if omitted, speak in current room)
    RE_SAY  = re.compile(r"^\s*!say(?:\s+(#\S+))?\s+(.+)$", re.IGNORECASE)

    # Adventure controls (room-scoped)
    RE_ADV_CANCEL  = re.compile(r"^\s*!adventure\s+cancel\s*$", re.IGNORECASE)
    RE_ADV_SHORTEN = re.compile(r"^\s*!adventure\s+shorten\s+(\d{1,4})\s*$", re.IGNORECASE)
    RE_ADV_EXTEND  = re.compile(r"^\s*!adventure\s+extend\s+(\d{1,4})\s*$", re.IGNORECASE)

    def __init__(self, bot):
        self.bot = bot
        if not hasattr(self.bot, "joined_channels"):
            self.bot.joined_channels = set()

    def on_load(self): pass
    def on_unload(self): pass

    def _deny(self, connection, event, username):
        # Silent denial keeps keys discreet; change to a message if you prefer feedback.
        return True

    # ---- helpers ----
    def _adv_state_for_room(self, room):
        """Return (st, cur) where st is the adventure module state dict, cur is current round (or None)
           only if it belongs to the given room."""
        st = self.bot.get_module_state("adventure")
        cur = st.get("current")
        if cur and cur.get("room") == room:
            return st, cur
        return st, None

    def _adv_cancel(self, connection, room):
        st, cur = self._adv_state_for_room(room)
        if not cur:
            connection.privmsg(room, "There is no active adventure in this room.")
            return
        a, b = cur.get("options", ("?", "?"))
        st["current"] = None  # background closer will no-op
        self.bot.save()
        connection.privmsg(room, f"As you wish. The adventure (1. {a} vs 2. {b}) is canceled.")

    def _adv_adjust_time(self, connection, room, delta_secs, mode):
        """mode='shorten' or 'extend'"""
        st, cur = self._adv_state_for_room(room)
        if not cur:
            connection.privmsg(room, "There is no active adventure in this room.")
            return

        now = time.time()
        close_epoch = float(cur.get("close_epoch", now))
        remaining = max(0, int(close_epoch - now))

        # compute new remaining
        if mode == "shorten":
            new_remaining = remaining - int(delta_secs)
        else:
            new_remaining = remaining + int(delta_secs)

        # enforce bounds: min 5s, max 30m
        new_remaining = max(5, min(new_remaining, 30 * 60))
        cur["close_epoch"] = now + new_remaining
        st["current"] = cur
        self.bot.save()

        action = "shortened" if mode == "shorten" else "extended"
        connection.privmsg(room, f"Very good. The adventure timer is {action}; {new_remaining}s remain.")

    # ---- IRC hook ----
    def on_pubmsg(self, connection, event, msg, username):
        room = event.target

        # Only admins may pass
        if not self.bot.is_admin(username):
            if (self.RE_JOIN.match(msg) or self.RE_PART.match(msg) or
                self.RE_SAY.match(msg) or self.RE_ADV_CANCEL.match(msg) or
                self.RE_ADV_SHORTEN.match(msg) or self.RE_ADV_EXTEND.match(msg)):
                return self._deny(connection, event, username)
            return False

        # --- !adventure cancel ---
        if self.RE_ADV_CANCEL.match(msg):
            self._adv_cancel(connection, room)
            return True

        # --- !adventure shorten <secs> ---
        m = self.RE_ADV_SHORTEN.match(msg)
        if m:
            secs = int(m.group(1))
            self._adv_adjust_time(connection, room, secs, mode="shorten")
            return True

        # --- !adventure extend <secs> ---
        m = self.RE_ADV_EXTEND.match(msg)
        if m:
            secs = int(m.group(1))
            self._adv_adjust_time(connection, room, secs, mode="extend")
            return True

        # --- !join #room ---
        m = self.RE_JOIN.match(msg)
        if m:
            new_room = m.group(1)
            try:
                if new_room not in getattr(self.bot, "joined_channels", {self.bot.primary_channel}):
                    connection.join(new_room)
                    self.bot.joined_channels.add(new_room)
                connection.privmsg(new_room, "At your service; I shall attend here as well.")
                connection.privmsg(room, f"I am now attending {new_room}, {self.bot.title_for(username)}.")
            except Exception as e:
                connection.privmsg(room, f"My apologies; I could not join {new_room}: {e!s}.")
            return True

        # --- !part #room ---
        m = self.RE_PART.match(msg)
        if m:
            part_room = m.group(1)
            try:
                if part_room in getattr(self.bot, "joined_channels", set()):
                    connection.part(part_room, "As you wish.")
                    self.bot.joined_channels.discard(part_room)
                else:
                    connection.privmsg(room, f"I am not presently attending {part_room}.")
            except Exception as e:
                connection.privmsg(room, f"My apologies; I could not part {part_room}: {e!s}.")
            return True

        # --- !say [#room] message ---
        m = self.RE_SAY.match(msg)
        if m:
            target_room = m.group(1) or room
            text = m.group(2).strip()
            try:
                connection.privmsg(target_room, text)
            except Exception as e:
                connection.privmsg(room, f"I could not convey the message to {target_room}: {e!s}.")
            return True

        return False

