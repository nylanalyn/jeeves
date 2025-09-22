# modules/hunt.py
# A persistent, config-driven animal hunting game for IRC.
import random
import re
import schedule
import sys
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Hunt(bot, config)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "1.2.0"
    description = "A game where users can hunt or hug animals that appear in the channel."

    # Default messages if not provided in config
    ANNOUNCEMENTS = [
        "Good heavens, it appears a creature has wandered into the premises!",
        "I do apologize for the intrusion, but an uninvited guest has appeared.",
        "Pardon me, but there seems to be a small animal in the room.",
        "Most unusual. A creature has made its presence known."
    ]
    HUG_SUCCESS_MESSAGES = [
        "Very good, {title}. You have hugged the {animal_name}.",
        "Excellent, {title}. The {animal_name} seems to appreciate the gesture.",
        "Splendid, {title}. You've made a new friend in the {animal_name}."
    ]
    HUNT_SUCCESS_MESSAGES = [
        "Well done, {title}. The {animal_name} has been secured.",
        "A successful capture, {title}. The grounds are safe once more.",
        "Impressive work, {title}. The {animal_name} is contained."
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        self.on_config_reload(config)
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_animal", self.get_state("active_animal", None))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None)) # For persistence
        self.save_state()

    def on_config_reload(self, config):
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])
        self.MIN_HOURS = config.get("hours_between_spawns", {}).get("min", 1)
        self.MAX_HOURS = config.get("hours_between_spawns", {}).get("max", 8)
        self.ANIMALS = config.get("animals", [])

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        
        next_spawn_str = self.get_state("next_spawn_time")
        if next_spawn_str:
            next_spawn_time = datetime.fromisoformat(next_spawn_str)
            now = datetime.now(UTC)
            
            if now >= next_spawn_time:
                # Time has passed, spawn immediately
                self._spawn_animal()
            else:
                # Time is in the future, schedule for the remainder
                remaining_seconds = (next_spawn_time - now).total_seconds()
                schedule.every(remaining_seconds).seconds.do(self._spawn_animal).tag(self.name, "spawn")
        elif not self.get_state("active_animal"):
             # No scheduled spawn and no active animal, so schedule a new one
            self._schedule_next_spawn()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)
        
    def _register_commands(self):
        self.register_command(r"^\s*!hunt\s*$", self._cmd_hunt, name="hunt", description="Capture the active animal.")
        self.register_command(r"^\s*!hug\s*$", self._cmd_hug, name="hug", description="Befriend the active animal.")
        self.register_command(r"^\s*!hunt\s+score\s*$", self._cmd_score, name="hunt score", description="Check your personal hunt/hug score.")
        self.register_command(r"^\s*!hunt\s+top\s*$", self._cmd_top, name="hunt top", description="Show the top 5 most active members.")
        self.register_command(r"^\s*!hunt\s+spawn\s*$", self._cmd_spawn, name="hunt spawn", admin_only=True, description="Force an animal to spawn.")

    def _schedule_next_spawn(self):
        if not self.ALLOWED_CHANNELS or not self.ANIMALS:
            return

        delay_hours = random.uniform(self.MIN_HOURS, self.MAX_HOURS)
        next_spawn_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        
        self.set_state("next_spawn_time", next_spawn_time.isoformat())
        self.save_state()

        schedule.every(delay_hours).hours.do(self._spawn_animal).tag(self.name, "spawn")

    def _spawn_animal(self):
        schedule.clear("spawn")
        
        animal_config = random.choice(self.ANIMALS)
        animal_name = animal_config.get("name", "creature")
        ascii_art = animal_config.get("ascii_art", "An animal appears.")
        
        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
        if not active_channels:
            self._schedule_next_spawn()
            return schedule.CancelJob

        announcement = random.choice(self.ANNOUNCEMENTS)
        for room in active_channels:
            self.safe_say(announcement, target=room)
            self.safe_say(ascii_art, target=room)
        
        self.set_state("active_animal", {"name": animal_name, "config": animal_config})
        self.set_state("next_spawn_time", None) # Clear scheduled time
        self.save_state()
        return schedule.CancelJob

    def _end_hunt(self, connection, event, username, action):
        active_animal = self.get_state("active_animal")
        if not active_animal:
            self.safe_reply(connection, event, "There are no creatures to be found at the moment.")
            return True

        animal_name = active_animal["name"]
        animal_config = active_animal["config"]
        
        # Determine success message
        if action == "hugged":
            msg_template = animal_config.get("hug_message") or random.choice(self.HUG_SUCCESS_MESSAGES)
        else: # hunted
            msg_template = animal_config.get("hunt_message") or random.choice(self.HUNT_SUCCESS_MESSAGES)
            
        response = msg_template.format(username=username, title=self.bot.title_for(username), animal_name=animal_name)
        self.safe_reply(connection, event, response)
        
        # Update score
        scores = self.get_state("scores", {})
        user_key = username.lower()
        scores.setdefault(user_key, {})
        score_key = f"{animal_name}_{action}"
        scores[user_key][score_key] = scores[user_key].get(score_key, 0) + 1
        
        self.set_state("scores", scores)
        self.set_state("active_animal", None)
        self.save_state()
        
        self._schedule_next_spawn()
        return True

    def _cmd_hunt(self, connection, event, msg, username, match):
        return self._end_hunt(connection, event, username, "hunted")

    def _cmd_hug(self, connection, event, msg, username, match):
        return self._end_hunt(connection, event, username, "hugged")

    def _cmd_score(self, connection, event, msg, username, match):
        scores = self.get_state("scores", {}).get(username.lower(), {})
        if not scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not yet interacted with any creatures.")
            return True
        
        parts = []
        for key, count in scores.items():
            animal, action = key.replace('_', ' ').rsplit(' ', 1)
            parts.append(f"{animal.capitalize()} {action}: {count}")
        
        response = f"Score for {self.bot.title_for(username)}: {', '.join(parts)}."
        self.safe_reply(connection, event, response)
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        scores = self.get_state("scores", {})
        if not scores:
            self.safe_reply(connection, event, "No one has yet tended to the grounds.")
            return True

        leaderboard = {}
        for user, user_scores in scores.items():
            total_hugs = sum(v for k, v in user_scores.items() if k.endswith("_hugged"))
            total_hunts = sum(v for k, v in user_scores.items() if k.endswith("_hunted"))
            leaderboard[user] = {"total": total_hugs + total_hunts, "hugs": total_hugs, "hunts": total_hunts}
        
        sorted_top = sorted(leaderboard.items(), key=lambda item: item[1]["total"], reverse=True)[:5]
        
        parts = []
        for user, data in sorted_top:
            parts.append(f"{user} ({data['total']}: {data['hugs']} hugs, {data['hunts']} hunts)")
            
        response = f"Top 5 most active members: {', '.join(parts)}."
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        
        schedule.clear("spawn")
        self._spawn_animal()
        self.safe_reply(connection, event, "As you wish. I have released an animal.")
        return True

