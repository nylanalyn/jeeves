# modules/chatter.py
# Enhanced daily/weekly scheduled messages + contextual responses
import random
import re
import schedule
import time
import threading
import functools
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
from .base import ResponseModule, SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    return Chatter(bot, config)

class Chatter(SimpleCommandModule, ResponseModule):
    name = "chatter"
    version = "2.3.0" # version bumped for refactor
    description = "Provides scheduled messages and conversational responses."

    # ... (patterns and response lines remain the same)
    ANIMAL_WORDS = re.compile(r"\b(?:duck|ducks|cat|cats|kitten|kittens|puppy|puppies|dog|dogs|rabbit|rabbits|bird|birds|fish|hamster|guinea\s+pig)\b", re.IGNORECASE)
    WEATHER_WORDS = re.compile(r"\b(?:rain|raining|sunny|cloudy|storm|snow|snowing|hot|cold|weather|forecast)\b", re.IGNORECASE)
    TECH_WORDS = re.compile(r"\b(?:bug|bugs|crash|crashed|error|broken|fix|deploy|deployment|server|database|code|coding|programming)\b", re.IGNORECASE)
    FOOD_WORDS = re.compile(r"\b(?:tea|coffee|lunch|dinner|breakfast|hungry|food|eat|eating|cake|biscuit|sandwich)\b", re.IGNORECASE)
    GREETING_WORDS = re.compile(r"\b(?:hello|hi|hey|good\s+morning|good\s+afternoon|good\s+evening|greetings)\b", re.IGNORECASE)
    DAILY_LINES = [ "If I might venture, {title}: turning it off and on again remains the sovereign remedy.", "Very good, {title}. I've queued the chaos for after tea.", "Might I suggest, {title}: that the cloud be treated as weather—admired, not trusted.", "Indeed, {title}: one cannot argue with results, though results frequently try.", "A most illuminating day, if I may observe. The servers appear to be in particularly cooperative spirits.", "The morning brings fresh opportunities for elegant solutions, {title}.", "I trust the digital realm is treating you kindly today, {title}.", "Another day dawns with infinite possibilities and finitely reliable networks.", "If I may note: today's challenges appear surmountable with the proper application of caffeine and logic.", ]
    WEEKLY_LINES = [ "If I may, {title}: a well-timed hint often accomplishes what a thousand words cannot.", "The subtext appears to be applying for a promotion to text, {title}.", "One observes that between the lines, there lies an entire novel of implication.", "The art of diplomatic suggestion remains undiminished by the digital age, {title}.", "I detect undertones that could benefit from a more forthright expression.", "The week's patterns suggest certain... unspoken considerations merit attention.", ]
    ANIMAL_RESPONSES = [ "If I may, there seems to be a veritable menagerie about. One risks tripping over a tail at every turn.", "The animal kingdom appears well-represented in today's discourse. Most charming.", "I do hope the creatures in question are receiving proper attention and care.", "A delightful menagerie of references, if I may observe.", "One cannot help but appreciate the diversity of our four-legged friends in conversation.", ]
    WEATHER_RESPONSES = [ "The weather does have a way of influencing both mood and server performance, I've observed.", "Nature's temperament appears as unpredictable as network connectivity, {title}.", "One must dress appropriately for both the weather and the possibility of server room visits.", "The meteorological conditions do seem to correlate with system stability in mysterious ways.", ]
    TECH_RESPONSES = [ "Ah, the eternal dance of human and machine. Most enlightening.", "I find that technical difficulties often resolve themselves with patience and proper documentation.", "The art of troubleshooting remains one of life's more philosophical pursuits.", "Technology, like a well-trained butler, performs best when properly maintained.", ]
    FOOD_RESPONSES = [ "A well-timed refreshment often provides clarity that hours of debugging cannot.", "The correlation between proper nutrition and code quality is well-established, {title}.", "I've observed that the best solutions often emerge during tea breaks.", "Sustenance for both body and mind remains essential for peak performance.", ]
    GREETING_RESPONSES = [ "Good {time_of_day}, {title}. I trust you're well?", "A pleasure to see you, {title}. The day progresses admirably.", "Greetings, {title}. I hope the day finds you in good spirits.", "Welcome, {title}. How may I be of assistance today?", ]

    def __init__(self, bot, config):
        super().__init__(bot)
        config_cooldowns = config.get("cooldowns", {})
        self._response_cooldowns = {
            "animal":   config_cooldowns.get("animal", 3600),
            "weather":  config_cooldowns.get("weather", 1800),
            "tech":     config_cooldowns.get("tech", 900),
            "food":     config_cooldowns.get("food", 1200),
            "greeting": config_cooldowns.get("greeting", 300),
        }
        self.set_state("last_daily", self.get_state("last_daily", None))
        self.set_state("last_weekly", self.get_state("last_weekly", None))
        self.set_state("last_animals", self.get_state("last_animals", None))
        self.set_state("daily_count", self.get_state("daily_count", 0))
        self.set_state("weekly_count", self.get_state("weekly_count", 0))
        self.set_state("response_counts", self.get_state("response_counts", {}))
        self.set_state("schedule_times", self.get_state("schedule_times", {}))
        self.set_state("user_interactions", self.get_state("user_interactions", {}))
        self.save_state()
        self._register_responses()
        self._register_commands()

    def _register_commands(self):
        self.register_command(r"^\s*!chatter\s+stats\s*$", self._cmd_stats,
                              name="chatter stats", admin_only=True, description="Show chatter statistics.")
        self.register_command(r"^\s*!chatter\s+test\s+daily\s*$", self._cmd_test_daily,
                              name="chatter test daily", admin_only=True, description="Force a daily message.")
        self.register_command(r"^\s*!chatter\s+test\s+weekly\s*$", self._cmd_test_weekly,
                              name="chatter test weekly", admin_only=True, description="Force a weekly message.")
    
    def _register_responses(self):
        self.add_response_pattern(self.ANIMAL_WORDS, lambda msg, user: self._handle_contextual_response("animal", msg, user), probability=0.25)
        self.add_response_pattern(self.WEATHER_WORDS, lambda msg, user: self._handle_contextual_response("weather", msg, user), probability=0.3)
        self.add_response_pattern(self.TECH_WORDS, lambda msg, user: self._handle_contextual_response("tech", msg, user), probability=0.5)
        self.add_response_pattern(self.FOOD_WORDS, lambda msg, user: self._handle_contextual_response("food", msg, user), probability=0.3)
        self.add_response_pattern(self.GREETING_WORDS, lambda msg, user: self._handle_contextual_response("greeting", msg, user), probability=0.6)

    def _handle_contextual_response(self, response_type: str, msg: str, username: str) -> Optional[str]:
        cooldown = self._response_cooldowns.get(response_type, 300)
        if cooldown < 0:
            return None
        if not self.check_rate_limit(response_type, cooldown):
            return None
        responses = {"animal": self.ANIMAL_RESPONSES, "weather": self.WEATHER_RESPONSES, "tech": self.TECH_RESPONSES, "food": self.FOOD_RESPONSES, "greeting": self.GREETING_RESPONSES,}.get(response_type, [])
        if not responses:
            return None
        response_text = self._format_line(random.choice(responses), username)
        counts = self.get_state("response_counts")
        counts[response_type] = counts.get(response_type, 0) + 1
        self.set_state("response_counts", counts)
        self.save_state()
        return response_text

    def on_load(self):
        super().on_load()
        schedule.clear(self.name)
        self._schedule_daily_message()
        self._schedule_weekly_message()

    def on_unload(self):
        super().on_unload()
        schedule.clear(self.name)

    def _get_time_of_day(self) -> str:
        hour = datetime.now(UTC).hour
        if 5 <= hour < 12: return "morning"
        elif 12 <= hour < 17: return "afternoon"
        else: return "evening"

    def _format_line(self, line: str, username: str = "nobody") -> str:
        return line.format(title=self.bot.title_for(username), pronouns=self.bot.pronouns_for(username), time_of_day=self._get_time_of_day())

    def _random_time(self) -> str:
        if random.random() < 0.7: hour = random.randint(9, 17)
        else: hour = random.randint(0, 23)
        minute = random.randint(0, 59)
        return f"{hour:02d}:{minute:02d}"

    def _schedule_daily_message(self):
        schedule.clear("daily")
        next_time = self._random_time()
        schedule.every().day.at(next_time).do(self._say_daily).tag(self.name, "daily")
        schedule_times = self.get_state("schedule_times")
        schedule_times["next_daily"] = next_time
        self.set_state("schedule_times", schedule_times)
        self.save_state()

    def _schedule_weekly_message(self):
        schedule.clear("weekly")
        weekday = random.choice(["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"])
        next_time = self._random_time()
        getattr(schedule.every(), weekday).at(next_time).do(self._say_weekly).tag(self.name, "weekly")
        schedule_times = self.get_state("schedule_times")
        schedule_times["next_weekly"] = f"{weekday} at {next_time}"
        self.set_state("schedule_times", schedule_times)
        self.save_state()

    def _say_daily(self):
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.get_state("last_daily") == today: return
        message = self._format_line(random.choice(self.DAILY_LINES))
        self.safe_say(message, self.bot.primary_channel)
        self.set_state("last_daily", today)
        self.set_state("daily_count", self.get_state("daily_count", 0) + 1)
        self.save_state()
        self._schedule_daily_message()

    def _say_weekly(self):
        year, week, _ = datetime.now(UTC).isocalendar()
        week_key = f"{year}-{week:02d}"
        if self.get_state("last_weekly") == week_key: return
        message = self._format_line(random.choice(self.WEEKLY_LINES))
        self.safe_say(message, self.bot.primary_channel)
        self.set_state("last_weekly", week_key)
        self.set_state("weekly_count", self.get_state("weekly_count", 0) + 1)
        self.save_state()
        self._schedule_weekly_message()

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        response_counts = stats.get("response_counts", {})
        schedule_times = stats.get("schedule_times", {})
        lines = [f"Daily messages sent: {stats.get('daily_count', 0)}", f"Weekly messages sent: {stats.get('weekly_count', 0)}", f"Last daily: {stats.get('last_daily', 'Never')}", f"Last weekly: {stats.get('last_weekly', 'Never')}", f"Response counts: {dict(response_counts)}", f"Next schedules: {dict(schedule_times)}"]
        self.safe_reply(connection, event, f"Chatter statistics: {'; '.join(lines)}")
        return True

    @admin_required
    def _cmd_test_daily(self, connection, event, msg, username, match):
        self._say_daily()
        self.safe_reply(connection, event, "Daily message triggered.")
        return True

    @admin_required
    def _cmd_test_weekly(self, connection, event, msg, username, match):
        self._say_weekly()
        self.safe_reply(connection, event, "Weekly message triggered.")
        return True
