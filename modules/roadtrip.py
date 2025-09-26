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
    version = "4.0.0" # Dynamic configuration refactor
    description = "Schedules surprise roadtrips for channel members with delayed story reporting."

    # These are considered "fluff" and won't be editable at runtime.
    EVENTS = {
        "the riverside park": {"solo": ["{p1} enjoyed a quiet moment by the water..."], "duo": ["{p1} and {p2} had a long conversation..."], "group": ["{p1} and the others started an impromptu game of frisbee..."]},
        "the old museum": {"solo": ["{p1} spent a thoughtful afternoon wandering the halls..."], "duo": ["{p1} and {p2} got into a surprisingly intense debate..."], "group": ["{p1} and the group accidentally set off a minor alarm..."]},
        "the observatory": {"solo": ["{p1} looked through the grand telescope..."], "duo": ["{p1} and {p2} stayed up late, pointing out constellations..."], "group": ["{p1} and the others watched a stunning meteor shower..."]},
        "the seaside pier": {"solo": ["{p1} ate a truly questionable hot dog..."], "duo": ["{p1} and {p2} tried their luck at the arcade games..."], "group": ["{p1} and the group bravely rode the rickety old Ferris wheel..."]},
        "the midnight diner": {"solo": ["{p1} drank lukewarm coffee..."], "duo": ["{p1} and {p2} shared a plate of questionable fries..."], "group": ["{p1} and the group somehow started a friendly pancake-eating contest..."]},
        "fallback": {"solo": ["{p1} had a quiet, introspective time at {dest}."], "duo": ["{p1} and {p2} found a cozy corner and chatted for hours."], "group": ["{p1} and the group explored {dest} and had a lovely time."]}
    }
    LOCATIONS = list(set(EVENTS.keys()) - {"fallback"})
    TRIGGER_MESSAGES = ["Of course! I'll prepare the car.", "Very good! I shall ready the motor.", "An excellent notion let me fetch the keys."]

    def __init__(self, bot, config):
        super().__init__(bot)
        self.static_keys = ["events", "locations", "trigger_messages"]
        self.set_state("messages_since_last", self.get_state("messages_since_last", {}))
        self.set_state("next_trip_earliest", self.get_state("next_trip_earliest", {}))
        self.set_state("next_trip_message_threshold", self.get_state("next_trip_message_threshold", {}))
        self.set_state("current_rsvp", self.get_state("current_rsvp", None))
        self.set_state("pending_reports", self.get_state("pending_reports", []))
        self.save_state()

        self._rsvp_pattern = re.compile(rf"^\s*coming\s+{self.bot.JEEVES_NAME_RE}!?\s*\.?\s*$", re.IGNORECASE)
        self._rsvp_alt_pattern = re.compile(r"^\s*!me\s*$", re.IGNORECASE)

    def _register_commands(self):
        self.register_command(r"^\s*!roadtrip\s*$", lambda c, e, m, u, ma: self.safe_reply(c, e, "The last outing has concluded. Perhaps another soon?"), name="roadtrip")
        self.register_command(r"^\s*!roadtrip\s+trigger\s*$", self._cmd_trigger, name="roadtrip trigger", admin_only=True)

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        for report in self.get_state("pending_reports", []):
            report_time = datetime.fromisoformat(report["report_at"])
            now = datetime.now(UTC)
            remaining_seconds = (report_time - now).total_seconds()
            if remaining_seconds <= 0:
                self._report_roadtrip_events(report["id"])
            else:
                schedule.every(remaining_seconds).seconds.do(self._report_roadtrip_events, report_id=report["id"]).tag(self.name, f"report-{report['id']}")

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def on_ambient_message(self, connection, event, msg, username):
        if not self.is_enabled(event.target):
            return False
        if self._try_collect_rsvp(msg, username, event.target):
            return True
        self._increment_message_count(event.target)
        if self._should_trigger_roadtrip(event.target):
            self._open_rsvp_window(connection, event)
        return False

    def _get_or_set_channel_state(self, state_dict, channel, compute_func):
        if channel not in state_dict:
            state_dict[channel] = compute_func()
        return state_dict[channel]

    def _compute_next_trip_time(self, channel):
        min_h = self.get_config_value("min_hours_between_trips", channel, 3)
        max_h = self.get_config_value("max_hours_between_trips", channel, 18)
        return (datetime.now(UTC) + timedelta(hours=random.randint(min_h, max_h))).isoformat()

    def _compute_message_threshold(self, channel):
        min_m = self.get_config_value("min_messages_for_trigger", channel, 35)
        max_m = self.get_config_value("max_messages_for_trigger", channel, 85)
        return random.randint(min_m, max_m)

    def _should_trigger_roadtrip(self, channel: str) -> bool:
        if self.get_state("current_rsvp"): return False

        earliest_times = self.get_state("next_trip_earliest", {})
        earliest_time_str = self._get_or_set_channel_state(earliest_times, channel, lambda: self._compute_next_trip_time(channel))
        
        thresholds = self.get_state("next_trip_message_threshold", {})
        threshold = self._get_or_set_channel_state(thresholds, channel, lambda: self._compute_message_threshold(channel))
        
        messages = self.get_state("messages_since_last", {}).get(channel, 0)

        time_ok = datetime.now(UTC) >= datetime.fromisoformat(earliest_time_str)
        msgs_ok = messages >= threshold
        
        prob = self.get_config_value("trigger_probability", channel, 0.25)
        return time_ok and msgs_ok and random.random() < prob

    def _reset_trigger_conditions(self, channel: str):
        for state_key, compute_func in [
            ("messages_since_last", lambda c: 0),
            ("next_trip_earliest", self._compute_next_trip_time),
            ("next_trip_message_threshold", self._compute_message_threshold)
        ]:
            state_dict = self.get_state(state_key, {})
            state_dict[channel] = compute_func(channel)
            self.set_state(state_key, state_dict)
        self.save_state()

    def _open_rsvp_window(self, connection, event):
        join_window = self.get_config_value("join_window_seconds", event.target, 120)
        destination = random.choice(self.LOCATIONS)
        trigger_msg = random.choice(self.TRIGGER_MESSAGES)
        
        self.safe_reply(connection, event, trigger_msg)
        self.safe_reply(connection, event, f"I have in mind an excursion to {destination}. Say \"coming jeeves\" or \"!me\" within {join_window}s.")
        
        self.set_state("current_rsvp", {
            "destination": destination, "room": event.target, "participants": [],
            "close_epoch": time.time() + join_window
        })
        self.save_state()
        schedule.every(join_window).seconds.do(self._close_rsvp_window).tag(self.name, "rsvp-close")

    def _close_rsvp_window(self):
        current_rsvp = self.get_state("current_rsvp")
        if not current_rsvp: return schedule.CancelJob
        schedule.clear("rsvp-close")

        room, participants, dest = current_rsvp["room"], current_rsvp["participants"], current_rsvp["destination"]
        if participants:
            details = [f"{p} ({self.bot.pronouns_for(p)})" for p in participants]
            self.safe_say(f"To {dest}: {', '.join(details)}. Do buckle up.", target=room)
            
            report_id = f"{self.name}-{int(time.time())}"
            delay = self.get_config_value("report_delay_seconds", room, 3600)
            report_at = datetime.now(UTC) + timedelta(seconds=delay)
            
            pending = self.get_state("pending_reports", [])
            pending.append({"id": report_id, "room": room, "destination": dest, "participants": participants, "report_at": report_at.isoformat()})
            self.set_state("pending_reports", pending)
            
            schedule.every(delay).seconds.do(self._report_roadtrip_events, report_id=report_id).tag(self.name, f"report-{report_id}")
        else:
            self.safe_say(f"No takers. I shall cancel the reservation for {dest}.", target=room)
        
        self.set_state("current_rsvp", None)
        self._reset_trigger_conditions(room)
        return schedule.CancelJob

    def _report_roadtrip_events(self, report_id: str):
        pending = self.get_state("pending_reports", [])
        report = next((r for r in pending if r["id"] == report_id), None)
        if not report: return schedule.CancelJob

        self.set_state("pending_reports", [r for r in pending if r["id"] != report_id])
        self.save_state()

        p_count = len(report["participants"])
        size_key = "solo" if p_count == 1 else "duo" if p_count == 2 else "group"
        events = self.EVENTS.get(report["destination"], self.EVENTS["fallback"])
        story = random.choice(events.get(size_key, self.EVENTS["fallback"][size_key]))

        p = report["participants"]
        story = story.format(p1=p[0], p2=p[1] if p_count > 1 else '', dest=report["destination"])
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

    @admin_required
    def _cmd_trigger(self, connection, event, msg, username, match):
        if self.get_state("current_rsvp"):
            self.safe_reply(connection, event, "An RSVP is already in progress.")
        else:
            self._open_rsvp_window(connection, event)
        return True
