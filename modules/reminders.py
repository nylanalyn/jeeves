# modules/reminders.py
# A module for setting and receiving timed reminders.
import re
import schedule
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    """Initializes the Reminders module."""
    return Reminders(bot, config)

class Reminders(SimpleCommandModule):
    """Handles setting, storing, and delivering timed reminders for users."""
    name = "reminders"
    version = "1.0.0"
    description = "Set a reminder for yourself or another user."

    def __init__(self, bot, config):
        """Initializes the module's state and schedules pending reminders."""
        super().__init__(bot)
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


    def _parse_timeframe(self, text: str) -> Optional[timedelta]:
        """Parses a human-readable timeframe into a timedelta object."""
        text = text.lower()
        
        # Matches "in X unit" (e.g., "in 10 minutes")
        match = re.match(r"in\s+(\d+)\s+(second|minute|hour|day|week)s?", text)
        if match:
            value, unit = int(match.group(1)), match.group(2)
            if unit.startswith("second"): return timedelta(seconds=value)
            if unit.startswith("minute"): return timedelta(minutes=value)
            if unit.startswith("hour"): return timedelta(hours=value)
            if unit.startswith("day"): return timedelta(days=value)
            if unit.startswith("week"): return timedelta(weeks=value)
            
        # Add more complex parsing for "at 5pm" or "tomorrow at 9am" here if needed
            
        return None

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
        
        # Find the end of the timeframe part of the message
        timeframe_match = re.match(r"^(in\s+\d+\s+\w+s?)\s+(?:to|that)?\s*(.*)", rest_of_message, re.IGNORECASE)
        
        if not timeframe_match:
            self.safe_reply(connection, event, "My apologies, I do not understand that timeframe. Please use a format like 'in 10 minutes' or 'in 2 hours'.")
            return True
            
        timeframe_str, reminder_message = timeframe_match.groups()
        
        if not reminder_message:
            self.safe_reply(connection, event, "You must provide a message for the reminder.")
            return True

        delta = self._parse_timeframe(timeframe_str)
        if not delta:
            self.safe_reply(connection, event, "I could not parse that timeframe. Please use units like 'seconds', 'minutes', 'hours', etc.")
            return True
            
        now = datetime.now(UTC)
        remind_at = now + delta
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

        # Schedule the delivery
        schedule.every(delta.total_seconds()).seconds.do(self._deliver_reminder, reminder_id=reminder_id).tag(self.name)
        
        self.safe_reply(connection, event, f"Very good, {self.bot.title_for(username)}. I shall remind {to_user} in {timeframe_str}.")
        return True
