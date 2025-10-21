# modules/hunt.py
# A game where users can hunt or hug animals that appear in the channel.
import random
import re
import schedule
import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot):
    return Hunt(bot)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "2.0.0" # Added catch timer and reverted score complexity.
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
    MURDER_MESSAGES = [
        "YOU KILLED IT!",
        "DEAD! Stone cold dead!",
        "You shot it to death! Good heavens!",
        "MURDERED IN COLD BLOOD!",
        "The {animal_name} didn't stand a chance. Absolutely obliterated!",
        "FATALITY! The {animal_name} has been slain!"
    ]

    def __init__(self, bot):
        super().__init__(bot)
        self._is_loaded = False
        self._spawn_lock = threading.Lock()
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("active_animal", self.get_state("active_animal", None))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None))
        self.set_state("event", self.get_state("event", None))
        # The on_config_reload will be called by the bot core on load
        # so we don't need to call it manually here.

    def on_config_reload(self, config):
        # Allow for runtime changes via !admin set
        pass

    def on_load(self):
        super().on_load()
        self._is_loaded = True
        schedule.clear(self.name)
        
        event = self.get_state("event")
        if event and event.get("active"):
            # Logic to resume an event
            self._resume_event_scheduler()
            return

        next_spawn_str = self.get_state("next_spawn_time")
        if next_spawn_str:
            # Logic to resume a normal spawn timer
            self._resume_normal_spawn_scheduler(next_spawn_str)
        elif not self.get_state("active_animal"):
            self._schedule_next_spawn()

    def _resume_event_scheduler(self):
        event = self.get_state("event")
        next_event_spawn_str = event.get("next_spawn_time")
        if next_event_spawn_str:
            next_spawn_time = datetime.fromisoformat(next_event_spawn_str)
            now = datetime.now(UTC)
            if now >= next_spawn_time:
                self._start_event_spawn()
            else:
                remaining = (next_spawn_time - now).total_seconds()
                if remaining > 0:
                    schedule.every(remaining).seconds.do(self._start_event_spawn).tag(f"{self.name}-event_spawn")
        else:
             self._start_event_spawn()

    def _resume_normal_spawn_scheduler(self, next_spawn_str):
        next_spawn_time = datetime.fromisoformat(next_spawn_str)
        now = datetime.now(UTC)
        if now >= next_spawn_time:
            self._spawn_animal()
        else:
            remaining_seconds = (next_spawn_time - now).total_seconds()
            if remaining_seconds > 0:
                schedule.every(remaining_seconds).seconds.do(self._spawn_animal).tag(f"{self.name}-spawn")

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _register_commands(self):
        self.register_command(r"^\s*!hug(?:\s+(.+))?\s*$", self._cmd_hug, name="hug", description="Befriend the animal.")
        self.register_command(r"^\s*!release\s+(hug|hunt)\s*$", self._cmd_release, name="release", description="Release a previously caught or befriended animal.")
        self.register_command(r"^\s*!hunt(?:\s+(.*))?$", self._cmd_hunt_master, name="hunt", description="The main command for the hunt game. Use '!hunt help' for subcommands.")

    def _format_timedelta(self, td: timedelta) -> str:
        seconds = int(td.total_seconds())
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)

        parts = []
        if days > 0: parts.append(f"{days} day{'s' if days != 1 else ''}")
        if hours > 0: parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
        if minutes > 0: parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
        if seconds > 0 or not parts: parts.append(f"{seconds} second{'s' if seconds != 1 else ''}")
        
        return ", ".join(parts)

    def _cmd_hunt_master(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target): return False
        
        args_str = (match.group(1) or "").strip()
        
        if not args_str:
            return self._handle_hunt_animal(connection, event, username)

        args = args_str.split()
        subcommand = args[0].lower()

        if subcommand == "score":
            return self._handle_score(connection, event, username, args[1:])
        elif subcommand == "top":
            return self._handle_top(connection, event, username)
        elif subcommand == "admin":
            return self._handle_admin(connection, event, username, args[1:])
        elif subcommand == "spawn":
            return self._handle_admin_spawn(connection, event, username)
        elif subcommand == "help":
            return self._handle_help(connection, event, username)
        else:
            return self._handle_hunt_guest(connection, event, username, args_str)

    def _handle_hunt_animal(self, connection, event, username):
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hunted")
        self.safe_reply(connection, event, f"There is nothing to hunt at the moment, {self.bot.title_for(username)}.")
        return True
    
    def _handle_hunt_guest(self, connection, event, username, target_name):
        self.safe_reply(connection, event, f"I must strongly object, {self.bot.title_for(username)}. Hunting the guests is strictly against household policy.")
        return True

    def _handle_score(self, connection, event, username, args):
        target_user_nick = args[0] if args else username
        self._cmd_score(connection, event, "", username, target_user_nick)
        return True

    def _handle_top(self, connection, event, username):
        self._cmd_top(connection, event, "", username, None)
        return True

    def _handle_admin(self, connection, event, username, args):
        if not self.bot.is_admin(event.source): return True 

        if not args:
            self.safe_reply(connection, event, "Usage: !hunt admin <spawn|add|event>")
            return True

        admin_subcommand = args[0].lower()
        if admin_subcommand == "spawn":
            return self._handle_admin_spawn(connection, event, username)
        elif admin_subcommand == "add":
            if len(args) != 5:
                self.safe_reply(connection, event, "Usage: !hunt admin add <user> <animal> <hunted|hugged> <amount>")
                return True
            return self._cmd_admin_add(connection, event, "", username, args[1:])
        elif admin_subcommand == "event":
            if len(args) != 4:
                self.safe_reply(connection, event, "Usage: !hunt admin event <user> <animal> <hunted|hugged>")
                return True
            return self._cmd_admin_event(connection, event, "", username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown admin command '{admin_subcommand}'.")
            return True

    def _handle_admin_spawn(self, connection, event, username):
        if not self.bot.is_admin(event.source): return True
        return self._cmd_admin_spawn(connection, event, "", username, None)

    def _handle_help(self, connection, event, username):
        help_lines = [ "!hunt - Hunt the currently active animal.", "!hug - Befriend the currently active animal.", "!release <hunt|hug> - Release a captured animal.", "!hunt score [user] - Check your score.", "!hunt top - Show the leaderboard.", "!hunt help - Show this message." ]
        if self.bot.is_admin(event.source):
            help_lines.extend(["Admin:", "!hunt spawn - Force an animal to appear.", "!hunt admin add <user> <animal> <hunted|hugged> <amount> - Add to a score.", "!hunt admin event <user> <animal> <hunted|hugged> - Start a migration event."])
        
        for line in help_lines:
            self.safe_privmsg(username, line)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you the details privately.")
        return True

    def _schedule_next_spawn(self):
        # Clear any existing spawn jobs to prevent duplicates
        cleared_count = len(schedule.get_jobs(f"{self.name}-spawn"))
        schedule.clear(f"{self.name}-spawn")
        if cleared_count > 0:
            self.log_debug(f"_schedule_next_spawn: cleared {cleared_count} existing spawn job(s)")

        allowed_channels = self.get_config_value("allowed_channels", default=[])
        animals = self.get_config_value("animals", default=[])
        if not allowed_channels or not animals:
            return

        min_h = self.get_config_value("min_hours_between_spawns", default=2)
        max_h = self.get_config_value("max_hours_between_spawns", default=10)
        delay_hours = random.uniform(min_h, max_h)
        next_spawn_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        self.log_debug(f"_schedule_next_spawn: scheduling spawn in {delay_hours:.2f} hours (at {next_spawn_time.isoformat()})")

        self.set_state("next_spawn_time", next_spawn_time.isoformat())
        self.save_state()
        schedule.every(delay_hours * 3600).seconds.do(self._spawn_animal).tag(f"{self.name}-spawn")

    def _spawn_animal(self, target_channel: Optional[str] = None) -> bool:
        # Use a lock to prevent race conditions when multiple scheduled jobs fire simultaneously
        with self._spawn_lock:
            # Clear spawn jobs immediately to prevent race conditions
            pending_jobs = len(schedule.get_jobs(f"{self.name}-spawn"))
            schedule.clear(f"{self.name}-spawn")
            self.log_debug(f"_spawn_animal called (target_channel={target_channel}, cleared {pending_jobs} pending job(s))")

            animals = self.get_config_value("animals", default=[])
            if not animals:
                self.log_debug("No animals configured, scheduling next spawn")
                self._schedule_next_spawn()
                return False

            allowed_channels = self.get_config_value("allowed_channels", default=[])

            # Deduplicate channels in case of config duplicates
            spawn_locations = list(set([room for room in allowed_channels if room in self.bot.joined_channels and self.is_enabled(room)]))
            self.log_debug_vars("channel_resolution",
                               allowed_channels=allowed_channels,
                               joined_channels=self.bot.joined_channels,
                               spawn_locations=spawn_locations)

            if target_channel and target_channel in spawn_locations:
                spawn_locations = [target_channel]
                self.log_debug(f"target_channel specified, using only: {spawn_locations}")

            if not spawn_locations:
                self.log_debug("No valid spawn locations, scheduling next spawn")
                self._schedule_next_spawn()
                return False

            # Check if there's already an active animal
            existing_animal = self.get_state("active_animal")
            if existing_animal:
                self.log_debug(f"WARNING: active_animal already exists: {existing_animal}")
                self.log_debug("Skipping spawn, scheduling next attempt")
                self._schedule_next_spawn()
                return False

            animal = random.choice(animals).copy()
            animal['spawned_at'] = datetime.now(UTC).isoformat()
            self.log_debug(f"Selected animal: {animal.get('name', 'unknown')}")

            self.set_state("active_animal", animal)
            self.save_state()
            self.log_debug(f"Saved active_animal to state")

            self.log_debug(f"Announcing to {len(spawn_locations)} rooms: {spawn_locations}")
            for room in spawn_locations:
                self.log_debug(f"Sending announcement to {room}")
                self.safe_say(random.choice(self.SPAWN_ANNOUNCEMENTS), target=room)
                self.safe_say(animal.get("ascii_art", "An animal appears."), target=room)

            return True

    def _end_hunt(self, connection, event, username, action):
        self.log_debug(f"_end_hunt called by {username}, action={action}")
        active_animal = self.get_state("active_animal")
        if not active_animal:
            self.log_debug("_end_hunt: no active_animal found")
            return True

        self.log_debug(f"_end_hunt: processing animal '{active_animal.get('name', 'unknown')}'")
        # Calculate time to catch
        time_to_catch_str = ""
        if 'spawned_at' in active_animal:
            try:
                spawn_time = datetime.fromisoformat(active_animal['spawned_at'])
                catch_time = datetime.now(UTC)
                duration = self._format_timedelta(catch_time - spawn_time)
                time_to_catch_str = f" in {duration}"
            except (ValueError, TypeError):
                self.log_debug("Could not parse spawn time for active animal.")

        animal_name = active_animal.get("name", "animal").lower()
        user_id = self.bot.get_user_id(username)

        # Special handling for user "dead" - they MURDER animals
        is_dead = username.lower() == "dead"
        if is_dead and action == "hunted":
            action = "murdered"

        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        score_key = f"{animal_name}_{action}"
        user_scores[score_key] = user_scores.get(score_key, 0) + 1
        scores[user_id] = user_scores

        self.set_state("scores", scores)
        self.set_state("active_animal", None)
        self.log_debug(f"_end_hunt: cleared active_animal, saved scores")
        self.save_state()

        # Special murder messages for user "dead"
        if is_dead and action == "murdered":
            murder_msg = random.choice(self.MURDER_MESSAGES).format(animal_name=animal_name)
            self.safe_reply(connection, event, murder_msg + time_to_catch_str + ".")
        else:
            msg_key = "hug_message" if action == "hugged" else "hunt_message"
            custom_msg = active_animal.get(msg_key)

            if custom_msg:
                self.safe_reply(connection, event, custom_msg.format(username=self.bot.title_for(username)) + time_to_catch_str + ".")
            else:
                self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. You have {action} the {animal_name}{time_to_catch_str}.")

        self.log_debug(f"_end_hunt: complete, scheduling next spawn")
        self._schedule_next_spawn()
        return True

    def _cmd_hug(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target): return False
        
        if match.group(1):
            self.safe_reply(connection, event, f"While the sentiment is appreciated, {self.bot.title_for(username)}, one must always seek consent before embracing another.")
            return True
            
        if self.get_state("active_animal"):
            return self._end_hunt(connection, event, username, "hugged")
        
        self.safe_reply(connection, event, f"There is nothing to hug at the moment, {self.bot.title_for(username)}.")
        return True

    def _cmd_release(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target): return False

        if self.get_state("active_animal"):
            self.safe_reply(connection, event, f"I must insist we deal with the current creature first, {self.bot.title_for(username)}.")
            return True
            
        action_type = match.group(1)
        score_suffix = "_hugged" if action_type == "hug" else "_hunted"
        user_id = self.bot.get_user_id(username)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        
        releasable = [k for k, v in user_scores.items() if k.endswith(score_suffix) and v > 0]
        if not releasable:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, but you have no {action_type}ed animals to release.")
            return True
            
        key_to_release = random.choice(releasable)
        animal_name = key_to_release.replace(score_suffix, "")
        
        user_scores[key_to_release] -= 1
        if user_scores[key_to_release] == 0:
            del user_scores[key_to_release]
        
        self.set_state("scores", scores)
        self.save_state()

        self.log_debug(f"_cmd_release: {username} released a {animal_name}, spawning replacement in {event.target}")
        self.safe_reply(connection, event, random.choice(self.RELEASE_MESSAGES).format(title=self.bot.title_for(username), animal_name=animal_name.capitalize()))
        self._spawn_animal(target_channel=event.target)
        return True

    def _cmd_score(self, connection, event, msg, username, target_user_nick):
        user_id = self.bot.get_user_id(target_user_nick)
        scores = self.get_state("scores", {}).get(user_id, {})
        if not scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} has not yet interacted with any animals.")
            return True
            
        parts = [f"{k.replace('_', ' ').capitalize()}: {v}" for k, v in sorted(scores.items()) if v > 0]
        if not parts:
             self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} has not yet interacted with any animals.")
             return True

        self.safe_reply(connection, event, f"Score for {self.bot.title_for(target_user_nick)}: {', '.join(parts)}.")
        return True

    def _cmd_top(self, connection, event, msg, username, match):
        all_scores = self.get_state("scores", {})
        if not all_scores:
            self.safe_reply(connection, event, "No scores have been recorded yet.")
            return True

        user_map = self.bot.get_module_state("users").get("user_map", {})
        leaderboard = {uid: sum(s.values()) for uid, s in all_scores.items()}
        sorted_top = sorted(leaderboard.items(), key=lambda item: item[1], reverse=True)[:5]

        top_list = []
        for i, (uid, total) in enumerate(sorted_top):
             user_scores = all_scores.get(uid, {})
             display_nick = user_map.get(uid, {}).get("canonical_nick", "Unknown User")
             hugs = sum(v for k, v in user_scores.items() if k.endswith("_hugged"))
             hunts = sum(v for k, v in user_scores.items() if k.endswith("_hunted"))
             murders = sum(v for k, v in user_scores.items() if k.endswith("_murdered"))

             # Build stats string
             if murders > 0:
                 top_list.append(f"#{i+1} {display_nick} ({total}: {hugs} hugs, {hunts} hunts, {murders} murders)")
             else:
                 top_list.append(f"#{i+1} {display_nick} ({total}: {hugs} hugs, {hunts} hunts)")

        self.safe_reply(connection, event, f"Top 5 most active members: {'; '.join(top_list)}")
        return True

    def _cmd_admin_spawn(self, connection, event, msg, username, match):
        if self.get_state("active_animal"):
            self.safe_reply(connection, event, "An animal is already active.")
            return True
        if self._spawn_animal(target_channel=event.target):
            self.safe_reply(connection, event, "As you wish. I have released an animal.")
        else:
            self.safe_reply(connection, event, f"I cannot spawn an animal in this channel ('{event.target}').")
        return True

    def _cmd_admin_add(self, connection, event, msg, username, args):
        target_user, animal_name, action, amount_str = args
        
        user_id = self.bot.get_user_id(target_user)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        score_key = f"{animal_name.lower()}_{action}"
        
        user_scores[score_key] = user_scores.get(score_key, 0) + int(amount_str)
        scores[user_id] = user_scores
        
        self.set_state("scores", scores)
        self.save_state()
        self.safe_reply(connection, event, f"Very good. Added {amount_str} to {target_user}'s {animal_name} {action} score.")
        return True

    def _cmd_admin_event(self, connection, event, msg, username, args):
        # This function would need significant rework with the simplified score system
        # and is outside the scope of the immediate bugfix.
        self.safe_reply(connection, event, "The event system is not compatible with the simplified scoring model.")
        return True

