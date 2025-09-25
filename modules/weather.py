# modules/weather.py
# Weather module for local weather lookups
import re
import requests
import json
from typing import Dict, Any, Optional
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Weather(bot, config)

class Weather(SimpleCommandModule):
    name = "weather"
    version = "2.1.0" # Added country_code storage for better integration
    description = "Provides weather information for saved or specified locations."

    def __init__(self, bot, config):
        super().__init__(bot)
        self.set_state("user_locations", self.get_state("user_locations", {}))
        self.save_state()
        
        self.http_session = self.requests_retry_session()

        name_pat = self.bot.JEEVES_NAME_RE
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
        self.register_command(r"^\s*!w\s*$", self._cmd_weather_self, name="w", description="Alias for !weather.")
        self.register_command(r"^\s*!w\s+(.+)$", self._cmd_weather_other, name="w other", description="Alias for !weather other.")

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if self.RE_NL_WEATHER.search(msg):
            user_id = self.bot.get_user_id(username)
            location_obj = self.get_state("user_locations", {}).get(user_id)
            if not location_obj:
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a default location.")
                return True
            
            self._reply_with_weather(connection, event, location_obj, username)
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

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, requester: str, target_user: Optional[str] = None) -> str:
        try:
            timeseries0 = data['properties']['timeseries'][0]
            now = timeseries0['data']['instant']['details']
            temp_c = now.get('air_temperature')
            wind_speed_ms = float(now.get('wind_speed', 0.0))
            wind_speed_mph = round(wind_speed_ms * 2.2369)
            wind_speed_kph = round(wind_speed_ms * 3.6)
            summary_data = timeseries0['data'].get('next_1_hours')
            summary_code = (summary_data['summary'].get('symbol_code', 'N/A')
                            if summary_data and 'summary' in summary_data else 'N/A')
            summary = summary_code.replace('_', ' ').capitalize()
            temp_str = f"{int((temp_c * 9 / 5) + 32)}°F/{temp_c}°C" if temp_c is not None else "N/A"
            
            report_string = f"{summary}. Temp: {temp_str}. Wind: {wind_speed_mph} mph / {wind_speed_kph} kph."
            
            requester_title = self.bot.title_for(requester)
            if target_user:
                return f"As you wish, {requester_title}. The weather for {self.bot.title_for(target_user)} in {location_name} is: {report_string}"
            else:
                return f"{requester_title}, the weather in {location_name} is: {report_string}"
        except (KeyError, IndexError, ValueError):
            return f"My apologies, {self.bot.title_for(requester)}, I could not format the weather report."

    def _reply_with_weather(self, connection, event, location_obj, requester, target_user=None):
        location_name = location_obj.get('short_name') or location_obj.get('display_name') or 'their location'
        
        weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"])
        if weather_data:
            report = self._format_weather_report(weather_data, location_name, requester, target_user)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(requester)}, I could not fetch the weather.")

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geo_data_tuple = self._get_geocode_data(location_input)
        if not geo_data_tuple:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I could not find coordinates for '{location_input}'.")
            return True
        
        lat, lon, geo_data = geo_data_tuple
        short_name = self._format_location_name(geo_data)
        country_code = geo_data.get("address", {}).get("country_code", "us").upper()
        user_id = self.bot.get_user_id(username)
        
        user_locations = self.get_state("user_locations")
        user_locations[user_id] = {
            "lat": lat, 
            "lon": lon, 
            "short_name": short_name, 
            "display_name": geo_data.get("display_name"),
            "country_code": country_code
        }
        self.set_state("user_locations", user_locations)
        self.save_state()
        
        self.safe_reply(connection, event, f"Noted, {self.bot.title_for(username)}. Your location is set to '{short_name}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location.")
            return True
        self._reply_with_weather(connection, event, location_obj, username)
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        
        users_module = self.bot.pm.plugins.get("users")
        target_user_id = None
        if users_module:
            nick_map = users_module.get_state("nick_map", {})
            target_user_id = nick_map.get(query.lower())
            
        if target_user_id:
            location_obj = self.get_state("user_locations", {}).get(target_user_id)
            if location_obj:
                self._reply_with_weather(connection, event, location_obj, username, target_user=query)
                return True

        geo_data_tuple = self._get_geocode_data(query)
        if not geo_data_tuple:
            self.safe_reply(connection, event, f"My apologies, I could not find a user or location named '{query}'.")
            return True
        
        lat, lon, geo_data = geo_data_tuple
        short_name = self._format_location_name(geo_data)
        country_code = geo_data.get("address", {}).get("country_code", "us").upper()
        location_obj = {
            "lat": lat, 
            "lon": lon, 
            "short_name": short_name, 
            "display_name": geo_data.get("display_name"),
            "country_code": country_code
        }
        self._reply_with_weather(connection, event, location_obj, username)
        return True
