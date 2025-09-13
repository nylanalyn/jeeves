# modules/roadtrip.py
# Surprise roadtrips with RSVP and history (pronoun-aware).
import random
import re
import time
import threading
from datetime import datetime, timezone, timedelta

UTC = timezone.utc

ROADTRIP_MIN_HOURS = 3
ROADTRIP_MAX_HOURS = 18
ROADTRIP_MSGS_MIN = 35
ROADTRIP_MSGS_MAX = 85
TRIGGER_PROBABILITY = 0.25
ROADTRIP_JOIN_WINDOW = 120  # seconds

ROADTRIP_TRIGGER_LINE = "Of course, {title}; I’ll prepare the car."

TRIP_LOCATIONS = [
    "the riverside park","the old museum","the observatory","the seaside pier","the midnight diner",
    "the botanical gardens","the antique arcade","the lighthouse","the market square","the hilltop ruins",
    "the art-house cinema","the railway depot","the speakeasy","the planetarium","the neon alley",
    "the tea pavilion","the bookshop maze","the clocktower","the rooftops","the brothel","the funfair",
    "the stormbreak causeway",
]

def setup(bot):
    return Roadtrip(bot)

class Roadtrip:
    name = "roadtrip"

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        self.st.setdefault("msgs_since_last", 0)
        self.st.setdefault("next_trip_earliest", self._compute_next_trip_time().isoformat())
        self.st.setdefault("next_trip_msg_threshold", self._compute_next_trip_msg_threshold())
        self.st.setdefault("current", None)  # RSVP window
        self.st.setdefault("history", [])
        self.bot.save()

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_RSVP = re.compile(rf"^\s*coming\s+{name_pat}!?\s*\.?\s*$", re.IGNORECASE)
        self.RE_RSVP_ALT = re.compile(r"^\s*!me\s*$", re.IGNORECASE)
        self.RE_CMD_ROADTRIP = re.compile(r"^\s*!roadtrip\s*$", re.IGNORECASE)

    def on_load(self): pass
    def on_unload(self): pass

    # ---- helpers ----
    def _compute_next_trip_time(self):
        hrs = random.randint(ROADTRIP_MIN_HOURS, ROADTRIP_MAX_HOURS)
        return datetime.now(UTC) + timedelta(hours=hrs)

    def _compute_next_trip_msg_threshold(self):
        return random.randint(ROADTRIP_MSGS_MIN, ROADTRIP_MSGS_MAX)

    def _time_ok(self):
        try:
            earliest = datetime.fromisoformat(self.st.get("next_trip_earliest"))
        except Exception:
            earliest = self._compute_next_trip_time()
            self.st["next_trip_earliest"] = earliest.isoformat()
            self.bot.save()
        return datetime.now(UTC) >= earliest

    def _msgs_ok(self):
        return int(self.st.get("msgs_since_last", 0)) >= int(self.st.get("next_trip_msg_threshold", 0))

    def _reset_gates(self):
        self.st["msgs_since_last"] = 0
        self.st["next_trip_earliest"] = self._compute_next_trip_time().isoformat()
        self.st["next_trip_msg_threshold"] = self._compute_next_trip_msg_threshold()
        self.bot.save()

    def _open_window(self, connection, room):
        destination = random.choice(TRIP_LOCATIONS)
        # neutral announcement in this room
        connection.privmsg(room, ROADTRIP_TRIGGER_LINE.format(title=self.bot.title_for("nobody")))
        connection.privmsg(
            room,
            f"Shall we? I’ve in mind a little excursion to {destination}. "
            f'Say "coming jeeves!" or "coming jeevesbot!" or "!me" within {ROADTRIP_JOIN_WINDOW} seconds to be shown to the car.'
        )
        now = datetime.now(UTC)
        open_until = (now + timedelta(seconds=ROADTRIP_JOIN_WINDOW)).timestamp()
        self.st["current"] = {
            "open_until_epoch": open_until,
            "participants": [],
            "triggered_at": now.isoformat(),
            "location": destination,
            "room": room,
        }
        self.bot.save()
        threading.Thread(target=self._close_window_after_delay, daemon=True).start()

    def _close_window_after_delay(self):
        time.sleep(ROADTRIP_JOIN_WINDOW)
        self._close_window()

    def _close_window(self):
        cur = self.st.get("current")
        if not cur:
            return
        room = cur.get("room")
        participants = list(dict.fromkeys(cur.get("participants", [])))
        date_iso = cur.get("triggered_at", datetime.now(UTC).isoformat())
        destination = cur.get("location", "parts unknown")

        entry = {
            "date_iso": date_iso,
            "participants": participants,
            "msgs_at_trigger": int(self.st.get("msgs_since_last", 0)),
            "location": destination,
            "room": room,
        }
        hist = self.st.get("history", [])
        hist.append(entry)
        self.st["history"] = hist
        self.st["current"] = None
        self.bot.save()

        if participants:
            details = [f"{p} ({self.bot.pronouns_for(p)})" for p in participants]
            self.bot.connection.privmsg(room, f"Very good. Outing to {destination}: {', '.join(details)}. Do buckle up.")
        else:
            self.bot.connection.privmsg(room, f"No takers. I shall cancel the reservation for {destination}.")

        self._reset_gates()

    def _maybe_collect_rsvp(self, connection, room, msg, username):
        cur = self.st.get("current")
        if not cur:
            return False
        if time.time() > float(cur.get("open_until_epoch", 0)):
            self._close_window()
            return True

        if self.RE_RSVP.match(msg) or self.RE_RSVP_ALT.match(msg):
            participants = cur.get("participants", [])
            if username not in participants:
                participants.append(username)
                cur["participants"] = participants
                self.st["current"] = cur
                self.bot.save()
                connection.privmsg(room, f"Noted, {username}. Mind the running board.")
            return True
        return False

    def _maybe_trigger(self, connection, room):
        if self.st.get("current"):
            return
        if self._time_ok() and self._msgs_ok() and random.random() < TRIGGER_PROBABILITY:
            self._open_window(connection, room)

    def _answer_latest(self, connection, room, username):
        hist = self.st.get("history", [])
        if not hist:
            connection.privmsg(room, f"{username}, no roadtrips on the books yet, {self.bot.title_for(username)}.")
            return True
        last = hist[-1]
        when = last.get("date_iso", "")
        pax = last.get("participants", [])
        destination = last.get("location", "parts unknown")
        if pax:
            details = [f"{p} ({self.bot.pronouns_for(p)})" for p in pax]
            connection.privmsg(room, f"{username}, most recent outing to {destination} ({when}): {', '.join(details)}.")
        else:
            connection.privmsg(room, f"{username}, the most recent outing to {destination} ({when}) departed without passengers, {self.bot.title_for(username)}.")
        return True

    # ---- IRC hook ----
    def on_pubmsg(self, connection, event, msg, username):
        room = event.target  # speak in the room where the chatter happened

        if self.RE_CMD_ROADTRIP.match(msg):
            return self._answer_latest(connection, room, username)

        if self._maybe_collect_rsvp(connection, room, msg, username):
            return True

        # count chatter per *global* gates (simple shared pot)
        self.st["msgs_since_last"] = int(self.st.get("msgs_since_last", 0)) + 1
        self.bot.save()
        self._maybe_trigger(connection, room)
        return False

