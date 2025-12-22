# modules/weather.py
# Weather module for local weather lookups
import re
import json
from typing import Dict, Any, Optional
from .base import SimpleCommandModule, admin_required
from . import achievement_hooks

class Weather(SimpleCommandModule):
    name = "weather"
    version = "4.4.0" # Refactored to use ModuleBase http and state
    description = "Provides weather information for saved or specified locations."

    def __init__(self, bot):
        super().__init__(bot)
        
        # Ensure user_locations state exists
        if not self.get_state("user_locations"):
            self.set_state("user_locations", {})
            self.save_state()

        name_pat = self.bot.JEEVES_NAME_RE
        self.RE_NL_WEATHER = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what's\s+the|how\s+is\s+the|tell\s+me\s+about\s+the)?\s*weather(?:[\s?]|$)",
            re.IGNORECASE)

    def _register_commands(self):
        self.register_command(r"^\s*!location\s*$", self._cmd_show_location, name="location show")
        self.register_command(r"^\s*!location\s+(.+)$", self._cmd_set_location, name="location")
        self.register_command(r"^\s*!weather\s*$", self._cmd_weather_self, name="weather")
        self.register_command(r"^\s*!weather\s+(.+)$", self._cmd_weather_other, name="weather other")
        self.register_command(r"^\s*!w\s*$", self._cmd_weather_self, name="w")
        self.register_command(r"^\s*!w\s+(.+)$", self._cmd_weather_other, name="w other")
        self.register_command(r"^\s*!wf\s*$", self._cmd_forecast_self, name="forecast")
        self.register_command(r"^\s*!wf\s+(.+)$", self._cmd_forecast_other, name="forecast other")

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target):
            return False

        if self.RE_NL_WEATHER.search(msg):
            user_id = self.bot.get_user_id(username)
            location_obj = self.get_state("user_locations", {}).get(user_id)
            if not location_obj:
                if self.has_flavor_enabled(username):
                    self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a default location.")
                else:
                    self.safe_reply(connection, event, "No default location set.")
                return True

            self._reply_with_weather(connection, event, location_obj, username)
            return True
        return False

    def _get_weather_data(self, lat: str, lon: str, country_code: str = None) -> Optional[Dict[str, Any]]:
        """Fetch weather data using PirateWeather for US locations, yr.no for others."""
        # Determine if location is in the US
        use_pirate = country_code == "US"

        if use_pirate:
            return self._get_pirate_weather_data(lat, lon)
        else:
            return self._get_met_norway_weather_data(lat, lon)

    def _get_pirate_weather_data(self, lat: str, lon: str) -> Optional[Dict[str, Any]]:
        """Fetch weather from PirateWeather API (US locations)."""
        api_key = self.bot.config.get("api_keys", {}).get("pirateweather")
        if not api_key:
            self._record_error("PirateWeather API key not configured")
            return None

        if self.http is None:
            self._record_error("HTTP client not available for PirateWeather request")
            return None

        # PirateWeather uses DarkSky-compatible API
        weather_url = f"https://api.pirateweather.net/forecast/{api_key}/{lat},{lon}?units=us"
        try:
            data = self.http.get_json(weather_url)
            return data
        except Exception as e:
            self._record_error(f"PirateWeather API request failed for {lat},{lon}: {e}")
            return None

    def _get_met_norway_weather_data(self, lat: str, lon: str) -> Optional[Dict[str, Any]]:
        """Fetch weather from MET Norway API (international locations)."""
        if self.http is None:
            self._record_error("HTTP client not available for MET Norway request")
            return None

        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        try:
            # Use shared HTTP client (User-Agent is handled by http_utils)
            data = self.http.get_json(weather_url)
            return data
        except Exception as e:
            self._record_error(f"MET Norway API request failed for {lat},{lon}: {e}")
            return None

    def _calculate_feels_like(self, temp_c: float, humidity: float, wind_speed_ms: float) -> float:
        """Calculate feels-like temperature using heat index and wind chill formulas."""
        temp_f = (temp_c * 9 / 5) + 32

        # If cold (below 50°F / 10°C), use wind chill
        if temp_f <= 50:
            # Wind chill formula (requires wind speed in mph)
            wind_mph = wind_speed_ms * 2.237
            if wind_mph > 3:
                feels_like_f = 35.74 + (0.6215 * temp_f) - (35.75 * (wind_mph ** 0.16)) + (0.4275 * temp_f * (wind_mph ** 0.16))
                return round((feels_like_f - 32) * 5 / 9, 1)

        # If warm (above 80°F / 26.7°C), use heat index
        elif temp_f >= 80 and humidity >= 40:
            # Heat index formula
            hi = -42.379 + (2.04901523 * temp_f) + (10.14333127 * humidity)
            hi -= 0.22475541 * temp_f * humidity
            hi -= 6.83783e-3 * temp_f ** 2
            hi -= 5.481717e-2 * humidity ** 2
            hi += 1.22874e-3 * temp_f ** 2 * humidity
            hi += 8.5282e-4 * temp_f * humidity ** 2
            hi -= 1.99e-6 * temp_f ** 2 * humidity ** 2
            return round((hi - 32) * 5 / 9, 1)

        # Otherwise, feels like equals actual temperature
        return temp_c

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, requester: str, is_pirate: bool = False, target_user: Optional[str] = None) -> str:
        try:
            if is_pirate:
                # PirateWeather format (DarkSky-compatible)
                current = data.get('currently', {})
                temp_f = current.get('temperature')
                temp_c = round((temp_f - 32) * 5 / 9, 1) if temp_f is not None else None
                feels_like_f = current.get('apparentTemperature')
                feels_like_c = round((feels_like_f - 32) * 5 / 9, 1) if feels_like_f is not None else None
                humidity = current.get('humidity')
                humidity_pct = int(humidity * 100) if humidity is not None else None
                wind_mph = round(current.get('windSpeed', 0.0))
                wind_kph = round(wind_mph * 1.60934)
                summary = current.get('summary', 'N/A')
                temp_str = f"{int(temp_f)}°F/{temp_c}°C" if temp_f is not None else "N/A"
                feels_like_str = f" Feels like: {int(feels_like_f)}°F/{feels_like_c}°C." if feels_like_f is not None else ""
                humidity_str = f" Humidititty: {humidity_pct}%." if humidity_pct is not None else ""
            else:
                # MET Norway format
                now = data['properties']['timeseries'][0]['data']['instant']['details']
                temp_c = now.get('air_temperature')
                humidity_pct = now.get('relative_humidity')
                wind_speed_ms = float(now.get('wind_speed', 0.0))
                wind_mph = round(wind_speed_ms * 2.237)
                wind_kph = round(wind_speed_ms * 3.6)
                summary_code = data['properties']['timeseries'][0]['data'].get('next_1_hours', {}).get('summary', {}).get('symbol_code', 'N/A')
                summary = summary_code.replace('_', ' ').capitalize()
                temp_str = f"{int((temp_c * 9 / 5) + 32)}°F/{temp_c}°C" if temp_c is not None else "N/A"

                # Calculate feels-like temperature
                if temp_c is not None and humidity_pct is not None:
                    feels_like_c = self._calculate_feels_like(temp_c, humidity_pct, wind_speed_ms)
                    feels_like_f = int((feels_like_c * 9 / 5) + 32)
                    feels_like_str = f" Feels like: {feels_like_f}°F/{feels_like_c}°C."
                else:
                    feels_like_str = ""

                humidity_str = f" Humidititty: {int(humidity_pct)}%." if humidity_pct is not None else ""

            report = f"{summary}. Temp: {temp_str}.{feels_like_str}{humidity_str} Wind: {wind_mph} mph / {wind_kph} kph."

            if self.has_flavor_enabled(requester):
                requester_title = self.bot.title_for(requester)
                if target_user:
                    return f"As you wish, {requester_title}. The weather for {self.bot.title_for(target_user)} in {location_name} is: {report}"
                else:
                    return f"{requester_title}, the weather in {location_name} is: {report}"
            else:
                return f"{location_name}: {report}"
        except (KeyError, IndexError, ValueError):
            if self.has_flavor_enabled(requester):
                return f"My apologies, {self.bot.title_for(requester)}, I could not format the weather report."
            else:
                return "Could not format weather report."

    def _reply_with_weather(self, connection, event, location_obj, requester, target_user=None):
        location_name = (
            location_obj.get('user_input')
            or location_obj.get('short_name')
            or location_obj.get('display_name')
            or 'their location'
        )
        country_code = location_obj.get('country_code', 'US').upper()

        weather_data = self._get_weather_data(location_obj["lat"], location_obj["lon"], country_code)
        if weather_data:
            is_pirate = country_code == "US"
            report = self._format_weather_report(weather_data, location_name, requester, is_pirate, target_user)
            self.safe_reply(connection, event, report)
            # Record achievement progress
            achievement_hooks.record_weather_check(self.bot, requester)
        else:
            if self.has_flavor_enabled(requester):
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(requester)}, I could not fetch the weather.")
            else:
                self.safe_reply(connection, event, "Could not fetch weather.")

    def _get_forecast_data(self, lat: str, lon: str, country_code: Optional[str] = None) -> Optional[list]:
        """Fetch 3-day forecast data."""
        use_pirate = country_code == "US"

        if use_pirate:
            return self._get_pirate_forecast(lat, lon)
        else:
            return self._get_met_norway_forecast(lat, lon)

    def _get_pirate_forecast(self, lat: str, lon: str) -> Optional[list]:
        """Extract 3-day forecast from PirateWeather API."""
        api_key = self.bot.config.get("api_keys", {}).get("pirateweather")
        if not api_key:
            return None

        if self.http is None:
            self._record_error("HTTP client not available for PirateWeather forecast request")
            return None

        weather_url = f"https://api.pirateweather.net/forecast/{api_key}/{lat},{lon}?units=us"
        try:
            data = self.http.get_json(weather_url)
            if not data:
                return None

            daily = data.get('daily', {}).get('data', [])
            if not daily or len(daily) < 4:
                return None

            forecast = []
            # Skip today (index 0), get next 3 days
            for day in daily[1:4]:
                forecast.append({
                    'day': day.get('time'),
                    'condition': day.get('summary', 'Unknown'),
                    'temp_high_f': day.get('temperatureHigh'),
                    'temp_low_f': day.get('temperatureLow'),
                    'temp_high_c': round((day.get('temperatureHigh', 32) - 32) * 5 / 9, 1) if day.get('temperatureHigh') else None,
                    'temp_low_c': round((day.get('temperatureLow', 32) - 32) * 5 / 9, 1) if day.get('temperatureLow') else None,
                })
            return forecast
        except Exception:
            return None

    def _get_met_norway_forecast(self, lat: str, lon: str) -> Optional[list]:
        """Extract 3-day forecast from MET Norway API."""
        if self.http is None:
            self._record_error("HTTP client not available for MET Norway forecast request")
            return None

        weather_url = f"https://api.met.no/weatherapi/locationforecast/2.0/complete?lat={lat}&lon={lon}"
        try:
            data = self.http.get_json(weather_url)
            if not data:
                return None

            timeseries = data.get('properties', {}).get('timeseries', [])
            if not timeseries:
                return None

            # Group by day and find representative data (around noon)
            from datetime import datetime, timedelta, timezone
            forecast = []
            today = datetime.utcnow().date()

            for day_offset in range(1, 4):  # Next 3 days
                target_date = today + timedelta(days=day_offset)

                # Find entries for this day, preferably around noon
                day_entries = []
                for entry in timeseries:
                    entry_time = datetime.fromisoformat(entry['time'].replace('Z', '+00:00'))
                    if entry_time.date() == target_date:
                        day_entries.append(entry)

                if not day_entries:
                    continue

                # Find entry closest to noon (make noon_target timezone-aware)
                noon_target = datetime.combine(target_date, datetime.min.time().replace(hour=12)).replace(tzinfo=timezone.utc)
                closest_entry = min(day_entries,
                                  key=lambda e: abs((datetime.fromisoformat(e['time'].replace('Z', '+00:00')) - noon_target).total_seconds()))

                details = closest_entry.get('data', {}).get('instant', {}).get('details', {})
                temp_c = details.get('air_temperature')

                # Get weather symbol
                next_hours = closest_entry.get('data', {}).get('next_6_hours') or closest_entry.get('data', {}).get('next_1_hours', {})
                symbol_code = next_hours.get('summary', {}).get('symbol_code', 'unknown')
                condition = symbol_code.replace('_', ' ').replace('day', '').replace('night', '').strip().capitalize()

                forecast.append({
                    'day': target_date.strftime('%A'),
                    'condition': condition,
                    'temp_high_f': int((temp_c * 9 / 5) + 32) if temp_c else None,
                    'temp_low_f': None,  # MET Norway doesn't provide high/low easily
                    'temp_high_c': temp_c,
                    'temp_low_c': None,
                })

            return forecast if forecast else None
        except Exception:
            return None

    def _format_forecast_report(self, forecast_data: list, location_name: str, requester: str, is_pirate: bool = False) -> str:
        """Format 3-day forecast into readable text."""
        if not forecast_data:
            return "Forecast data unavailable."

        from datetime import datetime

        lines = []
        for day_data in forecast_data:
            if is_pirate and isinstance(day_data['day'], (int, float)):
                # PirateWeather uses Unix timestamp
                day_name = datetime.fromtimestamp(day_data['day']).strftime('%A')
            else:
                day_name = day_data['day']

            condition = day_data['condition']

            if is_pirate and day_data['temp_high_f'] and day_data['temp_low_f']:
                temp_str = f"{int(day_data['temp_high_f'])}/{int(day_data['temp_low_f'])}°F ({day_data['temp_high_c']}/{day_data['temp_low_c']}°C)"
            elif day_data['temp_high_f']:
                temp_str = f"~{int(day_data['temp_high_f'])}°F ({day_data['temp_high_c']}°C)"
            else:
                temp_str = "N/A"

            lines.append(f"{day_name}: {condition}, {temp_str}")

        forecast_text = " | ".join(lines)

        if self.has_flavor_enabled(requester):
            return f"{self.bot.title_for(requester)}, the forecast for {location_name}: {forecast_text}"
        else:
            return f"{location_name} forecast: {forecast_text}"

    def _reply_with_forecast(self, connection, event, location_obj, requester):
        """Reply with a 3-day forecast for the given location."""
        location_name = (
            location_obj.get('user_input')
            or location_obj.get('short_name')
            or location_obj.get('display_name')
            or 'the location'
        )
        country_code = location_obj.get('country_code', 'US').upper()

        forecast_data = self._get_forecast_data(location_obj["lat"], location_obj["lon"], country_code)
        if forecast_data:
            is_pirate = country_code == "US"
            report = self._format_forecast_report(forecast_data, location_name, requester, is_pirate)
            self.safe_reply(connection, event, report)
        else:
            if self.has_flavor_enabled(requester):
                self.safe_reply(connection, event, f"My apologies, {self.bot.title_for(requester)}, I could not fetch the forecast.")
            else:
                self.safe_reply(connection, event, "Could not fetch forecast.")

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geo_data_tuple = self._get_geocode_data(location_input)
        if not geo_data_tuple:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I could not find coordinates for '{location_input}'.")
            else:
                self.safe_reply(connection, event, f"Location '{location_input}' not found.")
            return True

        lat, lon, geo_data = geo_data_tuple
        short_name = self._format_location_name(geo_data)
        country_code = geo_data.get("address", {}).get("country_code", "us").upper()
        user_id = self.bot.get_user_id(username)

        locations = self.get_state("user_locations") or {}
        locations[user_id] = {
            "lat": lat,
            "lon": lon,
            "short_name": short_name,
            "display_name": geo_data.get("display_name"),
            "country_code": country_code,
            "user_input": location_input,
        }
        self.set_state("user_locations", locations)
        self.save_state()

        if self.has_flavor_enabled(username):
            self.safe_reply(connection, event, f"Noted, {self.bot.title_for(username)}. Your location is set to '{short_name}'.")
        else:
            self.safe_reply(connection, event, f"Location set to '{short_name}'.")
        return True

    def _cmd_show_location(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location.")
            else:
                self.safe_reply(connection, event, "No location set.")
            return True

        stored_name = (
            location_obj.get("user_input")
            or location_obj.get("short_name")
            or location_obj.get("display_name")
            or "your location"
        )

        if self.has_flavor_enabled(username):
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, your location is set to '{stored_name}'.")
        else:
            self.safe_reply(connection, event, f"Your location is set to '{stored_name}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location.")
            else:
                self.safe_reply(connection, event, "No location set.")
            return True
        self._reply_with_weather(connection, event, location_obj, username)
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()
        
        users_module = self.bot.pm.plugins.get("users")
        target_user_id = users_module.get_state("nick_map", {}).get(query.lower()) if users_module else None
            
        if target_user_id and (location_obj := self.get_state("user_locations", {}).get(target_user_id)):
            self._reply_with_weather(connection, event, location_obj, username, target_user=query)
            return True

        geo_data_tuple = self._get_geocode_data(query)
        if not geo_data_tuple:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"My apologies, I could not find a user or location named '{query}'.")
            else:
                self.safe_reply(connection, event, f"User or location '{query}' not found.")
            return True

        lat, lon, geo_data = geo_data_tuple
        location_obj = {
            "lat": lat, "lon": lon, "short_name": self._format_location_name(geo_data),
            "display_name": geo_data.get("display_name"), "country_code": geo_data.get("address", {}).get("country_code", "us").upper()
        }
        self._reply_with_weather(connection, event, location_obj, username)
        return True

    def _cmd_forecast_self(self, connection, event, msg, username, match):
        """Handle !wf command to show forecast for user's saved location."""
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"{self.bot.title_for(username)}, you have not set a location.")
            else:
                self.safe_reply(connection, event, "No location set.")
            return True
        self._reply_with_forecast(connection, event, location_obj, username)
        return True

    def _cmd_forecast_other(self, connection, event, msg, username, match):
        """Handle !wf <location> command to show forecast for specified location."""
        query = match.group(1).strip()

        users_module = self.bot.pm.plugins.get("users")
        target_user_id = users_module.get_state("nick_map", {}).get(query.lower()) if users_module else None

        if target_user_id and (location_obj := self.get_state("user_locations", {}).get(target_user_id)):
            self._reply_with_forecast(connection, event, location_obj, username)
            return True

        geo_data_tuple = self._get_geocode_data(query)
        if not geo_data_tuple:
            if self.has_flavor_enabled(username):
                self.safe_reply(connection, event, f"My apologies, I could not find a user or location named '{query}'.")
            else:
                self.safe_reply(connection, event, f"User or location '{query}' not found.")
            return True

        lat, lon, geo_data = geo_data_tuple
        location_obj = {
            "lat": lat, "lon": lon, "short_name": self._format_location_name(geo_data),
            "display_name": geo_data.get("display_name"), "country_code": geo_data.get("address", {}).get("country_code", "us").upper()
        }
        self._reply_with_forecast(connection, event, location_obj, username)
        return True

def setup(bot):
    return Weather(bot)
