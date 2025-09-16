# modules/adventure.py
# Enhanced choose-your-own-adventure with better state management and admin controls
import random
import re
import time
import schedule
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Adventure(bot, config)

class Adventure(SimpleCommandModule):
    name = "adventure"
    version = "2.3.1" # version bumped
    description = "A choose-your-own-adventure game for the channel."
    
    # Adventure locations and story bits...
    PLACES = [ "the Neon Bazaar", "the Clockwork Conservatory", "the Signal Archives", "the Subterranean Gardens", "the Rusted Funicular", "the Mirror Maze", "the Lattice Observatory", "the Stormbreak Causeway", "the Midnight Diner", "the Old Museum", "the Lighthouse", "the Planetarium", "the Rooftops", "the Antique Arcade", "the Bookshop Maze", "the Railway Depot", "the Tea Pavilion", "the Neon Alley", "the Forgotten Server Farm", "the Catacomb Switchyard", "the Endless Lobby", "the Glass Cathedral", "the Iron Menagerie", "the Holographic Forest", "the Perpetual Carnival", "the Shattered Aqueduct", "the Gilded Boiler Room", "the Abandoned Data Center", "the Fractured Causeway", "the Vaulted Terminal", "the Hall of Expired Passwords", "the Cryogenic Garden", "the Wax Cylinder Library", "the Vanishing Platform", "the Singing Substation", "the Spiral Archives", "the Candlelit Foundry", "the Flooded Crypt", "the Black Glass Bridge", "the Chimera Menagerie", "the Tarnished Observatory", "the Hollow Clocktower", "the Paper Lantern Pier", "the Last Greenhouse", "the Red Circuit Cathedral", "the Forgotten Monorail", "the Smouldering Atrium", "the Binary Bazaar", ]
    STORY_BITS = [ "A locked cabinet hummed like a captive beehive in {place}.", "Someone had chalked unfamiliar sigils on the floor of {place}.", "In {place}, screens woke without power and showed a room three seconds ahead.", "The air in {place} tasted like coins and old arguments.", "A brass plaque in {place} listed names none of you remembered becoming.", "Every footstep in {place} arrived before the boot that made it.", "A maintenance door in {place} opened onto an identical maintenance door.", "Even the shadows in {place} kept their own inventories.", "You found a keyring labeled 'spares' in {place}; none of the keys matched each other.", "At {place}, the public address system whispered your question back with an extra word.", "Rain pooled in {place} and reflected not the ceiling but a low gray sky.", "The map at {place} had a 'you were here' marker that moved if you looked away.", "The chandeliers in {place} flickered in binary, on and off, like a code you almost understood.", "A statue in {place} briefly turned its head to watch you pass.", "The floor of {place} was carpeted with expired access cards.", "Wind in {place} carried voices speaking passwords from decades ago.", "A grandfather clock in {place} ticked backwards; your shadow obeyed it.", "A vending machine in {place} dispensed coins older than the city.", "At {place}, mirrors refused to show anyone standing alone.", "Pigeons in {place} recited error codes instead of cooing.", "The walls of {place} wept condensation that smelled of solder.", "A fountain in {place} sprayed letters instead of water.", "Elevators in {place} opened onto hallways that should not exist.", "Every sign in {place} pointed toward exits that never appeared.", "The sky above {place} displayed old chat logs scrolling endlessly.", "In {place}, all doors locked themselves when you looked directly at them.", "A pile of shoes in {place} was still warm to the touch.", "Lanterns in {place} illuminated scenes from tomorrow’s news.", "A clockwork bird sang in {place}; the song made your teeth ache.", "Even silence in {place} had a background hum, like a server rack dreaming.", ]

    RE_VOTE_1 = re.compile(r"^\s*!?1[.,!\s]*\s*$")
    RE_VOTE_2 = re.compile(r"^\s*!?2[.,!\s]*\s*$")

    def __init__(self, bot, config):
        super().__init__(bot)
        self.VOTE_WINDOW_SEC = config.get("vote_window_seconds", 75)
        self.STORY_SENTENCES_PER_ROUND = config.get("story_sentences_per_round", 3)
        self.MAX_HISTORY_ENTRIES = 50

        self.set_state("current", self.get_state("current", None))
        self.set_state("history", self.get_state("history", []))
        self.set_state("stats", self.get_state("stats", {"adventures_started": 0, "adventures_completed": 0, "total_votes_cast": 0, "most_popular_location": None}))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!adventure\s*$", self._cmd_start,
                              name="adventure", description="Start a choose-your-own-adventure voting session.")
        self.register_command(r"^\s*!adventure\s+(now|status)\s*$", self._cmd_status,
                              name="adventure status", description="Check the status of the current adventure.")
        self.register_command(r"^\s*!adventure\s+(last|history)\s*$", self._cmd_last,
                              name="adventure last", description="Show the last adventure and its outcome.")
        self.register_command(r"^\s*!adventure\s+cancel\s*$", self._cmd_adv_cancel,
                              name="adventure cancel", admin_only=True, description="[Admin] Cancel the current adventure.")
        self.register_command(r"^\s*!adventure\s+shorten\s+(\d+)\s*$", self._cmd_adv_shorten,
                              name="adventure shorten", admin_only=True, description="[Admin] Shorten adventure timer by N seconds.")
        self.register_command(r"^\s*!adventure\s+extend\s+(\d+)\s*$", self._cmd_adv_extend,
                              name="adventure extend", admin_only=True, description="[Admin] Extend adventure timer by N seconds.")

    def on_load(self):
        super().on_load()
        schedule.clear(f"{self.name}-cleanup")
        current = self.get_state("current")
        if current:
            close_time = float(current.get("close_epoch", 0))
            now = time.time()
            if now >= close_time:
                self._close_adventure_round()
            else:
                room = current.get("room")
                if room:
                    remaining_seconds = int(close_time - now)
                    if remaining_seconds > 0:
                        schedule.every(remaining_seconds).seconds.do(lambda: self._close_adventure_scheduled(room)).tag(f"{self.name}-close-{room}")

    def on_unload(self):
        super().on_unload()
        current = self.get_state("current")
        if current:
            room = current.get("room")
            if room:
                schedule.clear(f"{self.name}-close-{room}")

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            if time.time() > float(current.get("close_epoch", 0)):
                self._close_adventure_round()
                return True
            if self.RE_VOTE_1.match(msg):
                self._add_vote(username, 1)
                return True
            if self.RE_VOTE_2.match(msg):
                self._add_vote(username, 2)
                return True
        return False

    def _cmd_start(self, connection, event, msg, username, match):
        # ... (rest of the functions remain the same)
        current = self.get_state("current")
        room = event.target
        if current and current.get("room") == room:
            options = current["options"]
            close_time = float(current.get("close_epoch", 0))
            secs_left = max(0, int(close_time - time.time()))
            self.safe_reply(connection, event, f"An adventure is already underway: 1. {options[0]} or 2. {options[1]} — {secs_left}s left.")
            return True
        if current and current.get("room") != room:
            other_room = current.get("room")
            self.safe_reply(connection, event, f"I'm afraid there's already an adventure underway in {other_room}. One expedition at a time, if you please.")
            return True
        options = self._get_two_places()
        title = self.bot.title_for(username)
        self.safe_reply(connection, event, f"Very good, {title}; an adventure it is. Shall we set out for 1. {options[0]} or 2. {options[1]}? Say 1 or 2 to vote.")
        close_time = time.time() + self.VOTE_WINDOW_SEC
        new_adventure = {"room": room, "options": options, "votes_1": [], "votes_2": [], "starter": username, "close_epoch": close_time, "started_at": datetime.now(UTC).isoformat()}
        self.set_state("current", new_adventure)
        self.save_state()
        self._schedule_adventure_close(room)
        stats = self.get_state("stats")
        stats["adventures_started"] = stats.get("adventures_started", 0) + 1
        self.set_state("stats", stats)
        self.save_state()
        return True

    def _cmd_status(self, connection, event, msg, username, match):
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            options = current["options"]
            close_time = float(current.get("close_epoch", 0))
            secs_left = max(0, int(close_time - time.time()))
            votes_1 = len(current.get("votes_1", []))
            votes_2 = len(current.get("votes_2", []))
            self.safe_reply(connection, event, f"{username}, voting in progress: 1. {options[0]} ({votes_1} votes) or 2. {options[1]} ({votes_2} votes) — {secs_left}s remaining.")
        else:
            self.safe_reply(connection, event, f"{username}, there is no adventure afoot.")
        return True

    def _cmd_last(self, connection, event, msg, username, match):
        history = self.get_state("history")
        if not history:
            self.safe_reply(connection, event, f"{username}, no adventures have been logged yet.")
            return True
        last = history[-1]
        options = last["options"]
        vote_counts = last.get("vote_counts", [0, 0])
        winner = last["winner"]
        when = last["when"][:16]
        self.safe_reply(connection, event, f"{username}, last adventure: 1. {options[0]} ({vote_counts[0]}) vs 2. {options[1]} ({vote_counts[1]}) → {winner} at {when}.")
        return True

    @admin_required
    def _cmd_adv_cancel(self, connection, event, msg, username, match):
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            self._close_adventure_round()
            self.safe_reply(connection, event, "Adventure has been cancelled.")
        else:
            self.safe_reply(connection, event, "There is no adventure in this channel to cancel.")
        return True

    @admin_required
    def _cmd_adv_shorten(self, connection, event, msg, username, match):
        delta_secs = int(match.group(1))
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            new_close_time = float(current.get("close_epoch", 0)) - delta_secs
            current["close_epoch"] = new_close_time
            self.set_state("current", current)
            self.save_state()
            self.safe_reply(connection, event, f"Adventure timer shortened by {delta_secs} seconds.")
        else:
            self.safe_reply(connection, event, "There is no adventure in this channel to modify.")
        return True

    @admin_required
    def _cmd_adv_extend(self, connection, event, msg, username, match):
        delta_secs = int(match.group(1))
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            new_close_time = float(current.get("close_epoch", 0)) + delta_secs
            current["close_epoch"] = new_close_time
            self.set_state("current", current)
            self.save_state()
            self.safe_reply(connection, event, f"Adventure timer extended by {delta_secs} seconds.")
        else:
            self.safe_reply(connection, event, "There is no adventure in this channel to modify.")
        return True

    def _get_two_places(self) -> Tuple[str, str]:
        return tuple(random.sample(self.PLACES, 2))

    def _create_story(self, place: str) -> str:
        bits = random.sample(self.STORY_BITS, self.STORY_SENTENCES_PER_ROUND)
        lines = [bit.format(place=place) for bit in bits]
        return " ".join(lines)

    def _schedule_adventure_close(self, room: str) -> None:
        schedule.clear(f"{self.name}-close-{room}")
        schedule.every(self.VOTE_WINDOW_SEC).seconds.do(lambda: self._close_adventure_scheduled(room)).tag(f"{self.name}-close-{room}")

    def _close_adventure_scheduled(self, expected_room: str):
        current = self.get_state("current")
        if not current or current.get("room") != expected_room:
            return schedule.CancelJob
        self._close_adventure_round()
        return schedule.CancelJob

    def _close_adventure_round(self):
        current = self.get_state("current")
        if not current:
            return
        room = current["room"]
        options = current["options"]
        votes_1 = current.get("votes_1", [])
        votes_2 = current.get("votes_2", [])
        schedule.clear(f"{self.name}-close-{room}")
        votes_1 = list(dict.fromkeys(votes_1))
        votes_2 = list(dict.fromkeys(votes_2))
        c1, c2 = len(votes_1), len(votes_2)
        if c1 == c2:
            winner = random.choice(options)
            tie_note = " (tie—decided by the fates)"
        elif c1 > c2:
            winner = options[0]
            tie_note = ""
        else:
            winner = options[1]
            tie_note = ""
        story = self._create_story(winner)
        detail_1 = f"{c1} vote{'s' if c1 != 1 else ''}"
        detail_2 = f"{c2} vote{'s' if c2 != 1 else ''}"
        try:
            self.bot.connection.privmsg(room, f"Votes tallied: 1. {options[0]} → {detail_1}; 2. {options[1]} → {detail_2}.{tie_note}")
            self.bot.connection.privmsg(room, f"To {winner} then. {story}")
        except Exception as e:
            self._record_error(f"error announcing results: {e}")
        entry = {"when": datetime.now(UTC).isoformat(), "room": room, "options": list(options), "votes_1": votes_1, "votes_2": votes_2, "winner": winner, "starter": current.get("starter"), "vote_counts": [c1, c2]}
        history = self.get_state("history", [])
        history.append(entry)
        if len(history) > self.MAX_HISTORY_ENTRIES:
            history = history[-self.MAX_HISTORY_ENTRIES:]
        stats = self.get_state("stats")
        stats["adventures_completed"] = stats.get("adventures_completed", 0) + 1
        stats["total_votes_cast"] = stats.get("total_votes_cast", 0) + c1 + c2
        location_counts = {}
        for h in history:
            winner_loc = h.get("winner")
            if winner_loc:
                location_counts[winner_loc] = location_counts.get(winner_loc, 0) + 1
        if location_counts:
            stats["most_popular_location"] = max(location_counts, key=location_counts.get)
        self.set_state("history", history)
        self.set_state("current", None)
        self.set_state("stats", stats)
        self.save_state()

    def _add_vote(self, username: str, vote_option: int) -> bool:
        current = self.get_state("current")
        if not current:
            return False
        close_time = float(current.get("close_epoch", 0))
        if time.time() > close_time:
            self._close_adventure_round()
            return True
        votes_1 = current.get("votes_1", [])
        votes_2 = current.get("votes_2", [])
        if username in votes_1:
            votes_1.remove(username)
        if username in votes_2:
            votes_2.remove(username)
        if vote_option == 1:
            votes_1.append(username)
        else:
            votes_2.append(username)
        current["votes_1"] = votes_1
        current["votes_2"] = votes_2
        self.set_state("current", current)
        self.save_state()
        return True