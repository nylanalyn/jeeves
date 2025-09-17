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
    version = "3.0.0" # Major feature update
    description = "Schedules surprise roadtrips for channel members with delayed story reporting."

    # --- NEW: Event Storylets ---
    # Organized by location, then by participant count (solo, duo, group)
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
        "the botanical gardens": {
            "solo": ["{p1} found a hidden bench in the rose garden and read for a while, undisturbed."],
            "duo": ["{p1} and {p2} got hopelessly lost in the hedge maze and had to be rescued by a gardener."],
            "group": ["{p1} and company took turns trying to identify exotic plants, with hilariously wrong results."]
        },
        "the antique arcade": {
            "solo": ["{p1} became obsessed with an old pinball machine, determined to beat a high score from 1982."],
            "duo": ["{p1} and {p2} challenged each other to a series of vintage games, the rivalry was palpable."],
            "group": ["{p1} and the rest spent a small fortune in tokens trying to win enough tickets for a lava lamp."]
        },
        "the lighthouse": {
            "solo": ["{p1} climbed all the way to the top and watched the ships on the horizon."],
            "duo": ["{p1} and {p2} told each other spooky ghost stories in the echoing chambers of the lighthouse."],
            "group": ["{p1} and the others helped the keeper polish the giant lens, a surprisingly satisfying task."]
        },
        # Adding a fallback for any locations not explicitly defined
        "fallback": {
            "solo": ["{p1} had a quiet, introspective time at {dest}."],
            "duo": ["{p1} and {p2} found a cozy corner at {dest} and chatted for hours."],
            "group": ["{p1} and the group explored {dest} and generally had a lovely time."]
        }
    }

    LOCATIONS = list(set(EVENTS.keys()) - {"fallback"}) # Auto-populate locations from events

    TRIGGER_MESSAGES = [
        "Of course, {title}; I'll prepare the car.",
        "Very good, {title}; I shall ready the motor.",
        "An excellent notion, {title}; let me fetch the keys.",
        "Splendid idea, {title}; the vehicle awaits.",
    ]

    def __init__(self, bot, config):
        super().__init__(bot)
        
        self.MIN_HOURS_BETWEEN_TRIPS = config.get("hours_between_trips", {}).get("min", 3)
        self.MAX_HOURS_BETWEEN_TRIPS = config.get("hours_between_trips", {}).get("max", 18)
        self.MIN_MESSAGES_FOR_TRIGGER = config.get("messages_for_trigger", {}).get("min", 35)
        self.MAX_MESSAGES_FOR_TRIGGER = config.get("messages_for_trigger", {}).get("max", 85)
        self.TRIGGER_PROBABILITY = config.get("trigger_probability", 0.25)
        self.JOIN_WINDOW_SECONDS = config.get("join_window_seconds", 120)
        self.REPORT_DELAY_SECONDS = 3600 # NEW: 1 hour delay for the report

        self.set_state("messages_since_last", self.get_state("messages_since_last", 0))
        self.set_state("next_trip_earliest", self.get_state("next_trip_earliest", self._compute_next_trip_time().isoformat()))
        self.set_state("next_trip_message_threshold", self.get_state("next_trip_message_threshold", self._compute_message_threshold()))
        self.set_state("current_rsvp", self.get_state("current_rsvp", None))
        self.set_state("pending_reports", self.get_state("pending_reports", [])) # NEW
        self.set_state("history", self.get_state("history", []))
        self.save_state()

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
        # ... (logic for restoring scheduled reports)
        pending_reports = self.get_state("pending_reports", [])
        for report in pending_reports:
            report_time = datetime.fromisoformat(report["report_at"])
            now = datetime.now(UTC)
            if now >= report_time:
                self._report_roadtrip_events(report["id"])
            else:
                remaining_seconds = (report_time - now).total_seconds()
                schedule.every(remaining_seconds).seconds.do(self._report_roadtrip_events, report_id=report["id"]).tag(self.name, f"report-{report['id']}")

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def on_pubmsg(self, connection, event, msg, username):
        if super().on_pubmsg(connection, event, msg, username):
            return True
        if self._try_collect_rsvp(msg, username, event.target):
            return True
        self._increment_message_count()
        if self._should_trigger_roadtrip():
            self._open_rsvp_window(connection, event)
        return False

    def _close_rsvp_window(self):
        current_rsvp = self.get_state("current_rsvp")
        if not current_rsvp: return
        schedule.clear(f"rsvp-close")

        room = current_rsvp["room"]
        participants = list(dict.fromkeys(current_rsvp.get("participants", [])))
        destination = current_rsvp["destination"]

        try:
            if participants:
                details = [f"{p} ({self.bot.pronouns_for(p)})" for p in participants]
                self.bot.connection.privmsg(room, f"Very good. Outing to {destination}: {', '.join(details)}. Do buckle up.")
                
                # NEW: Schedule the event report
                report_id = f"{self.name}-{int(time.time())}"
                report_at = datetime.now(UTC) + timedelta(seconds=self.REPORT_DELAY_SECONDS)
                pending_report = {
                    "id": report_id,
                    "room": room,
                    "destination": destination,
                    "participants": participants,
                    "report_at": report_at.isoformat()
                }
                pending_reports = self.get_state("pending_reports", [])
                pending_reports.append(pending_report)
                self.set_state("pending_reports", pending_reports)
                self.save_state()
                schedule.every(self.REPORT_DELAY_SECONDS).seconds.do(self._report_roadtrip_events, report_id=report_id).tag(self.name, f"report-{report_id}")
            else:
                self.bot.connection.privmsg(room, f"No takers. I shall cancel the reservation for {destination}.")
        except Exception as e: self._record_error(f"error announcing results: {e}")
        
        self.set_state("current_rsvp", None)
        self.save_state()
        self._reset_trigger_conditions()
    
    # --- NEW: Event Reporting Function ---
    def _report_roadtrip_events(self, report_id: str):
        pending_reports = self.get_state("pending_reports", [])
        report_to_send = None
        for report in pending_reports:
            if report["id"] == report_id:
                report_to_send = report
                break
        
        if not report_to_send:
            return schedule.CancelJob

        # Remove the report from the pending list
        new_pending_reports = [r for r in pending_reports if r["id"] != report_id]
        self.set_state("pending_reports", new_pending_reports)
        self.save_state()

        participants = report_to_send["participants"]
        destination = report_to_send["destination"]
        room = report_to_send["room"]
        
        # Determine group size
        count = len(participants)
        if count == 1:
            size_key = "solo"
        elif count == 2:
            size_key = "duo"
        else:
            size_key = "group"

        # Select the event text
        event_options = self.EVENTS.get(destination, self.EVENTS["fallback"])
        story_template = random.choice(event_options.get(size_key, self.EVENTS["fallback"][size_key]))

        # Format the names
        if count == 1:
            p1 = participants[0]
            story = story_template.format(p1=p1, dest=destination)
        elif count == 2:
            p1, p2 = participants[0], participants[1]
            story = story_template.format(p1=p1, p2=p2, dest=destination)
        else:
            p1 = participants[0]
            story = story_template.format(p1=p1, dest=destination)

        self.safe_say(f"A report from the roadtrip to {destination}: {story}", target=room)
        
        return schedule.CancelJob

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
        lines = [
            f"Triggered: {triggered}", f"Completed: {completed}",
            f"Total participants: {total_participants}",
            f"Avg participants: {avg_participants:.1f}",
            f"Popular destination: {popular_dest}",
            f"Messages: {messages_count}/{threshold} {msg_ok}",
            f"Time gate: {time_ok}"
        ]
        self.safe_reply(connection, event, f"Roadtrip stats: {'; '.join(lines)}")
        return True

    @admin_required
    def _cmd_trigger(self, connection, event, msg, username, match):
        if self.get_state("current_rsvp"):
            self.safe_reply(connection, event, "A roadtrip RSVP window is already active.")
        else:
            self._open_rsvp_window(connection, event)
        return True