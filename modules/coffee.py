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
    version = "3.0.0" # Dynamic configuration refactor
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
        super().__init__(bot)
        self.tf = TimezoneFinder()
        self.set_state("user_beverage_counts", self.get_state("user_beverage_counts", {}))
        self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!coffee(?:\s+--force)?\s*$", self._cmd_coffee,
                              name="coffee",
                              description="Request a beverage. Use --force to insist.",
                              cooldown=10.0) # Base cooldown

    def _get_user_local_hour(self, user_id: str) -> int:
        """Determines the user's local hour, falling back to server UTC hour."""
        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        user_loc = user_locations.get(user_id)

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
        user_id = self.bot.get_user_id(username)
        channel = event.target
        force_flag = "--force" in msg
        
        # Fetch configuration values dynamically for the current channel
        beverage_limit = self.get_config_value("beverage_limit", channel, 2)
        limit_reset_hours = self.get_config_value("limit_reset_hours", channel, 1)
        limit_message = self.get_config_value("limit_message", channel, "Perhaps that is enough beverages for now, {title}.")
        force_messages = self.get_config_value("force_messages", channel, ["Very well, {title}. If you insist."])

        user_counts = self.get_state("user_beverage_counts", {})
        user_data = user_counts.get(user_id, {"count": 0, "timestamp": 0})
        
        if time.time() - user_data["timestamp"] > limit_reset_hours * 3600:
            user_data = {"count": 0, "timestamp": 0}

        if user_data["count"] >= beverage_limit:
            self.safe_reply(connection, event, limit_message.format(title=title))
            return True

        local_hour = self._get_user_local_hour(user_id)
        response = ""

        if 5 <= local_hour < 12:
            drink = random.choice(self.COFFEE_DRINKS)
            response = f"At once, {title}. I have prepared {drink} for you."
        elif 12 <= local_hour < 17:
            if force_flag:
                response = f"{random.choice(force_messages).format(title=title)} I shall prepare {random.choice(self.COFFEE_DRINKS)}."
            else:
                drink = random.choice(self.TEA_DRINKS)
                response = f"It is getting a little late for coffee, {title}. Might I suggest {drink} instead?"
        else:
            if force_flag:
                response = f"{random.choice(force_messages).format(title=title)} I shall prepare {random.choice(self.COFFEE_DRINKS)}."
            else:
                drink = random.choice(self.EVENING_DRINKS)
                response = f"{title}, I do worry about your sleep schedule. Perhaps {drink} would be more suitable."

        self.safe_reply(connection, event, response)
        
        user_data["count"] += 1
        user_data["timestamp"] = time.time()
        user_counts[user_id] = user_data
        self.set_state("user_beverage_counts", user_counts)
        self.save_state()
        return True
