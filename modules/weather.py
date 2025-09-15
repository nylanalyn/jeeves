# modules/weather.py
# Weather module for local weather lookups
import re
import functools
import os
import requests
import sys
import pytz
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from .base import SimpleCommandModule, ResponseModule, admin_required

def setup(bot):
    return Weather(bot)

class Weather(SimpleCommandModule, ResponseModule):
    name = "weather"
    version = "1.1.0"
    description = "Provides weather information for saved or specified locations using Pirate Weather."

    API_KEY = os.getenv("PIRATE_WEATHER_API_KEY")

    def __init__(self, bot):
        super().__init__(bot)
        self.set_state("user_locations", self.get_state("user_locations", {}))
        self.save_state()

        if not self.API_KEY:
            self._record_error("PIRATE_WEATHER_API_KEY environment variable is not set. Weather commands will not work.")
            print("[weather] WARNING: PIRATE_WEATHER_API_KEY environment variable is not set.", file=sys.stderr)
        
        self._register_commands()
        self._register_responses()

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

    def _register_responses(self):
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        weather_pattern = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what's\s+the|how\s+is\s+the|tell\s+me\s+about\s+the)?\s*weather(?:[\s?]|$)",
            re.IGNORECASE
        )
        
        self.add_response_pattern(
            weather_pattern,
            lambda msg, user: self._handle_natural_weather(msg, user),
            probability=1.0
        )

    def _handle_natural_weather(self, msg: str, username: str) -> Optional[str]:
        user_locations = self.get_state("user_locations")
        location_input = user_locations.get(username.lower())
        
        if not location_input:
            return f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one."

        weather_data_tuple = self._get_weather_data(location_input)
        if weather_data_tuple:
            weather_data, location_name = weather_data_tuple
            return self._format_weather_report(weather_data, location_name, username)
        else:
            return f"{username}, I'm afraid I could not fetch the weather for your location."

    def _get_weather_data(self, location: str) -> Optional[Tuple[Dict[str, Any], str]]:
        if not self.API_KEY:
            return None

        geo_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location)}&format=json&limit=1"
        try:
            geo_response = requests.get(geo_url, headers={'User-Agent': 'JeevesIRCBot'})
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            if not geo_data:
                return None
            lat = geo_data[0]["lat"]
            lon = geo_data[0]["lon"]
            location_name = geo_data[0]["display_name"]
        except requests.exceptions.RequestException as e:
            self._record_error(f"Geocoding request failed for {location}: {e}")
            return None

        weather_url = f"https://api.pirateweather.net/forecast/{self.API_KEY}/{lat},{lon}"
        try:
            weather_response = requests.get(weather_url)
            weather_response.raise_for_status()
            weather_data = weather_response.json()
            return (weather_data, location_name)
        except requests.exceptions.RequestException as e:
            self._record_error(f"Pirate Weather API request failed for {location}: {e}")
            return None

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, username: str) -> str:
        try:
            if "currently" not in data:
                return f"{username}, I could not find a weather report for that location."
            
            currently = data["currently"]
            summary = currently.get("summary", "no summary")
            temperature = currently.get("temperature", "N/A")
            feels_like = currently.get("apparentTemperature", "N/A")
            humidity = currently.get("humidity", "N/A")
            wind_speed = currently.get("windSpeed", "N/A")
            
            timezone_str = data.get("timezone", "UTC")
            
            try:
                import pytz
                report_time_utc = datetime.fromtimestamp(currently.get("time", 0), tz=timezone.utc)
                report_time_local = report_time_utc.astimezone(pytz.timezone(timezone_str))
                formatted_time = report_time_local.strftime('%H:%M %Z')
            except ImportError:
                formatted_time = "time unknown"
                print("[weather] WARNING: 'pytz' library not found. Timezone formatting disabled.", file=sys.stderr)

            title = self.bot.title_for(username)
            
            return (
                f"{title} {username}, the weather in {location_name} is currently {summary}. "
                f"The temperature is {temperature}°F, and it feels like {feels_like}°F. "
                f"Wind speed is {wind_speed} mph and humidity is {int(humidity * 100)}%. "
                f"(Reported at {formatted_time})"
            )
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
        location_input = user_locations.get(username.lower())
        
        if not location_input:
            self.safe_reply(connection, event, f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one.")
            return True

        weather_data_tuple = self._get_weather_data(location_input)
        if weather_data_tuple:
            weather_data, location_name = weather_data_tuple
            report = self._format_weather_report(weather_data, location_name, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not fetch the weather for your location.")
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        
        weather_data_tuple = self._get_weather_data(location_input)
        
        if weather_data_tuple:
            weather_data, location_name = weather_data_tuple
            report = self._format_weather_report(weather_data, location_name, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not find a weather report for '{location_input}'.")
        return True
    
    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state("stats", {})
        locations_set = len(self.get_state("user_locations", {}))
        self.safe_reply(connection, event, f"Weather stats: {locations_set} users have set a location.")
        return True

    def on_pubmsg(self, connection, event, msg, username):
        if self._handle_message(connection, event, msg, username):
            return True
            
        return super().on_pubmsg(connection, event, msg, username)