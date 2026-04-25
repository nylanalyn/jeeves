# modules/weird_weather.py
# Turn !w responses into absurd, obscure units of measurement.
# Toggle on/off per-channel with !weird. Admin-only toggle.

import re
import math
import random
import threading
from typing import Optional
from .base import SimpleCommandModule, admin_required


class WeirdWeather(SimpleCommandModule):
    name = "weird_weather"
    version = "1.0.0"
    description = "Toggles absurd weather units for the weather module."

    def __init__(self, bot):
        super().__init__(bot)
        if self.get_state("enabled_channels") is None:
            self.set_state("enabled_channels", {})
            self.save_state()

    def _register_commands(self):
        self.register_command(r"^\s*!weird\s*$",     self._cmd_toggle, name="toggle", description="Toggle absurd weather units for this channel")
        self.register_command(r"^\s*!weird\s+(on|off)\s*$", self._cmd_set,    name="set",    description="Explicitly set weird weather on/off")

    # ------------------------------------------------------------------
    #  Conversions
    # ------------------------------------------------------------------
    ABSURD_TEMPS = [
        ("Rankine",  "°R",  lambda c: round((c * 9 / 5) + 491.67, 1) if c is not None else None, "Absolute scale; water freezes at ~491.67°R"),
        ("Delisle",  "°D",  lambda c: round((100 - c) * 1.5, 1)      if c is not None else None, "Backwards scale; 100°D = freezing"),
        ("Newton",   "°N",  lambda c: round(c * 0.33, 1)              if c is not None else None, "Isaac's scale; water freezes at 0°N"),
        ("Réaumur",  "°Ré", lambda c: round(c * 0.8, 1)              if c is not None else None, "18th-century French; popular in czarist Russia"),
    ]

    @staticmethod
    def _to_furlongs_per_fortnight(mph: float) -> int:
        return round(mph * 2688)

    @staticmethod
    def _to_knots(mph: float) -> int:
        return round(mph * 0.868976)

    @staticmethod
    def _to_beaufort(mph: float) -> str:
        grade = min(12, max(0, int(round((mph / 1.15) ** (2 / 3)))))
        names = [
            "Calm", "Light air", "Light breeze", "Gentle breeze",
            "Moderate breeze", "Fresh breeze", "Strong breeze",
            "High wind", "Gale", "Strong gale", "Storm",
            "Violent storm", "Hurricane"
        ]
        return f"{grade} ({names[grade]})"

    @staticmethod
    def _to_mach(mph: float) -> str:
        return f"{mph / 761.0:.5f}"

    ABSURD_WINDS = [
        ("furlongs/fortnight", _to_furlongs_per_fortnight),
        ("knots",              _to_knots),
        ("Beaufort",           _to_beaufort),
        ("Mach (sea level)",    _to_mach),
    ]

    @staticmethod
    def _to_grains_per_cubic_foot(temp_c: float, rh: float) -> int:
        sat_vp = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
        vp = sat_vp * (rh / 100.0)
        kg_m3 = (vp * 100) / (461.5 * (temp_c + 273.15))
        return round(kg_m3 * 436995.72)

    @staticmethod
    def _to_dew_gap(temp_c: float, rh: float) -> str:
        a, b = 17.271, 237.7
        alpha = ((a * temp_c) / (b + temp_c)) + math.log(rh / 100.0)
        dew_c = (b * alpha) / (a - alpha)
        return f"{temp_c - dew_c:.1f}°C gap"

    @staticmethod
    def _to_grams_water_per_m3(temp_c: float, rh: float) -> str:
        sat_vp = 6.112 * math.exp((17.67 * temp_c) / (temp_c + 243.5))
        vp = sat_vp * (rh / 100.0)
        g_m3 = (vp * 100) / (461.5 * (temp_c + 273.15)) * 1000
        return f"{g_m3:.1f} g H₂O/m³"

    ABSURD_HUMIDITIES = [
        ("gr/ft³",           _to_grains_per_cubic_foot,    "Obscure absolute humidity unit. Real, genuinely used in HVAC"),
        ("dew gap",          _to_dew_gap,                   "Dew-point offset — how dry the air is"),
        ("g H₂O/m³",         _to_grams_water_per_m3,        "Actual water vapor density"),
    ]

    # ------------------------------------------------------------------
    #  Random selection per report
    # ------------------------------------------------------------------

    def _pick_temp(self, celsius: Optional[float]) -> str:
        name, sym, fn, _ = random.choice(self.ABSURD_TEMPS)
        val = fn(celsius)
        return f"{val}{sym}" if val is not None else "N/A"

    def _pick_wind(self, mph: float) -> str:
        lbl, fn = random.choice(self.ABSURD_WINDS)
        val = fn(mph)
        if lbl == "knots":
            return f"{val} knots"
        if lbl == "Mach (sea level)":
            return f"Mach {val}"
        return f"{val} {lbl}"

    def _pick_humidity(self, temp_c: float, rh: float) -> str:
        lbl, fn, desc = random.choice(self.ABSURD_HUMIDITIES)
        val = fn(temp_c, rh)
        if lbl == "dew gap":
            return f"{val}"
        return f"{val}"

    # ------------------------------------------------------------------
    #  Report mangler — works on the already-formatted text
    # ------------------------------------------------------------------
    def _mangle_report(self, report: str, temp_c: Optional[float], humidity_pct: Optional[float], wind_mph: float) -> str:
        """
        Swap readable units in `report` for absurd ones.
        Assumes the exact structure produced by the weather module.
        """
        out = report
        if temp_c is not None:
            weird = self._pick_temp(temp_c)
            out = re.sub(r'Temp: [^\.]+\.',  f'Temp: {weird}.', out)
            out = re.sub(r'Feels like: [^\.]+\.', f'Feels like: {weird}.', out)
        if wind_mph is not None:
            weird = self._pick_wind(wind_mph)
            out = re.sub(r'Wind: [^\.]+\.', f'Wind: {weird}.', out)
        if humidity_pct is not None and temp_c is not None:
            weird = self._pick_humidity(temp_c, humidity_pct)
            out = re.sub(r'Humidity: [^\.]+\.', f'Humidity: {weird}.', out)
        return out

    # ------------------------------------------------------------------
    #  Hooks into the weather module
    # ------------------------------------------------------------------

    def _is_weird(self, channel: str) -> bool:
        return self.get_state("enabled_channels", {}).get(channel, False)

    def _install_hooks(self):
        """Monkey-patch the weather module's reply method."""
        weather_mod = self.bot.pm.plugins.get("weather")
        if not weather_mod:
            return False
        if getattr(weather_mod, "_weird_installed", False):
            return True

        weird_self = self
        orig_format = weather_mod._format_weather_report

        # no-op in single-thread; harmless safeguard otherwise
        _ctx = threading.local()
        _ctx.channel = None

        def _weird_reply(self, connection, event, location_obj, requester, target_user=None):
            channel = event.target
            location_name = (
                location_obj.get('user_input')
                or location_obj.get('short_name')
                or location_obj.get('display_name')
                or 'their location'
            )
            country_code = location_obj.get('country_code', 'US').upper()

            result = weather_mod._get_weather_data(location_obj["lat"], location_obj["lon"], country_code)
            if result:
                data, is_pirate = result
                report = orig_format(data, location_name, requester, is_pirate, target_user)

                if weird_self._is_weird(channel):
                    # Extract raw numbers for conversions
                    raw_tc = raw_rh = raw_wind = None
                    try:
                        if is_pirate:
                            cur = data.get('currently', {})
                            tf = cur.get('temperature')
                            raw_tc = round((tf - 32) * 5 / 9, 1) if tf is not None else None
                            h = cur.get('humidity')
                            raw_rh = int(h * 100) if h is not None else None
                            raw_wind = round(cur.get('windSpeed', 0.0))
                        else:
                            details = data['properties']['timeseries'][0]['data']['instant']['details']
                            raw_tc = details.get('air_temperature')
                            raw_rh = details.get('relative_humidity')
                            ws = float(details.get('wind_speed', 0.0))
                            raw_wind = round(ws * 2.237)
                    except Exception:
                        pass
                    report = weird_self._mangle_report(
                        report, raw_tc, raw_rh, raw_wind if raw_wind else 0
                    )

                weather_mod.safe_reply(connection, event, report)
                from . import achievement_hooks
                achievement_hooks.record_weather_check(weather_mod.bot, requester)
            else:
                if weather_mod.has_flavor_enabled(requester):
                    weather_mod.safe_reply(
                        connection, event,
                        f"My apologies, {weather_mod.bot.title_for(requester)}, I could not fetch the weather."
                    )
                else:
                    weather_mod.safe_reply(connection, event, "Could not fetch weather.")

        weather_mod._reply_with_weather_original = weather_mod._reply_with_weather
        weather_mod._reply_with_weather = _weird_reply
        weather_mod._weird_installed = True
        weather_mod._weird_original = orig_format
        return True

    def _uninstall_hooks(self):
        weather_mod = self.bot.pm.plugins.get("weather")
        if not weather_mod:
            return False
        if getattr(weather_mod, "_weird_installed", False):
            weather_mod._reply_with_weather = weather_mod._reply_with_weather_original
            del weather_mod._reply_with_weather_original
            del weather_mod._weird_installed
            weather_mod._weird_original = weather_mod._weird_original  # no-op holder; clean it up
            if hasattr(weather_mod, "_weird_original"):
                del weather_mod._weird_original
            return True
        return False

    # ------------------------------------------------------------------
    #  Commands
    # ------------------------------------------------------------------

    @admin_required
    def _cmd_toggle(self, connection, event, msg, username, match):
        channel = event.target
        enabled = self._is_weird(channel)
        new_state = not enabled
        channels = self.get_state("enabled_channels", {})
        channels[channel] = new_state
        self.set_state("enabled_channels", channels)
        self.save_state()

        _t  = random.choice([t[0] for t in self.ABSURD_TEMPS])
        _w  = random.choice([w[0] for w in self.ABSURD_WINDS])
        _h  = random.choice([h[0] for h in self.ABSURD_HUMIDITIES])

        if new_state:
            ok = self._install_hooks()
            self.safe_reply(connection, event,
                f"🌀 WEIRD WEATHER ENGAGED. Temperatures now in {_t}. "
                f"Wind in {_w}. Humidity in {_h}. "
                f"Good luck deciphering reality. | Use !weird to toggle off."
            )
        else:
            self._uninstall_hooks()
            self.safe_reply(connection, event,
                "🌡️ WEIRD WEATHER DISENGAGED. Readable units restored. The normies thank you."
            )

    @admin_required
    def _cmd_set(self, connection, event, msg, username, match):
        channel = event.target
        want = match.group(1).lower()
        channels = self.get_state("enabled_channels", {})
        if want == "on":
            channels[channel] = True
            self.set_state("enabled_channels", channels)
            self.save_state()
            self._install_hooks()
            self.safe_reply(connection, event, "🌀 WEIRD WEATHER: ON (forced).| Use !weird to toggle.")
        else:
            channels[channel] = False
            self.set_state("enabled_channels", channels)
            self.save_state()
            self._uninstall_hooks()
            self.safe_reply(connection, event, "🌡️ WEIRD WEATHER: OFF (forced).| Use !weird to toggle.")

    def on_module_loaded(self):
        """Re-apply hooks on restart if any channel(s) were left weird."""
        channels = self.get_state("enabled_channels", {})
        if any(channels.values()):
            self._install_hooks()
