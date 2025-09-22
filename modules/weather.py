# modules/weather.py
# Weather module using centralized geolocation from the base module.
import re
import requests
import json
from typing import Dict, Any, Optional
from datetime import datetime
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Weather(bot, config)

class Weather(SimpleCommandModule):
    name = "weather"
    version = "1.4.1"
    description = "Provides weather information for saved or specified locations."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.set_state("user_locations", self.get_state("user_locations", {}))
        self.save_state()
        
        self.http_session = self.requests_retry_session()

        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        self.RE_NL_WEATHER = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what's\s+the|how\s+is\s+the|tell\s+me\s+about\s+the)?\s*weather(?:[\s?]|$)",
            re.IGNORECASE)

    def _register_commands(self):
        self.register_command(r"^\s*!location\s+(.+)$", self._cmd_set_location,
            name="location", description="Set your default location. Usage: !location <city, state/country>")
        self.register_command(r"^\s*!weather\s*$", self._cmd_weather_self,
            name="weather", description="Get the weather for your default location.")
        self.register_command(r"^\s*!weather\s+(.+)$", self._cmd_weather_other,
            name="weather other", description="Get the weather for a specific location or user. Usage: !weather <city/user>")
        self.register_command(r"^\s*!weather\s+stats\s*$", self._cmd_stats,
            name="weather stats", admin_only=True, description="Show weather module statistics.")
        # Aliases
        self.register_command(r"^\s*!w\s*$", self._cmd_weather_self,
            name="w", description="Alias for !weather.")
        self.register_command(r"^\s*!w\s+(.+)$", self._cmd_weather_other,
            name="w other", description="Alias for !weather other.")

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if self.RE_NL_WEATHER.search(msg):
            location_obj = self.get_state("user_locations", {}).get(username.lower())
            if not location_obj:
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a default location. Use '!location <city>' to set one.")
                return True
            
            weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"])
            if weather_data:
                location_name = location_obj.get('short_name', location_obj.get('display_name', 'your location'))
                report = self._format_weather_report(weather_data, location_name, username)
                self.safe_reply(connection, event, report)
            else:
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not fetch the weather for your location.")
            return True
        return False

    def _get_weather_data(self, lat: str, lon: str) -> Optional[Dict[str, Any]]:
        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        headers = {'User-Agent': 'JeevesIRCBot/1.0'}
        try:
            response = self.http_session.get(weather_url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except (requests.exceptions.RequestException, json.JSONDecodeError) as e:
            self._record_error(f"MET Norway API request failed for {lat},{lon}: {e}")
            return None

    def _get_weather_report_string(self, data: Dict[str, Any]) -> Optional[str]:
        try:
            timeseries0 = data['properties']['timeseries'][0]
            now = timeseries0['data']['instant']['details']
            summary_data = timeseries0['data'].get('next_1_hours')
            temp_c = now.get('air_temperature')
            wind_speed_ms = float(now.get('wind_speed', 0.0))
            wind_speed_mph = round(wind_speed_ms * 2.2369)
            summary_code = (summary_data['summary'].get('symbol_code', 'no summary')
                            if summary_data and 'summary' in summary_data else 'no summary')
            summary = summary_code.replace('_', ' ').capitalize()
            temp_str = f"{self._c_to_f(temp_c)}°F/{temp_c}°C" if temp_c is not None else "N/A"
            report_time_utc = datetime.fromisoformat(timeseries0['time'])
            formatted_time = report_time_utc.strftime('%H:%M %Z')
            return f"{summary}. Temp: {temp_str}. Wind: {wind_speed_mph} mph. (as of {formatted_time})"
        except (KeyError, IndexError, ValueError):
            return None

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, requester: str, target_user: Optional[str] = None) -> str:
        report_string = self._get_weather_report_string(data)
        if not report_string:
            return f"My apologies, {self.bot.title_for(requester)}, I could not format the weather report."

        requester_title = self.bot.title_for(requester)
        if target_user:
            target_title = self.bot.title_for(target_user)
            return f"As you wish, {requester_title}. The weather for {target_title} in {location_name} is currently: {report_string}"
        else:
            return f"{requester_title}, the weather in {location_name} is currently: {report_string}"

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geo_data_tuple = self._get_geocode_data(location_input)
        if not geo_data_tuple:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I could not find coordinates for '{location_input}'.")
            return True
        
        lat, lon, geo_data = geo_data_tuple
        short_name = self._format_location_name(geo_data)

        user_locations = self.get_state("user_locations")
        user_locations[username.lower()] = {
            "query": location_input, 
            "lat": lat, 
            "lon": lon, 
            "display_name": geo_data.get("display_name"),
            "short_name": short_name
        }
        self.set_state("user_locations", user_locations)
        self.save_state()
        self.safe_reply(connection, event, f"Noted, {self.bot.title_for(username)}. Your location is set to '{short_name}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        location_obj = self.get_state("user_locations", {}).get(username.lower())
        if not location_obj:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location. Use '!location <city>' to set one.")
            return True
        weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"])
        if weather_data:
            location_name = location_obj.get('short_name', location_obj.get('display_name', 'your location'))
            self.safe_reply(connection, event, self._format_weather_report(weather_data, location_name, username))
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not fetch the weather for your location.")
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        user_locations = self.get_state("user_locations", {})
        
        if query.lower() in user_locations:
            location_obj = user_locations[query.lower()]
            weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"])
            if weather_data:
                location_name = location_obj.get('short_name', location_obj.get('display_name', 'their location'))
                report = self._format_weather_report(weather_data, location_name, username, target_user=query)
                self.safe_reply(connection, event, report)
            else:
                self.safe_reply(connection, event, f"My apologies, I could not fetch the weather for {query}.")
            return True

        geo_data_tuple = self._get_geocode_data(query)
        if not geo_data_tuple:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not find a location or user named '{query}'.")
            return True
        
        lat, lon, geo_data = geo_data_tuple
        short_name = self._format_location_name(geo_data)
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            report = self._format_weather_report(weather_data, short_name, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(username)}, I could not find a weather report for '{query}'.")
        return True

    def _c_to_f(self, temp_c: float) -> int:
        return int((temp_c * 9 / 5) + 32)

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        locations_set = len(self.get_state("user_locations", {}))
        self.safe_reply(connection, event, f"Weather stats: {locations_set} users have set a location.")
        return True

