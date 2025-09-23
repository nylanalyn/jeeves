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
    version = "2.0.0" # UUID Refactor
    description = "A game of hunting or hugging randomly appearing animals."

    SPAWN_ANNOUNCEMENTS = [
        "Good heavens, it appears a creature has wandered into the premises!",
        "I do apologize for the intrusion, but an animal has made its way inside.",
        "Pardon me, but it seems we have a small, uninvited guest.",
        "Attention, please. A wild animal has been spotted in the vicinity."
    ]
    RELEASE_MESSAGES = [
        "Very well, {title}. I shall open the doors. Do try to be more decisive in the future.",
        "As you wish, {title}. The {animal_name} has been... liberated. I shall fetch a dustpan.",
        "If you insist, {title}. The {animal_name} is now free to roam the premises. Again.",
        "Releasing the {animal_name}, {title}. I trust this chaotic cycle will not become a habit."
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        self._is_loaded = False
        self.set_state("scores", self.get_state("scores", {})) # Keyed by user_id
        self.set_state("active_animal", self.get_state("active_animal", None))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None))
        self.set_state("event", self.get_state("event", None))
        self.on_config_reload(config)

    def on_config_reload(self, config):
        hunt_config = config.get(self.name, config)
        self.MIN_HOURS = hunt_config.get("min_hours_between_spawns", 2)
        self.MAX_HOURS = hunt_config.get("max_hours_between_spawns", 10)
        self.ANIMALS = hunt_config.get("animals", [])
        self.ALLOWED_CHANNELS = hunt_config.get("allowed_channels", [])
        event_settings = hunt_config.get("event_settings", {})
        self.EVENT_ESCAPE_CHANCE = event_settings.get("escape_chance", 0.1)
        self.EVENT_MIN_DELAY_MINS = event_settings.get("min_flock_delay_minutes", 2)
        self.EVENT_MAX_DELAY_MINS = event_settings.get("max_flock_delay_minutes", 60)
        if self._is_loaded:
             self._schedule_next_spawn()

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        
        event = self.get_state("event")
        if event and event.get("active"):
            next_event_spawn_str = event.get("next_spawn_time")
            if next_event_spawn_str:
                next_spawn_time = datetime.fromisoformat(next_event_spawn_str)
                now = datetime.now(UTC)
                if now >= next_spawn_time:
                    self._start_event_spawn()
                else:
                    remaining = (next_spawn_time - now).total_seconds()
                    if remaining > 0:
                        schedule.every(remaining).seconds.do(self._start_event_spawn).tag(self.name, "event_spawn")
            else:
                 self._start_event_spawn()
            self._is_loaded = True
            return

        next_spawn_str = self.get_state("next_spawn_time")
        if next_spawn_str:
            next_spawn_time = datetime.fromisoformat(next_spawn_str)
            now = datetime.now(UTC)
            if now >= next_spawn_time:
                self._spawn_animal()
            else:
                remaining_seconds = (next_spawn_time - now).total_seconds()
                if remaining_seconds > 0:
                    schedule.every(remaining_seconds).seconds.do(self._spawn_animal).tag(self.name, "spawn")
        elif not self.get_state("active_animal"):
            self._schedule_next_spawn()
        self._is_loaded = True

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _register_commands(self):
        self.register_command(r"^\s*!hug\s*$", self._cmd_hug, name="hug", description="Befriend the animal.")
        self.register_command(r"^\s*!hunt\s*$", self._cmd_hunt, name="hunt", description="Capture the animal.")
        self.register_command(r"^\s*!release\s+(hug|hunt)\s*$", self._cmd_release, name="release", description="Release a previously caught or befriended animal.")
        self.register_command(r"^\s*!hunt\s+score(?:\s+(\S+))?\s*$", self._cmd_score, name="hunt score", description="Check your or another user's hunt/hug score.")
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

    def _schedule_next_event_spawn(self):
        schedule.clear(self.name)
        event = self.get_state("event")
        if not (event and event.get("active") and event.get("flocks")):
            self.safe_say("The last flock has been accounted for. The Great Duck Migration has concluded!")
            self.set_state("event", None)
            self.save_state()
            self._schedule_next_spawn()
            return
        if random.random() < self.EVENT_ESCAPE_CHANCE:
            escaped_flock_size = event["flocks"].pop(0)
            self.set_state("event", event)
            self.save_state()
            self.safe_say(f"Oh dear, it seems a flock of {escaped_flock_size} ducks has flown the coop!")
            self._schedule_next_event_spawn()
            return
        delay_seconds = random.randint(self.EVENT_MIN_DELAY_MINS * 60, self.EVENT_MAX_DELAY_MINS * 60)
        next_spawn_time = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        event["next_spawn_time"] = next_spawn_time.isoformat()
        self.set_state("event", event)
        self.save_state()
        schedule.every(delay_seconds).seconds.do(self._start_event_spawn).tag(self.name, "event_spawn")

    def _start_event_spawn(self):
        schedule.clear(self.name)
        event = self.get_state("event")
        if not (event and event.get("active") and event.get("flocks")):
            self._schedule_next_spawn()
            return schedule.CancelJob
        animal_name = event.get("animal_name")
        animal_to_spawn = next((animal for animal in self.ANIMALS if animal.get("name", "").lower() == animal_name), None)
        if not animal_to_spawn:
            self.set_state("event", None)
            self._schedule_next_spawn()
            return schedule.CancelJob
        current_flock_size = event["flocks"][0]
        animal_to_spawn["flock_size"] = current_flock_size
        self.set_state("active_animal", animal_to_spawn)
        self.save_state()
        active_channels = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]
        for room in active_channels:
             self.safe_say(f"A flock of {current_flock_size} ducks from {event['name']} appears! ({len(event['flocks'])} flocks remaining)", target=room)
             self.safe_say(animal_to_spawn.get("ascii_art", "An animal appears."), target=room)
        return schedule.CancelJob

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
        event_state = self.get_state("event")
        if not active_animal:
            return
        is_event_catch = event_state and event_state.get("active") and event_state.get("animal_name") == active_animal.get("name", "").lower()
        score_to_add = active_animal.get("flock_size", 1) if is_event_catch else 1
        animal_name = active_animal.get("name", "animal").lower()
        user_id = self.bot.get_user_id(username)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        score_key = f"{animal_name}_{action}"
        user_scores[score_key] = user_scores.get(score_key, 0) + score_to_add
        scores[user_id] = user_scores
        self.set_state("scores", scores)
        self.set_state("active_animal", None)
        self.save_state()
        if is_event_catch:
            self.safe_reply(connection, event, f"Excellent work, {self.bot.title_for(username)}! You have {action} a flock of {score_to_add} ducks!")
            event_state["flocks"].pop(0)
            event_state.pop("next_spawn_time", None)
            self.set_state("event", event_state)
            self.save_state()
            self._schedule_next_event_spawn()
        else:
            msg_key = "hug_message" if action == "hugged" else "hunt_message"
            custom_msg = active_animal.get(msg_key)
            if custom_msg:
                self.safe_reply(connection, event, custom_msg.format(username=self.bot.title_for(username)))
            else:
                title = self.bot.title_for(username)
                self.safe_reply(connection, event, f"Very good, {title}. You have {action} the {animal_name}.")
            self._schedule_next_spawn()
        return True

    def _cmd_hug(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS: return True
        if self.get_state("active_animal"): return self._end_hunt(connection, event, username, "hugged")
        return True

    def _cmd_hunt(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS: return True
        if self.get_state("active_animal"): return self._end_hunt(connection, event, username, "hunted")
        return True

    def _cmd_release(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS: return True
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, f"I must insist we deal with the current creature first, {self.bot.title_for(username)}.")
            return True
        action_type = match.group(1)
        score_suffix = "_hugged" if action_type == "hug" else "_hunted"
        user_id = self.bot.get_user_id(username)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        releasable_animals = [k for k, v in user_scores.items() if k.endswith(score_suffix) and v > 0]
        if not releasable_animals:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but you have no {action_type}ed animals to release.")
            return True
        animal_to_release_key = random.choice(releasable_animals)
        animal_name_lower = animal_to_release_key.replace(score_suffix, "")
        user_scores[animal_to_release_key] -= 1
        if user_scores[animal_to_release_key] == 0:
            del user_scores[animal_to_release_key]
        scores[user_id] = user_scores
        animal_data_to_spawn = next((a for a in self.ANIMALS if a.get("name", "").lower() == animal_name_lower), None)
        self.set_state("scores", scores)
        if animal_data_to_spawn:
            self.set_state("active_animal", animal_data_to_spawn)
        self.save_state()
        response_template = random.choice(self.RELEASE_MESSAGES)
        response = response_template.format(title=self.bot.title_for(username), animal_name=animal_name_lower.capitalize())
        self.safe_reply(connection, event, response)
        if animal_data_to_spawn:
            self.safe_say(animal_data_to_spawn.get("ascii_art", f"A {animal_name_lower} is now loose!"), target=event.target)
        else:
            self.safe_reply(connection, event, f"It seems the {animal_name_lower.capitalize()} has vanished entirely.")
        return True

    def _cmd_score(self, connection, event, msg, username, match):
        target_user_nick = match.group(1) or username
        user_id = self.bot.get_user_id(target_user_nick)
        
        scores = self.get_state("scores", {}).get(user_id, {})
        if not scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} has not yet interacted with any animals.")
            return True
        
        parts = []
        for key, count in sorted(scores.items()):
            animal, action = key.replace('_', ' ').rsplit(' ', 1)
            parts.append(f"{animal.capitalize()} {action}: {count}")

        self.safe_reply(connection, event, f"Score for {self.bot.title_for(target_user_nick)}: {', '.join(parts)}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        all_scores = self.get_state("scores", {})
        if not all_scores:
            self.safe_reply(connection, event, "No scores have been recorded yet.")
            return True
            
        user_module_state = self.bot.get_module_state("users")
        user_map = user_module_state.get("user_map", {})
        
        leaderboard = {user_id: sum(scores.values()) for user_id, scores in all_scores.items()}
        sorted_top_ids = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)[:5]
        
        top_list = []
        for i, (user_id, total_score) in enumerate(sorted_top_ids):
             user_scores = all_scores.get(user_id, {})
             user_profile = user_map.get(user_id)
             display_nick = user_profile.get("canonical_nick", "Unknown User") if user_profile else "Unknown User"
             
             hugs = sum(v for k, v in user_scores.items() if k.endswith("_hugged"))
             hunts = sum(v for k, v in user_scores.items() if k.endswith("_hunted"))
             top_list.append(f"{i+1}. {display_nick} ({total_score}: {hugs} hugs, {hunts} hunts)")

        self.safe_reply(connection, event, f"Top 5 most active members: {'; '.join(top_list)}")
        return True

    def _cmd_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        self._spawn_animal()
        self.safe_reply(connection, event, "As you wish. I have released an animal.")
        return True

