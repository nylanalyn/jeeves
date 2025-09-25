# modules/adventure.py
# Enhanced choose-your-own-adventure with better state management and admin controls
import random
import re
import time
import schedule
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Adventure(bot, config)

class Adventure(SimpleCommandModule):
    name = "adventure"
    version = "2.5.1" # Fixed statistics calculation error
    description = "A choose-your-own-adventure game for the channel."
    
    # Adventure locations and story bits...
    PLACES = [ "the Neon Bazaar", "the Clockwork Conservatory", "the Signal Archives", "the Subterranean Gardens", "the Rusted Funicular", "the Mirror Maze", "the Lattice Observatory", "the Stormbreak Causeway", "the Midnight Diner", "the Old Museum", "the Lighthouse", "the Planetarium", "the Rooftops", "the Antique Arcade", "the Bookshop Maze", "the Railway Depot", "the Tea Pavilion", "the Neon Alley", "the Forgotten Server Farm", "the Catacomb Switchyard", "the Endless Lobby", "the Glass Cathedral", "the Iron Menagerie", "the Holographic Forest", "the Perpetual Carnival", "the Shattered Aqueduct", "the Gilded Boiler Room", "the Abandoned Data Center", "the Fractured Causeway", "the Vaulted Terminal", "the Hall of Expired Passwords", "the Cryogenic Garden", "the Wax Cylinder Library", "the Vanishing Platform", "the Singing Substation", "the Spiral Archives", "the Candlelit Foundry", "the Flooded Crypt", "the Black Glass Bridge", "the Chimera Menagerie", "the Tarnished Observatory", "the Hollow Clocktower", "the Paper Lantern Pier", "the Last Greenhouse", "the Red Circuit Cathedral", "the Forgotten Monorail", "the Smouldering Atrium", "the Binary Bazaar", ]
    STORY_BITS = [ "A locked cabinet hummed like a captive beehive in {place}.", "Someone had chalked unfamiliar sigils on the floor of {place}.", "In {place}, screens woke without power and showed a room three seconds ahead.", "The air in {place} tasted like coins and old arguments.", "A brass plaque in {place} listed names none of you remembered becoming.", "Every footstep in {place} arrived before the boot that made it.", "A maintenance door in {place} opened onto an identical maintenance door.", "Even the shadows in {place} kept their own inventories.", "You found a keyring labeled 'spares' in {place}; none of the keys matched each other.", "At {place}, the public address system whispered your question back with an extra word.", "Rain pooled in {place} and reflected not the ceiling but a low gray sky.", "The map at {place} had a 'you were here' marker that moved if you looked away.", "The chandeliers in {place} flickered in binary, on and off, like a code you almost understood.", "A statue in {place} briefly turned its head to watch you pass.", "The floor of {place} was carpeted with expired access cards.", "Wind in {place} carried voices speaking passwords from decades ago.", "A grandfather clock in {place} ticked backwards; your shadow obeyed it.", "A vending machine in {place} dispensed coins older than the city.", "At {place}, mirrors refused to show anyone standing alone.", "Pigeons in {place} recited error codes instead of cooing.", "The walls of {place} wept condensation that smelled of solder.", "A fountain in {place} sprayed letters instead of water.", "Elevators in {place} opened onto hallways that should not exist.", "Every sign in {place} pointed toward exits that never appeared.", "The sky above {place} displayed old chat logs scrolling endlessly.", "In {place}, all doors locked themselves when you looked directly at them.", "A pile of shoes in {place} was still warm to the touch.", "Lanterns in {place} illuminated scenes from tomorrow’s news.", "A clockwork bird sang in {place}; the song made your teeth ache.", "Even silence in {place} had a background hum, like a server rack dreaming.", ]

    RE_VOTE_1 = re.compile(r"^\s*!?1[.,!\s]*\s*$")
    RE_VOTE_2 = re.compile(r"^\s*!?2[.,!\s]*\s*$")

    def __init__(self, bot, config):
        super().__init__(bot)
        self.on_config_reload(config)
        self.set_state("current", self.get_state("current", None))
        self.set_state("history", self.get_state("history", []))
        self.set_state("stats", self.get_state("stats", {"adventures_started": 0, "adventures_completed": 0, "total_votes_cast": 0, "most_popular_location": None}))
        self.set_state("inventories", self.get_state("inventories", {})) # New state for items
        self.save_state()

    def on_config_reload(self, config):
        self.VOTE_WINDOW_SEC = config.get("vote_window_seconds", 75)
        self.STORY_SENTENCES_PER_ROUND = config.get("story_sentences_per_round", 3)
        self.MAX_HISTORY_ENTRIES = 50
        # New item settings
        self.ITEM_FIND_CHANCE = config.get("item_find_chance", 0.25)
        self.ITEM_ADJECTIVES = config.get("item_adjectives", ["Unusual"])
        self.ITEM_NOUNS = config.get("item_nouns", ["Thing"])
        self.MAX_INVENTORY_SIZE = config.get("max_inventory_size", 3)


    def _register_commands(self):
        self.register_command(r"^\s*!adventure\s*$", self._cmd_start, name="adventure")
        self.register_command(r"^\s*!adventure\s+(now|status)\s*$", self._cmd_status, name="adventure status")
        self.register_command(r"^\s*!adventure\s+(last|history)\s*$", self._cmd_last, name="adventure last")
        self.register_command(r"^\s*!items(?:\s+(\S+))?\s*$", self._cmd_items, name="items")
        self.register_command(r"^\s*!adventure\s+cancel\s*$", self._cmd_adv_cancel, name="adventure cancel", admin_only=True)
        self.register_command(r"^\s*!adventure\s+shorten\s+(\d+)\s*$", self._cmd_adv_shorten, name="adventure shorten", admin_only=True)
        self.register_command(r"^\s*!adventure\s+extend\s+(\d+)\s*$", self._cmd_adv_extend, name="adventure extend", admin_only=True)

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
        if current and (room := current.get("room")):
            schedule.clear(f"{self.name}-close-{room}")

    def on_ambient_message(self, connection, event, msg, username):
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
        current, room = self.get_state("current"), event.target
        if current and current.get("room") == room:
            options, close_time = current["options"], float(current.get("close_epoch", 0))
            secs_left = max(0, int(close_time - time.time()))
            self.safe_reply(connection, event, f"An adventure is already underway: 1. {options[0]} or 2. {options[1]} — {secs_left}s left.")
            return True
        if current and current.get("room") != room:
            self.safe_reply(connection, event, f"I'm afraid there's already an adventure underway in {current.get('room')}. One expedition at a time, if you please.")
            return True
        options = self._get_two_places()
        self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}; an adventure it is. Shall we set out for 1. {options[0]} or 2. {options[1]}? Say 1 or 2 to vote.")
        close_time = time.time() + self.VOTE_WINDOW_SEC
        self.set_state("current", {"room": room, "options": options, "votes_1": [], "votes_2": [], "starter": username, "close_epoch": close_time, "started_at": datetime.now(UTC).isoformat()})
        self._schedule_adventure_close(room)
        stats = self.get_state("stats")
        stats["adventures_started"] = stats.get("adventures_started", 0) + 1
        self.set_state("stats", stats)
        self.save_state()
        return True

    def _cmd_status(self, connection, event, msg, username, match):
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            options, close_time = current["options"], float(current.get("close_epoch", 0))
            secs_left = max(0, int(close_time - time.time()))
            votes_1, votes_2 = len(current.get("votes_1", [])), len(current.get("votes_2", []))
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
        options, vote_counts, winner, when = last["options"], last.get("vote_counts", [0, 0]), last["winner"], last["when"][:16]
        self.safe_reply(connection, event, f"{username}, last adventure: 1. {options[0]} ({vote_counts[0]}) vs 2. {options[1]} ({vote_counts[1]}) → {winner} at {when}.")
        return True

    def _cmd_items(self, connection, event, msg, username, match):
        target_user_nick = match.group(1) or username
        user_id = self.bot.get_user_id(target_user_nick)
        inventories = self.get_state("inventories", {})
        user_items = inventories.get(user_id, [])
        if not user_items:
            self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} is not carrying any peculiar items.")
            return True
        items_str = ", ".join(user_items)
        self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)}'s pockets contain: {items_str}.")
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

    def _modify_adventure_time(self, event, delta_secs: int):
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            current["close_epoch"] = float(current.get("close_epoch", 0)) + delta_secs
            self.set_state("current", current)
            self.save_state()
            return True
        return False

    @admin_required
    def _cmd_adv_shorten(self, connection, event, msg, username, match):
        if self._modify_adventure_time(event, -int(match.group(1))):
            self.safe_reply(connection, event, f"Adventure timer shortened.")
        else:
            self.safe_reply(connection, event, "There is no adventure in this channel to modify.")
        return True

    @admin_required
    def _cmd_adv_extend(self, connection, event, msg, username, match):
        if self._modify_adventure_time(event, int(match.group(1))):
            self.safe_reply(connection, event, f"Adventure timer extended.")
        else:
            self.safe_reply(connection, event, "There is no adventure in this channel to modify.")
        return True

    def _get_two_places(self) -> Tuple[str, str]:
        return tuple(random.sample(self.PLACES, 2))

    def _create_story(self, place: str) -> str:
        bits = random.sample(self.STORY_BITS, self.STORY_SENTENCES_PER_ROUND)
        return " ".join(bit.format(place=place) for bit in bits)

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
        if not current: return
        room, options = current["room"], current["options"]
        votes_1, votes_2 = list(dict.fromkeys(current.get("votes_1", []))), list(dict.fromkeys(current.get("votes_2", [])))
        schedule.clear(f"{self.name}-close-{room}")
        c1, c2 = len(votes_1), len(votes_2)
        if c1 == c2:
            winner, winning_voters = random.choice(options), votes_1 + votes_2
            tie_note = " (tie—decided by the fates)"
        elif c1 > c2:
            winner, winning_voters = options[0], votes_1
            tie_note = ""
        else:
            winner, winning_voters = options[1], votes_2
            tie_note = ""
        story = self._create_story(winner)
        self.safe_say(f"Votes tallied: 1. {options[0]} → {c1} vote{'s' if c1 != 1 else ''}; 2. {options[1]} → {c2} vote{'s' if c2 != 1 else ''}.{tie_note}", room)
        self.safe_say(f"To {winner} then. {story}", room)
        
        self._handle_item_discovery(room, winning_voters)

        history = self.get_state("history", [])
        history.append({"when": datetime.now(UTC).isoformat(), "room": room, "options": list(options), "votes_1": votes_1, "votes_2": votes_2, "winner": winner, "starter": current.get("starter"), "vote_counts": [c1, c2]})
        if len(history) > self.MAX_HISTORY_ENTRIES: history = history[-self.MAX_HISTORY_ENTRIES:]
        
        stats = self.get_state("stats")
        stats["adventures_completed"] = stats.get("adventures_completed", 0) + 1
        stats["total_votes_cast"] = stats.get("total_votes_cast", 0) + c1 + c2
        
        # Correctly calculate location counts
        location_counts = {}
        for h in history:
            if winner_loc := h.get("winner"):
                location_counts[winner_loc] = location_counts.get(winner_loc, 0) + 1
        
        if location_counts: 
            stats["most_popular_location"] = max(location_counts, key=location_counts.get)
        
        self.set_state("history", history)
        self.set_state("current", None)
        self.set_state("stats", stats)
        self.save_state()

    def _handle_item_discovery(self, room: str, winning_voters: List[str]):
        if not winning_voters or not self.ITEM_ADJECTIVES or not self.ITEM_NOUNS:
            return
        if random.random() <= self.ITEM_FIND_CHANCE:
            lucky_winner = random.choice(winning_voters)
            item_adj = random.choice(self.ITEM_ADJECTIVES)
            item_noun = random.choice(self.ITEM_NOUNS)
            item_name = f"a {item_adj} {item_noun}"
            
            self.safe_say(f"As a bonus, {lucky_winner} found {item_name}!", room)
            
            winner_id = self.bot.get_user_id(lucky_winner)
            inventories = self.get_state("inventories", {})
            user_inventory = deque(inventories.get(winner_id, []), maxlen=self.MAX_INVENTORY_SIZE)
            user_inventory.append(item_name)
            inventories[winner_id] = list(user_inventory)
            self.set_state("inventories", inventories)
            # No need to call save_state() here, it's called at the end of _close_adventure_round

    def _add_vote(self, username: str, vote_option: int) -> bool:
        current = self.get_state("current")
        if not current: return False
        if time.time() > float(current.get("close_epoch", 0)):
            self._close_adventure_round()
            return True
        votes_1, votes_2 = current.get("votes_1", []), current.get("votes_2", [])
        if username in votes_1: votes_1.remove(username)
        if username in votes_2: votes_2.remove(username)
        (votes_1 if vote_option == 1 else votes_2).append(username)
        current["votes_1"], current["votes_2"] = votes_1, votes_2
        self.set_state("current", current)
        self.save_state()
        return True

