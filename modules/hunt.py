# modules/hunt.py
# A game where users can hunt or hug animals that appear in the channel.
import random
import re
import schedule
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Hunt(bot, config)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "1.8.0" # Refactored to a single robust command handler
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
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_animal", self.get_state("active_animal", None))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None))
        self.set_state("event", self.get_state("event", None))
        self.on_config_reload(config)

    def on_config_reload(self, config):
        self.MIN_HOURS = config.get("min_hours_between_spawns", 2)
        self.MAX_HOURS = config.get("max_hours_between_spawns", 10)
        self.ANIMALS = config.get("animals", [])
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])
        
        event_settings = config.get("event_settings", {})
        self.EVENT_ESCAPE_CHANCE = event_settings.get("escape_chance", 0.1)
        self.EVENT_MIN_DELAY_MINS = event_settings.get("min_flock_delay_minutes", 2)
        self.EVENT_MAX_DELAY_MINS = event_settings.get("max_flock_delay_minutes", 60)
        self.EVENT_MIN_FLOCK_SIZE = event_settings.get("min_flock_size", 20)
        self.EVENT_MAX_FLOCK_SIZE = event_settings.get("max_flock_size", 50)
        
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
        # Register non-hunt commands
        self.register_command(r"^\s*!hug(?:\s+(.+))?\s*$", self._cmd_hug, name="hug", description="Befriend the animal.")
        self.register_command(r"^\s*!release\s+(hug|hunt)\s*$", self._cmd_release, name="release", description="Release a previously caught or befriended animal.")
        
        # Register a single, master command for all !hunt variations
        self.register_command(r"^\s*!hunt(?:\s+(.*))?$", self._cmd_hunt_master, name="hunt", description="The main command for the hunt game. Use '!hunt help' for subcommands.")

    # --- Master Command Handler ---

    def _cmd_hunt_master(self, connection, event, msg, username, match):
        """The single entry point for all '!hunt' commands."""
        args_str = (match.group(1) or "").strip()
        
        # Bare '!hunt' command
        if not args_str:
            return self._handle_hunt_animal(connection, event, username)

        args = args_str.split()
        subcommand = args[0].lower()

        # Route to the correct handler based on the subcommand
        if subcommand == "score":
            return self._handle_score(connection, event, username, args[1:])
        elif subcommand == "top":
            return self._handle_top(connection, event, username)
        elif subcommand == "admin":
            return self._handle_admin(connection, event, username, args[1:])
        elif subcommand == "spawn": # Admin alias
            return self._handle_admin_spawn(connection, event, username)
        elif subcommand == "help":
            return self._handle_help(connection, event, username)
        else:
            # Assumes '!hunt <target>' for hunting another user
            return self._handle_hunt_guest(connection, event, username, args_str)

    # --- Subcommand Handlers ---

    def _handle_hunt_animal(self, connection, event, username):
        """Logic for a bare `!hunt` command to hunt a spawned animal."""
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            self.safe_reply(connection, event, "My apologies, but the hunt is not active in this channel.")
            return True
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hunted")
        self.safe_reply(connection, event, f"There is nothing to hunt at the moment, {self.bot.title_for(username)}.")
        return True
    
    def _handle_hunt_guest(self, connection, event, username, target_name):
        """Logic for `!hunt <user>`."""
        title = self.bot.title_for(username)
        self.safe_reply(connection, event, f"I must strongly object, {title}. Hunting the guests is strictly against household policy.")
        return True

    def _handle_score(self, connection, event, username, args):
        """Logic for `!hunt score [user]`."""
        target_user_nick = args[0] if args else username
        self._cmd_score(connection, event, "", username, target_user_nick)
        return True

    def _handle_top(self, connection, event, username):
        """Logic for `!hunt top`."""
        self._cmd_top(connection, event, "", username, None)
        return True

    def _handle_admin(self, connection, event, username, args):
        """Router for `!hunt admin ...` commands."""
        if not self.bot.is_admin(event.source):
            return True # Silently ignore for non-admins

        if not args:
            self.safe_reply(connection, event, "Please specify an admin command. Use `!hunt help` for options.")
            return True

        admin_subcommand = args[0].lower()
        
        if admin_subcommand == "spawn":
            return self._handle_admin_spawn(connection, event, username)
        elif admin_subcommand == "add":
            if len(args) != 5:
                self.safe_reply(connection, event, "Usage: !hunt admin add <user> <animal> <hunted|hugged> <amount>")
                return True
            return self._cmd_admin_add(connection, event, "", username, args[1:])
        elif admin_subcommand == "fixscores":
            return self._cmd_admin_fixscores(connection, event, "", username, None)
        elif admin_subcommand == "event":
            if len(args) != 4:
                self.safe_reply(connection, event, "Usage: !hunt admin event <user> <animal> <hunted|hugged>")
                return True
            return self._cmd_admin_event(connection, event, "", username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown admin command '{admin_subcommand}'.")
            return True

    def _handle_admin_spawn(self, connection, event, username):
        """Wrapper for the admin spawn logic to ensure admin rights."""
        if not self.bot.is_admin(event.source):
            return True # Silently ignore
        return self._cmd_admin_spawn(connection, event, "", username, None)

    def _handle_help(self, connection, event, username):
        """Displays hunt-specific help."""
        help_lines = [
            "!hunt - Hunt the currently active animal.",
            "!hug - Befriend the currently active animal.",
            "!release <hunt|hug> - Release one of your captured animals back into the wild.",
            "!hunt score [user] - Check your score, or another user's.",
            "!hunt top - Show the leaderboard.",
            "!hunt help - Show this message."
        ]
        if self.bot.is_admin(event.source):
            help_lines.extend([
                "Admin:",
                "!hunt spawn - Force an animal to appear.",
                "!hunt admin add <user> <animal> <hunted|hugged> <amount> - Add to a user's score.",
                "!hunt admin event <user> <animal> <hunted|hugged> - Start a migration event with a user's animals."
            ])
        
        self.safe_reply(connection, event, f"--- {self.name.capitalize()} Commands ---")
        for line in help_lines:
            self.safe_privmsg(username, line)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you the details privately.")
        return True

    # --- Core Logic (largely unchanged) ---

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
            self.safe_say("The last flock has been accounted for. The Great Migration has concluded!")
            self.set_state("event", None)
            self.save_state()
            self._schedule_next_spawn()
            return
        if random.random() < self.EVENT_ESCAPE_CHANCE:
            escaped_flock_size = event["flocks"].pop(0)
            self.set_state("event", event)
            self.save_state()
            self.safe_say(f"Oh dear, it seems a flock of {escaped_flock_size} {event['animal_name']}s has flown the coop!")
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
             self.safe_say(f"A flock of {current_flock_size} {animal_name}s from {event['name']} appears! ({len(event['flocks'])} flocks remaining)", target=room)
             self.safe_say(animal_to_spawn.get("ascii_art", "An animal appears."), target=room)
        return schedule.CancelJob

    def _spawn_animal(self, target_channel: Optional[str] = None) -> bool:
        schedule.clear("spawn")
        if not self.ANIMALS:
            self._schedule_next_spawn()
            return False

        spawn_locations = []
        if target_channel:
            if target_channel in self.ALLOWED_CHANNELS:
                spawn_locations.append(target_channel)
        else:
            spawn_locations = [room for room in self.ALLOWED_CHANNELS if room in self.bot.joined_channels]

        if not spawn_locations:
            self._schedule_next_spawn()
            return False
            
        animal = random.choice(self.ANIMALS)
        self.set_state("active_animal", animal)
        self.save_state()
        announcement = random.choice(self.SPAWN_ANNOUNCEMENTS)
        
        for room in spawn_locations:
            self.safe_say(announcement, target=room)
            self.safe_say(animal.get("ascii_art", "An animal appears."), target=room)
            
        return True

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
            self.safe_reply(connection, event, f"Excellent work, {self.bot.title_for(username)}! You have {action} a flock of {score_to_add} {animal_name}s!")
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
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            self.safe_reply(connection, event, "My apologies, but the hunt is not active in this channel.")
            return True
        
        target = match.group(1)
        if target:
            title = self.bot.title_for(username)
            self.safe_reply(connection, event, f"While the sentiment is appreciated, {title}, one must always seek consent before embracing another.")
            return True
            
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hugged")
        
        self.safe_reply(connection, event, f"There is nothing to hug at the moment, {self.bot.title_for(username)}.")
        return True

    def _cmd_release(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            self.safe_reply(connection, event, "My apologies, but the hunt is not active in this channel.")
            return True
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

    def _cmd_score(self, connection, event, msg, username, target_user_nick):
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

    def _find_animal_by_name(self, name_input: str) -> Optional[Dict[str, Any]]:
        name_lower = name_input.lower()
        for animal in self.ANIMALS:
            config_name = animal.get("name", "").lower()
            if not config_name: continue
            if name_lower == config_name: return animal
            if name_lower == f"{config_name}s": return animal
            if config_name.endswith('y') and name_lower == f"{config_name[:-1]}ies": return animal
        return None

    def _cmd_admin_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        if self._spawn_animal(target_channel=event.target):
            self.safe_reply(connection, event, "As you wish. I have released an animal.")
        else:
            self.safe_reply(connection, event, f"I cannot spawn an animal in this channel ('{event.target}'). Please ensure it is in the `allowed_channels` list in your configuration.")
        return True

    def _cmd_admin_add(self, connection, event, msg, username, args):
        target_user, animal_name_input, action, amount_str = args
        amount = int(amount_str)
        matched_animal = self._find_animal_by_name(animal_name_input)
        if not matched_animal:
            self.safe_reply(connection, event, f"I am not familiar with an animal named '{animal_name_input}'.")
            return True
        canonical_animal_name = matched_animal['name'].lower()
        user_id = self.bot.get_user_id(target_user)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        score_key = f"{canonical_animal_name}_{action}"
        user_scores[score_key] = user_scores.get(score_key, 0) + amount
        scores[user_id] = user_scores
        self.set_state("scores", scores)
        self.save_state()
        self.safe_reply(connection, event, f"Very good. Added {amount} to {target_user}'s {canonical_animal_name} {action} score.")
        return True

    def _cmd_admin_fixscores(self, connection, event, msg, username, match):
        all_scores = self.get_state("scores", {})
        fixed_count = 0
        canonical_animal_names = {a['name'].lower() for a in self.ANIMALS if 'name' in a}
        for user_id, user_scores in all_scores.items():
            new_scores = {}
            for key, count in user_scores.items():
                try:
                    animal, action = key.rsplit('_', 1)
                    if animal in canonical_animal_names and action in ["hunted", "hugged"]:
                         new_scores[key] = new_scores.get(key, 0) + count
                    else:
                        fixed_count += 1
                except ValueError:
                    fixed_count += 1
            all_scores[user_id] = new_scores
        self.set_state("scores", all_scores)
        self.save_state()
        self.safe_reply(connection, event, f"Score normalization complete. Inspected scores for {len(all_scores)} users. Found and corrected {fixed_count} potential inconsistencies.")
        return True

    def _cmd_admin_event(self, connection, event, msg, username, args):
        target_user, animal_name_input, action = args
        matched_animal = self._find_animal_by_name(animal_name_input)
        if not matched_animal:
            self.safe_reply(connection, event, f"I am not familiar with an animal named '{animal_name_input}'.")
            return True
        canonical_animal_name = matched_animal['name'].lower()
        score_key = f"{canonical_animal_name}_{action}"
        user_id = self.bot.get_user_id(target_user)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        animal_count = user_scores.pop(score_key, 0)
        if animal_count == 0:
            self.safe_reply(connection, event, f"{target_user} has no {action} {canonical_animal_name}s to release.")
            return True
        flocks = []
        remaining = animal_count
        while remaining > self.EVENT_MIN_FLOCK_SIZE:
            flock_size = random.randint(self.EVENT_MIN_FLOCK_SIZE, self.EVENT_MAX_FLOCK_SIZE)
            if remaining - flock_size < self.EVENT_MIN_FLOCK_SIZE:
                flocks.append(remaining)
                remaining = 0
                break
            flocks.append(flock_size)
            remaining -= flock_size
        if remaining > 0: flocks.append(remaining)
        if not flocks:
            self.safe_reply(connection, event, f"Not enough {canonical_animal_name}s ({animal_count}) to form any flocks.")
            user_scores[score_key] = animal_count
            return True
        scores[user_id] = user_scores
        self.set_state("scores", scores)
        self.set_state("event", {
            "active": True, "name": f"The Great {canonical_animal_name.capitalize()} Migration",
            "flocks": flocks, "animal_name": canonical_animal_name
        })
        self.save_state()
        self.safe_say(f"Attention! By order of {username}, {target_user} has released {animal_count} {canonical_animal_name}s! The Great {canonical_animal_name.capitalize()} Migration has begun!")
        self._start_event_spawn()
        return True

