# modules/roadtrip.py
# Enhanced surprise roadtrips using the SimpleCommandModule framework
import random
import re
import time
import schedule
import functools
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Roadtrip(bot, config)

class Roadtrip(SimpleCommandModule):
    name = "roadtrip"
    version = "2.3.1" # version bumped
    description = "Schedules surprise roadtrips for channel members."

    # ... (LOCATIONS and TRIGGER_MESSAGES remain the same)
    LOCATIONS = [ "the riverside park", "the old museum", "the observatory", "the seaside pier", "the midnight diner", "the botanical gardens", "the antique arcade", "the lighthouse", "the market square", "the hilltop ruins", "the art-house cinema", "the railway depot", "the speakeasy", "the planetarium", "the neon alley", "the tea pavilion", "the bookshop maze", "the clocktower", "the rooftops", "the brothel", "the funfair", "the stormbreak causeway", ]
    TRIGGER_MESSAGES = [ "Of course, {title}; I'll prepare the car.", "Very good, {title}; I shall ready the motor.", "An excellent notion, {title}; let me fetch the keys.", "Splendid idea, {title}; the vehicle awaits.", ]

    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.MIN_HOURS_BETWEEN_TRIPS = config.get("hours_between_trips", {}).get("min", 3)
        self.MAX_HOURS_BETWEEN_TRIPS = config.get("hours_between_trips", {}).get("max", 18)
        self.MIN_MESSAGES_FOR_TRIGGER = config.get("messages_for_trigger", {}).get("min", 35)
        self.MAX_MESSAGES_FOR_TRIGGER = config.get("messages_for_trigger", {}).get("max", 85)
        self.TRIGGER_PROBABILITY = config.get("trigger_probability", 0.25)
        self.JOIN_WINDOW_SECONDS = config.get("join_window_seconds", 120)
        self.MAX_HISTORY_ENTRIES = 20

        # ... (rest of the __init__ function remains the same)
        self.set_state("messages_since_last", self.get_state("messages_since_last", 0))
        self.set_state("next_trip_earliest", self.get_state("next_trip_earliest", self._compute_next_trip_time().isoformat()))
        self.set_state("next_trip_message_threshold", self.get_state("next_trip_message_threshold", self._compute_message_threshold()))
        self.set_state("current_rsvp", self.get_state("current_rsvp", None))
        self.set_state("history", self.get_state("history", []))
        self.set_state("stats", self.get_state("stats", {"trips_triggered": 0, "trips_completed": 0, "total_participants": 0, "messages_at_triggers": [], "most_popular_destination": None, "average_participants": 0.0}))
        self.save_state()
        self._rsvp_pattern = re.compile(rf"^\s*coming\s+{self.bot.JEEVES_NAME_RE}!?\s*\.?\s*$", re.IGNORECASE)
        self._rsvp_alt_pattern = re.compile(r"^\s*!me\s*$", re.IGNORECASE)

    def _register_commands(self):
        self.register_command(r"^\s*!roadtrip\s*$", self._cmd_roadtrip,
                              name="roadtrip", description="Show details of the most recent roadtrip.")
        self.register_command(r"^\s*!roadtrip\s+stats\s*$", self._cmd_stats,
                              name="roadtrip stats", admin_only=True, description="Show roadtrip statistics.")
        self.register_command(r"^\s*!roadtrip\s+trigger\s*$", self._cmd_trigger,
                              name="roadtrip trigger", admin_only=True, description="Force a roadtrip to start.")
    
    # ... (rest of the functions remain the same)
    def on_load(self):
        super().on_load()
        schedule.clear(f"{self.name}-close")
        current_rsvp = self.get_state("current_rsvp")
        if current_rsvp:
            open_until = float(current_rsvp.get("close_epoch", 0))
            now = time.time()
            if now >= open_until:
                self._close_rsvp_window()
            else:
                remaining_seconds = int(open_until - now)
                if remaining_seconds > 0:
                    schedule.every(remaining_seconds).seconds.do(self._close_rsvp_window_scheduled).tag(f"{self.name}-close")

    def on_unload(self):
        super().on_unload()
        schedule.clear(f"{self.name}-close")

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True
        if self._try_collect_rsvp(msg, username, event.target):
            return True
        self._increment_message_count()
        if self._should_trigger_roadtrip():
            self._open_rsvp_window(connection, event.target)
        return False

    def _compute_next_trip_time(self) -> datetime:
        hours = random.randint(self.MIN_HOURS_BETWEEN_TRIPS, self.MAX_HOURS_BETWEEN_TRIPS)
        return datetime.now(UTC) + timedelta(hours=hours)

    def _compute_message_threshold(self) -> int:
        return random.randint(self.MIN_MESSAGES_FOR_TRIGGER, self.MAX_MESSAGES_FOR_TRIGGER)

    def _time_gate_passed(self) -> bool:
        try:
            earliest_str = self.get_state("next_trip_earliest")
            if not earliest_str: return True
            earliest = datetime.fromisoformat(earliest_str)
            return datetime.now(UTC) >= earliest
        except (ValueError, TypeError):
            self.set_state("next_trip_earliest", self._compute_next_trip_time().isoformat())
            self.save_state()
            return False

    def _message_gate_passed(self) -> bool:
        message_count = self.get_state("messages_since_last", 0)
        threshold = self.get_state("next_trip_message_threshold", 0)
        return message_count >= threshold

    def _should_trigger_roadtrip(self) -> bool:
        if self.get_state("current_rsvp"): return False
        if not self._time_gate_passed() or not self._message_gate_passed(): return False
        return random.random() < self.TRIGGER_PROBABILITY

    def _reset_trigger_conditions(self):
        self.set_state("messages_since_last", 0)
        self.set_state("next_trip_earliest", self._compute_next_trip_time().isoformat())
        self.set_state("next_trip_message_threshold", self._compute_message_threshold())
        self.save_state()

    def _open_rsvp_window(self, connection, event):
        destination = random.choice(self.LOCATIONS)
        trigger_msg = random.choice(self.TRIGGER_MESSAGES)
        title = self.bot.title_for("nobody")
        self.safe_reply(connection, event, trigger_msg.format(title=title))
        self.safe_reply(connection, event, f"Shall we? I've in mind a little excursion to {destination}. Say \"coming jeeves!\" or \"!me\" within {self.JOIN_WINDOW_SECONDS} seconds to be shown to the car.")
        now = datetime.now(UTC)
        close_time = time.time() + self.JOIN_WINDOW_SECONDS
        rsvp_state = {"destination": destination, "room": event.target, "participants": [], "triggered_at": now.isoformat(), "close_epoch": close_time, "messages_at_trigger": self.get_state("messages_since_last", 0)}
        self.set_state("current_rsvp", rsvp_state)
        self.save_state()
        schedule.every(self.JOIN_WINDOW_SECONDS).seconds.do(self._close_rsvp_window_scheduled).tag(f"{self.name}-close")
        stats = self.get_state("stats")
        stats["trips_triggered"] = stats.get("trips_triggered", 0) + 1
        messages_list = stats.get("messages_at_triggers", [])
        messages_list.append(rsvp_state["messages_at_trigger"])
        stats["messages_at_triggers"] = messages_list[-20:]
        self.set_state("stats", stats)
        self.save_state()

    def _close_rsvp_window_scheduled(self):
        self._close_rsvp_window()
        return schedule.CancelJob

    def _close_rsvp_window(self):
        current_rsvp = self.get_state("current_rsvp")
        if not current_rsvp: return
        schedule.clear(f"{self.name}-close")
        room = current_rsvp["room"]
        participants = list(dict.fromkeys(current_rsvp.get("participants", [])))
        destination = current_rsvp["destination"]
        history_entry = {"date_iso": current_rsvp["triggered_at"], "participants": participants, "messages_at_trigger": current_rsvp["messages_at_trigger"], "destination": destination, "room": room, "participant_count": len(participants)}
        history = self.get_state("history", [])
        history.append(history_entry)
        if len(history) > self.MAX_HISTORY_ENTRIES: history = history[-self.MAX_HISTORY_ENTRIES:]
        stats = self.get_state("stats")
        stats["trips_completed"] = stats.get("trips_completed", 0) + 1
        stats["total_participants"] = stats.get("total_participants", 0) + len(participants)
        completed = stats["trips_completed"]
        if completed > 0: stats["average_participants"] = stats["total_participants"] / completed
        dest_counts = {}
        for h in history:
            dest = h.get("destination")
            if dest: dest_counts[dest] = dest_counts.get(dest, 0) + 1
        if dest_counts: stats["most_popular_destination"] = max(dest_counts, key=dest_counts.get)
        self.set_state("history", history)
        self.set_state("current_rsvp", None)
        self.set_state("stats", stats)
        self.save_state()
        try:
            if participants:
                details = [f"{p} ({self.bot.pronouns_for(p)})" for p in participants]
                self.bot.connection.privmsg(room, f"Very good. Outing to {destination}: {', '.join(details)}. Do buckle up.")
            else:
                self.bot.connection.privmsg(room, f"No takers. I shall cancel the reservation for {destination}.")
        except Exception as e: self._record_error(f"error announcing results: {e}")
        self._reset_trigger_conditions()

    def _try_collect_rsvp(self, msg: str, username: str, room: str) -> bool:
        current_rsvp = self.get_state("current_rsvp")
        if not current_rsvp or current_rsvp.get("room") != room: return False
        close_time = float(current_rsvp.get("close_epoch", 0))
        if time.time() > close_time:
            self._close_rsvp_window()
            return True
        if self._rsvp_pattern.match(msg) or self._rsvp_alt_pattern.match(msg):
            participants = current_rsvp.get("participants", [])
            if username not in participants:
                participants.append(username)
                current_rsvp["participants"] = participants
                self.set_state("current_rsvp", current_rsvp)
                self.save_state()
                self.safe_say(f"Noted, {username}. Mind the running board.", target=room)
            return True
        return False

    def _increment_message_count(self):
        self.set_state("messages_since_last", self.get_state("messages_since_last", 0) + 1)
        self.save_state()

    def _answer_latest(self, connection, room: str, username: str):
        history = self.get_state("history", [])
        if not history:
            self.safe_say(f"{username}, no roadtrips on the books yet, {self.bot.title_for(username)}.", target=room)
            return True
        last_trip = history[-1]
        when = last_trip.get("date_iso", "unknown time")[:16]
        participants = last_trip.get("participants", [])
        destination = last_trip.get("destination", "parts unknown")
        if participants:
            details = [f"{p} ({self.bot.pronouns_for(p)})" for p in participants]
            self.safe_say(f"{username}, most recent outing to {destination} ({when}): {', '.join(details)}.", target=room)
        else:
            self.safe_say(f"{username}, the most recent outing to {destination} ({when}) departed without passengers, {self.bot.title_for(username)}.", target=room)
        return True

    def _cmd_roadtrip(self, connection, event, msg, username, match):
        return self._answer_latest(connection, event.target, username)

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state("stats")
        triggered = stats.get("trips_triggered", 0)
        completed = stats.get("trips_completed", 0)
        total_participants = stats.get("total_participants", 0)
        avg_participants = stats.get("average_participants", 0.0)
        popular_dest = stats.get("most_popular_destination", "None")
        messages_count = self.get_state("messages_since_last", 0)
        threshold = self.get_state("next_trip_message_threshold", 0)
        time_ok = "✓" if self._time_gate_passed() else "✗"
        msg_ok = "✓" if self._message_gate_passed() else "✗"
        lines = [f"Triggered: {triggered}", f"Completed: {completed}", f"Total participants: {total_participants}", f"Avg participants: {avg_participants:.1f}", f"Popular destination: {popular_dest}", f"Messages: {messages_count}/{threshold} {msg_ok}", f"Time gate: {time_ok}"]
        self.safe_reply(connection, event, f"Roadtrip stats: {'; '.join(lines)}")
        return True

    @admin_required
    def _cmd_trigger(self, connection, event, msg, username, match):
        if self.get_state("current_rsvp"):
            self.safe_reply(connection, event, "A roadtrip RSVP window is already active.")
        else:
            self._open_rsvp_window(connection, event.target)
        return True