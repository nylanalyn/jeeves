# modules/adventure.py
# Room-wide "choose your own adventure" with 1/2 voting and a short generated story.

import random
import re
import time
import threading
from datetime import datetime, timezone, timedelta

UTC = timezone.utc

VOTE_WINDOW_SEC = 75  # how long to accept votes
STORY_SENTENCES_PER_ROUND = 3

PLACES = [
    "the Neon Bazaar", "the Clockwork Conservatory", "the Signal Archives", "the Subterranean Gardens",
    "the Rusted Funicular", "the Mirror Maze", "the Lattice Observatory", "the Stormbreak Causeway",
    "the Midnight Diner", "the Old Museum", "the Lighthouse", "the Planetarium", "the Rooftops",
    "the Antique Arcade", "the Bookshop Maze", "the Railway Depot", "the Tea Pavilion", "the Neon Alley",
]

# Lightly spooky / tech-goth snippets; {place} gets inserted.
STORY_BITS = [
    "A locked cabinet hummed like a captive beehive in {place}.",
    "Someone had chalked unfamiliar sigils on the floor of {place}.",
    "In {place}, screens woke without power and showed a room three seconds ahead.",
    "The air in {place} tasted like coins and old arguments.",
    "A brass plaque in {place} listed names none of you remembered becoming.",
    "Every footstep in {place} arrived before the boot that made it.",
    "A maintenance door in {place} opened onto an identical maintenance door.",
    "Even the shadows in {place} kept their own inventories.",
    "You found a keyring labeled 'spares' in {place}; none of the keys matched each other.",
    "At {place}, the public address system whispered your question back with an extra word.",
    "Rain pooled in {place} and reflected not the ceiling but a low gray sky.",
    "The map at {place} had a 'you were here' marker that moved if you looked away.",
]

def setup(bot):
    return Adventure(bot)

class Adventure:
    name = "adventure"

    # Accept "1", "2", "!1", "!2", "1.", "2," etc., alone on the line.
    RE_VOTE_1 = re.compile(r"^\s*!?1[.,! ]*\s*$")
    RE_VOTE_2 = re.compile(r"^\s*!?2[.,! ]*\s*$")
    RE_CMD_START = re.compile(r"^\s*!adventure\s*$", re.IGNORECASE)
    RE_CMD_STATUS = re.compile(r"^\s*!adventure\s+(now|status)\s*$", re.IGNORECASE)
    RE_CMD_LAST = re.compile(r"^\s*!adventure\s+(last|history)\s*$", re.IGNORECASE)

    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        # persistent structure
        self.st.setdefault("current", None)   # current round dict
        self.st.setdefault("history", [])     # list of past rounds
        self.bot.save()

    # ----- helpers -----
    def _two_places(self):
        a, b = random.sample(PLACES, 2)
        return a, b

    def _mk_story(self, place):
        # choose unique sentences
        bits = random.sample(STORY_BITS, STORY_SENTENCES_PER_ROUND)
        lines = [s.format(place=place) for s in bits]
        return " ".join(lines)

    def _announce_round(self, connection, room, a, b, starter_title):
        connection.privmsg(
            room,
            f"Very good, {starter_title}; an adventure it is. "
            f"Shall we set out for 1. {a} or 2. {b}? Say 1 or 2 to vote."
        )

    def _close_after_delay(self):
        time.sleep(VOTE_WINDOW_SEC)
        self._close_round()

    def _close_round(self):
        cur = self.st.get("current")
        if not cur:
            return
        room = cur["room"]
        a, b = cur["options"]
        # tally
        v1 = list(cur["votes_1"])
        v2 = list(cur["votes_2"])
        c1, c2 = len(v1), len(v2)

        if c1 == c2:
            winner = random.choice([a, b])
            tie_note = " (tie—decided by the fates)"
        elif c1 > c2:
            winner = a
            tie_note = ""
        else:
            winner = b
            tie_note = ""

        story = self._mk_story(winner)

        # Announce result
        detail_1 = f"{c1} vote{'s' if c1 != 1 else ''}"
        detail_2 = f"{c2} vote{'s' if c2 != 1 else ''}"
        self.bot.connection.privmsg(room, f"Votes tallied: 1. {a} → {detail_1}; 2. {b} → {detail_2}.{tie_note}")
        self.bot.connection.privmsg(room, f"To {winner} then. {story}")

        # record history
        entry = {
            "when": datetime.now(UTC).isoformat(),
            "room": room,
            "options": [a, b],
            "votes_1": v1,
            "votes_2": v2,
            "winner": winner,
        }
        hist = self.st.get("history", [])
        hist.append(entry)
        self.st["history"] = hist
        self.st["current"] = None
        self.bot.save()

    # ----- IRC hooks -----
    def on_pubmsg(self, connection, event, msg, username):
        room = event.target

        # status
        if self.RE_CMD_STATUS.match(msg):
            cur = self.st.get("current")
            if cur and cur.get("room") == room:
                a, b = cur["options"]
                secs_left = max(0, int(cur["close_epoch"] - time.time()))
                connection.privmsg(
                    room,
                    f"{username}, voting in progress: 1. {a} or 2. {b} — {secs_left}s remaining."
                )
            else:
                connection.privmsg(room, f"{username}, there is no adventure afoot.")
            return True

        # last result
        if self.RE_CMD_LAST.match(msg):
            hist = self.st.get("history", [])
            if not hist:
                connection.privmsg(room, f"{username}, no adventures have been logged yet.")
                return True
            last = hist[-1]
            a, b = last["options"]
            c1, c2 = len(last["votes_1"]), len(last["votes_2"])
            winner = last["winner"]
            connection.privmsg(
                room,
                f"{username}, last adventure: 1. {a} ({c1}) vs 2. {b} ({c2}) → {winner} at {last['when']}."
            )
            return True

        # start
        if self.RE_CMD_START.match(msg):
            if self.st.get("current") and self.st["current"].get("room") == room:
                a, b = self.st["current"]["options"]
                secs_left = max(0, int(self.st["current"]["close_epoch"] - time.time()))
                connection.privmsg(room, f"An adventure is already underway: 1. {a} or 2. {b} — {secs_left}s left.")
                return True

            a, b = self._two_places()
            title = self.bot.title_for(username)
            self._announce_round(connection, room, a, b, title)
            close_at = time.time() + VOTE_WINDOW_SEC
            self.st["current"] = {
                "room": room,
                "options": (a, b),
                "votes_1": set(),  # use sets to avoid duplicate voters
                "votes_2": set(),
                "starter": username,
                "close_epoch": close_at,
            }
            self.bot.save()
            threading.Thread(target=self._close_after_delay, daemon=True).start()
            return True

        # votes
        cur = self.st.get("current")
        if cur and cur.get("room") == room:
            if time.time() > float(cur.get("close_epoch", 0)):
                # close lazily if messages arrive after deadline
                self._close_round()
                return True

            if self.RE_VOTE_1.match(msg):
                cur["votes_1"].add(username)
                self.st["current"] = cur
                self.bot.save()
                return True
            if self.RE_VOTE_2.match(msg):
                cur["votes_2"].add(username)
                self.st["current"] = cur
                self.bot.save()
                return True

        return False

