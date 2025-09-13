# modules/chatter.py
# Daily/weekly lines + monthly animal quip (pronoun-aware).
import random
import re
import schedule
from datetime import datetime, timezone
UTC = timezone.utc

ANIMAL_WORDS = re.compile(r"\b(duck|cat|puppy|dog)\b", re.IGNORECASE)

JEEVES_DAILY_LINES = [
    "If I might venture, {title}: turning it off and on again remains the sovereign remedy.",
    "Very good, {title}. I’ve queued the chaos for after tea.",
    "Might I suggest, {title}, that the cloud be treated as weather—admired, not trusted.",
    "Indeed, {title}: one cannot argue with results, though results frequently try.",
]

SUGGESTIVE_WEEKLY_LINES = [
    "If I may, {title}: a well-timed hint often accomplishes what a thousand words cannot.",
    "The subtext appears to be applying for a promotion to text, {title}.",
]

def setup(bot): return Chatter(bot)

class Chatter:
    name = "chatter"
    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)

    def _fmt(self, line, user="nobody"):
        return line.format(
            title=self.bot.title_for(user),
            pronouns=self.bot.pronouns_for(user),
        )

    def _rand_time(self):
        return f"{random.randint(0,23):02d}:{random.randint(0,59):02d}"

    def on_load(self):
        schedule.clear(self.name)
        # daily
        schedule.every().day.at(self._rand_time()).do(self._say_daily).tag(self.name, "daily")
        # weekly
        wd = random.choice(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"])
        getattr(schedule.every(), wd).at(self._rand_time()).do(self._say_weekly).tag(self.name, "weekly")

    def on_unload(self):
        schedule.clear(self.name)

    def _say_daily(self):
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if self.st.get("last_daily") == today:
            return
        self.bot.say(self._fmt(random.choice(JEEVES_DAILY_LINES)))
        self.st["last_daily"] = today
        self.bot.save()
        # re-randomize time for tomorrow
        schedule.clear("daily")
        schedule.every().day.at(self._rand_time()).do(self._say_daily).tag(self.name, "daily")

    def _say_weekly(self):
        year, week, _ = datetime.now(UTC).isocalendar()
        key = f"{year}-{week:02d}"
        if self.st.get("last_weekly") == key:
            return
        self.bot.say(self._fmt(random.choice(SUGGESTIVE_WEEKLY_LINES)))
        self.st["last_weekly"] = key
        self.bot.save()
        # re-randomize weekday/time
        schedule.clear("weekly")
        wd = random.choice(["monday","tuesday","wednesday","thursday","friday","saturday","sunday"])
        getattr(schedule.every(), wd).at(self._rand_time()).do(self._say_weekly).tag(self.name, "weekly")

    def on_pubmsg(self, connection, event, msg, username):
        # first animal mention of the month
        if ANIMAL_WORDS.search(msg):
            month_key = datetime.now(UTC).strftime("%Y-%m")
            if self.st.get("last_animals") != month_key:
                self.st["last_animals"] = month_key
                self.bot.save()
                connection.privmsg(event.target, "If I may, there seems to be a veritable menagerie about. One risks tripping over a tail at every turn.")
                return True
        return False

