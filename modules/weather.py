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

def setup(bot, config):
    return Weather(bot, config)

class Weather(SimpleCommandModule, ResponseModule):
    name = "weather"
    version = "1.1.1" # version bumped
    description = "Provides weather information for saved or specified locations."

    API_KEY = os.getenv("PIRATE_WEATHER_API_KEY")

    def __init__(self, bot, config):
        super().__init__(bot)
        self.set_state("user_locations", self.get_state("user_locations", {}))
        self.save_state()

        if not self.API_KEY:
            self._record_error("PIRATE_WEATHER_API_KEY environment variable is not set.")
        
        self._register_commands()
        self._register_responses()

    def _register_commands(self):
        self.register_command(
            r"^\s*!location\s+(.+)$", self._cmd_set_location,
            name="location", description="Set your default location for !weather. Usage: !location <city, state/country>"
        )
        self.register_command(
            r"^\s*!weather\s*$", self._cmd_weather_self,
            name="weather", description="Get the weather for your default location."
        )
        self.register_command(
            r"^\s*!weather\s+(.+)$", self._cmd_weather_other,
            name="weather other", description="Get the weather for a specific location. Usage: !weather <city, state/country>"
        )
        self.register_command(
            r"^\s*!weather\s+stats\s*$", self._cmd_stats,
            name="weather stats", admin_only=True,
            description="Show weather module statistics."
        )
    
    # ... (rest of the functions remain the same)
    def _register_responses(self):
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        weather_pattern = re.compile(rf"\b{name_pat}[,!\s]*\s*(?:what's\s+the|how\s+is\s+the|tell\s+me\s+about\s+the)?\s*weather(?:[\s?]|$)", re.IGNORECASE)
        self.add_response_pattern(weather_pattern, lambda msg, user: self._handle_natural_weather(msg, user), probability=1.0)

    def _handle_natural_weather(self, msg: str, username: str) -> Optional[str]:
        user_locations = self.get_state("user_locations")
        location_obj = user_locations.get(username.lower())
        if not location_obj:
            return f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one."
        lat, lon = location_obj["lat"], location_obj["lon"]
        short_name = location_obj["query"]
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            report = self._format_weather_report(weather_data, short_name, username)
            self.safe_reply(self.bot.connection, self.bot.primary_channel, report)
            return report
        else:
            return f"{username}, I'm afraid I could not fetch the weather for your location."

    def _get_geocode_data(self, location: str) -> Optional[Tuple[str, str, str]]:
        geo_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location)}&format=json&limit=1"
        try:
            geo_response = requests.get(geo_url, headers={'User-Agent': 'JeevesIRCBot'})
            geo_response.raise_for_status()
            geo_data = geo_response.json()
            if not geo_data:
                return None
            lat = geo_data[0]["lat"]
            lon = geo_data[0]["lon"]
            display_name = geo_data[0]["display_name"]
            return (lat, lon, display_name)
        except Exception as e:
            self._record_error(f"Geocoding request failed for {location}: {e}")
            return None

    def _get_weather_data(self, lat: str, lon: str) -> Optional[Dict[str, Any]]:
        if not self.API_KEY:
            self._record_error("API key is missing, cannot fetch weather.")
            return None
        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        headers = {'User-Agent': 'JeevesIRCBot/1.0 https://github.com/your/repo'}
        try:
            weather_response = requests.get(weather_url, headers=headers)
            weather_response.raise_for_status()
            return weather_response.json()
        except requests.exceptions.RequestException as e:
            self._record_error(f"MET Norway API request failed for {lat},{lon}: {e}")
            return None

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, username: str) -> str:
        try:
            now = data['properties']['timeseries'][0]['data']['instant']['details']
            summary_data = data['properties']['timeseries'][0]['data'].get('next_1_hours')
            temp_c = now.get('air_temperature')
            wind_ms = now.get('wind_speed', 0)
            wind_speed_mph = int(wind_ms * 2.237)
            summary_code = "no summary"
            if summary_data and 'summary' in summary_data:
                summary_code = summary_data['summary'].get('symbol_code', 'no summary')
            summary = summary_code.replace('_', ' ').capitalize()
            temp_str = f"{self._c_to_f(temp_c)}°F/{temp_c}°C" if temp_c is not None else "N/A"
            report_time_str = data['properties']['timeseries'][0]['time']
            report_time_utc = datetime.fromisoformat(report_time_str)
            formatted_time = report_time_utc.strftime('%H:%M %Z')
            title = self.bot.title_for(username)
            return (f"{title} {username}, the weather in {location_name} is currently: {summary}. The temperature is {temp_str}. Wind speed is {wind_speed_mph} mph. (Reported at {formatted_time})")
        except (KeyError, IndexError, Exception) as e:
            self._record_error(f"Failed to format yr.no weather report: {e}")
            return f"{username}, I'm afraid I could not format the weather report from the new source."

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geo_data = self._get_geocode_data(location_input)
        if not geo_data:
            self.safe_reply(connection, event, f"{username}, I'm sorry, I could not find coordinates for '{location_input}'. Please be more specific.")
            return True
        lat, lon, display_name = geo_data
        user_locations = self.get_state("user_locations")
        user_locations[username.lower()] = {"query": location_input, "lat": lat, "lon": lon, "display_name": display_name}
        self.set_state("user_locations", user_locations)
        self.save_state()
        self.safe_reply(connection, event, f"{username}, noted. I have saved your location as '{display_name}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        user_locations = self.get_state("user_locations")
        location_obj = user_locations.get(username.lower())
        if not location_obj:
            self.safe_reply(connection, event, f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one.")
            return True
        lat, lon = location_obj["lat"], location_obj["lon"]
        short_name = location_obj["query"]
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            report = self._format_weather_report(weather_data, short_name, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not fetch the weather for your location.")
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geocode_data = self._get_geocode_data(location_input)
        if not geocode_data:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not find a location for '{location_input}'.")
            return True
        lat, lon, _ = geocode_data
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            report = self._format_weather_report(weather_data, location_input, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not find a weather report for '{location_input}'.")
        return True

    def _c_to_f(self, temp_c: float) -> int:
        return int((temp_c * 9 / 5) + 32)

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