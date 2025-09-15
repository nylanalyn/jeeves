# modules/weather.py
# Weather module for local weather lookups using the SimpleCommandModule framework
import re
import functools
import os
import requests
from typing import Dict, Any, Optional
from datetime import datetime, timezone, timedelta
from .base import SimpleCommandModule, admin_required

def setup(bot):
    return Weather(bot)

# The admin_required decorator to be used with commands
# This decorator checks if the user is an admin before running the command
def admin_required(func):
    @functools.wraps(func)
    def wrapper(self, connection, event, msg, username, *args, **kwargs):
        if not self.bot.is_admin(username):
            return False
        return func(self, connection, event, msg, username, *args, **kwargs)
    return wrapper

class Weather(SimpleCommandModule):
    name = "weather"
    version = "1.0.0"
    description = "Provides weather information for saved or specified locations using Pirate Weather."

    # Load the API key from an environment variable for security.
    API_KEY = os.getenv("PIRATE_WEATHER_API_KEY")

    def __init__(self, bot):
        super().__init__(bot)

        # State will store user locations, e.g., {"nullveil": "Brandon, FL"}
        self.set_state("user_locations", self.get_state("user_locations", {}))
        self.save_state()

        # Check if the API key is present
        if not self.API_KEY:
            self._record_error("PIRATE_WEATHER_API_KEY environment variable is not set. Weather commands will not work.")
            print("[weather] WARNING: PIRATE_WEATHER_API_KEY environment variable is not set. Weather commands will not work.", file=sys.stderr)

    def _register_commands(self):
        self.register_command(
            r"^\s*!location\s+(.+)$",
            self._cmd_set_location,
            description="Set your default location for !weather. Usage: !location <city, state/country>"
        )
        self.register_command(
            r"^\s*!weather\s*$",
            self._cmd_weather_self,
            description="Get the weather for your default location."
        )
        self.register_command(
            r"^\s*!weather\s+(.+)$",
            self._cmd_weather_other,
            description="Get the weather for a specific location. Usage: !weather <city, state/country>"
        )
        self.register_command(
            r"^\s*!weather\s+stats\s*$",
            self._cmd_stats,
            admin_only=True,
            description="Show weather module statistics."
        )

    def _get_weather_data(self, location: str) -> Optional[Dict[str, Any]]:
        """
        Fetches weather data from the Pirate Weather API.
        This uses a geocoding service (like OpenWeather's) first to get lat/lon.
        """
        if not self.API_KEY:
            return None

        # Step 1: Geocoding (to get lat/lon from location string)
        # This uses OpenWeather's geocoding API, which is free and does not
        # require a key for simple geocoding requests.
        geo_url = f"http://api.openweathermap.org/geo/1.0/direct?q={requests.utils.quote(location)}&limit=1&appid=YOUR_OPENWEATHER_API_KEY_OR_USE_ANY_VALID_KEY"
        try:
            geo_response = requests.get(geo_url)
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            if not geo_data:
                return None
            lat = geo_data[0]["lat"]
            lon = geo_data[0]["lon"]
        except requests.exceptions.RequestException as e:
            self._record_error(f"Geocoding request failed for {location}: {e}")
            return None

        # Step 2: Fetch weather data using Pirate Weather API
        weather_url = f"https://api.pirateweather.net/forecast/{self.API_KEY}/{lat},{lon}"
        try:
            weather_response = requests.get(weather_url)
            weather_response.raise_for_status()
            return weather_response.json()
        except requests.exceptions.RequestException as e:
            self._record_error(f"Pirate Weather API request failed for {location}: {e}")
            return None

    def _format_weather_report(self, data: Dict[str, Any], username: str) -> str:
        """
        Formats the API response into a user-friendly string.
        """
        try:
            if "currently" not in data:
                return f"{username}, I could not find a weather report for that location."
            
            summary = data["currently"]["summary"]
            temperature = data["currently"]["temperature"]
            
            # The timezone from the API is often a string like "America/New_York"
            timezone_str = data.get("timezone", "UTC")
            
            # Format the time of the report
            report_time_utc = datetime.fromtimestamp(data["currently"]["time"], tz=timezone.utc)
            report_time_local = report_time_utc.astimezone(pytz.timezone(timezone_str))
            
            title = self.bot.title_for(username)
            return f"{title} {username}, the weather in {data['timezone']} is currently {summary} with a temperature of {temperature}°F. (Reported at {report_time_local.strftime('%H:%M %Z')})"
        except Exception as e:
            self._record_error(f"Failed to format weather report: {e}")
            return f"{username}, I'm afraid I could not format the weather report."

    def _cmd_set_location(self, connection, event, msg, username, match):
        location = match.group(1).strip()
        user_locations = self.get_state("user_locations")
        user_locations[username.lower()] = location
        self.set_state("user_locations", user_locations)
        self.save_state()
        self.safe_reply(connection, event, f"{username}, I have saved your location as '{location}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        user_locations = self.get_state("user_locations")
        location = user_locations.get(username.lower())

        if not location:
            self.safe_reply(connection, event, f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one.")
            return True

        weather_data = self._get_weather_data(location)
        if weather_data:
            report = self._format_weather_report(weather_data, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not fetch the weather for your location.")
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        location = match.group(1).strip()
        weather_data = self._get_weather_data(location)
        
        if weather_data:
            report = self._format_weather_report(weather_data, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not find a weather report for '{location}'.")
        return True
    
    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state("stats", {})
        locations_set = len(self.get_state("user_locations", {}))
        self.safe_reply(connection, event, f"Weather stats: {locations_set} users have set a location.")
        return True

    def on_pubmsg(self, connection, event, msg, username):
        return super().on_pubmsg(connection, event, msg, username)