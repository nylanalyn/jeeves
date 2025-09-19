# modules/weather.py
# Weather module for local weather lookups
import re
import functools
import os
import requests
import sys
import json
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone, timedelta
from .base import SimpleCommandModule, ResponseModule, admin_required

def setup(bot, config):
    return Weather(bot, config)

class Weather(SimpleCommandModule, ResponseModule):
    name = "weather"
    version = "1.2.2" # version bumped
    description = "Provides weather information for saved or specified locations."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.set_state("user_locations", self.get_state("user_locations", {}))
        self.save_state()
        
        # Create a resilient session for making API calls
        self.http_session = self.requests_retry_session()

        self._register_commands()
        self._register_responses()

    def _register_commands(self):
        self.register_command(r"^\s*!location\s+(.+)$", self._cmd_set_location,
            name="location", description="Set your default location. Usage: !location <city, state/country>")
        self.register_command(r"^\s*!weather\s*$", self._cmd_weather_self,
            name="weather", description="Get the weather for your default location.")
        self.register_command(r"^\s*!weather\s+(.+)$", self._cmd_weather_other,
            name="weather other", description="Get the weather for a specific location. Usage: !weather <city, state/country>")
        self.register_command(r"^\s*!weather\s+stats\s*$", self._cmd_stats,
            name="weather stats", admin_only=True, description="Show weather module statistics.")

    def _register_responses(self):
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        weather_pattern = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what's\s+the|how\s+is\s+the|tell\s+me\s+about\s+the)?\s*weather(?:[\s?]|$)",
            re.IGNORECASE)
        self.add_response_pattern(weather_pattern, lambda msg, user: self._handle_natural_weather(msg, user), probability=1.0)

    def _handle_natural_weather(self, msg: str, username: str) -> Optional[str]:
        location_obj = self.get_state("user_locations", {}).get(username.lower())
        if not location_obj:
            return f"{username}, you have not set a default location. Use '!location <city>' to set one."
        
        weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"])
        if weather_data:
            report = self._format_weather_report(weather_data, location_obj["query"], username)
            self.safe_reply(self.bot.connection, self.bot.primary_channel, report)
            return report # Return to satisfy handler
        else:
            return f"{username}, I'm afraid I could not fetch the weather for your location."

    def _get_geocode_data(self, location: str) -> Optional[Tuple[str, str, str]]:
        geo_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location)}&format=json&limit=1"
        try:
            response = self.http_session.get(geo_url, headers={'User-Agent': 'JeevesIRCBot'}, timeout=10) # Use the session
            response.raise_for_status()
            geo_data = response.json()
            if not geo_data: return None
            return (geo_data[0]["lat"], geo_data[0]["lon"], geo_data[0]["display_name"])
        except (requests.exceptions.RequestException, json.JSONDecodeError, IndexError) as e:
            self._record_error(f"Geocoding request failed for {location}: {e}")
            return None

    def _get_weather_data(self, lat: str, lon: str) -> Optional[Dict[str, Any]]:
        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        headers = {'User-Agent': 'JeevesIRCBot/1.0 https://github.com/your/repo'}
        try:
            response = self.http_session.get(weather_url, headers=headers, timeout=10) # Use the session
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self._record_error(f"MET Norway API request failed for {lat},{lon}: {e}")
            return None

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, username: str) -> str:
        try:
            now = data['properties']['timeseries'][0]['data']['instant']['details']
            summary_data = data['properties']['timeseries'][0]['data'].get('next_1_hours')
            temp_c = now.get('air_temperature')
            wind_speed_mph = int(now.get('wind_speed', 0) * 2.237)
            summary_code = summary_data['summary'].get('symbol_code', 'no summary') if summary_data and 'summary' in summary_data else 'no summary'
            summary = summary_code.replace('_', ' ').capitalize()
            temp_str = f"{self._c_to_f(temp_c)}°F/{temp_c}°C" if temp_c is not None else "N/A"
            report_time_utc = datetime.fromisoformat(data['properties']['timeseries'][0]['time'])
            formatted_time = report_time_utc.strftime('%H:%M %Z')
            title = self.bot.title_for(username)
            
            # FIXED: Rewrote the return statement to use explicit string concatenation
            # for better compatibility with older Python versions.
            report = (f"{title}, the weather in {location_name} is currently: {summary}. " +
                      f"Temperature: {temp_str}. Wind: {wind_speed_mph} mph. (Reported at {formatted_time})")
            return report
            
        except (KeyError, IndexError) as e:
            self._record_error(f"Failed to format weather report: {e}")
            return f"{username}, I'm afraid I could not format the weather report."

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geo_data = self._get_geocode_data(location_input)
        if not geo_data:
            self.safe_reply(connection, event, f"{username}, I could not find coordinates for '{location_input}'.")
            return True
        lat, lon, display_name = geo_data
        user_locations = self.get_state("user_locations")
        user_locations[username.lower()] = {"query": location_input, "lat": lat, "lon": lon, "display_name": display_name}
        self.set_state("user_locations", user_locations)
        self.save_state()
        self.safe_reply(connection, event, f"{username}, noted. Your location is set to '{display_name}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        location_obj = self.get_state("user_locations", {}).get(username.lower())
        if not location_obj:
            self.safe_reply(connection, event, f"{username}, you have not set a default location. Use '!location <city>' to set one.")
            return True
        weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"])
        if weather_data:
            self.safe_reply(connection, event, self._format_weather_report(weather_data, location_obj["query"], username))
        else:
            self.safe_reply(connection, event, f"{username}, I could not fetch the weather for your location.")
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geocode_data = self._get_geocode_data(location_input)
        if not geocode_data:
            self.safe_reply(connection, event, f"{username}, I could not find a location for '{location_input}'.")
            return True
        lat, lon, _ = geocode_data
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            self.safe_reply(connection, event, self._format_weather_report(weather_data, location_input, username))
        else:
            self.safe_reply(connection, event, f"{username}, I could not find a weather report for '{location_input}'.")
        return True

    def _c_to_f(self, temp_c: float) -> int:
        return int((temp_c * 9 / 5) + 32)

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        locations_set = len(self.get_state("user_locations", {}))
        self.safe_reply(connection, event, f"Weather stats: {locations_set} users have set a location.")
        return True

    def on_pubmsg(self, connection, event, msg, username):
        if self._handle_message(connection, event, msg, username):
            return True
        return super().on_pubmsg(connection, event, msg, username)


