# modules/hunt.py
# A game where users can hunt or hug animals that appear in the channel.
import random
import re
import schedule
import threading
import time
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .base import SimpleCommandModule, admin_required
from . import achievement_hooks

UTC = timezone.utc

def setup(bot: Any) -> 'Hunt':
    return Hunt(bot)

class Hunt(SimpleCommandModule):
    name = "hunt"
    version = "2.0.0" # Added catch timer and reverted score complexity.
    description = "A game of hunting or hugging randomly appearing animals."

    REMINDER_INTERVAL_HOURS = 12
    MAX_REMINDERS = 4
    ESCAPE_MISHAP_CHANCE = 0.05
    DEFAULT_ANIMAL_HAPPINESS = 3
    MIN_FOLLOWER_ESCAPE = 2
    MAX_FOLLOWER_ESCAPE = 3
    PENDING_HUG_EXPIRY_SECONDS = 600
    COLLECTIVE_NOUNS: List[str] = [
        "flock",
        "clowder",
        "litter",
        "murder",
        "team",
        "cluster",
        "herd",
        "pack",
        "parliament",
        "gaggle",
        "pod",
        "troop",
        "pride",
        "colony",
        "army",
    ]

    SPAWN_ANNOUNCEMENTS: List[str] = [
        "Good heavens, it appears a creature has wandered into the premises!",
        "I do apologize for the intrusion, but an animal has made its way inside.",
        "Pardon me, but it seems we have a small, uninvited guest.",
        "Attention, please. A wild animal has been spotted in the vicinity."
    ]
    REMINDER_MESSAGES: List[str] = [
        "Please, people. The {animal} is still running amok in here!",
        "Now, people, this is getting ridiculous, that {animal} is still loose!",
        "I must insist, this unruly {animal} remains at large and it is most unseemly.",
        "This is quite beyond the pale. Someone must address the {animal} immediately.",
    ]
    REMOVAL_MESSAGE = "You will be happy to know I took care of the intruder. The {animal} has been removed."
    RELEASE_MESSAGES: List[str] = [
        "Very well, {title}. I shall open the doors. Do try to be more decisive in the future.",
        "As you wish, {title}. The {animal_name} has been... liberated. I shall fetch a dustpan.",
        "If you insist, {title}. The {animal_name} is now free to roam the premises. Again.",
        "Releasing the {animal_name}, {title}. I trust this chaotic cycle will not become a habit."
    ]
    MURDER_MESSAGES: List[str] = [
        "YOU KILLED IT!",
        "DEAD! Stone cold dead!",
        "You shot it to death! Good heavens!",
        "MURDERED IN COLD BLOOD!",
        "The {animal_name} didn't stand a chance. Absolutely obliterated!",
        "FATALITY! The {animal_name} has been slain!"
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self._is_loaded: bool = False
        self._spawn_lock: threading.Lock = threading.Lock()
        self._spawn_job_token: Optional[str] = None
        self._pending_hug_requests: Dict[str, Dict[str, Any]] = {}
        self.set_state("scores", self.get_state("scores", {}))
        self.set_state("animal_happiness", self.get_state("animal_happiness", {}))
        # Migration: convert old active_animal to active_animals list
        old_active = self.get_state("active_animal", None)
        if old_active:
            self.set_state("active_animals", [old_active])
            self.set_state("active_animal", None)
            self.save_state()
        else:
            self.set_state("active_animals", self.get_state("active_animals", []))
        self.set_state("next_spawn_time", self.get_state("next_spawn_time", None))
        self.set_state("event", self.get_state("event", None))
        self.set_state("active_collective_noun", self.get_state("active_collective_noun", None))
        self.set_state("reminder_state", self.get_state("reminder_state", None))
        # The on_config_reload will be called by the bot core on load
        # so we don't need to call it manually here.

    def _event_is_active(self) -> bool:
        event_state = self.get_state("event")
        return bool(event_state and event_state.get("active"))

    def _normalize_species_filter(self, raw: Optional[str]) -> str:
        if not raw:
            return "all"
        if raw.lower() == "all":
            return "all"
        normalized = self._normalize_animal_key(raw)
        known_species = self._get_species_keys()
        return normalized if normalized in known_species else ""

    def _aggregate_user_animals(self, user_scores: Dict[str, int]) -> Dict[str, int]:
        """Return counts of tracked animals for a user."""
        totals = {species: 0 for species in self._get_species_keys()}
        for key, value in user_scores.items():
            for species in totals:
                if key.startswith(f"{species}_"):
                    totals[species] += value
        return totals

    def _get_animal_happiness(self, user_id: str) -> int:
        happiness = self.get_state("animal_happiness", {})
        return int(happiness.get(user_id, self.DEFAULT_ANIMAL_HAPPINESS))

    def _set_animal_happiness(self, user_id: str, value: int) -> None:
        happiness = self.get_state("animal_happiness", {})
        happiness[user_id] = value
        self.set_state("animal_happiness", happiness)

    def _pluralize(self, word: str, count: int) -> str:
        """
        Return the correct plural form of a word based on count.
        Handles common English pluralization rules:
        - Returns word unchanged if count == 1
        - Words ending in 'y' preceded by consonant -> 'ies' (e.g., 'Puppy' -> 'Puppies')
        - Otherwise appends 's'
        """
        if count == 1:
            return word

        # Handle words ending in 'y' preceded by a consonant
        if len(word) >= 2 and word[-1].lower() == 'y' and word[-2].lower() not in 'aeiou':
            return word[:-1] + 'ies'

        # Default: append 's'
        return word + 's'

    def _remove_random_animals_from_scores(self, user_id: str, count: int) -> Dict[str, int]:
        """
        Remove a number of hunted/hugged animals from a user's scores, weighted by their counts.
        Returns a mapping of display name -> removed count for messaging.
        """
        if count <= 0:
            return {}

        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        candidates = [(k, v) for k, v in user_scores.items() if v > 0 and (k.endswith("_hunted") or k.endswith("_hugged"))]
        if not candidates:
            return {}

        removed: Dict[str, int] = {}

        for _ in range(count):
            total_owned = sum(v for _, v in candidates)
            if total_owned <= 0:
                break

            pick = random.randint(1, total_owned)
            running = 0
            chosen_index = 0
            for idx, (key, value) in enumerate(candidates):
                running += value
                if pick <= running:
                    chosen_index = idx
                    break

            chosen_key, chosen_value = candidates[chosen_index]
            user_scores[chosen_key] = chosen_value - 1
            if user_scores[chosen_key] <= 0:
                del user_scores[chosen_key]
                candidates.pop(chosen_index)
            else:
                candidates[chosen_index] = (chosen_key, user_scores[chosen_key])

            animal_name = chosen_key.rsplit("_", 1)[0]
            display_name = self._lookup_display_name(animal_name)
            removed[display_name] = removed.get(display_name, 0) + 1

        if user_scores:
            scores[user_id] = user_scores
        elif user_id in scores:
            del scores[user_id]

        self.set_state("scores", scores)
        return removed

    def _format_follower_loss(self, losses: Dict[str, int]) -> str:
        if not losses:
            return ""
        total_lost = sum(losses.values())
        parts = []
        for name, qty in losses.items():
            suffix = "s" if qty != 1 else ""
            parts.append(f"{qty} {name}{suffix}")
        if not parts:
            return ""
        if len(parts) == 1:
            verb = "slips" if total_lost == 1 else "slip"
            return f"In the chaos, {parts[0]} {verb} out after it!"
        joined = ", ".join(parts[:-1]) + f" and {parts[-1]}"
        return f"In the chaos, {joined} slip out after it!"

    def _cleanup_pending_hugs(self) -> None:
        now = time.time()
        expired = [uid for uid, meta in self._pending_hug_requests.items() if now - meta.get("requested_at", 0) > self.PENDING_HUG_EXPIRY_SECONDS]
        for uid in expired:
            del self._pending_hug_requests[uid]

    def _resolve_user_id(self, nick: str, create_if_missing: bool = True) -> Optional[str]:
        """
        Resolve a user ID by nick, searching cached user maps first to avoid
        creating duplicate IDs when an admin targets someone who already has scores.
        """
        lower_nick = str(nick or "").lower()
        users_state = self.bot.get_module_state("users") or {}
        user_map = users_state.get("user_map", {})
        nick_map = users_state.get("nick_map", {})

        candidates: List[str] = []
        if lower_nick in nick_map:
            candidates.append(nick_map[lower_nick])

        for uid, profile in user_map.items():
            canonical = str(profile.get("canonical_nick", "")).lower()
            if canonical == lower_nick:
                candidates.append(uid)
                continue
            for seen in profile.get("seen_nicks") or []:
                if str(seen).lower() == lower_nick:
                    candidates.append(uid)

        if candidates:
            scores = self.get_state("scores", {})
            for uid in candidates:
                if scores.get(uid):
                    return uid
            return candidates[0]

        if create_if_missing:
            return self.bot.get_user_id(nick)
        return None

    def _lookup_scores_by_nick(self, nick: str) -> Optional[str]:
        """
        Fallback lookup: search the users state for any profile whose canonical or seen
        nick matches, and return a user_id that actually has hunt scores.
        """
        lower_nick = str(nick or "").lower()
        users_state = self.bot.get_module_state("users") or {}
        user_map = users_state.get("user_map", {})
        scores = self.get_state("scores", {})

        # First, map nick -> list of matching ids
        matching_ids: List[str] = []
        for uid, profile in user_map.items():
            canonical = str(profile.get("canonical_nick", "")).lower()
            if canonical == lower_nick:
                matching_ids.append(uid)
                continue
            for seen in profile.get("seen_nicks") or []:
                if str(seen).lower() == lower_nick:
                    matching_ids.append(uid)
                    break

        # Prefer an ID that actually has scores
        for uid in matching_ids:
            if scores.get(uid):
                return uid

        return matching_ids[0] if matching_ids else None

    def on_config_reload(self, config: Dict[str, Any]) -> None:
        # Allow for runtime changes via !admin set
        pass

    def on_load(self) -> None:
        super().on_load()
        self._is_loaded = True
        cleared = self._clear_scheduled_jobs(self.name, f"{self.name}-spawn", f"{self.name}-event_spawn", self._reminder_tag())
        if cleared:
            self.log_debug(f"on_load: cleared {cleared} leftover scheduled job(s)")
        
        event = self.get_state("event")
        if event and event.get("active"):
            # Logic to resume an event
            self._resume_event_scheduler()
            self._resume_reminder_scheduler()
            return

        next_spawn_str = self.get_state("next_spawn_time")
        if next_spawn_str:
            # Logic to resume a normal spawn timer
            self._resume_normal_spawn_scheduler(next_spawn_str)
        elif not self.get_state("active_animals"):
            self._schedule_next_spawn()
        self._resume_reminder_scheduler()

    def _clear_scheduled_jobs(self, *tags: str) -> int:
        if not tags:
            tags = (f"{self.name}-spawn", f"{self.name}-event_spawn", self._reminder_tag(), self.name)
        total_cleared = 0
        for tag in tags:
            jobs = schedule.get_jobs(tag)
            if not jobs:
                continue
            count = len(jobs)
            schedule.clear(tag)
            if tag == f"{self.name}-spawn":
                self._spawn_job_token = None
            total_cleared += count
        return total_cleared

    def _reminder_tag(self) -> str:
        return f"{self.name}-reminder"

    def _reminder_interval_seconds(self) -> float:
        return max(self.REMINDER_INTERVAL_HOURS * 3600, 1.0)

    def _clear_reminder_state(self, save: bool = True) -> None:
        self._clear_scheduled_jobs(self._reminder_tag())
        self.set_state("reminder_state", None)
        if save:
            self.save_state()

    def _get_reminder_channels(self, preferred: Optional[List[str]] = None) -> List[str]:
        preferred = preferred or []
        channels = [room for room in preferred if room in self.bot.joined_channels and self.is_enabled(room)]
        if channels:
            return list(dict.fromkeys(channels))
        allowed_channels = self.get_config_value("allowed_channels", default=[])
        return [room for room in allowed_channels if room in self.bot.joined_channels and self.is_enabled(room)]

    def _schedule_reminder(self, count: int, delay_seconds: float, channels: Optional[List[str]] = None) -> None:
        self._clear_scheduled_jobs(self._reminder_tag())
        next_time = datetime.now(UTC) + timedelta(seconds=max(delay_seconds, 1))
        reminder_state = {
            "count": max(0, int(count)),
            "next_time": next_time.isoformat(),
            "channels": channels or self.get_state("reminder_state", {}).get("channels") or [],
        }
        self.set_state("reminder_state", reminder_state)
        self.save_state()
        schedule.every(max(delay_seconds, 1)).seconds.do(self._handle_reminder_tick).tag(self._reminder_tag())

    def _resume_reminder_scheduler(self) -> None:
        active_animals = self.get_state("active_animals", [])
        if not active_animals:
            self._clear_reminder_state()
            return

        reminder_state = self.get_state("reminder_state") or {}
        count = int(reminder_state.get("count") or 0)
        channels = reminder_state.get("channels") or []
        delay_seconds = self._reminder_interval_seconds()

        next_time_str = reminder_state.get("next_time")
        if next_time_str:
            try:
                next_time = datetime.fromisoformat(next_time_str)
                now = datetime.now(UTC)
                if now >= next_time:
                    delay_seconds = 1
                else:
                    delay_seconds = max((next_time - now).total_seconds(), 1)
            except (ValueError, TypeError):
                pass
        else:
            try:
                spawn_time = datetime.fromisoformat(active_animals[0].get("spawned_at"))
                now = datetime.now(UTC)
                elapsed = (now - spawn_time).total_seconds()
                interval = self._reminder_interval_seconds()
                intervals_elapsed = int(elapsed // interval)
                count = min(max(count, intervals_elapsed), self.MAX_REMINDERS)
                time_into_interval = elapsed % interval
                delay_seconds = max(interval - time_into_interval, 1)
            except Exception as exc:
                self.log_debug(f"[hunt] Failed to restore reminder timing: {exc}")

        self._schedule_reminder(count=count, delay_seconds=delay_seconds, channels=channels)

    def _handle_reminder_tick(self):
        active_animals = self.get_state("active_animals", [])
        if not active_animals:
            self._clear_reminder_state()
            return schedule.CancelJob

        reminder_state = self.get_state("reminder_state") or {}
        count = int(reminder_state.get("count") or 0)
        channels = reminder_state.get("channels") or []

        if count >= self.MAX_REMINDERS:
            self._handle_forced_removal(channels)
            return schedule.CancelJob

        first_animal = active_animals[0]
        display_name = self._get_animal_display_name(first_animal).lower()
        template_index = min(count, len(self.REMINDER_MESSAGES) - 1)
        message_template = self.REMINDER_MESSAGES[template_index]

        for room in self._get_reminder_channels(channels):
            self.safe_say(message_template.format(animal=display_name), target=room)

        count += 1
        self._schedule_reminder(count=count, delay_seconds=self._reminder_interval_seconds(), channels=channels)
        return schedule.CancelJob

    def _handle_forced_removal(self, channels: Optional[List[str]] = None) -> None:
        active_animals = self.get_state("active_animals", [])
        if not active_animals:
            self._clear_reminder_state()
            return

        display_name = self._get_animal_display_name(active_animals[0]).lower()
        for room in self._get_reminder_channels(channels):
            self.safe_say(self.REMOVAL_MESSAGE.format(animal=display_name), target=room)

        self.set_state("active_animals", [])
        self._set_active_collective_noun(None)
        self._clear_reminder_state(save=False)
        self.save_state()

        if self._event_is_active():
            self._schedule_next_event_spawn()
        else:
            self._schedule_next_spawn()

    def _resume_event_scheduler(self) -> None:
        self._clear_scheduled_jobs(f"{self.name}-event_spawn")
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

    def _resume_normal_spawn_scheduler(self, next_spawn_str: str) -> None:
        self._clear_scheduled_jobs(f"{self.name}-spawn")
        next_spawn_time = datetime.fromisoformat(next_spawn_str)
        now = datetime.now(UTC)
        if now >= next_spawn_time:
            self._spawn_animal()
        else:
            remaining_seconds = (next_spawn_time - now).total_seconds()
            if remaining_seconds > 0:
                self._queue_spawn_job(remaining_seconds)

    def _get_event_settings(self) -> Dict[str, Any]:
        return self.get_config_value("event_settings", default={}) or {}

    def _get_event_delay_seconds(self, initial: bool = False) -> float:
        settings = self._get_event_settings()
        min_delay = float(settings.get("min_flock_delay_minutes", 2) or 0)
        max_delay = float(settings.get("max_flock_delay_minutes", min_delay) or 0)
        if max_delay < min_delay:
            max_delay = min_delay
        delay_minutes = min_delay if initial else random.uniform(min_delay, max_delay)
        return max(delay_minutes * 60, 1.0)

    def _get_event_group_size(self, remaining_for_species: int) -> int:
        settings = self._get_event_settings()
        min_size = max(int(settings.get("min_flock_size", 1) or 1), 1)
        max_size = int(settings.get("max_flock_size", min_size) or min_size)
        if max_size < min_size:
            max_size = min_size
        group_size = random.randint(min_size, max_size)
        return max(1, min(group_size, remaining_for_species))

    def _schedule_next_event_spawn(self, delay_seconds: Optional[float] = None, initial: bool = False) -> None:
        event_state = self.get_state("event")
        if not event_state or not event_state.get("active"):
            self.log_debug("_schedule_next_event_spawn: no active event, skipping scheduler setup")
            return
        delay = delay_seconds if delay_seconds is not None else self._get_event_delay_seconds(initial=initial)
        self._clear_scheduled_jobs(f"{self.name}-event_spawn")
        next_time = datetime.now(UTC) + timedelta(seconds=delay)
        event_state["next_spawn_time"] = next_time.isoformat()
        self.set_state("event", event_state)
        self.save_state()
        schedule.every(delay).seconds.do(self._start_event_spawn).tag(f"{self.name}-event_spawn")
        self.log_debug(f"_schedule_next_event_spawn: scheduled in {delay:.2f}s at {next_time.isoformat()}")

    def _select_next_event_species(self, event_state: Dict[str, Any]) -> Optional[str]:
        remaining_map = event_state.get("remaining", {})
        available = [k for k, v in remaining_map.items() if v > 0]
        if not available:
            return None
        chosen = random.choice(available)
        group_size = self._get_event_group_size(remaining_map.get(chosen, 0))
        event_state["current_group_animal"] = chosen
        event_state["current_group_remaining"] = group_size
        self.log_debug(f"_select_next_event_species: picked {chosen} group of {group_size}")
        return chosen

    def _finish_event(self) -> None:
        self.log_debug("_finish_event: ending migration event and resuming normal spawns")
        self._clear_scheduled_jobs(f"{self.name}-event_spawn")
        self.set_state("event", None)
        self.save_state()
        if not self.get_state("active_animals"):
            self._schedule_next_spawn()

    def _start_event_spawn(self) -> Optional[str]:
        event_state = self.get_state("event") or {}
        if not event_state.get("active"):
            self.log_debug("_start_event_spawn: no active event")
            return schedule.CancelJob

        remaining_map = event_state.get("remaining", {})
        total_remaining = sum(v for v in remaining_map.values())
        if total_remaining <= 0:
            self.log_debug("_start_event_spawn: no animals left to release")
            self._finish_event()
            return schedule.CancelJob

        if self.get_state("active_animals"):
            self.log_debug("_start_event_spawn: active_animals already present, delaying release")
            self._schedule_next_event_spawn(delay_seconds=self._get_event_delay_seconds(initial=False))
            return schedule.CancelJob

        species = event_state.get("current_group_animal")
        group_remaining = int(event_state.get("current_group_remaining") or 0)
        if not species or group_remaining <= 0 or remaining_map.get(species, 0) <= 0:
            species = self._select_next_event_species(event_state)
            group_remaining = int(event_state.get("current_group_remaining") or 0)
            if not species or group_remaining <= 0:
                self.log_debug("_start_event_spawn: failed to select next group")
                self._finish_event()
                return schedule.CancelJob

        settings = self._get_event_settings()
        escape_chance = float(settings.get("escape_chance", 0.0) or 0.0)

        # Spawn the entire flock at once
        animals_to_spawn = group_remaining
        escaped_count = 0

        # Process escapes first
        if escape_chance > 0:
            for _ in range(animals_to_spawn):
                if random.random() < escape_chance:
                    escaped_count += 1
            animals_to_spawn -= escaped_count

        if escaped_count > 0:
            self.log_debug(f"_start_event_spawn: {escaped_count} {species} escaped during release")

        # Spawn all non-escaped animals
        if animals_to_spawn > 0:
            spawned = self._spawn_animal_flock(forced_animal_key=species, count=animals_to_spawn)
            if not spawned:
                self.log_debug("_start_event_spawn: spawn failed, rescheduling")
                self._schedule_next_event_spawn()
                return schedule.CancelJob

        # Update event state
        total_processed = group_remaining
        event_state["remaining"][species] = max(0, remaining_map.get(species, 0) - total_processed)
        event_state["current_group_remaining"] = 0
        event_state["next_spawn_time"] = None
        self.set_state("event", event_state)
        self.save_state()

        # Schedule next flock spawn only after this entire flock is cleared
        if sum(event_state.get("remaining", {}).values()) > 0:
            if animals_to_spawn == 0:
                # All animals escaped, schedule next flock immediately
                self._schedule_next_event_spawn()
            # else: wait for flock to be cleared via _end_hunt
        else:
            self._finish_event()
        return schedule.CancelJob

    def on_unload(self) -> None:
        super().on_unload()
        self._clear_scheduled_jobs(self.name, f"{self.name}-spawn", f"{self.name}-event_spawn", self._reminder_tag())

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!hug(?:\s+(.+))?\s*$", self._cmd_hug, name="hug", description="Befriend the animal.")
        self.register_command(r"^\s*!release\s+(hug|hunt)\s*$", self._cmd_release, name="release", description="Release a previously caught or befriended animal.")
        self.register_command(r"^\s*!hunt(?:\s+(.*))?$", self._cmd_hunt_master, name="hunt", description="The main command for the hunt game. Use '!hunt help' for subcommands.")
        self.register_command(r"^\s*!consent\s*$", self._cmd_consent, name="consent", description="Approve the last hug request aimed at you.")
        self.register_command(r"^\s*!bang\s*$", self._cmd_bang, name="bang", description="Risky hunting - 50/50 chance to hunt or miss!")

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

    def _pick_collective_noun(self) -> str:
        """Return a random collective noun for a group of animals."""
        return random.choice(self.COLLECTIVE_NOUNS)

    def _get_active_collective_noun(self) -> str:
        return self.get_state("active_collective_noun") or "flock"

    def _set_active_collective_noun(self, noun: Optional[str]) -> None:
        self.set_state("active_collective_noun", noun)

    def _cmd_hunt_master(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
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

    def _handle_hunt_animal(self, connection: Any, event: Any, username: str) -> bool:
        if self.get_state("active_animals"):
            return self._end_hunt(connection, event, username, "hunted")
        self.safe_reply(connection, event, f"There is nothing to hunt at the moment, {self.bot.title_for(username)}.")
        return True

    def _handle_hunt_guest(self, connection: Any, event: Any, username: str, target_name: str) -> bool:
        self.safe_reply(connection, event, f"I must strongly object, {self.bot.title_for(username)}. Hunting the guests is strictly against household policy.")
        return True

    def _handle_score(self, connection: Any, event: Any, username: str, args: List[str]) -> bool:
        target_user_nick = args[0] if args else username
        self._cmd_score(connection, event, "", username, target_user_nick)
        return True

    def _handle_top(self, connection: Any, event: Any, username: str) -> bool:
        self._cmd_top(connection, event, "", username, None)
        return True

    def _handle_admin(self, connection: Any, event: Any, username: str, args: List[str]) -> bool:
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
            if len(args) not in (2, 3):
                self.safe_reply(connection, event, f"Usage: !hunt admin event <user> [{self._species_filter_usage()}]")
                return True
            return self._cmd_admin_event(connection, event, "", username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown admin command '{admin_subcommand}'.")
            return True

    def _get_animals_config(self) -> List[Dict[str, Any]]:
        themes = self.get_config_value("animal_themes", default={}) or {}
        active_theme = self.get_config_value("animal_theme", default="") or ""
        if active_theme and isinstance(themes, dict):
            theme_entry = themes.get(active_theme)
            if isinstance(theme_entry, dict):
                theme_animals = theme_entry.get("animals")
            else:
                theme_animals = theme_entry
            if isinstance(theme_animals, list):
                return theme_animals
        return self.get_config_value("animals", default=[]) or []

    def _get_animal_score_name(self, animal: Dict[str, Any]) -> str:
        return str(animal.get("score_key") or animal.get("score_name") or animal.get("name", "animal")).lower()

    def _get_animal_display_name(self, animal: Dict[str, Any]) -> str:
        return animal.get("display_name") or animal.get("name", "Animal")

    def _get_species_keys(self) -> List[str]:
        return sorted({
            key for key in (self._get_animal_score_name(animal) for animal in self._get_animals_config())
            if key
        })

    def _lookup_display_name(self, score_name: str) -> str:
        score = str(score_name).lower()
        for entry in self._get_animals_config():
            candidate = entry.get("score_key") or entry.get("score_name") or entry.get("name")
            if candidate and str(candidate).lower() == score:
                return entry.get("display_name") or entry.get("name", score_name.title())
        return score_name.title()

    def _normalize_animal_key(self, name: str) -> str:
        """Normalize user-supplied animal names to their canonical score key."""
        normalized = str(name).lower()
        for entry in self._get_animals_config():
            score = str(entry.get("score_key") or entry.get("score_name") or entry.get("name", "")).lower()
            display = str(entry.get("display_name") or entry.get("name", "")).lower()
            if normalized in (score, display):
                return score
        return normalized

    def _format_score_label(self, score_key: str) -> str:
        if "_" not in score_key:
            return score_key.title()
        base, action = score_key.rsplit("_", 1)
        display = self._lookup_display_name(base)
        return f"{display} {action.capitalize()}"

    def _species_filter_usage(self) -> str:
        options = self._get_species_keys()
        if not options:
            return "all"
        return f"{'|'.join(options)}|all"

    def _species_filter_options_text(self) -> str:
        options = self._get_species_keys()
        if not options:
            return "all"
        return f"{', '.join(options)}, or all"

    def _handle_admin_spawn(self, connection: Any, event: Any, username: str) -> bool:
        if not self.bot.is_admin(event.source): return True
        return self._cmd_admin_spawn(connection, event, "", username, None)

    def _handle_help(self, connection: Any, event: Any, username: str) -> bool:
        help_lines = [ "!hunt - Hunt the currently active animal.", "!hug - Befriend the currently active animal.", "!consent - Approve the last hug request aimed at you.", "!release <hunt|hug> - Release a captured animal.", "!hunt score [user] - Check your score.", "!hunt top - Show the leaderboard.", "!hunt help - Show this message." ]
        if self.bot.is_admin(event.source):
            help_lines.extend([
                "Admin:",
                "!hunt spawn - Force an animal to appear.",
                "!hunt admin add <user> <animal> <hunted|hugged> <amount> - Add to a score.",
                f"!hunt admin event <user> [{self._species_filter_usage()}] - Release a user's animals back into the channel over time.",
            ])

        for line in help_lines:
            self.safe_privmsg(username, line)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I have sent you the details privately.")
        return True

    def _schedule_next_spawn(self) -> None:
        if self._event_is_active():
            self.log_debug("_schedule_next_spawn: event active, skipping normal scheduling")
            return
        # Clear any existing spawn jobs to prevent duplicates
        cleared_count = self._clear_scheduled_jobs(f"{self.name}-spawn")
        if cleared_count > 0:
            self.log_debug(f"_schedule_next_spawn: cleared {cleared_count} existing spawn job(s)")

        allowed_channels = self.get_config_value("allowed_channels", default=[])
        animals = self._get_animals_config()
        if not allowed_channels or not animals:
            return

        min_h = self.get_config_value("min_hours_between_spawns", default=2)
        max_h = self.get_config_value("max_hours_between_spawns", default=10)
        delay_hours = random.uniform(min_h, max_h)
        next_spawn_time = datetime.now(UTC) + timedelta(hours=delay_hours)
        self.log_debug(f"_schedule_next_spawn: scheduling spawn in {delay_hours:.2f} hours (at {next_spawn_time.isoformat()})")

        self.set_state("next_spawn_time", next_spawn_time.isoformat())
        self.save_state()
        self._queue_spawn_job(delay_hours * 3600)

    def _queue_spawn_job(self, delay_seconds: float, target_channel: Optional[str] = None) -> None:
        """
        Schedule a single-fire spawn job identified by a token so duplicate pending jobs
        (e.g., after multiple !admin reloads) do not stack and fire back-to-back.
        """
        token = uuid.uuid4().hex
        self._spawn_job_token = token

        def _run_scheduled_spawn(job_token: str, channel_override: Optional[str] = None):
            if job_token != self._spawn_job_token:
                self.log_debug(f"_queue_spawn_job: ignoring stale spawn job token={job_token}")
                return schedule.CancelJob
            try:
                self.log_debug(f"_queue_spawn_job: executing spawn job token={job_token}, target_channel={channel_override}")
                self._spawn_animal(target_channel=channel_override)
            finally:
                # Prevent stale comparisons if another job is scheduled while this one runs
                if self._spawn_job_token == job_token:
                    self._spawn_job_token = None
            return schedule.CancelJob

        schedule.every(delay_seconds).seconds.do(_run_scheduled_spawn, token, target_channel).tag(f"{self.name}-spawn")

    def _spawn_animal(self, target_channel: Optional[str] = None, forced_animal_key: Optional[str] = None) -> bool:
        # Use a lock to prevent race conditions when multiple scheduled jobs fire simultaneously
        with self._spawn_lock:
            # Clear spawn jobs immediately to prevent race conditions
            pending_jobs = len(schedule.get_jobs(f"{self.name}-spawn"))
            schedule.clear(f"{self.name}-spawn")
            # Reset spawn token since the job has fired (or is being forced manually)
            self._spawn_job_token = None
            self.log_debug(f"_spawn_animal called (target_channel={target_channel}, cleared {pending_jobs} pending job(s))")

            animals = self._get_animals_config()
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

            # Check if there are already active animals
            existing_animals = self.get_state("active_animals", [])
            if existing_animals:
                self.log_debug(f"WARNING: active_animals already exist: {len(existing_animals)} animals")
                self.log_debug("Skipping spawn, scheduling next attempt")
                self._schedule_next_spawn()
                return False

            chosen_animal = None
            if forced_animal_key:
                normalized_key = str(forced_animal_key).lower()
                forced_pool = [a for a in animals if self._get_animal_score_name(a) == normalized_key]
                if forced_pool:
                    chosen_animal = random.choice(forced_pool).copy()
                else:
                    self.log_debug(f"_spawn_animal: forced_animal_key '{forced_animal_key}' not found in config, falling back to random")

            if not chosen_animal:
                chosen_animal = random.choice(animals).copy()
            animal = chosen_animal
            animal["score_name"] = self._get_animal_score_name(animal)
            animal["display_name"] = self._get_animal_display_name(animal)
            animal['spawned_at'] = datetime.now(UTC).isoformat()
            self.log_debug(f"Selected animal: {animal.get('display_name', animal.get('name', 'unknown'))} (forced={forced_animal_key})")

            self.set_state("active_animals", [animal])
            self._set_active_collective_noun(None)
            self.set_state("next_spawn_time", None)
            self.save_state()
            self.log_debug(f"Saved active_animal to state (now using active_animals list)")
            self._schedule_reminder(count=0, delay_seconds=self._reminder_interval_seconds(), channels=spawn_locations)

            self.log_debug(f"Announcing to {len(spawn_locations)} rooms: {spawn_locations}")
            for room in spawn_locations:
                self.log_debug(f"Sending announcement to {room}")
                self.safe_say(random.choice(self.SPAWN_ANNOUNCEMENTS), target=room)
                self.safe_say(animal.get("ascii_art", "An animal appears."), target=room)

            return True

    def _spawn_animal_flock(self, forced_animal_key: Optional[str] = None, count: int = 1, target_channel: Optional[str] = None) -> bool:
        """Spawn multiple animals at once as a flock."""
        with self._spawn_lock:
            # Clear spawn jobs immediately to prevent race conditions
            pending_jobs = len(schedule.get_jobs(f"{self.name}-spawn"))
            schedule.clear(f"{self.name}-spawn")
            self._spawn_job_token = None
            self.log_debug(f"_spawn_animal_flock called (count={count}, target_channel={target_channel}, cleared {pending_jobs} pending job(s))")

            animals_config = self._get_animals_config()
            if not animals_config:
                self.log_debug("No animals configured")
                return False

            allowed_channels = self.get_config_value("allowed_channels", default=[])
            spawn_locations = list(set([room for room in allowed_channels if room in self.bot.joined_channels and self.is_enabled(room)]))

            if target_channel and target_channel in spawn_locations:
                spawn_locations = [target_channel]

            if not spawn_locations:
                self.log_debug("No valid spawn locations")
                return False

            # Check if there are already active animals
            existing_animals = self.get_state("active_animals", [])
            if existing_animals:
                self.log_debug(f"WARNING: active_animals already exist: {len(existing_animals)} animals")
                return False

            # Create the flock
            flock = []
            spawn_time = datetime.now(UTC).isoformat()
            collective_noun = self._pick_collective_noun()

            for _ in range(count):
                chosen_animal = None
                if forced_animal_key:
                    normalized_key = str(forced_animal_key).lower()
                    forced_pool = [a for a in animals_config if self._get_animal_score_name(a) == normalized_key]
                    if forced_pool:
                        chosen_animal = random.choice(forced_pool).copy()

                if not chosen_animal:
                    chosen_animal = random.choice(animals_config).copy()

                animal = chosen_animal
                animal["score_name"] = self._get_animal_score_name(animal)
                animal["display_name"] = self._get_animal_display_name(animal)
                animal['spawned_at'] = spawn_time
                flock.append(animal)

            self.set_state("active_animals", flock)
            self._set_active_collective_noun(collective_noun)
            self.set_state("next_spawn_time", None)
            self.save_state()
            self.log_debug(f"Spawned flock of {len(flock)} {forced_animal_key or 'animals'}")
            self._schedule_reminder(count=0, delay_seconds=self._reminder_interval_seconds(), channels=spawn_locations)

            # Announce the flock
            display_name = flock[0]["display_name"] if flock else "animals"
            for room in spawn_locations:
                self.log_debug(f"Announcing flock to {room}")
                self.safe_say(random.choice(self.SPAWN_ANNOUNCEMENTS), target=room)
                self.safe_say(f"A {collective_noun} of {len(flock)} {self._pluralize(display_name, len(flock))} appears!", target=room)
                # Show the ascii art once for the flock
                if flock:
                    self.safe_say(flock[0].get("ascii_art", "Animals appear."), target=room)

            return True

    def _end_hunt(self, connection: Any, event: Any, username: str, action: str) -> bool:
        self.log_debug(f"_end_hunt called by {username}, action={action}")
        active_animals = self.get_state("active_animals", [])
        if not active_animals:
            self.log_debug("_end_hunt: no active_animals found")
            return True
        collective_noun = self._get_active_collective_noun()

        # Catch the entire flock at once
        flock_size = len(active_animals)
        first_animal = active_animals[0]

        self.log_debug(f"_end_hunt: catching entire flock of {flock_size} animals")

        # Calculate time to catch (using first animal's spawn time)
        time_to_catch_str = ""
        if 'spawned_at' in first_animal:
            try:
                spawn_time = datetime.fromisoformat(first_animal['spawned_at'])
                catch_time = datetime.now(UTC)
                duration = self._format_timedelta(catch_time - spawn_time)
                time_to_catch_str = f" in {duration}"
            except (ValueError, TypeError):
                self.log_debug("Could not parse spawn time for active animal.")

        display_name = self._get_animal_display_name(first_animal)
        user_id = self.bot.get_user_id(username)

        if self._handle_unlucky_escape(connection, event, username, user_id, active_animals):
            return True

        # Special handling for user "dead" - they MURDER animals
        is_dead = username.lower() == "dead"
        if is_dead and action == "hunted":
            action = "murdered"

        # Count animals by type and add them all to scores
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})

        animal_counts = {}
        for animal in active_animals:
            animal_score_name = self._get_animal_score_name(animal)
            score_key = f"{animal_score_name}_{action}"
            animal_counts[score_key] = animal_counts.get(score_key, 0) + 1

        for score_key, count in animal_counts.items():
            user_scores[score_key] = user_scores.get(score_key, 0) + count

        scores[user_id] = user_scores

        # Clear all animals from active_animals
        self.set_state("scores", scores)
        self.set_state("active_animals", [])
        self._set_active_collective_noun(None)
        self._clear_reminder_state(save=False)
        self.log_debug(f"_end_hunt: caught entire flock of {flock_size} animals, cleared active_animals, saved scores")
        self.save_state()

        # Record achievement progress
        if action == "hunted":
            achievement_hooks.record_animal_hunt(self.bot, username)
        elif action == "hugged":
            achievement_hooks.record_animal_hug(self.bot, username)

        # Build response message
        flock_msg = f"the entire {collective_noun} of {flock_size} {self._pluralize(display_name, flock_size)}" if flock_size > 1 else f"the {display_name}"

        # Special murder messages for user "dead"
        if is_dead and action == "murdered":
            if flock_size > 1:
                murder_msg = f"MASSACRE! All {flock_size} {self._pluralize(display_name, flock_size)} in the {collective_noun} obliterated!"
            else:
                murder_msg = random.choice(self.MURDER_MESSAGES).format(animal_name=display_name.lower())
            self.safe_reply(connection, event, f"{murder_msg}{time_to_catch_str}.")
        else:
            msg_key = "hug_message" if action == "hugged" else "hunt_message"
            custom_msg = first_animal.get(msg_key)

            if custom_msg and flock_size == 1:
                self.safe_reply(connection, event, f"{custom_msg.format(username=self.bot.title_for(username), animal=display_name)}{time_to_catch_str}.")
            else:
                self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. You have {action} {flock_msg}{time_to_catch_str}.")

        # Schedule next flock or next spawn since flock is now cleared
        if self._event_is_active():
            self.log_debug("_end_hunt: flock cleared, event active, scheduling next flock")
            self._schedule_next_event_spawn()
        else:
            self.log_debug(f"_end_hunt: flock cleared, scheduling next spawn")
            self._schedule_next_spawn()

        return True

    def _cmd_hug(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target): return False

        if match.group(1):
            target = match.group(1).strip()
            if target:
                self._cleanup_pending_hugs()
                target_id = self.bot.get_user_id(target)
                requester_id = self.bot.get_user_id(username)
                self._pending_hug_requests[target_id] = {
                    "requester_id": requester_id,
                    "requester_nick": username,
                    "target_nick": target,
                    "channel": event.target,
                    "requested_at": time.time(),
                }
            self.safe_reply(connection, event, f"While the sentiment is appreciated, {self.bot.title_for(username)}, one must always seek consent before embracing another.")
            return True

        if self.get_state("active_animals"):
            return self._end_hunt(connection, event, username, "hugged")

        self.safe_reply(connection, event, f"There is nothing to hug at the moment, {self.bot.title_for(username)}.")
        return True

    def _cmd_bang(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target): return False

        active_animals = self.get_state("active_animals", [])
        if not active_animals:
            self.safe_reply(connection, event, f"There is nothing to hunt at the moment, {self.bot.title_for(username)}.")
            return True

        # 50/50 chance to hit or miss
        if random.random() < 0.5:
            # Success! Hunt the animal normally
            return self._end_hunt(connection, event, username, "hunted")
        else:
            # Miss! Animal escapes
            flock_size = len(active_animals)
            first_animal = active_animals[0]
            display_name = self._get_animal_display_name(first_animal)
            collective_noun = self._get_active_collective_noun()

            # Clear the animals without awarding points
            self.set_state("active_animals", [])
            self._set_active_collective_noun(None)
            self._clear_reminder_state(save=False)
            self.save_state()

            # Send failure message
            if flock_size > 1:
                self.safe_reply(connection, event, f"Good heavens, {self.bot.title_for(username)}! Your reckless shooting has frightened away the entire {collective_noun} of {flock_size} {self._pluralize(display_name, flock_size)}! Perhaps next time you might consider the !hunt command instead?")
            else:
                self.safe_reply(connection, event, f"Oh dear. You missed entirely, {self.bot.title_for(username)}, and the {display_name} has escaped. I did warn you about using firearms indoors.")

            # Schedule next spawn since the animal(s) escaped
            if self._event_is_active():
                self._schedule_next_event_spawn()
            else:
                self._schedule_next_spawn()

            return True

    def _cmd_consent(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target): return False

        self._cleanup_pending_hugs()
        target_id = self.bot.get_user_id(username)
        pending = self._pending_hug_requests.get(target_id)
        if not pending:
            self.safe_reply(connection, event, f"There is no pending hug request for you, {self.bot.title_for(username)}.")
            return True

        pending_channel = pending.get("channel")
        if pending_channel and pending_channel != event.target:
            self.safe_reply(connection, event, f"Consent must be given in {pending_channel}, where the request was made.")
            return True

        requester = pending.get("requester_nick", "someone")
        del self._pending_hug_requests[target_id]
        self.safe_reply(connection, event, f"{self.bot.title_for(requester)} hugs {self.bot.title_for(username)} with their consent.")
        return True

    def _handle_unlucky_escape(self, connection: Any, event: Any, username: str, user_id: str, active_animals: List[Dict[str, Any]]) -> bool:
        if not active_animals or random.random() >= self.ESCAPE_MISHAP_CHANCE:
            return False

        first_animal = active_animals[0]
        species = self._get_animal_score_name(first_animal)
        display_name = self._get_animal_display_name(first_animal)
        display_group = self._pluralize(display_name, 2)
        mishap_msg = first_animal.get("escape_mishap_message") or f"The {display_group} wriggle free and bolt for the exit!"

        happiness_before = self._get_animal_happiness(user_id)
        new_happiness = max(0, happiness_before - 1)
        self._set_animal_happiness(user_id, new_happiness)

        follower_losses: Dict[str, int] = {}
        if new_happiness <= 0:
            followers_to_escape = random.randint(self.MIN_FOLLOWER_ESCAPE, self.MAX_FOLLOWER_ESCAPE)
            follower_losses = self._remove_random_animals_from_scores(user_id, followers_to_escape)
            self._set_animal_happiness(user_id, self.DEFAULT_ANIMAL_HAPPINESS)

        self.set_state("active_animals", [])
        self._set_active_collective_noun(None)
        self._clear_reminder_state(save=False)
        self.save_state()

        reply_parts = [f"Oh no, {self.bot.title_for(username)}! {mishap_msg}"]
        loss_msg = self._format_follower_loss(follower_losses)
        if loss_msg:
            reply_parts.append(loss_msg)
        else:
            reply_parts.append("Perhaps a calmer approach will keep the rest of your menagerie content.")

        self.safe_reply(connection, event, " ".join(reply_parts))

        if self._event_is_active():
            self._schedule_next_event_spawn()
        else:
            self._schedule_next_spawn()
        return True

    def _cmd_release(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target): return False

        if self.get_state("active_animals"):
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
        display_name = self._lookup_display_name(animal_name)

        user_scores[key_to_release] -= 1
        if user_scores[key_to_release] == 0:
            del user_scores[key_to_release]

        self.set_state("scores", scores)
        self.save_state()

        self.log_debug(f"_cmd_release: {username} released a {animal_name}, spawning replacement in {event.target}")
        self.safe_reply(connection, event, random.choice(self.RELEASE_MESSAGES).format(title=self.bot.title_for(username), animal_name=display_name))
        self._spawn_animal(target_channel=event.target)
        return True

    def _cmd_score(self, connection: Any, event: Any, msg: str, username: str, target_user_nick: str) -> bool:
        user_id = self.bot.get_user_id(target_user_nick)
        scores = self.get_state("scores", {}).get(user_id, {})
        if not scores:
            self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} has not yet interacted with any animals.")
            return True

        parts = [f"{self._format_score_label(k)}: {v}" for k, v in sorted(scores.items()) if v > 0]
        if not parts:
             self.safe_reply(connection, event, f"{self.bot.title_for(target_user_nick)} has not yet interacted with any animals.")
             return True

        self.safe_reply(connection, event, f"Score for {self.bot.title_for(target_user_nick)}: {', '.join(parts)}.")
        return True

    def _cmd_top(self, connection: Any, event: Any, msg: str, username: str, match: Any) -> bool:
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

    def _cmd_admin_spawn(self, connection: Any, event: Any, msg: str, username: str, match: Any) -> bool:
        if self.get_state("active_animals"):
            self.safe_reply(connection, event, "Animals are already active.")
            return True
        if self._spawn_animal(target_channel=event.target):
            self.safe_reply(connection, event, "As you wish. I have released an animal.")
        else:
            self.safe_reply(connection, event, f"I cannot spawn an animal in this channel ('{event.target}').")
        return True

    def _cmd_admin_add(self, connection: Any, event: Any, msg: str, username: str, args: List[str]) -> bool:
        target_user, animal_name, action, amount_str = args

        user_id = self.bot.get_user_id(target_user)
        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        score_key = f"{self._normalize_animal_key(animal_name)}_{action}"

        user_scores[score_key] = user_scores.get(score_key, 0) + int(amount_str)
        scores[user_id] = user_scores

        self.set_state("scores", scores)
        self.save_state()
        self.safe_reply(connection, event, f"Very good. Added {amount_str} to {target_user}'s {animal_name} {action} score.")
        return True

    def _cmd_admin_event(self, connection: Any, event: Any, msg: str, username: str, args: List[str]) -> bool:
        target_user = args[0]
        filter_arg = args[1] if len(args) > 1 else "all"
        species_filter = self._normalize_species_filter(filter_arg)

        if not species_filter:
            self.safe_reply(connection, event, f"Invalid animal group. Use {self._species_filter_options_text()}.")
            return True

        if self._event_is_active():
            self.safe_reply(connection, event, "An event is already in progress. Please wait for it to finish or restart the bot state.")
            return True

        user_id = self._resolve_user_id(target_user, create_if_missing=False)
        if not user_id:
            user_id = self._lookup_scores_by_nick(target_user)

        scores = self.get_state("scores", {})
        user_scores = scores.get(user_id, {})
        if not user_scores:
            # One last fallback: scan profiles for this nick and pick the one with scores
            fallback_id = self._lookup_scores_by_nick(target_user)
            if fallback_id:
                user_id = fallback_id
                user_scores = scores.get(user_id, {})

        if not user_scores:
            self.safe_reply(connection, event, f"No animals recorded for {self.bot.title_for(target_user)}.")
            return True

        totals = self._aggregate_user_animals(user_scores)
        configured_keys = {self._get_animal_score_name(a) for a in self._get_animals_config()}
        totals = {species: count for species, count in totals.items() if count > 0 and species in configured_keys}

        if species_filter != "all":
            totals = {species: count for species, count in totals.items() if species == species_filter}

        if not totals:
            self.safe_reply(connection, event, f"There are no {filter_arg} to release for {self.bot.title_for(target_user)}.")
            return True

        # Remove the animals from the user's scores immediately.
        species_to_clear = set(totals.keys()) if species_filter == "all" else {species_filter}
        updated_user_scores = {}
        for key, value in user_scores.items():
            matched = False
            for species in species_to_clear:
                if key.startswith(f"{species}_"):
                    matched = True
                    break
            if matched:
                continue
            updated_user_scores[key] = value
        if updated_user_scores:
            scores[user_id] = updated_user_scores
        elif user_id in scores:
            del scores[user_id]
        self.set_state("scores", scores)
        self.save_state()

        event_state = {
            "active": True,
            "target_user": target_user,
            "target_user_id": user_id,
            "remaining": totals,
            "current_group_animal": None,
            "current_group_remaining": 0,
            "started_at": datetime.now(UTC).isoformat(),
            "next_spawn_time": None,
        }

        self.set_state("event", event_state)
        self.save_state()

        # Remove any pending spawns so the event controls the cadence.
        self._clear_scheduled_jobs(f"{self.name}-spawn", f"{self.name}-event_spawn")
        self._schedule_next_event_spawn(initial=True)

        summary = ", ".join(f"{k}: {v}" for k, v in totals.items())
        total_count = sum(totals.values())
        self.safe_reply(connection, event, f"Understood. Releasing {total_count} animals from {self.bot.title_for(target_user)} ({summary}). They will appear in themed collectives over time.")
        return True
