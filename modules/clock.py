# modules/clock.py
# A module for providing accurate, timezone-aware time for users and locations.
import re
from datetime import datetime
import pytz
from timezonefinder import TimezoneFinder
from typing import Optional, Dict, Any
from .base import SimpleCommandModule

def setup(bot):
    return Clock(bot)

class Clock(SimpleCommandModule):
    name = "clock"
    version = "3.0.0" # Dynamic configuration refactor
    description = "Provides the local time for users based on their set location."

    def __init__(self, bot):
        super().__init__(bot)
        self.tf = TimezoneFinder()

    def _register_commands(self):
        self.register_command(r"^\s*!time\s*$", self._cmd_time_self, 
                              name="time", 
                              description="Get the local time for your default location.",
                              cooldown=10.0) # Base cooldown, can be overridden per-channel
        self.register_command(r"^\s*!time\s+(.+)$", self._cmd_time_other, 
                              name="time other", 
                              description="Get the time for another user, a location, or the server.",
                              cooldown=10.0)

    def _get_time_for_coords(self, lat: str, lon: str) -> Optional[str]:
        """Gets the formatted local time string for a given latitude and longitude."""
        tz_name = self.tf.timezone_at(lng=float(lon), lat=float(lat))
        if not tz_name: return None
        try:
            timezone = pytz.timezone(tz_name)
            local_time = datetime.now(timezone)
            return local_time.strftime('%A, %B %d at %I:%M %p %Z')
        except pytz.UnknownTimeZoneError:
            return None

    def _cmd_time_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        user_loc = user_locations.get(user_id)

        if user_loc:
            location_name = user_loc.get('short_name') or user_loc.get('display_name') or 'your location'
            time_str = self._get_time_for_coords(user_loc['lat'], user_loc['lon'])
            
            if time_str:
                self.safe_reply(connection, event, f"For {self.bot.title_for(username)}, the time in {location_name} is {time_str}.")
            else:
                self.safe_reply(connection, event, f"My apologies, I could not determine the timezone for your location.")
        else:
            server_time = datetime.now(pytz.utc).strftime('%I:%M %p %Z')
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location. The server time is {server_time}.")
        return True

    def _cmd_time_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()

        if query.lower() == 'server':
            server_time = datetime.now(pytz.utc).strftime('%A, %B %d at %I:%M %p %Z')
            self.safe_reply(connection, event, f"The server's current time is {server_time}.")
            return True

        users_module = self.bot.pm.plugins.get("users")
        target_user_id = None
        if users_module:
            nick_map = users_module.get_state("nick_map", {})
            target_user_id = nick_map.get(query.lower())

        if target_user_id:
            user_locations = self.bot.get_module_state("weather").get("user_locations", {})
            target_user_loc = user_locations.get(target_user_id)
            if target_user_loc:
                location_name = target_user_loc.get('short_name') or target_user_loc.get('display_name') or 'their location'
                time_str = self._get_time_for_coords(target_user_loc['lat'], target_user_loc['lon'])
                if time_str:
                    self.safe_reply(connection, event, f"The time for {self.bot.title_for(query)} in {location_name} is {time_str}.")
                else:
                    self.safe_reply(connection, event, f"I'm afraid I could not determine the timezone for {self.bot.title_for(query)}'s location.")
                return True

        geo_data_tuple = self._get_geocode_data(query)
        if geo_data_tuple:
            lat, lon, geo_data = geo_data_tuple
            display_name = self._format_location_name(geo_data)
            time_str = self._get_time_for_coords(lat, lon)
            if time_str:
                self.safe_reply(connection, event, f"The current time in {display_name} is {time_str}.")
            else:
                self.safe_reply(connection, event, f"My apologies, I could not find a timezone for {display_name}.")
        else:
            self.safe_reply(connection, event, f"I could not find a user or location named '{query}'.")
        return True
