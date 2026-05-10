import unittest
from types import SimpleNamespace

from modules.weather2 import OPEN_METEO_GEO_URL, Weather2


SPAIN_OVIEDO = {
    "name": "Oviedo",
    "latitude": 43.36029,
    "longitude": -5.84476,
    "country_code": "ES",
    "country": "Spain",
    "admin1": "Principality of Asturias",
}

FLORIDA_OVIEDO = {
    "name": "Oviedo",
    "latitude": 28.67,
    "longitude": -81.20812,
    "country_code": "US",
    "country": "United States",
    "admin1": "Florida",
}


class FakeHTTP:
    def __init__(self, results):
        self.results = results
        self.calls = []

    def get_json(self, url, params=None, headers=None):
        self.calls.append((url, dict(params or {}), dict(headers or {})))
        if url != OPEN_METEO_GEO_URL:
            raise AssertionError(f"unexpected URL: {url}")
        return {"results": self.results}


class ConnectionStub:
    def __init__(self):
        self.messages = []

    def privmsg(self, target, text):
        self.messages.append((target, text))


class UsersStub:
    def has_flavor_enabled(self, username):
        return False

    def get_state(self, key=None, default=None):
        if key == "nick_map":
            return {}
        return default


class BotStub:
    def __init__(self):
        self.config = {"weather2": {"allowed_channels": ["#test"]}}
        self.primary_channel = "#test"
        self.JEEVES_NAME_RE = r"jeeves"
        self.pm = SimpleNamespace(plugins={"users": UsersStub()})
        self._states = {"weather2": {}, "weather": {}}
        self.debug_messages = []

    def get_module_state(self, name):
        return self._states.setdefault(name, {}).copy()

    def update_module_state(self, name, state):
        self._states[name] = state.copy()

    def get_user_id(self, username):
        return f"user:{username.lower()}"

    def title_for(self, username):
        return username

    def log_debug(self, message):
        self.debug_messages.append(message)


def make_weather(results):
    bot = BotStub()
    weather = Weather2(bot)
    weather.http = FakeHTTP(results)
    return bot, weather


def event(username="Alice", target="#test"):
    return SimpleNamespace(target=target, source=SimpleNamespace(nick=username))


class TestWeather2Geocoding(unittest.TestCase):
    def test_state_code_query_searches_city_and_filters_us_admin1(self):
        _, weather = make_weather([SPAIN_OVIEDO, FLORIDA_OVIEDO])

        geo = weather._geocode("oviedo, fl")

        self.assertIsNotNone(geo)
        self.assertEqual(geo["lat"], "28.67")
        self.assertEqual(geo["lon"], "-81.20812")
        self.assertEqual(geo["short_name"], "Oviedo, Florida, US")
        self.assertEqual(geo["user_input"], "oviedo, fl")
        _, params, _ = weather.http.calls[-1]
        self.assertEqual(params["name"], "oviedo")
        self.assertEqual(params["count"], 100)

    def test_usa_query_searches_city_and_filters_country(self):
        _, weather = make_weather([SPAIN_OVIEDO, FLORIDA_OVIEDO])

        geo = weather._geocode("oviedo USA")

        self.assertIsNotNone(geo)
        self.assertEqual(geo["short_name"], "Oviedo, Florida, US")
        self.assertEqual(geo["user_input"], "oviedo USA")
        _, params, _ = weather.http.calls[-1]
        self.assertEqual(params["name"], "oviedo")
        self.assertEqual(params["count"], 100)

    def test_comma_us_query_searches_city_and_filters_country(self):
        _, weather = make_weather([SPAIN_OVIEDO, FLORIDA_OVIEDO])

        geo = weather._geocode("oviedo, us")

        self.assertIsNotNone(geo)
        self.assertEqual(geo["short_name"], "Oviedo, Florida, US")
        _, params, _ = weather.http.calls[-1]
        self.assertEqual(params["name"], "oviedo")
        self.assertEqual(params["count"], 100)


    def test_unqualified_query_keeps_open_meteo_top_result(self):
        _, weather = make_weather([SPAIN_OVIEDO, FLORIDA_OVIEDO])

        geo = weather._geocode("oviedo")

        self.assertIsNotNone(geo)
        self.assertEqual(
            geo["short_name"], "Oviedo, Principality of Asturias, ES"
        )
        _, params, _ = weather.http.calls[-1]
        self.assertEqual(params["name"], "oviedo")
        self.assertEqual(params["count"], 1)

    def test_state_code_query_does_not_fall_back_to_wrong_state(self):
        _, weather = make_weather([SPAIN_OVIEDO, FLORIDA_OVIEDO])

        self.assertIsNone(weather._geocode("oviedo, ca"))

    def test_location_command_accepts_state_code(self):
        bot, weather = make_weather([SPAIN_OVIEDO, FLORIDA_OVIEDO])
        connection = ConnectionStub()

        handled = weather._dispatch_commands(
            connection, event(), "!location oviedo, fl", "Alice"
        )

        self.assertTrue(handled)
        self.assertEqual(
            connection.messages[-1],
            ("#test", "Location set to 'Oviedo, Florida, US'."),
        )
        stored = bot._states["weather2"]["user_locations"]["user:alice"]
        self.assertEqual(stored["short_name"], "Oviedo, Florida, US")


if __name__ == "__main__":
    unittest.main()
