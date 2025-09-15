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
        location_obj = user_locations.get(username.lower())
        
        if not location_obj:
            return f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one."

        # Use the saved coordinates and short name from the new data structure
        lat, lon = location_obj["lat"], location_obj["lon"]
        short_name = location_obj["query"]
        
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            report = self._format_weather_report(weather_data, short_name, username)
            # For natural language, we reply directly to the channel
            self.safe_reply(self.bot.connection, self.bot.primary_channel, report)
            return report # Return the report to satisfy the handler
        else:
            return f"{username}, I'm afraid I could not fetch the weather for your location."

    def _get_geocode_data(self, location: str) -> Optional[Tuple[str, str, str]]:
        """Geocodes a location string and returns lat, lon, and display_name."""
        geo_url = f"https://nominatim.openstreetmap.org/search?q={requests.utils.quote(location)}&format=json&limit=1"
        try:
            geo_response = requests.get(geo_url, headers={'User-Agent': 'JeevesIRCBot'})
            
            # --- DEBUG LINE ADDED ---
            print(f"[WEATHER DEBUG] RAW GEOCODE RESPONSE for '{location}': {geo_response.text}")
            
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
            
        weather_url = f"https://api.pirateweather.net/forecast/{self.API_KEY}/{lat},{lon}"
        try:
            weather_response = requests.get(weather_url)

            # --- DEBUG LINE ADDED ---
            print(f"[WEATHER DEBUG] RAW WEATHER RESPONSE for '{lat},{lon}': {weather_response.text}")

            weather_response.raise_for_status()
            return weather_response.json()
        except Exception as e:
            self._record_error(f"Pirate Weather API request failed for {lat},{lon}: {e}")
            return None

    def _format_weather_report(self, data: Dict[str, Any], location_name: str, username: str) -> str:
        try:
            currently = data["currently"]
            summary = currently.get("summary", "no summary")
            temp_f = currently.get("temperature")
            feels_f = currently.get("apparentTemperature")
            humidity = currently.get("humidity", "N/A")
            wind_speed = currently.get("windSpeed", "N/A")
            
            # Format the new temperature strings
            temp_str = f"{temp_f}°F/{self._f_to_c(temp_f)}°C" if temp_f is not None else "N/A"
            feels_str = f"{feels_f}°F/{self._f_to_c(feels_f)}°C" if feels_f is not None else "N/A"
            
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
                        f"The temperature is {temp_str}, and it feels like {feels_str}. "
                        f"Wind speed is {wind_speed} mph and humidity is {int(humidity * 100)}%. "
                        f"(Reported at {formatted_time})"
                    )
        except Exception as e:
            self._record_error(f"Failed to format weather report: {e}")
            return f"{username}, I'm afraid I could not format the weather report."

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
    
        # We now geocode immediately to validate the location
        geo_data = self._get_geocode_data(location_input)
    
        if not geo_data:
            self.safe_reply(connection, event, f"{username}, I'm sorry, I could not find coordinates for '{location_input}'. Please be more specific.")
            return True

        lat, lon, display_name = geo_data
    
        # Save a structured object instead of just the input string
        user_locations = self.get_state("user_locations")
        user_locations[username.lower()] = {
            "query": location_input, # The user's short name
           "lat": lat,
            "lon": lon,
            "display_name": display_name # The full name for confirmation
        }
        self.set_state("user_locations", user_locations)
        self.save_state()
    
        # Confirm with the full, unambiguous name
        self.safe_reply(connection, event, f"{username}, noted. I have saved your location as '{display_name}'.")
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        user_locations = self.get_state("user_locations")
        location_obj = user_locations.get(username.lower())
        
        if not location_obj:
            self.safe_reply(connection, event, f"{username}, you have not set a default location. Use '!location <city, state/country>' to set one.")
            return True

        # Use the saved coordinates and short name
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
        
        lat, lon, _ = geocode_data # We don't need the long display_name here
        
        weather_data = self._get_weather_data(lat, lon)
        if weather_data:
            # For one-off lookups, use the user's original input as the name
            report = self._format_weather_report(weather_data, location_input, username)
            self.safe_reply(connection, event, report)
        else:
            self.safe_reply(connection, event, f"{username}, I'm afraid I could not find a weather report for '{location_input}'.")
        return True
    
    def _f_to_c(self, temp_f: float) -> int:
        """Converts Fahrenheit to Celsius and returns an integer."""
        return int((temp_f - 32) * 5 / 9)


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