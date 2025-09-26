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
    version = "2.0.0" # Dynamic configuration refactor
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
        self.static_keys = ["animals", "event_settings"]
        
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_animal", self.get_state("active_animal", None))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None))
        self.set_state("event", self.get_state("event", None))
        self.save_state()

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        
        event = self.get_state("event")
        if event and event.get("active"):
            self._handle_event_load(event)
            return

        next_spawn_str = self.get_state("next_spawn_time")
        if next_spawn_str:
            self._handle_regular_spawn_load(next_spawn_str)
        elif not self.get_state("active_animal"):
            self._schedule_next_spawn()

    def _handle_event_load(self, event):
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

    def _handle_regular_spawn_load(self, next_spawn_str):
        next_spawn_time = datetime.fromisoformat(next_spawn_str)
        now = datetime.now(UTC)
        if now >= next_spawn_time:
            self._spawn_animal()
        else:
            remaining_seconds = (next_spawn_time - now).total_seconds()
            if remaining_seconds > 0:
                schedule.every(remaining_seconds).seconds.do(self._spawn_animal).tag(self.name, "spawn")

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _register_commands(self):
        self.register_command(r"^\s*!hug(?:\s+(.+))?\s*$", self._cmd_hug, name="hug")
        self.register_command(r"^\s*!release\s+(hug|hunt)\s*$", self._cmd_release, name="release")
        self.register_command(r"^\s*!hunt(?:\s+(.*))?$", self._cmd_hunt_master, name="hunt")

    def _cmd_hunt_master(self, connection, event, msg, username, match):
        """Master handler for all !hunt commands."""
        args_str = (match.group(1) or "").strip()
        
        if not args_str: return self._handle_hunt_animal(connection, event, username)

        args = args_str.split()
        subcommand = args[0].lower()

        if subcommand == "score": return self._handle_score(connection, event, username, args[1:])
        if subcommand == "top": return self._handle_top(connection, event, username)
        if subcommand == "admin": return self._handle_admin(connection, event, username, args[1:])
        if subcommand == "spawn": return self._handle_admin_spawn(connection, event, username) # Admin alias
        if subcommand == "help": return self._handle_help(connection, event, username)
        
        return self._handle_hunt_guest(connection, event, username, args_str)

    # --- Subcommand Handlers ---

    def _handle_hunt_animal(self, connection, event, username):
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hunted")
        self.safe_reply(connection, event, f"There is nothing to hunt, {self.bot.title_for(username)}.")
        return True
    
    def _handle_hunt_guest(self, connection, event, username, target_name):
        self.safe_reply(connection, event, f"I must object, {self.bot.title_for(username)}. Hunting the guests is against policy.")
        return True

    def _handle_score(self, connection, event, username, args):
        target_user_nick = args[0] if args else username
        return self._cmd_score(connection, event, "", username, target_user_nick)

    def _handle_top(self, connection, event, username):
        return self._cmd_top(connection, event, "", username, None)

    def _handle_admin(self, connection, event, username, args):
        if not self.bot.is_admin(event.source): return True
        if not args: return self._usage(connection, event, "admin <spawn|add|event...>")
        admin_subcommand = args[0].lower()
        if admin_subcommand == "spawn": return self._handle_admin_spawn(connection, event, username)
        if admin_subcommand == "add":
            if len(args) != 5: return self._usage(connection, event, "admin add <user> <animal> <hunted|hugged> <amount>")
            return self._cmd_admin_add(connection, event, "", username, args[1:])
        if admin_subcommand == "event":
            if len(args) != 4: return self._usage(connection, event, "admin event <user> <animal> <hunted|hugged>")
            return self._cmd_admin_event(connection, event, "", username, args[1:])
        return self._usage(connection, event, f"unknown admin command '{admin_subcommand}'")

    def _usage(self, connection, event, command_args):
        self.safe_reply(connection, event, f"Usage: !hunt {command_args}")
        return True

    def _handle_admin_spawn(self, connection, event, username):
        if not self.bot.is_admin(event.source): return True
        return self._cmd_admin_spawn(connection, event, "", username, None)

    def _handle_help(self, connection, event, username):
        self.safe_reply(connection, event, "I have sent you the hunt commands privately.")
        lines = ["!hunt - Hunt the active animal.", "!hug - Befriend the active animal.", "!release <hunt|hug> - Release an animal.", "!hunt score [user] - Check scores.", "!hunt top - Show the leaderboard.", "!hunt help - Show this message." ]
        if self.bot.is_admin(event.source):
            lines.extend(["Admin:", "!hunt spawn - Force an animal to appear.", "!hunt admin add <user> <animal> <hunted|hugged> <amount> - Modify score.", "!hunt admin event <user> <animal> <hunted|hugged> - Start a migration event."])
        for line in lines: self.safe_privmsg(username, line)
        return True

    # --- Core Logic ---

    def _schedule_next_spawn(self):
        schedule.clear(self.name)
        min_h = self.get_config_value("min_hours_between_spawns", default=2)
        max_h = self.get_config_value("max_hours_between_spawns", default=10)
        animals = self.get_config_value("animals", default=[])
        if not animals: return
        
        delay_hours = random.uniform(min_h, max_h)
        next_spawn_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        self.set_state("next_spawn_time", next_spawn_time.isoformat())
        self.save_state()
        schedule.every(delay_hours * 3600).seconds.do(self._spawn_animal).tag(self.name, "spawn")

    def _spawn_animal(self, target_channel: Optional[str] = None):
        schedule.clear("spawn")
        animals = self.get_config_value("animals", default=[])
        if not animals:
            self._schedule_next_spawn()
            return
            
        spawn_locations = [
            room for room in self.bot.joined_channels
            if self.is_enabled(room)
        ]
        if target_channel and target_channel not in spawn_locations:
            spawn_locations = [] # Don't spawn if admin-spawned in a disabled channel

        if not spawn_locations and not target_channel:
            self._schedule_next_spawn()
            return
            
        animal = random.choice(animals)
        self.set_state("active_animal", animal)
        self.save_state()
        announcement = random.choice(self.SPAWN_ANNOUNCEMENTS)
        
        for room in ([target_channel] if target_channel else spawn_locations):
            self.safe_say(announcement, target=room)
            self.safe_say(animal.get("ascii_art", "An animal appears."), target=room)

    def _end_hunt(self, connection, event, username, action):
        active_animal = self.get_state("active_animal")
        if not active_animal: return
        
        # All event logic is now global, not per-channel
        event_state = self.get_state("event")
        is_event_catch = event_state and event_state.get("active") and event_state.get("animal_name") == active_animal.get("name", "").lower()
        score_to_add = active_animal.get("flock_size", 1) if is_event_catch else 1
        animal_name = active_animal.get("name", "animal").lower()
        user_id = self.bot.get_user_id(username)

        scores = self.get_state("scores", {})
        user_scores = scores.setdefault(user_id, {})
        score_key = f"{animal_name}_{action}"
        user_scores[score_key] = user_scores.get(score_key, 0) + score_to_add
        
        self.set_state("scores", scores)
        self.set_state("active_animal", None)

        if is_event_catch:
            self.safe_reply(connection, event, f"Excellent work, {self.bot.title_for(username)}! You have {action} a flock of {score_to_add} {animal_name}s!")
            event_state["flocks"].pop(0)
            event_state.pop("next_spawn_time", None)
            self.set_state("event", event_state)
            self._schedule_next_event_spawn()
        else:
            msg_key = "hug_message" if action == "hugged" else "hunt_message"
            custom_msg = active_animal.get(msg_key, "You have {action} the {animal_name}.")
            self.safe_reply(connection, event, custom_msg.format(username=self.bot.title_for(username), action=action, animal_name=animal_name))
            self._schedule_next_spawn()
        self.save_state()
        return True

    def _cmd_hug(self, connection, event, msg, username, match):
        if match.group(1):
            self.safe_reply(connection, event, f"While appreciated, {self.bot.title_for(username)}, one must seek consent before embracing another.")
            return True
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hugged")
        self.safe_reply(connection, event, f"There is nothing to hug, {self.bot.title_for(username)}.")
        return True

    def _cmd_release(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, f"We must deal with the current creature first, {self.bot.title_for(username)}.")
            return True
            
        action_type = match.group(1)
        score_suffix = "_hugged" if action_type == "hug" else "_hunted"
        user_id = self.bot.get_user_id(username)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        releasable = [k for k, v in user_scores.items() if k.endswith(score_suffix) and v > 0]
        
        if not releasable:
            self.safe_reply(connection, event, f"You have no {action_type}ed animals to release, {self.bot.title_for(username)}.")
            return True
            
        key_to_release = random.choice(releasable)
        animal_name = key_to_release.replace(score_suffix, "")
        user_scores[key_to_release] -= 1
        if user_scores[key_to_release] == 0:
            del user_scores[key_to_release]
        
        animals = self.get_config_value("animals", default=[])
        animal_data = next((a for a in animals if a.get("name", "").lower() == animal_name), None)
        
        self.set_state("scores", scores)
        if animal_data: self.set_state("active_animal", animal_data)
        self.save_state()
        
        response = random.choice(self.RELEASE_MESSAGES).format(title=self.bot.title_for(username), animal_name=animal_name.capitalize())
        self.safe_reply(connection, event, response)
        
        if animal_data:
            self.safe_say(animal_data.get("ascii_art", f"A {animal_name} is now loose!"), target=event.target)
        else:
            self.safe_reply(connection, event, f"It seems the {animal_name.capitalize()} has vanished entirely.")
        return True

    def _cmd_score(self, connection, event, msg, username, target_user_nick):
        user_id = self.bot.get_user_id(target_user_nick)
        scores = self.get_state("scores", {}).get(user_id, {})
        if not scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} has not yet interacted with any animals.")
            return True
        parts = [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in sorted(scores.items())]
        self.safe_reply(connection, event, f"Score for {self.bot.title_for(target_user_nick)}: {', '.join(parts)}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        all_scores = self.get_state("scores", {})
        if not all_scores:
            self.safe_reply(connection, event, "No scores have been recorded yet.")
            return True
        user_map = self.bot.get_module_state("users").get("user_map", {})
        leaderboard = {uid: sum(s.values()) for uid, s in all_scores.items()}
        top_ids = sorted(leaderboard.items(), key=lambda i: i[1], reverse=True)[:5]
        
        lines = []
        for i, (user_id, total) in enumerate(top_ids):
             scores = all_scores.get(user_id, {})
             display_nick = user_map.get(user_id, {}).get("canonical_nick", "Unknown")
             hugs = sum(v for k, v in scores.items() if k.endswith("_hugged"))
             hunts = sum(v for k, v in scores.items() if k.endswith("_hunted"))
             lines.append(f"{i+1}. {display_nick} ({total}: {hugs} hugs, {hunts} hunts)")
        self.safe_reply(connection, event, f"Top 5 hunters: {'; '.join(lines)}")
        return True

    # --- Admin & Event Logic ---
    
    def _schedule_next_event_spawn(self):
        schedule.clear(self.name)
        event = self.get_state("event")
        if not (event and event.get("active") and event.get("flocks")):
            self.safe_say("The last flock has been accounted for. The Great Migration has concluded!")
            self.set_state("event", None)
            self.save_state()
            self._schedule_next_spawn()
            return

        event_settings = self.get_config_value("event_settings", default={})
        if random.random() < event_settings.get("escape_chance", 0.1):
            escaped = event["flocks"].pop(0)
            self.set_state("event", event)
            self.save_state()
            self.safe_say(f"Oh dear, a flock of {escaped} {event['animal_name']}s has flown the coop!")
            self._schedule_next_event_spawn()
            return
            
        min_delay = event_settings.get("min_flock_delay_minutes", 2) * 60
        max_delay = event_settings.get("max_flock_delay_minutes", 60) * 60
        delay_seconds = random.randint(min_delay, max_delay)
        
        next_spawn_time = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        event["next_spawn_time"] = next_spawn_time.isoformat()
        self.set_state("event", event)
        self.save_state()
        schedule.every(delay_seconds).seconds.do(self._start_event_spawn).tag(self.name, "event_spawn")

    def _start_event_spawn(self):
        schedule.clear("event_spawn")
        event = self.get_state("event")
        if not (event and event.get("active") and event.get("flocks")):
            self._schedule_next_spawn()
            return schedule.CancelJob
            
        animals = self.get_config_value("animals", default=[])
        animal_to_spawn = next((a for a in animals if a.get("name", "").lower() == event["animal_name"]), None)
        if not animal_to_spawn:
            self.set_state("event", None)
            self._schedule_next_spawn()
            return schedule.CancelJob
            
        current_flock_size = event["flocks"][0]
        animal_to_spawn["flock_size"] = current_flock_size
        self.set_state("active_animal", animal_to_spawn)
        self.save_state()
        
        active_channels = [r for r in self.bot.joined_channels if self.is_enabled(r)]
        for room in active_channels:
             self.safe_say(f"A flock of {current_flock_size} {event['animal_name']}s from {event['name']} appears! ({len(event['flocks'])} flocks remaining)", target=room)
             self.safe_say(animal_to_spawn.get("ascii_art", "An animal appears."), target=room)
        return schedule.CancelJob

    def _find_animal_by_name(self, name_input: str) -> Optional[Dict[str, Any]]:
        name_lower = name_input.lower()
        animals = self.get_config_value("animals", default=[])
        for animal in animals:
            if name_lower == animal.get("name", "").lower():
                return animal
        return None

    def _cmd_admin_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        self._spawn_animal(target_channel=event.target)
        self.safe_reply(connection, event, "As you wish. I have released an animal.")
        return True

    def _cmd_admin_add(self, connection, event, msg, username, args):
        target_user, animal_name_input, action, amount_str = args
        matched_animal = self._find_animal_by_name(animal_name_input)
        if not matched_animal:
            self.safe_reply(connection, event, f"I am not familiar with '{animal_name_input}'.")
            return True
        
        user_id = self.bot.get_user_id(target_user)
        scores = self.get_state("scores", {})
        user_scores = scores.setdefault(user_id, {})
        key = f"{matched_animal['name'].lower()}_{action}"
        user_scores[key] = user_scores.get(key, 0) + int(amount_str)
        
        self.set_state("scores", scores)
        self.save_state()
        self.safe_reply(connection, event, f"Very good. Score updated for {target_user}.")
        return True

    def _cmd_admin_event(self, connection, event, msg, username, args):
        target_user, animal_name_input, action = args
        matched_animal = self._find_animal_by_name(animal_name_input)
        if not matched_animal:
            self.safe_reply(connection, event, f"I am not familiar with '{animal_name_input}'.")
            return True
            
        animal_name = matched_animal['name'].lower()
        score_key = f"{animal_name}_{action}"
        user_id = self.bot.get_user_id(target_user)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        animal_count = user_scores.pop(score_key, 0)

        if animal_count == 0:
            self.safe_reply(connection, event, f"{target_user} has no {action} {animal_name}s.")
            return True
        
        event_settings = self.get_config_value("event_settings", default={})
        min_flock = event_settings.get("min_flock_size", 20)
        max_flock = event_settings.get("max_flock_size", 50)
        
        flocks, remaining = [], animal_count
        while remaining > min_flock:
            flock_size = random.randint(min_flock, max_flock)
            if remaining - flock_size < min_flock:
                flocks.append(remaining)
                remaining = 0
                break
            flocks.append(flock_size)
            remaining -= flock_size
        if remaining > 0: flocks.append(remaining)
        
        if not flocks:
            self.safe_reply(connection, event, f"Not enough {animal_name}s ({animal_count}) to form a flock.")
            user_scores[score_key] = animal_count # Put them back
            return True
            
        scores[user_id] = user_scores
        self.set_state("scores", scores)
        self.set_state("event", {
            "active": True, "name": f"The Great {animal_name.capitalize()} Migration",
            "flocks": flocks, "animal_name": animal_name
        })
        self.save_state()
        
        self.safe_say(f"Attention! By order of {username}, {target_user} has released {animal_count} {animal_name}s! The Great {animal_name.capitalize()} Migration has begun!")
        self._start_event_spawn()
        return True
