# modules/hunt.py
# A game where users can hunt or hug animals that appear in the channel.
import random
import re
import schedule
import time
from datetime import datetime, timezone, timedelta
from .base import SimpleCommandModule

UTC = timezone.utc

def setup(bot, config):
    return Hunt(bot, config)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "1.3.2"
    description = "A game of hunting or hugging randomly appearing animals."

    SPAWN_ANNOUNCEMENTS = [
        "Good heavens, it appears a creature has wandered into the premises!",
        "I do apologize for the intrusion, but an animal has made its way inside.",
        "Pardon me, but it seems we have a small, uninvited guest.",
        "Attention, please. A wild animal has been spotted in the vicinity."
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        self._is_loaded = False
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_animal", self.get_state("active_animal", None))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None))
        self.on_config_reload(config)

    def on_config_reload(self, config):
        self.MIN_HOURS = config.get("min_hours_between_spawns", 2)
        self.MAX_HOURS = config.get("max_hours_between_spawns", 10)
        self.ANIMALS = config.get("animals", [])
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])

        # If config changes, reschedule if necessary
        if self._is_loaded:
             self._schedule_next_spawn()

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        next_spawn_str = self.get_state("next_spawn_time")
        if next_spawn_str:
            next_spawn_time = datetime.fromisoformat(next_spawn_str)
            now = datetime.now(UTC)
            if now >= next_spawn_time:
                self._spawn_animal()
            else:
                remaining_seconds = (next_spawn_time - now).total_seconds()
                schedule.every(remaining_seconds).seconds.do(self._spawn_animal).tag(self.name, "spawn")
        else:
            self._schedule_next_spawn()
        self._is_loaded = True

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _register_commands(self):
        self.register_command(r"^\s*!hug\s*$", self._cmd_hug, name="hug", description="Befriend the animal.")
        self.register_command(r"^\s*!hunt\s*$", self._cmd_hunt, name="hunt", description="Capture the animal.")
        self.register_command(r"^\s*!hunt\s+score\s*$", self._cmd_score, name="hunt score", description="Check your hunt/hug score.")
        self.register_command(r"^\s*!hunt\s+top\s*$", self._cmd_top, name="hunt top", description="Show the top 5 most active members.")
        self.register_command(r"^\s*!hunt\s+spawn\s*$", self._cmd_spawn, name="hunt spawn", admin_only=True, description="Force an animal to spawn.")

    def _schedule_next_spawn(self):
        schedule.clear(self.name)
        if not self.ALLOWED_CHANNELS or not self.ANIMALS:
            return

        delay_hours = random.uniform(self.MIN_HOURS, self.MAX_HOURS)
        next_spawn_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        self.set_state("next_spawn_time", next_spawn_time.isoformat())
        self.save_state()
        
        schedule.every(delay_hours * 3600).seconds.do(self._spawn_animal).tag(self.name, "spawn")

    def _spawn_animal(self):
        schedule.clear("spawn")
        if not self.ANIMALS:
            self._schedule_next_spawn()
            return schedule.CancelJob

        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
        if not active_channels:
            self._schedule_next_spawn()
            return schedule.CancelJob

        animal = random.choice(self.ANIMALS)
        self.set_state("active_animal", animal)
        self.save_state()

        announcement = random.choice(self.SPAWN_ANNOUNCEMENTS)
        for room in active_channels:
            self.safe_say(announcement, target=room)
            self.safe_say(animal.get("ascii_art", "An animal appears."), target=room)

        return schedule.CancelJob

    def _end_hunt(self, connection, event, username, action):
        active_animal = self.get_state("active_animal")
        if not active_animal:
            return

        animal_name = active_animal.get("name", "animal").lower()
        scores = self.get_state("scores", {})
        user_key = username.lower()
        user_scores = scores.get(user_key, {})
        
        score_key = f"{animal_name}_{action}"
        user_scores[score_key] = user_scores.get(score_key, 0) + 1
        scores[user_key] = user_scores
        
        self.set_state("scores", scores)
        self.set_state("active_animal", None)
        self.save_state()

        # Custom message logic
        msg_key = "hug_message" if action == "hugged" else "hunt_message"
        custom_msg = active_animal.get(msg_key)
        if custom_msg:
             self.safe_reply(connection, event, custom_msg.format(username=username))
        else: # Fallback
            title = self.bot.title_for(username)
            self.safe_reply(connection, event, f"Very good, {title}. You have {action} the {animal_name}.")

        self._schedule_next_spawn()
        return True

    def _cmd_hug(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return True
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hugged")
        return True

    def _cmd_hunt(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return True
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hunted")
        return True

    def _cmd_score(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return True
        scores = self.get_state("scores", {}).get(username.lower(), {})
        if not scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not yet interacted with any animals.")
            return True
        
        parts = []
        for key, count in sorted(scores.items()):
            animal, action = key.replace('_', ' ').rsplit(' ', 1)
            parts.append(f"{animal.capitalize()} {action}: {count}")

        self.safe_reply(connection, event, f"Score for {self.bot.title_for(username)}: {', '.join(parts)}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return True
        all_scores = self.get_state("scores", {})
        if not all_scores:
            self.safe_reply(connection, event, "No scores have been recorded yet.")
            return True

        leaderboard = {}
        for user, scores in all_scores.items():
            leaderboard[user] = sum(scores.values())

        sorted_top = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)[:5]
        
        top_list = []
        for i, (user, total_score) in enumerate(sorted_top):
             user_scores = all_scores.get(user, {})
             hugs = sum(v for k, v in user_scores.items() if k.endswith("_hugged"))
             hunts = sum(v for k, v in user_scores.items() if k.endswith("_hunted"))
             top_list.append(f"{i+1}. {user} ({total_score}: {hugs} hugs, {hunts} hunts)")

        self.safe_reply(connection, event, f"Top 5 most active members: {'; '.join(top_list)}")
        return True

    def _cmd_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        
        self._spawn_animal()
        self.safe_reply(connection, event, "As you wish. I have released an animal.")
        return True

