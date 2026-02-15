# modules/birthday.py
# Birthday storage and recall with on-speak greetings
import re
import random
from datetime import datetime, timezone
from typing import Any, ClassVar, Dict, List, Optional
from .base import SimpleCommandModule

def setup(bot: Any) -> 'Birthday':
    return Birthday(bot)

class Birthday(SimpleCommandModule):
    name = "birthday"
    version = "1.0.0"
    description = "Store and recall birthdays. Greets users on their birthday."

    GREETINGS: ClassVar[List[str]] = [
        "Happy birthday, {title}! Hope you have a wonderful day!",
        "It's {title}'s birthday today! Many happy returns!",
        "Happy birthday, {title}! May your day be filled with joy!",
        "A very happy birthday to {title}! Cheers!",
        "{title}, happy birthday! Wishing you all the best!",
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.set_state("birthdays", self.get_state("birthdays", {}))
        self.set_state("greeted_today", self.get_state("greeted_today", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!birthday\s+remove\s*$",
            self._cmd_remove,
            name="birthday remove",
            description="Remove your stored birthday."
        )
        self.register_command(
            r"^\s*!birthday\s+(\d{4}-\d{1,2}-\d{1,2})\s*$",
            self._cmd_set_full,
            name="birthday set full",
            description="Set your birthday with year: !birthday YYYY-MM-DD"
        )
        self.register_command(
            r"^\s*!birthday\s+(\d{1,2}-\d{1,2})\s*$",
            self._cmd_set_short,
            name="birthday set short",
            description="Set your birthday without year: !birthday MM-DD"
        )
        self.register_command(
            r"^\s*!birthday\s+(\S+)\s*$",
            self._cmd_query_other,
            name="birthday query other",
            description="Check someone else's birthday: !birthday <nick>"
        )
        self.register_command(
            r"^\s*!birthday\s*$",
            self._cmd_query_self,
            name="birthday query self",
            description="Check your own birthday."
        )

    def _cmd_set_full(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Set birthday with year: YYYY-MM-DD"""
        date_str = match.group(1)
        try:
            parsed = datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, that doesn't look like a valid date. Please use YYYY-MM-DD format (e.g. 2000-12-20).")
            return True

        if parsed.month < 1 or parsed.month > 12 or parsed.day < 1 or parsed.day > 31:
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, that doesn't look like a valid date.")
            return True

        if parsed.year > datetime.now(timezone.utc).year or parsed.year < 1900:
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, that year doesn't seem right.")
            return True

        user_id = self.bot.get_user_id(username)
        birthdays = self.get_state("birthdays", {})
        birthdays[user_id] = {"month": parsed.month, "day": parsed.day, "year": parsed.year}
        self.set_state("birthdays", birthdays)
        self.save_state()

        self.safe_reply(connection, event,
            f"{self.bot.title_for(username)}, your birthday has been set to {self._format_date(parsed.month, parsed.day, parsed.year)}.")
        return True

    def _cmd_set_short(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Set birthday without year: MM-DD"""
        date_str = match.group(1)
        parts = date_str.split("-")
        try:
            month = int(parts[0])
            day = int(parts[1])
            # Validate by constructing a date (use leap year to allow Feb 29)
            datetime(2000, month, day)
        except (ValueError, IndexError):
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, that doesn't look like a valid date. Please use MM-DD format (e.g. 12-20).")
            return True

        user_id = self.bot.get_user_id(username)
        birthdays = self.get_state("birthdays", {})
        birthdays[user_id] = {"month": month, "day": day, "year": None}
        self.set_state("birthdays", birthdays)
        self.save_state()

        self.safe_reply(connection, event,
            f"{self.bot.title_for(username)}, your birthday has been set to {self._format_date(month, day, None)}.")
        return True

    def _cmd_query_self(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Query own birthday."""
        user_id = self.bot.get_user_id(username)
        return self._show_birthday(connection, event, username, user_id, username)

    def _cmd_query_other(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Query someone else's birthday."""
        target_nick = match.group(1)

        # If it looks like a date format people commonly try, hint at the right format
        if re.match(r"^\d{1,2}/\d{1,2}", target_nick):
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, to set your birthday please use YYYY-MM-DD or MM-DD format with dashes (e.g. !birthday 2000-12-20 or !birthday 12-20).")
            return True

        target_id = self.bot.get_user_id(target_nick)
        return self._show_birthday(connection, event, username, target_id, target_nick)

    def _cmd_remove(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        """Remove stored birthday."""
        user_id = self.bot.get_user_id(username)
        birthdays = self.get_state("birthdays", {})
        if user_id in birthdays:
            del birthdays[user_id]
            self.set_state("birthdays", birthdays)
            self.save_state()
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, your birthday has been removed.")
        else:
            self.safe_reply(connection, event,
                f"{self.bot.title_for(username)}, you don't have a birthday on file.")
        return True

    def _show_birthday(self, connection: Any, event: Any, requester: str,
                       target_id: str, target_nick: str) -> bool:
        """Display a user's birthday."""
        birthdays = self.get_state("birthdays", {})
        entry = birthdays.get(target_id)
        if not entry:
            self.safe_reply(connection, event,
                f"{self.bot.title_for(requester)}, {target_nick} doesn't have a birthday on file.")
            return True

        month = entry["month"]
        day = entry["day"]
        year = entry.get("year")
        date_str = self._format_date(month, day, year)

        now = datetime.now(timezone.utc)
        is_today = (now.month == month and now.day == day)

        suffix = " -- that's today! Happy birthday!" if is_today else ""
        title = self.bot.title_for(target_nick)
        self.safe_reply(connection, event, f"{title}'s birthday is {date_str}.{suffix}")
        return True

    def on_ambient_message(self, connection: Any, event: Any, msg: str, username: str) -> bool:
        """Greet users on their birthday when they speak."""
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        birthdays = self.get_state("birthdays", {})
        entry = birthdays.get(user_id)
        if not entry:
            return False

        now = datetime.now(timezone.utc)
        if now.month != entry["month"] or now.day != entry["day"]:
            return False

        # Check if already greeted today
        greeted = self.get_state("greeted_today", {})
        today_str = now.strftime("%Y-%m-%d")

        # Reset greeted list if it's a new day
        if greeted.get("_date") != today_str:
            greeted = {"_date": today_str}

        if user_id in greeted:
            return False

        # Greet them!
        title = self.bot.title_for(username)
        greeting = random.choice(self.GREETINGS).format(title=title)
        self.safe_reply(connection, event, greeting)

        greeted[user_id] = today_str
        self.set_state("greeted_today", greeted)
        self.save_state()
        return True

    @staticmethod
    def _format_date(month: int, day: int, year: Optional[int]) -> str:
        """Format a birthday for display."""
        MONTHS = [
            "", "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December"
        ]
        month_name = MONTHS[month]
        if year:
            return f"{month_name} {day}, {year}"
        return f"{month_name} {day}"
