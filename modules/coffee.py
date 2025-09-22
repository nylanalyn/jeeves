# modules/coffee.py
# A module for serving time-appropriate beverages.
import re
import random
import time
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder
from .base import SimpleCommandModule

def setup(bot, config):
    return Coffee(bot, config)

class Coffee(SimpleCommandModule):
    name = "coffee"
    version = "1.2.1" # Version bump for bugfix
    description = "Serves a beverage appropriate to the user's local time."

    COFFEE_DRINKS = [
        "a freshly brewed black coffee", "a delightful café au lait", "a strong espresso",
        "a perfectly balanced cappuccino", "a smooth flat white", "a comforting latte",
        "an energizing Americano", "a rich macchiato"
    ]
    TEA_DRINKS = [
        "a cup of Earl Grey tea", "a soothing chamomile tea", "a classic English Breakfast tea",
        "a fragrant jasmine green tea", "a refreshing mint tea", "a robust Assam black tea"
    ]
    EVENING_DRINKS = [
        "a warm glass of milk with a dash of nutmeg", "a caffeine-free herbal infusion",
        "a mug of hot chocolate", "a soothing cup of peppermint tea", "a decaffeinated latte"
    ]

    def __init__(self, bot, config):
        # --- Pre-super() setup ---
        # This is where we define attributes needed by _register_commands,
        # which is called by the super().__init__() method.
        self.on_config_reload(config)
        self.tf = TimezoneFinder()

        # --- super() call ---
        # Now that COOLDOWN is set, we can safely initialize the base class.
        super().__init__(bot)

        # --- Post-super() setup ---
        # Initialize the module's state.
        self.set_state("user_beverage_counts", self.get_state("user_beverage_counts", {}))
        self.save_state()

    def on_config_reload(self, config):
        self.COOLDOWN = config.get("cooldown_seconds", 10.0)
        self.beverage_limit = config.get("beverage_limit", 2)
        self.limit_reset_hours = config.get("limit_reset_hours", 1)
        self.limit_message = config.get("limit_message", "Perhaps that is enough beverages for now, {title}.")
        self.FORCE_MESSAGES = config.get(
            "force_messages",
            [
                "Very well, {title}. Against my better judgment, one coffee, served with a side of concern for your circadian rhythm.",
                "As you insist, {title}. I shall prepare the coffee, but please note that I am noting this under 'questionable life choices'.",
                "Fine. One coffee. But I shall not be held responsible for the inevitable existential dread at 3 AM."
            ]
        )

    def _register_commands(self):
        self.register_command(r"^\s*!coffee(?:\s+(--force))?\s*$", self._cmd_coffee,
                              name="coffee",
                              description="Request a beverage. Use --force to insist on coffee.",
                              cooldown=self.COOLDOWN)

    def _get_user_local_hour(self, username: str) -> int:
        """Determines the user's local hour, falling back to server UTC hour."""
        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        user_loc = user_locations.get(username.lower())

        if user_loc and 'lat' in user_loc and 'lon' in user_loc:
            tz_name = self.tf.timezone_at(lng=float(user_loc['lon']), lat=float(user_loc['lat']))
            if tz_name:
                try:
                    timezone = pytz.timezone(tz_name)
                    return datetime.now(timezone).hour
                except pytz.UnknownTimeZoneError:
                    pass
        
        return datetime.now(pytz.utc).hour

    def _cmd_coffee(self, connection, event, msg, username, match):
        title = self.bot.title_for(username)
        user_key = username.lower()
        is_forced = match.group(1) is not None
        
        # Check user's beverage limit
        user_counts = self.get_state("user_beverage_counts", {})
        user_data = user_counts.get(user_key, {"count": 0, "timestamp": 0})
        
        if time.time() - user_data.get("timestamp", 0) > self.limit_reset_hours * 3600:
            user_data = {"count": 0, "timestamp": 0}

        if user_data.get("count", 0) >= self.beverage_limit:
            self.safe_reply(connection, event, self.limit_message.format(title=title))
            return True

        local_hour = self._get_user_local_hour(username)

        response = ""
        # The logic for serving a drink
        if 5 <= local_hour < 12: # Morning
            drink = random.choice(self.COFFEE_DRINKS)
            response = f"At once, {title}. I have prepared {drink} for you."
        elif is_forced: # User insists on coffee
            drink = random.choice(self.COFFEE_DRINKS)
            tantrum = random.choice(self.FORCE_MESSAGES).format(title=title)
            response = f"{tantrum} I have prepared {drink}."
        elif 12 <= local_hour < 17: # Afternoon
            drink = random.choice(self.TEA_DRINKS)
            response = f"It is getting a little late for coffee, {title}. Might I suggest {drink} instead?"
        else: # Evening/Night
            drink = random.choice(self.EVENING_DRINKS)
            response = f"{title}, I do worry about your sleep schedule. Perhaps {drink} would be more suitable at this hour."

        self.safe_reply(connection, event, response)

        # Update and save the user's beverage count
        user_data["count"] = user_data.get("count", 0) + 1
        user_data["timestamp"] = time.time()
        user_counts[user_key] = user_data
        self.set_state("user_beverage_counts", user_counts)
        self.save_state()

        return True

