# modules/clock.py
# A module for providing accurate, timezone-aware time using centralized geolocation.
import re
from datetime import datetime
import pytz
from typing import Optional
from timezonefinder import TimezoneFinder
from .base import SimpleCommandModule

def setup(bot, config):
    return Clock(bot, config)

class Clock(SimpleCommandModule):
    name = "clock"
    version = "1.2.1"
    description = "Provides the local time for users based on their set location."

    def __init__(self, bot, config):
        # Define attributes before calling super().__init__
        self.tf = TimezoneFinder()
        self.on_config_reload(config)
        
        # Now call the parent constructor, which will safely register commands
        super().__init__(bot)

    def on_config_reload(self, config):
        self.COOLDOWN = config.get("cooldown_seconds", 10.0)

    def _register_commands(self):
        self.register_command(r"^\s*!time\s*$", self._cmd_time_self, 
                              name="time", 
                              description="Get the local time for your default location.",
                              cooldown=self.COOLDOWN)
        self.register_command(r"^\s*!time\s+(.+)$", self._cmd_time_other, 
                              name="time other", 
                              description="Get the time for another user, a location, or the server.",
                              cooldown=self.COOLDOWN)

    def _get_time_for_coords(self, lat: str, lon: str) -> Optional[str]:
        """Gets the formatted local time string for a given latitude and longitude."""
        tz_name = self.tf.timezone_at(lng=float(lon), lat=float(lat))
        if not tz_name:
            return None
        
        try:
            timezone = pytz.timezone(tz_name)
            local_time = datetime.now(timezone)
            return local_time.strftime('%A, %B %d at %I:%M %p %Z')
        except pytz.UnknownTimeZoneError:
            self._record_error(f"Could not find timezone '{tz_name}'.")
            return None

    def _cmd_time_self(self, connection, event, msg, username, match):
        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        user_loc = user_locations.get(username.lower())

        if user_loc:
            time_str = self._get_time_for_coords(user_loc['lat'], user_loc['lon'])
            location_name = user_loc.get('short_name', user_loc.get('display_name', 'your location'))
            if time_str:
                self.safe_reply(connection, event, f"For {self.bot.title_for(username)}, the time in {location_name} is {time_str}.")
            else:
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not determine the timezone for your location.")
        else:
            server_time = datetime.now(pytz.utc).strftime('%I:%M %p %Z')
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location. The server time is {server_time}. Use '!location <city>' to set yours.")
        return True

    def _cmd_time_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()

        if query.lower() == 'server':
            server_time = datetime.now(pytz.utc).strftime('%A, %B %d at %I:%M %p %Z')
            self.safe_reply(connection, event, f"The server's current time is {server_time}.")
            return True

        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        target_user_loc = user_locations.get(query.lower())
        
        if target_user_loc:
            time_str = self._get_time_for_coords(target_user_loc['lat'], target_user_loc['lon'])
            location_name = target_user_loc.get('short_name', target_user_loc.get('display_name', 'their location'))
            if time_str:
                self.safe_reply(connection, event, f"The time for {self.bot.title_for(query)} in {location_name} is {time_str}.")
            else:
                self.safe_reply(connection, event, f"I'm afraid I could not determine the timezone for {self.bot.title_for(query)}'s location.")
        else:
            # Use the centralized geocoding method from the base class
            geo_data_tuple = self._get_geocode_data(query)
            if geo_data_tuple:
                lat, lon, geo_data = geo_data_tuple
                # Use the centralized formatting method
                display_name = self._format_location_name(geo_data)
                time_str = self._get_time_for_coords(lat, lon)
                if time_str:
                    self.safe_reply(connection, event, f"The current time in {display_name} is {time_str}.")
                else:
                    self.safe_reply(connection, event, f"My apologies, I could not find a timezone for {display_name}.")
            else:
                self.safe_reply(connection, event, f"I could not find a user or location named '{query}'.")
        return True

