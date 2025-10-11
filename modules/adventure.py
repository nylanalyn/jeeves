# modules/adventure.py
# Enhanced choose-your-own-adventure with dynamic configuration
import random
import re
import time
import schedule
import functools
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from collections import deque
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot):
    return Adventure(bot)

class Adventure(SimpleCommandModule):
    name = "adventure"
    version = "3.0.1" # Added missing is_enabled check
    description = "A choose-your-own-adventure game for the channel."
    
    PLACES = [ "the Neon Bazaar", "the Clockwork Conservatory", "the Signal Archives", "the Subterranean Gardens", "the Rusted Funicular", "the Mirror Maze", "the Lattice Observatory", "the Stormbreak Causeway", "the Midnight Diner", "the Old Museum", "the Lighthouse", "the Planetarium", "the Rooftops", "the Antique Arcade", "the Bookshop Maze", "the Railway Depot", "the Tea Pavilion", "the Neon Alley", "the Forgotten Server Farm", "the Catacomb Switchyard", "the Endless Lobby", "the Glass Cathedral", "the Iron Menagerie", "the Holographic Forest", "the Perpetual Carnival", "the Shattered Aqueduct", "the Gilded Boiler Room", "the Abandoned Data Center", "the Fractured Causeway", "the Vaulted Terminal", "the Hall of Expired Passwords", "the Cryogenic Garden", "the Wax Cylinder Library", "the Vanishing Platform", "the Singing Substation", "the Spiral Archives", "the Candlelit Foundry", "the Flooded Crypt", "the Black Glass Bridge", "the Chimera Menagerie", "the Tarnished Observatory", "the Hollow Clocktower", "the Paper Lantern Pier", "the Last Greenhouse", "the Red Circuit Cathedral", "the Forgotten Monorail", "the Smouldering Atrium", "the Binary Bazaar", ]
    # Story structure: Opening → Development → Climax
    STORY_OPENINGS = [
        "You step into {place}",
        "You cautiously enter {place}",
        "You find yourself in {place}",
        "The door leads you to {place}",
        "You cross the threshold into {place}",
        "Your footsteps echo as you enter {place}",
        "You push open the door to {place}",
        "Against better judgment, you enter {place}",
    ]

    STORY_DEVELOPMENTS = [
        "where the speakers whisper your name in a voice you almost recognize",
        "where every shadow moves independently of its owner",
        "where the walls are covered in photographs of people who haven't been born yet",
        "where clocks tick in reverse and your memories feel borrowed",
        "where the air tastes like copper and forgotten promises",
        "where mirrors show you standing in rooms you've never entered",
        "where the temperature drops ten degrees with each step forward",
        "where static-filled monitors display your own thoughts scrolling past",
        "where the floor is covered in keys that unlock nothing in this world",
        "where paintings on the walls follow you with painted eyes",
        "where the lights flicker in morse code spelling out your deepest secret",
        "where every surface is wet with condensation that smells like fear",
        "where distant music plays a song you heard in a dream last week",
        "where the elevator buttons go to floors that don't exist",
        "where your reflection arrives three seconds before you do",
    ]

    STORY_TRANSITIONS = [
        "As you make your way deeper",
        "Moving further into the space",
        "You press onward and",
        "Taking another step forward",
        "Unable to turn back, you continue and",
        "Something compels you forward, and",
        "Fighting every instinct to flee",
        "Your curiosity pulls you onward, and",
    ]

    STORY_CLIMAXES = [
        "you discover your own jacket hanging on a hook, still warm, though you're wearing it.",
        "a clock strikes thirteen and you realize you've been here before—in a dream you haven't had yet.",
        "you find a door with your name on it. The handwriting is yours, but you don't remember writing it.",
        "you see your own reflection smiling back at you, despite your face showing only terror.",
        "a phone rings. When you answer, you hear your own voice say 'turn around.' No one is there.",
        "you find a photograph of yourself standing in this exact spot, taken yesterday. You've never been here before.",
        "all the lights go out except one, illuminating a chair. Someone was just sitting there.",
        "you hear footsteps approaching that match your own gait perfectly. They stop when you stop.",
        "a note on the table reads 'We've been expecting you' in handwriting identical to your own.",
        "you notice the calendar on the wall. Today's date is circled in red, with one word: 'Finally.'",
        "you see a mannequin wearing clothes identical to yours. It wasn't there a moment ago.",
        "every door you passed now has your childhood bedroom number on it.",
        "you find a guest book. Your signature is on every page, dated years into the future.",
        "the emergency exit sign points directly at a solid wall. The wall feels warm when you touch it.",
        "you discover a recording of your own voice giving a guided tour of this place. You've never recorded anything.",
    ]

    RE_VOTE_1 = re.compile(r"^\s*!?1[.,!\s]*\s*$")
    RE_VOTE_2 = re.compile(r"^\s*!?2[.,!\s]*\s*$")

    def __init__(self, bot):
        super().__init__(bot)
        # These keys contain lists/dicts and are not suitable for simple runtime changes
        self.static_keys = ["item_adjectives", "item_nouns"]
        
        self.set_state("current", self.get_state("current", None))
        self.set_state("history", self.get_state("history", []))
        self.set_state("stats", self.get_state("stats", {"adventures_started": 0, "adventures_completed": 0, "total_votes_cast": 0, "most_popular_location": None}))
        self.set_state("inventories", self.get_state("inventories", {}))
        self.save_state()
        self.MAX_HISTORY_ENTRIES = 50

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
                        schedule.every(remaining_seconds).seconds.do(
                            functools.partial(self._close_adventure_scheduled, room)
                        ).tag(f"{self.name}-close-{room}")

    def on_unload(self):
        super().on_unload()
        current = self.get_state("current")
        if current and (room := current.get("room")):
            schedule.clear(f"{self.name}-close-{room}")

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target):
            return False
            
        current = self.get_state("current")
        if current and current.get("room") == event.target:
            if time.time() > float(current.get("close_epoch", 0)):
                self._close_adventure_round()
                return True
            if self.RE_VOTE_1.match(msg):
                self._add_vote(connection, event, username, 1)
                return True
            if self.RE_VOTE_2.match(msg):
                self._add_vote(connection, event, username, 2)
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
        vote_window = self.get_config_value("vote_window_seconds", room, 75)
        
        self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}; an adventure it is. Shall we set out for 1. {options[0]} or 2. {options[1]}? Say 1 or 2 to vote.")
        
        close_time = time.time() + vote_window
        self.set_state("current", {"room": room, "options": options, "votes_1": [], "votes_2": [], "starter": username, "close_epoch": close_time, "started_at": datetime.now(UTC).isoformat()})
        self._schedule_adventure_close(room, vote_window)
        
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

    def _create_story(self, place: str, room: str) -> str:
        # Create a cohesive narrative: Opening → Development → Transition → Climax
        opening = random.choice(self.STORY_OPENINGS).format(place=place)
        development = random.choice(self.STORY_DEVELOPMENTS)
        transition = random.choice(self.STORY_TRANSITIONS).lower()
        climax = random.choice(self.STORY_CLIMAXES)

        return f"{opening} {development}. {transition.capitalize()} {climax}"

    def _schedule_adventure_close(self, room: str, delay: int) -> None:
        schedule.clear(f"{self.name}-close-{room}")
        schedule.every(delay).seconds.do(
            functools.partial(self._close_adventure_scheduled, room)
        ).tag(f"{self.name}-close-{room}")

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
        story = self._create_story(winner, room)
        self.safe_say(f"Votes tallied: 1. {options[0]} → {c1} vote{'s' if c1 != 1 else ''}; 2. {options[1]} → {c2} vote{'s' if c2 != 1 else ''}.{tie_note}", room)
        self.safe_say(f"To {winner} then. {story}", room)
        
        self._handle_item_discovery(room, winning_voters)

        history = self.get_state("history", [])
        history.append({"when": datetime.now(UTC).isoformat(), "room": room, "options": list(options), "votes_1": votes_1, "votes_2": votes_2, "winner": winner, "starter": current.get("starter"), "vote_counts": [c1, c2]})
        if len(history) > self.MAX_HISTORY_ENTRIES: history = history[-self.MAX_HISTORY_ENTRIES:]
        
        stats = self.get_state("stats")
        stats["adventures_completed"] = stats.get("adventures_completed", 0) + 1
        stats["total_votes_cast"] = stats.get("total_votes_cast", 0) + c1 + c2
        
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
        item_find_chance = self.get_config_value("item_find_chance", room, 0.25)
        item_adjectives = self.get_config_value("item_adjectives", room, ["Unusual"])
        item_nouns = self.get_config_value("item_nouns", room, ["Thing"])

        if not winning_voters or not item_adjectives or not item_nouns:
            return
            
        if random.random() <= item_find_chance:
            lucky_winner = random.choice(winning_voters)
            item_adj = random.choice(item_adjectives)
            item_noun = random.choice(item_nouns)
            item_name = f"a {item_adj} {item_noun}"
            
            self.safe_say(f"As a bonus, {lucky_winner} found {item_name}!", room)
            
            winner_id = self.bot.get_user_id(lucky_winner)
            max_inventory_size = self.get_config_value("max_inventory_size", room, 3)
            inventories = self.get_state("inventories", {})
            user_inventory = deque(inventories.get(winner_id, []), maxlen=max_inventory_size)
            user_inventory.append(item_name)
            inventories[winner_id] = list(user_inventory)
            self.set_state("inventories", inventories)

    def _add_vote(self, connection, event, username: str, vote_option: int) -> bool:
        current = self.get_state("current")
        if not current: return False
        if time.time() > float(current.get("close_epoch", 0)):
            self._close_adventure_round()
            return True
        votes_1, votes_2 = current.get("votes_1", []), current.get("votes_2", [])
        previous_vote = None
        if username in votes_1:
            votes_1.remove(username)
            previous_vote = 1
        if username in votes_2:
            votes_2.remove(username)
            previous_vote = 2 if previous_vote is None else previous_vote

        target_votes = votes_1 if vote_option == 1 else votes_2
        target_votes.append(username)

        current["votes_1"], current["votes_2"] = votes_1, votes_2
        self.set_state("current", current)
        self.save_state()

        if previous_vote == vote_option:
            self.safe_reply(connection, event, f"{username}, your vote for option {vote_option} is already counted.")
        elif previous_vote is None:
            self.safe_reply(connection, event, f"{username}, vote recorded for option {vote_option}.")
        else:
            self.safe_reply(connection, event, f"{username}, vote updated to option {vote_option}.")

        return True
