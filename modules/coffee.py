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
    version = "1.1.1"
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
        # Load config values first so they are available for command registration.
        self.on_config_reload(config)
        # Now, initialize the base class. This will call _register_commands().
        super().__init__(bot)
        # Finally, set up state and other instance-specific properties.
        self.tf = TimezoneFinder()
        self.set_state("user_beverage_counts", self.get_state("user_beverage_counts", {}))

    def on_config_reload(self, config):
        self.COOLDOWN = config.get("cooldown_seconds", 10.0)
        self.beverage_limit = config.get("beverage_limit", 2)
        self.limit_reset_hours = config.get("limit_reset_hours", 1)
        self.limit_message = config.get("limit_message", "Perhaps that is enough beverages for now, {title}.")

    def _register_commands(self):
        self.register_command(r"^\s*!coffee\s*$", self._cmd_coffee,
                              name="coffee",
                              description="Request a beverage from Jeeves.",
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
        
        # Check user's beverage limit
        user_counts = self.get_state("user_beverage_counts", {})
        user_data = user_counts.get(user_key, {"count": 0, "timestamp": 0})
        
        # Reset count if the cooldown period has passed
        if time.time() - user_data["timestamp"] > self.limit_reset_hours * 3600:
            user_data = {"count": 0, "timestamp": 0}

        if user_data["count"] >= self.beverage_limit:
            self.safe_reply(connection, event, self.limit_message.format(title=title))
            return True

        local_hour = self._get_user_local_hour(username)

        response = ""
        if 5 <= local_hour < 12:
            drink = random.choice(self.COFFEE_DRINKS)
            response = f"At once, {title}. I have prepared {drink} for you."
        elif 12 <= local_hour < 17:
            drink = random.choice(self.TEA_DRINKS)
            response = f"It is getting a little late for coffee, {title}. Might I suggest {drink} instead?"
        else:
            drink = random.choice(self.EVENING_DRINKS)
            response = f"{title}, I do worry about your sleep schedule. Perhaps {drink} would be more suitable at this hour."

        self.safe_reply(connection, event, response)

        # Update user's count
        user_data["count"] += 1
        user_data["timestamp"] = time.time()
        user_counts[user_key] = user_data
        self.set_state("user_beverage_counts", user_counts)
        self.save_state()

        return True

