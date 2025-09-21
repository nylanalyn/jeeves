# modules/hunt.py
# A configurable animal hunting game for IRC.
import random
import re
import schedule
import time
from datetime import datetime
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Hunt(bot, config)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "1.2.1"
    description = "A game where users can hunt or hug animals that randomly appear."

    ANNOUNCEMENTS = [
        "Good heavens! It appears a creature has found its way into the premises.",
        "My apologies for the intrusion, but there seems to be a small visitor.",
        "Pardon me, but it would seem we have an uninvited, four-legged guest.",
        "I do beg your pardon, but a bit of wildlife has wandered in.",
        "Well, this is unexpected. A small animal has appeared."
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        # Load all configuration settings with sane defaults
        self.MIN_HOURS = config.get("min_hours_between_spawns", 1)
        self.MAX_HOURS = config.get("max_hours_between_spawns", 6)
        self.ANIMALS = config.get("animals", [])
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])

        # Initialize the module's state
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_hunt", self.get_state("active_hunt", None))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!hunt\s*$", self._cmd_hunt, name="hunt", description="Capture the animal that has appeared.")
        self.register_command(r"^\s*!hug\s*$", self._cmd_hug, name="hug", description="Befriend the animal that has appeared.")
        self.register_command(r"^\s*!hunt\s+score\s*$", self._cmd_score, name="hunt score", description="Check your personal hunting and hugging scores.")
        self.register_command(r"^\s*!hunt\s+top\s*$", self._cmd_top, name="hunt top", description="Show the top hunters and huggers.")
        self.register_command(r"^\s*!hunt\s+spawn\s*$", self._cmd_spawn, name="hunt spawn", admin_only=True, description="Force an animal to appear.")

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        # If the bot restarts with an active hunt, we let it persist.
        self._schedule_next_spawn()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_next_spawn(self):
        # Prevent scheduling a new spawn if one is already active
        if self.get_state("active_hunt"):
            return
            
        if not self.ANIMALS or not self.ALLOWED_CHANNELS:
            self._record_error("No animals or allowed_channels configured. The game will not run.")
            return

        delay_hours = random.uniform(self.MIN_HOURS, self.MAX_HOURS)
        schedule.every(delay_hours).hours.do(self._spawn_animal).tag(self.name, "spawn")

    def _spawn_animal(self):
        schedule.clear("spawn") # This job runs only once
        
        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
        if not active_channels:
            self._record_error("Scheduled to spawn, but bot is not in any allowed channels.")
            self._schedule_next_spawn()
            return schedule.CancelJob

        animal = random.choice(self.ANIMALS)
        announcement = random.choice(self.ANNOUNCEMENTS)

        for room in active_channels:
            self.safe_say(announcement, target=room)
            self.safe_say(animal.get("art", "An animal appears!"), target=room)
        
        self.set_state("active_hunt", {"animal": animal, "spawn_time": time.time()})
        self.save_state()
        
        return schedule.CancelJob

    def _end_hunt(self, winner, action):
        active_hunt = self.get_state("active_hunt")
        if not active_hunt:
            return

        animal = active_hunt["animal"]
        animal_name = animal.get("name", "animal")
        
        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]

        # A user won, so we record the score
        scores = self.get_state("scores", {})
        user_key = winner.lower()
        user_scores = scores.get(user_key, {})
        
        # BUG FIX: Changed from "{action}d" to "{action}ed" to create correct keys like "hugged" and "hunted"
        score_key = f"{animal_name}_{action}ed"
        user_scores[score_key] = user_scores.get(score_key, 0) + 1
        scores[user_key] = user_scores
        self.set_state("scores", scores)

        # Get the appropriate success message from the config
        message_template = animal.get(f"{action}_message", "{username} interacted with the animal.")
        message = message_template.format(username=winner)
        for room in active_channels:
            self.safe_say(message, target=room)

        # Clear the active hunt and schedule the next one
        self.set_state("active_hunt", None)
        self.save_state()
        self._schedule_next_spawn()
        return

    def _handle_action(self, connection, event, username, action):
        active_hunt = self.get_state("active_hunt")
        if not active_hunt:
            self.safe_reply(connection, event, f"There is nothing to {action}, {self.bot.title_for(username)}.")
            return True
        
        # User was successful, end the hunt with a winner
        self._end_hunt(winner=username, action=action)
        return True

    def _cmd_hunt(self, connection, event, msg, username, match):
        return self._handle_action(connection, event, username, "hunt")

    def _cmd_hug(self, connection, event, msg, username, match):
        return self._handle_action(connection, event, username, "hug")

    def _cmd_score(self, connection, event, msg, username, match):
        user_scores = self.get_state("scores", {}).get(username.lower(), {})
        if not user_scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not yet interacted with any animals.")
            return True
        
        parts = []
        for key, value in sorted(user_scores.items()):
            animal, action = key.split("_")
            formatted_key = f"{animal.capitalize()}s {action}"
            parts.append(f"{formatted_key}: {value}")
        
        score_str = ", ".join(parts)
        self.safe_reply(connection, event, f"Score for {self.bot.title_for(username)}: {score_str}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        scores = self.get_state("scores", {})
        if not scores:
            self.safe_reply(connection, event, "No scores have been recorded yet.")
            return True

        # Calculate total hunts and hugs for sorting
        totals = {}
        for user, user_scores in scores.items():
            total_hugs = sum(v for k, v in user_scores.items() if k.endswith("_hugged"))
            total_hunts = sum(v for k, v in user_scores.items() if k.endswith("_hunted"))
            totals[user] = {"hugs": total_hugs, "hunts": total_hunts, "total": total_hugs + total_hunts}

        sorted_users = sorted(totals.items(), key=lambda item: item[1]["total"], reverse=True)[:5]
        
        response = "Top 5 most active members: "
        parts = [f"{user} ({data['total']}: {data['hugs']} hugs, {data['hunts']} hunts)" for user, data in sorted_users]
        response += ", ".join(parts)
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_hunt"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        
        schedule.clear("spawn") # Cancel any pending scheduled spawn
        self._spawn_animal()
        self.safe_reply(connection, event, "As you wish. An animal has been summoned.")
        return True

