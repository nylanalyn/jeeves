# modules/reminders.py
# A module for setting and receiving timed reminders.
import re
import schedule
import time
import random
import pytz
from datetime import datetime, timezone, timedelta
from timezonefinder import TimezoneFinder
from typing import Optional, Dict, List, Tuple
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot):
    """Initializes the Reminders module."""
    return Reminders(bot)

class Reminders(SimpleCommandModule):
    """Handles setting, storing, and delivering timed reminders for users."""
    name = "reminders"
    version = "1.1.0"
    description = "Set a reminder for yourself or another user."

    def __init__(self, bot):
        """Initializes the module's state and schedules pending reminders."""
        super().__init__(bot)
        self.tf = TimezoneFinder()
        self.set_state("pending_reminders", self.get_state("pending_reminders", []))
        self.save_state()

    def _register_commands(self):
        """Registers the !remind command."""
        # Handles formats like: !remind me in 10 minutes to... OR !remind user at 5pm that...
        self.register_command(r"^\s*!remind\s+(\S+)\s+(.+)$", self._cmd_remind,
                              name="remind", description="Set a reminder. Usage: !remind <me/user> <timeframe> <message>")

    def on_load(self):
        """Schedules any reminders that were pending when the bot was last running."""
        super().on_load()
        schedule.clear(self.name)
        pending = self.get_state("pending_reminders", [])
        now = datetime.now(UTC)
        
        for reminder in pending:
            try:
                remind_time = datetime.fromisoformat(reminder["remind_at"])
                if now >= remind_time:
                    # If the bot was down, deliver overdue reminders immediately.
                    self._deliver_reminder(reminder["id"])
                else:
                    # Schedule future reminders
                    remaining_seconds = (remind_time - now).total_seconds()
                    schedule.every(remaining_seconds).seconds.do(self._deliver_reminder, reminder_id=reminder["id"]).tag(self.name)
            except (ValueError, TypeError) as e:
                self.log_debug(f"Could not schedule reminder on load: {e} - Data: {reminder}")


    def _get_user_tz(self, username: str) -> Tuple[pytz.BaseTzInfo, bool]:
        """Returns (timezone, had_location). Falls back to UTC if no location set."""
        user_id = self.bot.get_user_id(username)
        user_locations = self.bot.get_module_state("weather2").get("user_locations", {})
        user_loc = user_locations.get(user_id)
        if user_loc:
            tz_name = self.tf.timezone_at(lng=float(user_loc["lon"]), lat=float(user_loc["lat"]))
            if tz_name:
                try:
                    return pytz.timezone(tz_name), True
                except pytz.UnknownTimeZoneError:
                    pass
        return pytz.utc, False

    def _parse_timeframe(self, text: str) -> Optional[timedelta]:
        """Parses a relative timeframe like 'in 10 minutes' into a timedelta."""
        text = text.lower()
        match = re.match(r"in\s+(\d+)\s+(second|minute|hour|day|week)s?", text)
        if match:
            value, unit = int(match.group(1)), match.group(2)
            if unit.startswith("second"): return timedelta(seconds=value)
            if unit.startswith("minute"): return timedelta(minutes=value)
            if unit.startswith("hour"): return timedelta(hours=value)
            if unit.startswith("day"): return timedelta(days=value)
            if unit.startswith("week"): return timedelta(weeks=value)
        return None

    def _parse_absolute_time(self, text: str, username: str) -> Tuple[Optional[datetime], Optional[str], Optional[str], bool]:
        """
        Parses 'at 7am', 'at 3:30pm', 'tomorrow at 9am' etc.
        Returns (remind_at_utc, message, display_str, had_location).
        All fields are None on no match; remind_at_utc is None on bad time value.
        """
        match = re.match(
            r"^(tomorrow\s+)?at\s+(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s+(?:to\s+|that\s+)?(.*)",
            text, re.IGNORECASE
        )
        if not match:
            return None, None, None, False

        tomorrow_flag, hour_str, minute_str, ampm, message = match.groups()
        hour = int(hour_str)
        minute = int(minute_str) if minute_str else 0
        ampm = (ampm or "").lower()

        if ampm == "pm" and hour != 12:
            hour += 12
        elif ampm == "am" and hour == 12:
            hour = 0

        if hour > 23 or minute > 59:
            return None, None, None, False

        user_tz, had_location = self._get_user_tz(username)
        local_now = datetime.now(user_tz)
        target = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)

        if tomorrow_flag:
            target += timedelta(days=1)
        elif target <= local_now:
            target += timedelta(days=1)

        remind_at_utc = target.astimezone(UTC)
        display = target.strftime("%-I:%M %p %Z").strip()
        if tomorrow_flag:
            display = "tomorrow at " + display
        else:
            display = "at " + display

        return remind_at_utc, message.strip(), display, had_location

    def _deliver_reminder(self, reminder_id: str):
        """Finds and delivers a pending reminder, then removes it from the state."""
        pending = self.get_state("pending_reminders", [])
        reminder_to_deliver = next((r for r in pending if r.get("id") == reminder_id), None)
        
        if not reminder_to_deliver:
            return schedule.CancelJob

        # Remove the reminder from the list
        updated_pending = [r for r in pending if r.get("id") != reminder_id]
        self.set_state("pending_reminders", updated_pending)
        self.save_state()

        # Deliver the message
        from_user = reminder_to_deliver["from_user"]
        to_user = reminder_to_deliver["to_user"]
        message = reminder_to_deliver["message"]
        channel = reminder_to_deliver["channel"]
        
        self.safe_say(f"{to_user}, a reminder from {from_user}: {message}", target=channel)
        
        return schedule.CancelJob

    def _cmd_remind(self, connection, event, msg, username, match):
        """Handles the !remind command."""
        target, rest_of_message = match.groups()
        to_user = username if target.lower() == "me" else target

        remind_at = None
        reminder_message = None
        display_str = None

        # Try relative format: "in X minutes/hours/etc"
        relative_match = re.match(r"^(in\s+\d+\s+\w+s?)\s+(?:to\s+|that\s+)?(.*)", rest_of_message, re.IGNORECASE)
        if relative_match:
            timeframe_str, reminder_message = relative_match.groups()
            delta = self._parse_timeframe(timeframe_str)
            if delta:
                remind_at = datetime.now(UTC) + delta
                display_str = timeframe_str

        # Try absolute format: "[tomorrow] at HH[:MM][am/pm]"
        if remind_at is None:
            remind_at, reminder_message, display_str, had_location = self._parse_absolute_time(rest_of_message, username)
            if remind_at is not None and not had_location:
                self.safe_reply(connection, event, "Note: you have no location set, so I'm assuming UTC for that time.")

        if remind_at is None:
            self.safe_reply(connection, event,
                "My apologies, I do not understand that timeframe. "
                "Try 'in 10 minutes', 'at 7pm', or 'tomorrow at 9am'.")
            return True

        if not reminder_message:
            self.safe_reply(connection, event, "You must provide a message for the reminder.")
            return True

        now = datetime.now(UTC)
        reminder_id = f"rem-{int(time.time())}-{random.randint(100, 999)}"
        new_reminder = {
            "id": reminder_id,
            "from_user": username,
            "to_user": to_user,
            "message": reminder_message,
            "channel": event.target,
            "set_at": now.isoformat(),
            "remind_at": remind_at.isoformat()
        }

        pending = self.get_state("pending_reminders", [])
        pending.append(new_reminder)
        self.set_state("pending_reminders", pending)
        self.save_state()

        remaining_seconds = (remind_at - now).total_seconds()
        schedule.every(remaining_seconds).seconds.do(self._deliver_reminder, reminder_id=reminder_id).tag(self.name)

        self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. I shall remind {to_user} {display_str}.")
        return True
