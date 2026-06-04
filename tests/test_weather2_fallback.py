import unittest

from modules.weather2 import WTTR_URL, Weather2
from tests.test_weather2_geocode import BotStub, ConnectionStub, event


WTTR_CURRENT = {
    "weatherDesc": [{"value": "Partly cloudy"}],
    "temp_F": "81",
    "temp_C": "27",
    "FeelsLikeF": "84",
    "FeelsLikeC": "29",
    "humidity": "74",
    "windspeedMiles": "9",
    "windspeedKmph": "14",
}

LOCATION = {
    "lat": "27.95",
    "lon": "-82.46",
    "user_input": "Tampa, Florida",
}


class FallbackHTTP:
    def __init__(self, wttr_data=None):
        self.wttr_data = wttr_data
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        if url.startswith(WTTR_URL):
            if self.wttr_data is None:
                raise RuntimeError("wttr.in unavailable")
            return {"current_condition": [self.wttr_data]}
        raise RuntimeError("Open-Meteo unavailable")


class FlavorUsersStub:
    def has_flavor_enabled(self, username):
        return True

    def get_state(self, key=None, default=None):
        return default


class TestWeather2Fallback(unittest.TestCase):
    def make_weather(self, wttr_data=WTTR_CURRENT, flavor=False):
        bot = BotStub()
        if flavor:
            bot.pm.plugins["users"] = FlavorUsersStub()
        weather = Weather2(bot)
        fake_http = FallbackHTTP(wttr_data)
        weather.forecast_http = fake_http
        weather.fallback_http = fake_http
        return weather

    def test_current_weather_uses_wttr_after_open_meteo_failure(self):
        weather = self.make_weather()
        connection = ConnectionStub()

        weather._reply_with_weather(connection, event(), LOCATION, "Alice")

        self.assertEqual(
            connection.messages[-1],
            (
                "#test",
                "Open-Meteo appears to be broken. Temporary wttr.in replacement "
                "for Tampa, Florida: Partly cloudy. Temp: 81°F/27°C. "
                "Feels like: 84°F/29°C. Humidity: 74%. Wind: 9 mph / 14 km/h.",
            ),
        )
        self.assertEqual(
            weather.fallback_http.calls[-1][0],
            "https://wttr.in/27.95,-82.46",
        )
        self.assertEqual(weather.fallback_http.calls[-1][1], {"format": "j1"})

    def test_forecast_uses_basic_wttr_fallback_with_title(self):
        weather = self.make_weather(flavor=True)
        connection = ConnectionStub()

        weather._reply_with_forecast(connection, event(), LOCATION, "Alice")

        self.assertTrue(
            connection.messages[-1][1].startswith(
                "Open-Meteo appears to be broken, Alice. I can offer this "
                "temporary replacement from wttr.in for Tampa, Florida:"
            )
        )

    def test_reports_original_failure_when_wttr_is_also_unavailable(self):
        weather = self.make_weather(wttr_data=None)
        connection = ConnectionStub()

        weather._reply_with_weather(connection, event(), LOCATION, "Alice")

        self.assertEqual(
            connection.messages[-1],
            ("#test", "Could not fetch weather."),
        )


if __name__ == "__main__":
    unittest.main()
