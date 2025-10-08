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
    version = "3.1.0" # Added flavor text preference support
    description = "Provides the local time for users based on their set location."

    def __init__(self, bot):
        super().__init__(bot)
        self.tf = TimezoneFinder()

    def _register_commands(self):
        self.register_command(r"^\s*!time\s*$", self._cmd_time_self,
                              name="time",
                              description="Get the local time for your default location.",
                              cooldown=10.0) # Base cooldown, can be overridden per-channel
        self.register_command(r"^\s*!time\s+(12|24)\s*$", self._cmd_time_format,
                              name="time format",
                              description="Set your preferred time format (12-hour or 24-hour).",
                              cooldown=5.0)
        self.register_command(r"^\s*!time\s+(.+)$", self._cmd_time_other,
                              name="time other",
                              description="Get the time for another user, a location, or the server.",
                              cooldown=10.0)

    def _get_time_for_coords(self, lat: str, lon: str, country_code: Optional[str] = None, user_id: Optional[str] = None) -> Optional[str]:
        """Gets the formatted local time string for a given latitude and longitude."""
        tz_name = self.tf.timezone_at(lng=float(lon), lat=float(lat))
        if not tz_name: return None
        try:
            timezone = pytz.timezone(tz_name)
            local_time = datetime.now(timezone)

            # Check if user has a format preference set
            use_24hr = False
            if user_id:
                user_prefs = self.get_state("user_time_preferences", {})
                if user_id in user_prefs:
                    use_24hr = user_prefs[user_id] == 24
                else:
                    # Default based on location: 24-hour for European countries, 12-hour elsewhere
                    european_countries = {
                        'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
                        'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
                        'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB', 'UK', 'NO',
                        'CH', 'IS', 'LI', 'MC', 'SM', 'VA', 'AD', 'AL', 'BA', 'BY',
                        'ME', 'MK', 'MD', 'RS', 'UA'
                    }
                    use_24hr = country_code and country_code in european_countries
            else:
                # No user context, default based on country code
                european_countries = {
                    'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
                    'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
                    'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE', 'GB', 'UK', 'NO',
                    'CH', 'IS', 'LI', 'MC', 'SM', 'VA', 'AD', 'AL', 'BA', 'BY',
                    'ME', 'MK', 'MD', 'RS', 'UA'
                }
                use_24hr = country_code and country_code in european_countries

            if use_24hr:
                time_format = '%A, %B %d at %H:%M %Z'
            else:
                time_format = '%A, %B %d at %I:%M %p %Z'
            return local_time.strftime(time_format)
        except pytz.UnknownTimeZoneError:
            return None

    def _cmd_time_format(self, connection, event, msg, username, match):
        """Handle !time 12 or !time 24 to set user's time format preference."""
        user_id = self.bot.get_user_id(username)
        format_choice = int(match.group(1))

        user_prefs = self.get_state("user_time_preferences", {})
        user_prefs[user_id] = format_choice
        self.set_state("user_time_preferences", user_prefs)
        self.save_state()

        if self.has_flavor_enabled(username):
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your time format has been set to {format_choice}-hour.")
        else:
            self.safe_reply(connection, event, f"Time format set to {format_choice}-hour.")
        return True

    def _cmd_time_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        user_locations = self.bot.get_module_state("weather").get("user_locations", {})
        user_loc = user_locations.get(user_id)

        if user_loc:
            location_name = user_loc.get('short_name') or user_loc.get('display_name') or 'your location'
            country_code = user_loc.get('country_code')
            time_str = self._get_time_for_coords(user_loc['lat'], user_loc['lon'], country_code, user_id)

            if time_str:
                if self.has_flavor_enabled(username):
                    self.safe_reply(connection, event, f"For {self.bot.title_for(username)}, the time in {location_name} is {time_str}.")
                else:
                    self.safe_reply(connection, event, f"{location_name}: {time_str}")
            else:
                if self.has_flavor_enabled(username):
                    self.safe_reply(connection, event, f"My apologies, I could not determine the timezone for your location.")
                else:
                    self.safe_reply(connection, event, "Could not determine timezone.")
        else:
            server_time = datetime.now(pytz.utc).strftime('%I:%M %p %Z')
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location. The server time is {server_time}.")
            else:
                self.safe_reply(connection, event, f"No location set. Server time: {server_time}")
        return True

    def _cmd_time_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        has_flavor = self.has_flavor_enabled(username)

        if query.lower() == 'server':
            server_time = datetime.now(pytz.utc).strftime('%A, %B %d at %I:%M %p %Z')
            if has_flavor:
                self.safe_reply(connection, event, f"The server's current time is {server_time}.")
            else:
                self.safe_reply(connection, event, f"Server: {server_time}")
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
                country_code = target_user_loc.get('country_code')
                time_str = self._get_time_for_coords(target_user_loc['lat'], target_user_loc['lon'], country_code, target_user_id)
                if time_str:
                    if has_flavor:
                        self.safe_reply(connection, event, f"The time for {self.bot.title_for(query)} in {location_name} is {time_str}.")
                    else:
                        self.safe_reply(connection, event, f"{location_name}: {time_str}")
                else:
                    if has_flavor:
                        self.safe_reply(connection, event, f"I'm afraid I could not determine the timezone for {self.bot.title_for(query)}'s location.")
                    else:
                        self.safe_reply(connection, event, f"Could not determine timezone for {query}.")
                return True

        geo_data_tuple = self._get_geocode_data(query)
        if geo_data_tuple:
            lat, lon, geo_data = geo_data_tuple
            display_name = self._format_location_name(geo_data)
            country_code = geo_data.get('address', {}).get('country_code', '').upper()
            # When querying arbitrary locations, use the requesting user's preference
            requesting_user_id = self.bot.get_user_id(username)
            time_str = self._get_time_for_coords(lat, lon, country_code, requesting_user_id)
            if time_str:
                if has_flavor:
                    self.safe_reply(connection, event, f"The current time in {display_name} is {time_str}.")
                else:
                    self.safe_reply(connection, event, f"{display_name}: {time_str}")
            else:
                if has_flavor:
                    self.safe_reply(connection, event, f"My apologies, I could not find a timezone for {display_name}.")
                else:
                    self.safe_reply(connection, event, f"No timezone found for {display_name}.")
        else:
            if has_flavor:
                self.safe_reply(connection, event, f"I could not find a user or location named '{query}'.")
            else:
                self.safe_reply(connection, event, f"User or location '{query}' not found.")
        return True
