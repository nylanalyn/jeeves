# modules/weather2.py
# Weather module using Open-Meteo as the sole backend (no API key required)

import re
import threading
from datetime import datetime
from typing import Any, Dict, Optional

from .base import SimpleCommandModule
from . import achievement_hooks


# WMO Weather Code → Description mapping
# Complete set of documented WMO codes from Open-Meteo
WMO_CODES: Dict[int, str] = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snowfall",
    73: "Moderate snowfall",
    75: "Heavy snowfall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEO_URL = "https://geocoding-api.open-meteo.com/v1/search"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active"

CURRENT_PARAMS = (
    "temperature_2m,relative_humidity_2m,apparent_temperature,"
    "weather_code,wind_speed_10m,wind_gusts_10m,is_day"
)
DAILY_PARAMS = (
    "weather_code,temperature_2m_max,temperature_2m_min,"
    "apparent_temperature_max,apparent_temperature_min,"
    "precipitation_sum,wind_speed_10m_max,wind_gusts_10m_max"
)


class Weather2(SimpleCommandModule):
    """Open-Meteo based weather module — no API key required."""

    name = "weather2"
    version = "1.0.0"
    description = (
        "Weather information using Open-Meteo (worldwide, no API key)."
    )

    def __init__(self, bot):
        super().__init__(bot)

        # Auto-migrate locations from the old 'weather' module on first load.
        if not self.get_state("user_locations"):
            old_state = self.bot.get_module_state("weather")
            old_locations = old_state.get("user_locations", {})
            if old_locations:
                self.set_state("user_locations", dict(old_locations))
                self.save_state()
                self.log_debug(
                    f"Migrated {len(old_locations)} user locations from weather module"
                )

        name_pat = self.bot.JEEVES_NAME_RE
        self.RE_NL_WEATHER = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:what's\s+the|how\s+is\s+the|"
            rf"tell\s+me\s+about\s+the)?\s*weather(?:[\s?]|$)",
            re.IGNORECASE,
        )

    # ------------------------------------------------------------------
    # Command registration
    # ------------------------------------------------------------------

    def welcome_summary(self, channel: str = None) -> str:
        return "Set a default place with !location city, then use !weather or !wf."

    def contextual_hint(self, msg: str, username: str, channel: str) -> Optional[str]:
        if re.search(r"\b(weather|forecast)\b", msg, re.IGNORECASE):
            return "Set your default location with !location city, then use !weather or !wf."
        return None

    def _register_commands(self):
        self.register_command(
            r"^\s*!location\s*$",
            self._cmd_show_location,
            name="location show",
            description="Show your saved location",
        )
        self.register_command(
            r"^\s*!location\s+clear\s*$",
            self._cmd_clear_location,
            name="location clear",
            description="Delete your saved location",
        )
        self.register_command(
            r"^\s*!location\s+(.+)$",
            self._cmd_set_location,
            name="location",
            description="Set your default location",
        )
        self.register_command(
            r"^\s*!weather\s*$",
            self._cmd_weather_self,
            name="weather",
            description="Get weather for your location",
        )
        self.register_command(
            r"^\s*!weather\s+(.+)$",
            self._cmd_weather_other,
            name="weather other",
            description="Get weather for a specific location",
        )
        self.register_command(
            r"^\s*!w\s*$",
            self._cmd_weather_self,
            name="w",
            description="Short alias for !weather",
        )
        self.register_command(
            r"^\s*!w\s+(.+)$",
            self._cmd_weather_other,
            name="w other",
            description="Short alias for !weather <location>",
        )
        self.register_command(
            r"^\s*!wf\s*$",
            self._cmd_forecast_self,
            name="forecast",
            description="Get weather forecast for your location",
        )
        self.register_command(
            r"^\s*!wf\s+(.+)$",
            self._cmd_forecast_other,
            name="forecast other",
            description="Get weather forecast for a location",
        )

    # ------------------------------------------------------------------
    # Ambient trigger
    # ------------------------------------------------------------------

    def on_ambient_message(
        self, connection, event, msg: str, username: str
    ) -> bool:
        if not self.is_enabled(event.target):
            return False

        if self.RE_NL_WEATHER.search(msg):
            user_id = self.bot.get_user_id(username)
            location_obj = self.get_state("user_locations", {}).get(user_id)
            if not location_obj:
                if self.has_flavor_enabled(username):
                    self.safe_reply(
                        connection,
                        event,
                        f"{self.bot.title_for(username)}, you have not "
                        "set a default location.",
                    )
                else:
                    self.safe_reply(connection, event, "No default location set.")
                return True

            self._run_async(
                self._reply_with_weather, connection, event, location_obj, username
            )
            return True
        return False

    # ------------------------------------------------------------------
    # Async runner
    # ------------------------------------------------------------------

    def _run_async(self, fn, *args, **kwargs):
        """Run fn(*args, **kwargs) in a daemon thread."""
        t = threading.Thread(
            target=fn, args=args, kwargs=kwargs, daemon=True
        )
        t.start()

    # ------------------------------------------------------------------
    # Open-Meteo API calls
    # ------------------------------------------------------------------

    @classmethod
    def _split_us_state_query(cls, query: str) -> Optional[tuple[str, str]]:
        """Return ``(place, state_name)`` for US state-qualified queries."""
        cleaned = query.strip()
        if not cleaned:
            return None

        place = ""
        qualifier = ""
        if "," in cleaned:
            place, qualifier = cleaned.rsplit(",", 1)
        else:
            match = re.match(r"^(.+?)\s+([A-Za-z]{2})\.?$", cleaned)
            if match:
                place, qualifier = match.groups()

        place = place.strip()
        qualifier = qualifier.strip().lower().rstrip(".")
        state_name = cls.STATE_ABBREVS.get(qualifier)
        if state_name is None and qualifier in cls.STATE_ABBREVS.values():
            state_name = qualifier

        if not place or state_name is None:
            return None
        return place, state_name

    @staticmethod
    def _split_us_country_query(query: str) -> Optional[str]:
        """Return the place name for queries qualified with US/USA."""
        cleaned = query.strip()
        if not cleaned:
            return None

        qualifiers = (
            "united states of america",
            "united states",
            "u.s.a.",
            "u.s.a",
            "usa",
            "u.s.",
            "u.s",
            "us",
        )
        lowered = re.sub(r"\s+", " ", cleaned.casefold())

        if "," in cleaned:
            place, qualifier = cleaned.rsplit(",", 1)
            compact = qualifier.strip().casefold()
            if compact in qualifiers:
                place = place.strip()
                return place or None
            return None

        for qualifier in qualifiers:
            suffix = f" {qualifier}"
            if lowered.endswith(suffix):
                return cleaned[: -len(suffix)].strip() or None
        return None

    # ------------------------------------------------------------------

    def _geocode(self, query: str) -> Optional[Dict[str, Any]]:
        """Look up a place via the Open-Meteo geocoding API.

        Returns a dict with keys ``lat``, ``lon``, ``short_name``,
        ``display_name``, ``user_input``, or None.
        """
        if self.http is None:
            self._record_error("HTTP client not available for geocoding")
            return None

        state_query = self._split_us_state_query(query)
        country_query = None if state_query else self._split_us_country_query(query)
        lookup_name = (
            state_query[0] if state_query
            else country_query if country_query
            else query
        )
        result_count = 100 if state_query or country_query else 1

        try:
            data = self.http.get_json(
                OPEN_METEO_GEO_URL,
                params={
                    "name": lookup_name,
                    "count": result_count,
                    "language": "en",
                    "format": "json",
                },
            )
        except Exception as exc:
            self._record_error(f"Geocoding request failed for '{query}': {exc}")
            return None

        results = data.get("results")
        if not results:
            return None

        if state_query:
            _, state_name = state_query
            result = next(
                (
                    item for item in results
                    if item.get("country_code", "").upper() == "US"
                    and (item.get("admin1") or "").casefold() == state_name
                ),
                None,
            )
            if result is None:
                return None
        elif country_query:
            result = next(
                (
                    item for item in results
                    if item.get("country_code", "").upper() == "US"
                ),
                None,
            )
            if result is None:
                return None
        else:
            result = results[0]
        lat = str(result["latitude"])
        lon = str(result["longitude"])
        country_code = result.get("country_code", "us").upper()

        # Build a short name similar to the old Nominatim helper.
        parts = [result.get("name", "")]
        if result.get("admin1"):
            parts.append(result["admin1"])
        parts.append(country_code)
        short_name = ", ".join(p for p in parts if p)

        # display_name from Open-Meteo fields
        display_parts = [result.get("name", "")]
        if result.get("admin1"):
            display_parts.append(result["admin1"])
        if result.get("country"):
            display_parts.append(result["country"])
        display_name = ", ".join(display_parts)

        return {
            "lat": lat,
            "lon": lon,
            "short_name": short_name,
            "display_name": display_name,
            "user_input": query,
        }

    def _fetch_current(
        self, lat: str, lon: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch current conditions from Open-Meteo forecast API."""
        if self.http is None:
            self._record_error("HTTP client not available")
            return None

        try:
            data = self.http.get_json(
                OPEN_METEO_FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "current": CURRENT_PARAMS,
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                },
            )
        except Exception as exc:
            self._record_error(f"Current weather request failed: {exc}")
            return None

        return data.get("current")

    def _fetch_forecast(
        self, lat: str, lon: str
    ) -> Optional[Dict[str, Any]]:
        """Fetch daily forecast from Open-Meteo (today + 3 days)."""
        if self.http is None:
            self._record_error("HTTP client not available")
            return None

        try:
            data = self.http.get_json(
                OPEN_METEO_FORECAST_URL,
                params={
                    "latitude": lat,
                    "longitude": lon,
                    "daily": DAILY_PARAMS,
                    "temperature_unit": "celsius",
                    "wind_speed_unit": "kmh",
                    "timezone": "auto",
                    "forecast_days": 4,
                },
            )
        except Exception as exc:
            self._record_error(f"Forecast request failed: {exc}")
            return None

        return data.get("daily")

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _c_to_f(c: float) -> int:
        return int(round((c * 9 / 5) + 32))

    @staticmethod
    def _kph_to_mph(kph: float) -> int:
        return int(round(kph / 1.60934))

    @staticmethod
    def _describe_weather_code(code: Optional[int]) -> str:
        """Map a WMO weather code to a human-readable string."""
        if code is None:
            return "Unknown"
        return WMO_CODES.get(code, f"Unknown (code {code})")

    def _format_current(
        self,
        current: Dict[str, Any],
        location_name: str,
        requester: str,
        target_user: Optional[str] = None,
    ) -> str:
        """Build the current-conditions reply string."""
        try:
            temp_c = current.get("temperature_2m")
            humidity = current.get("relative_humidity_2m")
            feels_like_c = current.get("apparent_temperature")
            weather_code = current.get("weather_code")
            wind_kph = float(current.get("wind_speed_10m", 0))
            raw_gust = current.get("wind_gusts_10m")
            wind_gusts_kph = float(raw_gust) if raw_gust is not None else None
        except (TypeError, ValueError):
            return self._error_msg(requester)

        condition = self._describe_weather_code(weather_code)

        # Build the numerical portion.
        parts = [f"{condition}."]

        if temp_c is not None:
            temp_f = self._c_to_f(temp_c)
            parts.append(f"Temp: {temp_f}°F/{temp_c}°C.")
        if feels_like_c is not None:
            feels_like_f = self._c_to_f(feels_like_c)
            parts.append(f"Feels like: {feels_like_f}°F/{feels_like_c}°C.")
        if humidity is not None:
            parts.append(f"Humidity: {int(humidity)}%.")
        if wind_kph >= 0:
            wind_mph = self._kph_to_mph(wind_kph)
            if wind_gusts_kph is not None:
                gust_mph = self._kph_to_mph(wind_gusts_kph)
                parts.append(
                    f"Wind: {wind_mph} mph / {int(round(wind_kph))} km/h "
                    f"(gusts {gust_mph} mph / {int(round(wind_gusts_kph))} km/h)."
                )
            else:
                parts.append(f"Wind: {wind_mph} mph / {int(round(wind_kph))} km/h.")

        report = " ".join(parts)

        # Wrap with flavor / location prefix.
        if self.has_flavor_enabled(requester):
            title = self.bot.title_for(requester)
            if target_user:
                return (
                    f"As you wish, {title}. The weather for "
                    f"{self.bot.title_for(target_user)} in {location_name} "
                    f"is: {report}"
                )
            return f"{title}, the weather in {location_name} is: {report}"
        return f"{location_name}: {report}"

    def _format_forecast(
        self,
        daily: Dict[str, Any],
        location_name: str,
        requester: str,
    ) -> str:
        """Build the 3-day forecast reply string."""
        try:
            times = daily.get("time", [])
            codes = daily.get("weather_code", [])
            highs_c = daily.get("temperature_2m_max", [])
            lows_c = daily.get("temperature_2m_min", [])
            precip = daily.get("precipitation_sum", [])
        except (TypeError, ValueError):
            return self._error_msg(requester)

        # Skip today (index 0), take next 3 days.
        if len(times) < 4:
            return "Forecast data unavailable."

        lines = []
        for i in range(1, 4):
            try:
                day_name = datetime.strptime(times[i], "%Y-%m-%d").strftime("%A")
            except (ValueError, IndexError):
                day_name = "Unknown"

            condition = self._describe_weather_code(codes[i]) if i < len(codes) else "Unknown"

            precip_mm = precip[i] if i < len(precip) and precip[i] is not None else None
            precip_str = f" {int(precip_mm)}mm" if precip_mm and precip_mm > 0 else ""

            high_c = highs_c[i] if i < len(highs_c) and highs_c[i] is not None else None
            low_c = lows_c[i] if i < len(lows_c) and lows_c[i] is not None else None

            if high_c is not None and low_c is not None:
                high_f = self._c_to_f(high_c)
                low_f = self._c_to_f(low_c)
                temp_str = f"{high_f}/{low_f}°F ({high_c}/{low_c}°C)"
            elif high_c is not None:
                high_f = self._c_to_f(high_c)
                temp_str = f"~{high_f}°F ({high_c}°C)"
            else:
                temp_str = "N/A"

            lines.append(f"{day_name}: {condition}{precip_str}, {temp_str}")

        forecast_text = " | ".join(lines)

        if self.has_flavor_enabled(requester):
            title = self.bot.title_for(requester)
            return f"{title}, the forecast for {location_name}: {forecast_text}"
        return f"{location_name} forecast: {forecast_text}"

    def _error_msg(self, requester: str) -> str:
        if self.has_flavor_enabled(requester):
            return (
                f"My apologies, {self.bot.title_for(requester)}, "
                "I could not format the weather report."
            )
        return "Could not format weather report."

    # ------------------------------------------------------------------
    # Alerts
    # ------------------------------------------------------------------

    def _fetch_alerts(self, lat: str, lon: str) -> list:
        """Fetch active weather alerts from the US NWS API.

        Returns a list of alert property dicts with severity Severe or
        Extreme, or an empty list on failure / no alerts.
        """
        if self.http is None:
            self._record_error("HTTP client not available for alerts")
            return []

        try:
            data = self.http.get_json(
                NWS_ALERTS_URL,
                params={
                    "point": f"{lat},{lon}",
                    "status": "actual",
                    "message_type": "alert",
                },
                headers={
                    "User-Agent": "(jeeves-irc-bot)",
                    "Accept": "application/json",
                },
            )
        except Exception as exc:
            self._record_error(f"Alerts request failed: {exc}")
            return []

        features = data.get("features", [])
        if not features:
            return []

        severe = []
        for feat in features:
            props = feat.get("properties", {})
            severity = props.get("severity", "")
            if severity in ("Severe", "Extreme"):
                severe.append(props)

        return severe

    def _format_alerts(self, alerts: list, requester: str) -> str:
        """Format active alerts into concise warning.

        Returns empty string if no alerts to report.
        """
        if not alerts:
            return ""

        seen = set()
        events = []
        for a in alerts:
            event = a.get("event", "Weather Alert")
            if event not in seen:
                seen.add(event)
                events.append(event)

        if not events:
            return ""

        if len(events) == 1:
            events_str = events[0]
        elif len(events) == 2:
            events_str = f"{events[0]} and {events[1]}"
        else:
            events_str = ", ".join(events[:-1]) + f", and {events[-1]}"

        if self.has_flavor_enabled(requester):
            title = self.bot.title_for(requester)
            return f"Take care, {title}! {events_str} in your area."
        return f"URGENT: {events_str} for your location."

    # ------------------------------------------------------------------
    # Async reply helpers
    # ------------------------------------------------------------------

    def _reply_with_weather(
        self, connection, event, location_obj: Dict[str, Any],
        requester: str, target_user: Optional[str] = None,
    ) -> None:
        location_name = (
            location_obj.get("user_input")
            or location_obj.get("short_name")
            or location_obj.get("display_name")
            or "their location"
        )

        current = self._fetch_current(location_obj["lat"], location_obj["lon"])
        if current:
            report = self._format_current(
                current, location_name, requester, target_user
            )

            alerts = self._fetch_alerts(
                location_obj["lat"], location_obj["lon"]
            )
            alert_msg = self._format_alerts(alerts, requester)
            if alert_msg:
                report += "\n" + alert_msg

            self.safe_reply(connection, event, report)
            achievement_hooks.record_weather_check(self.bot, requester)
        else:
            if self.has_flavor_enabled(requester):
                self.safe_reply(
                    connection,
                    event,
                    f"My apologies, {self.bot.title_for(requester)}, "
                    "I could not fetch the weather.",
                )
            else:
                self.safe_reply(connection, event, "Could not fetch weather.")

    def _reply_with_forecast(
        self, connection, event, location_obj: Dict[str, Any],
        requester: str,
    ) -> None:
        location_name = (
            location_obj.get("user_input")
            or location_obj.get("short_name")
            or location_obj.get("display_name")
            or "the location"
        )

        daily = self._fetch_forecast(location_obj["lat"], location_obj["lon"])
        if daily:
            report = self._format_forecast(daily, location_name, requester)

            alerts = self._fetch_alerts(
                location_obj["lat"], location_obj["lon"]
            )
            alert_msg = self._format_alerts(alerts, requester)
            if alert_msg:
                report += "\n" + alert_msg

            self.safe_reply(connection, event, report)
        else:
            if self.has_flavor_enabled(requester):
                self.safe_reply(
                    connection,
                    event,
                    f"My apologies, {self.bot.title_for(requester)}, "
                    "I could not fetch the forecast.",
                )
            else:
                self.safe_reply(connection, event, "Could not fetch forecast.")

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    def _cmd_set_location(self, connection, event, msg, username, match):
        location_input = match.group(1).strip()
        geo = self._geocode(location_input)
        if not geo:
            if self.has_flavor_enabled(username):
                self.safe_reply(
                    connection,
                    event,
                    f"{self.bot.title_for(username)}, I could not find "
                    f"coordinates for '{location_input}'.",
                )
            else:
                self.safe_reply(
                    connection, event, f"Location '{location_input}' not found."
                )
            return True

        user_id = self.bot.get_user_id(username)
        locations = self.get_state("user_locations") or {}
        locations[user_id] = geo
        self.set_state("user_locations", locations)
        self.save_state()

        if self.has_flavor_enabled(username):
            self.safe_reply(
                connection,
                event,
                f"Noted, {self.bot.title_for(username)}. Your location "
                f"is set to '{geo['short_name']}'.",
            )
        else:
            self.safe_reply(
                connection, event, f"Location set to '{geo['short_name']}'."
            )
        return True

    def _cmd_clear_location(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        locations = self.get_state("user_locations") or {}
        if user_id in locations:
            del locations[user_id]
            self.set_state("user_locations", locations)
            self.save_state()
            if self.has_flavor_enabled(username):
                self.safe_reply(
                    connection,
                    event,
                    f"Your location data has been deleted, "
                    f"{self.bot.title_for(username)}.",
                )
            else:
                self.safe_reply(connection, event, "Location data deleted.")
        else:
            self.safe_reply(connection, event, "No location data to delete.")
        return True

    def _cmd_show_location(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            if self.has_flavor_enabled(username):
                self.safe_reply(
                    connection,
                    event,
                    f"{self.bot.title_for(username)}, you have not "
                    "set a location.",
                )
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
            self.safe_reply(
                connection,
                event,
                f"{self.bot.title_for(username)}, your location is set "
                f"to '{stored_name}'.",
            )
        else:
            self.safe_reply(
                connection, event, f"Your location is set to '{stored_name}'."
            )
        return True

    def _cmd_weather_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            if self.has_flavor_enabled(username):
                self.safe_reply(
                    connection,
                    event,
                    f"{self.bot.title_for(username)}, you have not "
                    "set a location.",
                )
            else:
                self.safe_reply(connection, event, "No location set.")
            return True
        self._run_async(
            self._reply_with_weather, connection, event, location_obj, username
        )
        return True

    def _cmd_weather_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()

        users_module = self.bot.pm.plugins.get("users")
        target_user_id = (
            users_module.get_state("nick_map", {}).get(query.lower())
            if users_module
            else None
        )

        if target_user_id and (
            location_obj := self.get_state("user_locations", {}).get(target_user_id)
        ):
            self._run_async(
                self._reply_with_weather,
                connection, event, location_obj, username,
                target_user=query,
            )
            return True

        def _lookup_and_reply():
            geo = self._geocode(query)
            if not geo:
                if self.has_flavor_enabled(username):
                    self.safe_reply(
                        connection,
                        event,
                        f"My apologies, I could not find a user or "
                        f"location named '{query}'.",
                    )
                else:
                    self.safe_reply(
                        connection,
                        event,
                        f"User or location '{query}' not found.",
                    )
                return
            self._reply_with_weather(connection, event, geo, username)

        self._run_async(_lookup_and_reply)
        return True

    def _cmd_forecast_self(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        location_obj = self.get_state("user_locations", {}).get(user_id)
        if not location_obj:
            if self.has_flavor_enabled(username):
                self.safe_reply(
                    connection,
                    event,
                    f"{self.bot.title_for(username)}, you have not "
                    "set a location.",
                )
            else:
                self.safe_reply(connection, event, "No location set.")
            return True
        self._run_async(
            self._reply_with_forecast, connection, event, location_obj, username
        )
        return True

    def _cmd_forecast_other(self, connection, event, msg, username, match):
        query = match.group(1).strip()

        users_module = self.bot.pm.plugins.get("users")
        target_user_id = (
            users_module.get_state("nick_map", {}).get(query.lower())
            if users_module
            else None
        )

        if target_user_id and (
            location_obj := self.get_state("user_locations", {}).get(target_user_id)
        ):
            self._run_async(
                self._reply_with_forecast,
                connection, event, location_obj, username,
            )
            return True

        def _lookup_and_reply():
            geo = self._geocode(query)
            if not geo:
                if self.has_flavor_enabled(username):
                    self.safe_reply(
                        connection,
                        event,
                        f"My apologies, I could not find a user or "
                        f"location named '{query}'.",
                    )
                else:
                    self.safe_reply(
                        connection,
                        event,
                        f"User or location '{query}' not found.",
                    )
                return
            self._reply_with_forecast(connection, event, geo, username)

        self._run_async(_lookup_and_reply)
        return True


def setup(bot):
    return Weather2(bot)
