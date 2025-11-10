"""
apioverload.py - A collection of silly and fun API integrations

Provides commands for various fun APIs:
- icanhazdadjoke: Random dad jokes
- TCGdex: Trading card game cards
- API.Bible: Bible verses
- Open Brewery DB: Brewery information
- CATAAS: Cat pictures (because internet)
- Nager.Date: Public holidays worldwide
"""

import sys
import json
import urllib.parse
from datetime import datetime
from .base import SimpleCommandModule


def setup(bot):
    return ApiOverload(bot)


class ApiOverload(SimpleCommandModule):
    name = "apioverload"
    version = "1.0.0"
    description = "A collection of fun and silly API integrations"

    def __init__(self, bot):
        super().__init__(bot)
        self.http_session = self.requests_retry_session()

        # API.Bible requires an API key
        self.bible_api_key = bot.config.get("api_keys", {}).get("bible_api_key")

    def _register_commands(self):
        """Register all the silly commands"""

        self.register_command(
            pattern=r"^\s*!dad\s*$",
            handler=self._cmd_dad,
            name="dad",
            cooldown=5.0,
            description="Get a random dad joke. Usage: !dad"
        )

        self.register_command(
            pattern=r"^\s*!card\s+(.+)$",
            handler=self._cmd_card,
            name="card",
            cooldown=3.0,
            description="Search for trading cards using TCGdex. Usage: !card <card name>"
        )

        self.register_command(
            pattern=r"^\s*!verse\s+(.+)$",
            handler=self._cmd_verse,
            name="verse",
            cooldown=3.0,
            description="Get a Bible verse. Usage: !verse <reference> (e.g., !verse John 3:16)"
        )

        self.register_command(
            pattern=r"^\s*!brewery(?:\s+(.+))?$",
            handler=self._cmd_brewery,
            name="brewery",
            cooldown=3.0,
            description="Search for breweries. Usage: !brewery <city or name>"
        )

        self.register_command(
            pattern=r"^\s*!cat(?:\s+(.+))?$",
            handler=self._cmd_cat,
            name="cat",
            cooldown=3.0,
            description="Get a random cat picture! Usage: !cat [tag]"
        )

        self.register_command(
            pattern=r"^\s*!holiday(?:\s+(.+))?$",
            handler=self._cmd_holiday,
            name="holiday",
            cooldown=5.0,
            description="Get today's holidays worldwide or search by country. Usage: !holiday [country code]"
        )

    def _cmd_dad(self, connection, event, msg, username, match):
        """Get a random dad joke from icanhazdadjoke"""
        if not self.is_enabled(event.target):
            return False

        try:
            headers = {
                "Accept": "application/json",
                "User-Agent": "JeevesBot IRC Bot (https://github.com/yourusername/jeeves)"
            }
            response = self.http_session.get("https://icanhazdadjoke.com/", headers=headers, timeout=10)
            response.raise_for_status()
            data = response.json()

            joke = data.get("joke", "I forgot the punchline!")
            self.safe_reply(connection, event, joke)

        except Exception as e:
            self.log_debug(f"Error fetching dad joke: {e}")
            self.safe_reply(connection, event, "Error fetching dad joke. I guess I'm not very punny today!")

        return True

    def _cmd_card(self, connection, event, msg, username, match):
        """Search TCGdex for trading card information"""
        if not self.is_enabled(event.target):
            return False

        search_term = match.group(1).strip()

        try:
            # TCGdex API - search for Pokemon cards (most popular TCG)
            url = f"https://api.tcgdex.net/v2/en/cards?name={urllib.parse.quote(search_term)}"
            response = self.http_session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            if not data or len(data) == 0:
                self.safe_reply(connection, event, f"No cards found for '{search_term}'")
                return True

            # Get first card's basic info
            card = data[0]
            card_id = card.get("id", "")

            # Fetch full card details to get flavor text
            detail_url = f"https://api.tcgdex.net/v2/en/cards/{card_id}"
            detail_response = self.http_session.get(detail_url, timeout=10)
            detail_response.raise_for_status()
            full_card = detail_response.json()

            card_name = full_card.get("name", "Unknown Card")
            set_name = full_card.get("set", {}).get("name", "Unknown Set")
            rarity = full_card.get("rarity", "Unknown")

            # Get HP and types if available
            hp = full_card.get("hp", "N/A")
            types = full_card.get("types", [])
            types_str = "/".join(types) if types else "N/A"

            # Get flavor text (description)
            flavor_text = full_card.get("description", "")

            # Build response
            response_text = f"{card_name} ({card_id}) - {set_name} | Type: {types_str} | HP: {hp} | Rarity: {rarity}"

            # Add flavor text if available (trim if too long)
            if flavor_text:
                if len(flavor_text) > 150:
                    flavor_text = flavor_text[:150] + "..."
                response_text += f" | {flavor_text}"

            self.safe_reply(connection, event, response_text)

        except Exception as e:
            self.log_debug(f"Error fetching card data: {e}")
            self.safe_reply(connection, event, f"Error fetching card data: {str(e)}")

        return True

    def _cmd_verse(self, connection, event, msg, username, match):
        """Get a Bible verse from API.Bible"""
        if not self.is_enabled(event.target):
            return False

        verse_ref = match.group(1).strip()

        if not self.bible_api_key:
            self.safe_reply(connection, event,
                          "Bible API key not configured. Please add 'bible_api_key' to api_keys in config to use this command.")
            return True

        try:
            # API.Bible requires authentication
            headers = {"api-key": self.bible_api_key}

            # Using KJV Bible
            bible_id = "de4e12af7f28f599-02"

            # First, search to find the verse ID
            search_url = f"https://rest.api.bible/v1/bibles/{bible_id}/search"
            params = {"query": verse_ref, "limit": 1}
            response = self.http_session.get(search_url, headers=headers, params=params, timeout=10)

            # Log the actual response for debugging
            self.log_debug(f"[apioverload] Bible API status: {response.status_code}")

            response.raise_for_status()
            data = response.json()

            if not data.get("data", {}).get("verses"):
                self.safe_reply(connection, event, f"Verse not found: {verse_ref}")
                return True

            # Get the verse ID
            verse_data = data["data"]["verses"][0]
            verse_id = verse_data.get("id")

            # Now fetch the full verse text
            verse_url = f"https://rest.api.bible/v1/bibles/{bible_id}/verses/{verse_id}"
            verse_response = self.http_session.get(verse_url, headers=headers, params={"content-type": "text"}, timeout=10)
            verse_response.raise_for_status()
            verse_json = verse_response.json()

            verse_content = verse_json.get("data", {}).get("content", "")
            verse_reference = verse_json.get("data", {}).get("reference", verse_ref)

            # Clean up HTML tags if present
            import re
            verse_text = re.sub(r'<[^>]+>', '', verse_content).strip()

            # Trim if too long
            if len(verse_text) > 350:
                verse_text = verse_text[:350] + "..."

            self.safe_reply(connection, event, f"{verse_reference}: {verse_text}")

        except Exception as e:
            self.log_debug(f"[apioverload] Error fetching Bible verse: {e}")
            self.safe_reply(connection, event, f"Error fetching verse: {str(e)}")

        return True

    def _cmd_brewery(self, connection, event, msg, username, match):
        """Search Open Brewery DB"""
        if not self.is_enabled(event.target):
            return False

        search_term = match.group(1)

        if not search_term:
            # Get a random brewery
            url = "https://api.openbrewerydb.org/v1/breweries/random"
        else:
            search_term = search_term.strip()
            # Search by city or name
            url = f"https://api.openbrewerydb.org/v1/breweries?by_city={urllib.parse.quote(search_term)}&per_page=1"

        try:
            response = self.http_session.get(url, timeout=10)
            response.raise_for_status()
            data = response.json()

            # Handle both single object and array responses
            if isinstance(data, list):
                if len(data) == 0:
                    self.safe_reply(connection, event, f"No breweries found for '{search_term}'")
                    return True
                brewery = data[0]
            else:
                brewery = data

            name = brewery.get("name", "Unknown Brewery")
            brewery_type = brewery.get("brewery_type", "").replace("_", " ").title()
            city = brewery.get("city", "")
            state = brewery.get("state", "")
            country = brewery.get("country", "")

            location_parts = [p for p in [city, state, country] if p]
            location = ", ".join(location_parts) if location_parts else "Unknown Location"

            website = brewery.get("website_url", "")

            response_text = f"{name} ({brewery_type}) - {location}"
            if website:
                response_text += f" | {website}"

            self.safe_reply(connection, event, response_text)

        except Exception as e:
            self.log_debug(f"Error fetching brewery data: {e}")
            self.safe_reply(connection, event, f"Error fetching brewery data: {str(e)}")

        return True

    def _cmd_cat(self, connection, event, msg, username, match):
        """Get a random cat picture from CATAAS"""
        if not self.is_enabled(event.target):
            return False

        tag = match.group(1)

        try:
            if tag:
                tag = tag.strip()
                url = f"https://cataas.com/cat/{urllib.parse.quote(tag)}"
            else:
                url = "https://cataas.com/cat"

            # CATAAS returns the image directly, so we just return the URL
            # We could also get JSON with /cat?json=true
            json_url = url + ("&json=true" if "?" in url else "?json=true")
            response = self.http_session.get(json_url, timeout=10)

            if response.status_code == 404:
                self.safe_reply(connection, event, f"No cats found with tag '{tag}'. Try another tag or use !cat for a random cat.")
                return True

            response.raise_for_status()
            data = response.json()

            # Build the full URL
            cat_url = f"{data.get('url', '/cat')}"

            tags = data.get("tags", [])
            tags_str = f" (tags: {', '.join(tags)})" if tags else ""

            self.safe_reply(connection, event, f"Here's a cat{tags_str}: {cat_url}")

        except Exception as e:
            self.log_debug(f"Error fetching cat: {e}")
            # Fallback to just returning the URL
            url = "https://cataas.com/cat"
            self.safe_reply(connection, event, f"Here's a cat: {url}")

        return True

    def _cmd_holiday(self, connection, event, msg, username, match):
        """Get today's holidays worldwide or for a specific country"""
        if not self.is_enabled(event.target):
            return False

        country_code = match.group(1)
        today = datetime.now().strftime("%Y-%m-%d")

        try:
            if country_code:
                # Get holidays for a specific country
                country_code = country_code.strip().upper()
                year = datetime.now().year
                url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
                response = self.http_session.get(url, timeout=10)

                if response.status_code == 404:
                    self.safe_reply(connection, event, f"Country code '{country_code}' not found. Try a 2-letter ISO code like US, GB, DE, etc.")
                    return True

                response.raise_for_status()
                data = response.json()

                # Filter for today's date
                today_holidays = [h for h in data if h.get("date") == today]

                if not today_holidays:
                    self.safe_reply(connection, event, f"No holidays today in {country_code}")
                    return True

                # Format the holidays
                holiday_names = [h.get("localName", h.get("name", "Unknown")) for h in today_holidays]
                self.safe_reply(connection, event, f"Holidays today in {country_code}: {', '.join(holiday_names)}")

            else:
                # Get worldwide holidays happening today
                url = "https://date.nager.at/api/v3/NextPublicHolidaysWorldwide"
                response = self.http_session.get(url, timeout=10)
                response.raise_for_status()
                data = response.json()

                # Filter for today's date
                today_holidays = [h for h in data if h.get("date") == today]

                if not today_holidays:
                    self.safe_reply(connection, event, "No major holidays being celebrated worldwide today")
                    return True

                # Group by holiday name and collect countries
                holidays_by_name = {}
                for holiday in today_holidays:
                    name = holiday.get("localName", holiday.get("name", "Unknown"))
                    country = holiday.get("countryCode", "??")
                    if name not in holidays_by_name:
                        holidays_by_name[name] = []
                    holidays_by_name[name].append(country)

                # Format response - limit to top 5 to avoid spam
                response_parts = []
                for name, countries in list(holidays_by_name.items())[:5]:
                    country_list = ", ".join(countries[:5])  # Limit countries shown
                    if len(countries) > 5:
                        country_list += f" +{len(countries) - 5} more"
                    response_parts.append(f"{name} ({country_list})")

                if len(holidays_by_name) > 5:
                    response_parts.append(f"and {len(holidays_by_name) - 5} more...")

                self.safe_reply(connection, event, f"Holidays today: {' | '.join(response_parts)}")

        except Exception as e:
            self.log_debug(f"Error fetching holiday data: {e}")
            self.safe_reply(connection, event, f"Error fetching holiday data: {str(e)}")

        return True
