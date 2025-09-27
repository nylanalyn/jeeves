# modules/roadtrip.py
# Enhanced surprise roadtrips with delayed event reporting
import random
import re
import time
import schedule
import functools
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Roadtrip(bot, config)

class Roadtrip(SimpleCommandModule):
    name = "roadtrip"
    version = "3.2.1" # Added robust state validation on init
    description = "Schedules surprise roadtrips for channel members with delayed story reporting."

    EVENTS = {
        "the riverside park": {
            "solo": ["{p1} enjoyed a quiet moment by the water, skipping stones across the surface."],
            "duo": ["{p1} and {p2} had a long conversation on a park bench, watching the boats go by."],
            "group": ["{p1} and the others started an impromptu game of frisbee that went on for hours."]
        },
        "the old museum": {
            "solo": ["{p1} spent a thoughtful afternoon wandering the halls, completely losing track of time."],
            "duo": ["{p1} and {p2} got into a surprisingly intense debate about modern art in front of a very confusing sculpture."],
            "group": ["{p1} and the group accidentally set off a minor alarm in the dinosaur exhibit, but played it cool."]
        },
        "the observatory": {
            "solo": ["{p1} looked through the grand telescope and felt a profound sense of cosmic insignificance, but in a good way."],
            "duo": ["{p1} and {p2} stayed up late, pointing out constellations to each other, both real and imagined."],
            "group": ["{p1} and the others watched a stunning meteor shower from the observatory dome."]
        },
        "the seaside pier": {
            "solo": ["{p1} ate a truly questionable hot dog while watching the waves crash against the pylons."],
            "duo": ["{p1} and {p2} tried their luck at the arcade games and left with a giant, impractical stuffed animal."],
            "group": ["{p1} and the group bravely rode the rickety old Ferris wheel, offering thrilling views and mild terror."]
        },
        "the midnight diner": {
            "solo": ["{p1} drank lukewarm coffee and listened to the old jukebox play forgotten songs."],
            "duo": ["{p1} and {p2} shared a plate of questionable fries and solved all the world's problems over three hours."],
            "group": ["{p1} and the group somehow started a friendly pancake-eating contest with the night-shift cook."]
        },
        "fallback": {
            "solo": ["{p1} had a quiet, introspective time at {dest}."],
            "duo": ["{p1} and {p2} found a cozy corner at {dest} and chatted for hours."],
            "group": ["{p1} and the group explored {dest} and generally had a lovely time."]
        }
    }

    LOCATIONS = list(set(EVENTS.keys()) - {"fallback"})

    TRIGGER_MESSAGES = [
        "Of course! I'll prepare the car.",
        "Very good! I shall ready the motor.",
        "An excellent notion let me fetch the keys.",
        "Splendid idea the vehicle awaits.",
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        
        # Robustly initialize state to handle legacy malformed data
        for key in ["messages_since_last", "next_trip_earliest", "next_trip_message_threshold"]:
            state_val = self.get_state(key, {})
            if not isinstance(state_val, dict):
                self.set_state(key, {})
        
        self.set_state("current_rsvp", self.get_state("current_rsvp", None))
        self.set_state("pending_reports", self.get_state("pending_reports", []))
        self.set_state("history", self.get_state("history", []))
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

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        pending_reports = self.get_state("pending_reports", [])
        for report in pending_reports:
            report_time = datetime.fromisoformat(report["report_at"])
            now = datetime.now(UTC)
            if now >= report_time:
                self._report_roadtrip_events(report["id"])
            else:
                remaining_seconds = (report_time - now).total_seconds()
                if remaining_seconds > 0:
                    schedule.every(remaining_seconds).seconds.do(self._report_roadtrip_events, report_id=report["id"]).tag(self.name, f"report-{report['id']}")

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target): return False
        
        if self._try_collect_rsvp(msg, username, event.target):
            return True
            
        self._increment_message_count(event.target)
        if self._should_trigger_roadtrip(event.target):
            self._open_rsvp_window(connection, event)
        return False

    def _compute_next_trip_time(self) -> datetime:
        min_h = self.get_config_value("hours_between_trips.min", default=3)
        max_h = self.get_config_value("hours_between_trips.max", default=18)
        hours = random.randint(min_h, max_h)
        return datetime.now(UTC) + timedelta(hours=hours)

    def _compute_message_threshold(self) -> int:
        min_m = self.get_config_value("messages_for_trigger.min", default=35)
        max_m = self.get_config_value("messages_for_trigger.max", default=85)
        return random.randint(min_m, max_m)

    def _time_gate_passed(self, channel: str) -> bool:
        earliest_times = self.get_state("next_trip_earliest", {})
        earliest_str = earliest_times.get(channel)
        if not earliest_str:
            earliest_times[channel] = self._compute_next_trip_time().isoformat()
            self.set_state("next_trip_earliest", earliest_times)
            self.save_state()
            return True
        return datetime.now(UTC) >= datetime.fromisoformat(earliest_str)

    def _message_gate_passed(self, channel: str) -> bool:
        counts = self.get_state("messages_since_last", {})
        thresholds = self.get_state("next_trip_message_threshold", {})
        
        threshold = thresholds.get(channel)
        if threshold is None:
            threshold = self._compute_message_threshold()
            thresholds[channel] = threshold
            self.set_state("next_trip_message_threshold", thresholds)
            self.save_state()
            
        return counts.get(channel, 0) >= threshold

    def _should_trigger_roadtrip(self, channel: str) -> bool:
        if self.get_state("current_rsvp"): return False
        if not self._time_gate_passed(channel) or not self._message_gate_passed(channel): return False
        
        trigger_prob = self.get_config_value("trigger_probability", channel, default=0.25)
        return random.random() < trigger_prob

    def _reset_trigger_conditions(self, channel: str):
        counts = self.get_state("messages_since_last", {})
        counts[channel] = 0
        self.set_state("messages_since_last", counts)

        earliest_times = self.get_state("next_trip_earliest", {})
        earliest_times[channel] = self._compute_next_trip_time().isoformat()
        self.set_state("next_trip_earliest", earliest_times)
        
        thresholds = self.get_state("next_trip_message_threshold", {})
        thresholds[channel] = self._compute_message_threshold()
        self.set_state("next_trip_message_threshold", thresholds)

        self.save_state()

    def _open_rsvp_window(self, connection, event):
        join_window = self.get_config_value("join_window_seconds", event.target, default=120)
        destination = random.choice(self.LOCATIONS)
        
        self.safe_reply(connection, event, random.choice(self.TRIGGER_MESSAGES))
        self.safe_reply(connection, event, f"Shall we? I've in mind a little excursion to {destination}. Say \"coming jeeves\" or \"!me\" within {join_window} seconds to be shown to the car.")
        
        close_time = time.time() + join_window
        self.set_state("current_rsvp", {
            "destination": destination, "room": event.target, "participants": [],
            "close_epoch": close_time
        })
        self.save_state()
        schedule.every(join_window).seconds.do(self._close_rsvp_window).tag(self.name, f"rsvp-close")

    def _close_rsvp_window(self):
        current_rsvp = self.get_state("current_rsvp")
        if not current_rsvp: return schedule.CancelJob

        schedule.clear("rsvp-close")
        room, participants, dest = current_rsvp["room"], current_rsvp["participants"], current_rsvp["destination"]
        report_delay = self.get_config_value("report_delay_seconds", room, default=3600)

        if participants:
            details = [f"{p} ({self.bot.pronouns_for(p)})" for p in participants]
            self.safe_say(f"Very good. Outing to {dest}: {', '.join(details)}. Do buckle up.", target=room)
            
            report_id = f"{self.name}-{int(time.time())}"
            report_at = datetime.now(UTC) + timedelta(seconds=report_delay)
            pending_reports = self.get_state("pending_reports", [])
            pending_reports.append({
                "id": report_id, "room": room, "destination": dest,
                "participants": participants, "report_at": report_at.isoformat()
            })
            self.set_state("pending_reports", pending_reports)
            schedule.every(report_delay).seconds.do(self._report_roadtrip_events, report_id=report_id).tag(self.name, f"report-{report_id}")
        else:
            self.safe_say(f"No takers. I shall cancel the reservation for {dest}.", target=room)
        
        self.set_state("current_rsvp", None)
        self._reset_trigger_conditions(room) # Pass the channel to reset
        return schedule.CancelJob

    def _report_roadtrip_events(self, report_id: str):
        pending_reports = self.get_state("pending_reports", [])
        report = next((r for r in pending_reports if r["id"] == report_id), None)
        if not report: return schedule.CancelJob

        self.set_state("pending_reports", [r for r in pending_reports if r["id"] != report_id])
        self.save_state()

        p_count = len(report["participants"])
        size_key = "solo" if p_count == 1 else "duo" if p_count == 2 else "group"
        
        events = self.EVENTS.get(report["destination"], self.EVENTS["fallback"])
        story = random.choice(events.get(size_key, self.EVENTS["fallback"][size_key]))

        if p_count == 1:
            story = story.format(p1=report["participants"][0], dest=report["destination"])
        elif p_count == 2:
            story = story.format(p1=report["participants"][0], p2=report["participants"][1], dest=report["destination"])
        else:
            story = story.format(p1=report["participants"][0], dest=report["destination"])

        self.safe_say(f"A report from the roadtrip to {report['destination']}: {story}", target=report["room"])
        return schedule.CancelJob

    def _try_collect_rsvp(self, msg: str, username: str, room: str) -> bool:
        current_rsvp = self.get_state("current_rsvp")
        if not current_rsvp or current_rsvp.get("room") != room: return False

        if time.time() > current_rsvp.get("close_epoch", 0):
            self._close_rsvp_window()
            return True
        
        if self._rsvp_pattern.match(msg) or self._rsvp_alt_pattern.match(msg):
            if username not in current_rsvp["participants"]:
                current_rsvp["participants"].append(username)
                self.set_state("current_rsvp", current_rsvp)
                self.save_state()
                self.safe_say(f"Noted, {username}. Mind the running board.", target=room)
            return True
        return False

    def _increment_message_count(self, channel: str):
        counts = self.get_state("messages_since_last", {})
        counts[channel] = counts.get(channel, 0) + 1
        self.set_state("messages_since_last", counts)
        self.save_state()

    def _cmd_roadtrip(self, connection, event, msg, username, match):
        self.safe_reply(connection, event, "The last outing has already concluded. Perhaps another soon?")
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        self.safe_reply(connection, event, f"Roadtrip stats: {len(stats.get('pending_reports', []))} reports pending. Message counts: {stats.get('messages_since_last', {})}")
        return True

    @admin_required
    def _cmd_trigger(self, connection, event, msg, username, match):
        if self.get_state("current_rsvp"):
            self.safe_reply(connection, event, "An RSVP is already in progress.")
        else:
            self._open_rsvp_window(connection, event)
        return True

