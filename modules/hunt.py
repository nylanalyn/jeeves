# modules/hunt.py
# A game where users can befriend or capture randomly appearing animals.
import random
import re
import time
import schedule
import sys
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Hunt(bot, config)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "1.4.0"
    description = "A game of befriending or capturing animals."

    SPAWN_ANNOUNCEMENTS = [
        "Good heavens, it appears a creature has wandered into the premises!",
        "I do apologize for the intrusion, but there seems to be a visitor.",
        "Most unusual. An animal has made an appearance.",
        "Pardon me, but it would seem we have an uninvited, four-legged guest.",
        "Attention, please. A wild animal is currently in the vicinity."
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        self._load_config(config)

        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_hunt", self.get_state("active_hunt", None))
        self.save_state()

    def _load_config(self, config: Dict[str, Any]):
        """Loads configuration settings from the config object."""
        self.MIN_HOURS = config.get("min_hours_between_spawns", 1)
        self.MAX_HOURS = config.get("max_hours_between_spawns", 8)
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])
        self.ANIMALS = config.get("animals", [])

    def on_config_reload(self, new_config: Dict[str, Any]):
        """Handle live configuration reloading."""
        old_min = self.MIN_HOURS
        old_max = self.MAX_HOURS

        self._load_config(new_config)

        if (old_min, old_max) != (self.MIN_HOURS, self.MAX_HOURS):
            print(f"[{self.name}] Hunt timing changed, rescheduling spawn timer.", file=sys.stderr)
            schedule.clear("spawn")
            self._schedule_next_spawn()

    def _register_commands(self):
        self.register_command(r"^\s*!hunt\s*$", lambda c, e, m, u, ma: self._cmd_action(c, e, m, u, ma, "hunt"),
                              name="hunt", description="Capture the active animal.")
        self.register_command(r"^\s*!hug\s*$", lambda c, e, m, u, ma: self._cmd_action(c, e, m, u, ma, "hug"),
                              name="hug", description="Befriend the active animal.")
        self.register_command(r"^\s*!hunt\s+score\s*$", self._cmd_score_self,
                              name="hunt score", description="Check your personal hunt/hug score.")
        self.register_command(r"^\s*!hunt\s+top\s*$", self._cmd_top,
                              name="hunt top", description="Show the top 5 most active members.")
        self.register_command(r"^\s*!hunt\s+spawn\s*$", self._cmd_spawn,
                              name="hunt spawn", admin_only=True, description="Force an animal to appear.")

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        if not self.get_state("active_hunt"):
            self._schedule_next_spawn()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_next_spawn(self):
        if not self.ALLOWED_CHANNELS or not self.ANIMALS:
            return
        delay_hours = random.uniform(self.MIN_HOURS, self.MAX_HOURS)
        schedule.every(delay_hours).hours.do(self._spawn_animal).tag(self.name, "spawn")

    def _spawn_animal(self):
        schedule.clear("spawn")
        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
        if not active_channels:
            self._schedule_next_spawn()
            return schedule.CancelJob

        chosen_animal = random.choice(self.ANIMALS)
        for room in active_channels:
            self.safe_say(random.choice(self.SPAWN_ANNOUNCEMENTS), target=room)
            self.safe_say(chosen_animal.get("ascii_art", "An animal appears."), target=room)

        self.set_state("active_hunt", {"animal": chosen_animal, "spawned_at": time.time()})
        self.save_state()
        return schedule.CancelJob

    def _end_hunt(self, connection, event, username: str, action: str):
        current_hunt = self.get_state("active_hunt")
        if not current_hunt: return

        animal = current_hunt["animal"]
        animal_name = animal.get("name", "creature")
        title = self.bot.title_for(username)
        scores = self.get_state("scores", {})
        user_key = username.lower()
        user_scores = scores.get(user_key, {})

        if action == "hug":
            score_key = f"{animal_name}_hugged"
            success_template = animal.get("hug_message", "Very good, {title}. You have hugged the {animal_name}.")
        else: # action == "hunt"
            score_key = f"{animal_name}_hunted"
            success_template = animal.get("hunt_message", "Well done, {title}. The {animal_name} has been secured.")

        user_scores[score_key] = user_scores.get(score_key, 0) + 1
        scores[user_key] = user_scores
        self.set_state("scores", scores)
        self.set_state("active_hunt", None)
        self.save_state()
        
        final_message = success_template.format(title=title, animal_name=animal_name, username=username)
        self.safe_reply(connection, event, final_message)
        self._schedule_next_spawn()

    def _cmd_action(self, connection, event, msg, username, match, action: str):
        active_hunt = self.get_state("active_hunt")
        if not active_hunt:
            self.safe_reply(connection, event, f"There is nothing to {action}, {self.bot.title_for(username)}.")
            return True
        self._end_hunt(connection, event, username, action)
        return True

    def _cmd_score_self(self, connection, event, msg, username, match):
        user_key = username.lower()
        user_scores = self.get_state("scores", {}).get(user_key, {})
        if not user_scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not yet interacted with any animals.")
            return True
        
        parts = []
        for key, count in sorted(user_scores.items()):
            animal, action = key.split('_')
            parts.append(f"{animal.capitalize()} {action}: {count}")
        
        score_str = ", ".join(parts)
        self.safe_reply(connection, event, f"Score for {self.bot.title_for(username)}: {score_str}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        all_scores = self.get_state("scores", {})
        if not all_scores:
            self.safe_reply(connection, event, "No one has yet interacted with the local fauna.")
            return True
        
        leaderboard = []
        for nick, scores in all_scores.items():
            total_hugs = sum(v for k, v in scores.items() if k.endswith("_hugged"))
            total_hunts = sum(v for k, v in scores.items() if k.endswith("_hunted"))
            total_score = total_hugs + total_hunts
            if total_score > 0:
                leaderboard.append((nick, total_score, total_hugs, total_hunts))

        sorted_board = sorted(leaderboard, key=lambda item: item[1], reverse=True)[:5]
        
        response_parts = [f"{nick} ({score}: {hugs} hugs, {hunts} hunts)" for nick, score, hugs, hunts in sorted_board]
        response = "Top 5 most active members: " + ", ".join(response_parts)
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_hunt"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        self._spawn_animal()
        self.safe_reply(connection, event, "As you wish. I have released an animal.")
        return True

