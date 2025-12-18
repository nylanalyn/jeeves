"""
apioverload.py - A collection of silly and fun API integrations

Provides commands for various fun APIs:
- icanhazdadjoke: Random dad jokes
- TCGdex: Trading card game cards
- API.Bible: Bible verses
- Open Brewery DB: Brewery information
- CATAAS: Cat pictures (because internet)
- Nager.Date: Public holidays worldwide
- IMDb API: Movie and TV show information
- MusicBrainz: Artist and band information
"""

import sys
import json
import re
import urllib.parse
from datetime import datetime
from .base import SimpleCommandModule
from .exception_utils import (
    handle_exceptions, safe_api_call, ExternalAPIException,
    UserInputException, log_module_event, log_security_event
)


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

        self.register_command(
            pattern=r"^\s*!imdb\s+(.+)$",
            handler=self._cmd_imdb,
            name="imdb",
            cooldown=3.0,
            description="Search IMDb for movies and TV shows. Usage: !imdb <title>"
        )

        self.register_command(
            pattern=r"^\s*!music\s+(.+)$",
            handler=self._cmd_music,
            name="music",
            cooldown=3.0,
            description="Look up artist/band info from MusicBrainz. Usage: !music <artist name>"
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

    @handle_exceptions(
        error_message="TCGdex API call failed",
        user_message="Unable to fetch card information at the moment. Please try again later.",
        log_exception=True,
        reraise=False
    )
    def _cmd_card(self, connection, event, msg, username, match):
        """Search TCGdex for trading card information"""
        if not self.is_enabled(event.target):
            return False

        search_term = match.group(1).strip()
        
        # Validate search term
        if len(search_term) > 100:
            raise UserInputException("Search term too long", "Search term is too long. Please use a shorter search term.")

        # TCGdex API - search for Pokemon cards (most popular TCG)
        url = f"https://api.tcgdex.net/v2/en/cards?name={urllib.parse.quote(search_term)}"
        response, error = safe_api_call(
            self.http_session.get, url, timeout=10,
            api_name="TCGdex API",
            user_message="Unable to fetch card information at the moment. Please try again later."
        )

        if error:
            # safe_api_call already logged the error details
            self.safe_reply(connection, event, error)
            return False

        data = response.json()

        if not data or len(data) == 0:
            self.safe_reply(connection, event, f"No cards found for '{search_term}'")
            return True

        # Get first card's basic info
        card = data[0]
        card_id = card.get("id", "")

        # Fetch full card details to get flavor text
        detail_url = f"https://api.tcgdex.net/v2/en/cards/{card_id}"
        detail_response, error = safe_api_call(
            self.http_session.get, detail_url, timeout=10,
            api_name="TCGdex Detail API",
            user_message="Unable to fetch card details at the moment."
        )

        if error:
            self.safe_reply(connection, event, error)
            return False
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
        log_module_event(self.name, "Card information fetched", {"user": username, "search_term": search_term})

        return True

    @handle_exceptions(
        error_message="Bible API call failed",
        user_message="Unable to fetch Bible verse at the moment. Please try again later.",
        log_exception=True,
        reraise=False
    )
    def _cmd_verse(self, connection, event, msg, username, match):
        """Get a Bible verse from API.Bible"""
        if not self.is_enabled(event.target):
            return False

        verse_ref = match.group(1).strip()

        if not self.bible_api_key:
            self.safe_reply(connection, event,
                          "Bible API key not configured. Please add 'bible_api_key' to api_keys in config to use this command.")
            return True

        # Validate verse reference
        if len(verse_ref) > 100:
            raise UserInputException("Verse reference too long", "Verse reference is too long. Please use a shorter reference.")

        # API.Bible requires authentication
        headers = {"api-key": self.bible_api_key}

        # Using KJV Bible
        bible_id = "de4e12af7f28f599-02"

        # First, search to find the verse ID
        search_url = f"https://rest.api.bible/v1/bibles/{bible_id}/search"
        params = {"query": verse_ref, "limit": 1}
        response, error = safe_api_call(
            self.http_session.get, search_url, headers=headers, params=params, timeout=10,
            api_name="Bible Search API",
            user_message="Unable to search for Bible verse at the moment."
        )

        if error:
            # safe_api_call already logged the error details
            self.safe_reply(connection, event, error)
            return False

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
        verse_response, error = safe_api_call(
            self.http_session.get, verse_url, headers=headers, params={"content-type": "text"}, timeout=10,
            api_name="Bible Verse API",
            user_message="Unable to fetch verse text at the moment."
        )

        if error:
            # safe_api_call already logged the error details
            self.safe_reply(connection, event, error)
            return False

        verse_response.raise_for_status()
        verse_json = verse_response.json()

        verse_content = verse_json.get("data", {}).get("content", "")
        verse_reference = verse_json.get("data", {}).get("reference", verse_ref)

        # Clean up HTML tags if present
        verse_text = re.sub(r'<[^>]+>', '', verse_content).strip()

        # Trim if too long
        if len(verse_text) > 350:
            verse_text = verse_text[:350] + "..."

        self.safe_reply(connection, event, f"{verse_reference}: {verse_text}")
        log_module_event(self.name, "Bible verse fetched", {"user": username, "verse": verse_ref})

        return True

    @handle_exceptions(
        error_message="Brewery API call failed",
        user_message="Unable to fetch brewery information at the moment. Please try again later.",
        log_exception=True,
        reraise=False
    )
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
            # Validate search term
            if len(search_term) > 50:
                raise UserInputException("Search term too long", "Search term is too long. Please use a shorter search term.")
            # Search by city or name
            url = f"https://api.openbrewerydb.org/v1/breweries?by_city={urllib.parse.quote(search_term)}&per_page=1"

        response, error = safe_api_call(
            self.http_session.get, url, timeout=10,
            api_name="Brewery API",
            user_message="Unable to fetch brewery information at the moment."
        )

        if error:
            # safe_api_call already logged the error details
            self.safe_reply(connection, event, error)
            return False

        response.raise_for_status()
        data = response.json()

        # Handle both single object and array responses
        if isinstance(data, list):
            if len(data) == 0:
                msg = f"No breweries found for '{search_term}'" if search_term else "No random brewery found"
                self.safe_reply(connection, event, msg)
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
        log_module_event(self.name, "Brewery information fetched", {"user": username, "search_term": search_term or "random"})

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

    @handle_exceptions(
        error_message="IMDb API call failed",
        user_message="Unable to fetch movie/TV information at the moment. Please try again later.",
        log_exception=True,
        reraise=False
    )
    def _cmd_imdb(self, connection, event, msg, username, match):
        """Search IMDb for movies and TV shows"""
        if not self.is_enabled(event.target):
            return False

        search_term = match.group(1).strip()

        # Validate search term
        if len(search_term) > 100:
            raise UserInputException("Search term too long", "Search term is too long. Please use a shorter title.")

        # IMDb API search
        url = f"https://api.imdbapi.dev/search/titles?query={urllib.parse.quote(search_term)}&limit=1"
        headers = {
            "Accept": "application/json",
            "User-Agent": "JeevesBot IRC Bot"
        }

        response, error = safe_api_call(
            self.http_session.get, url, headers=headers, timeout=10,
            api_name="IMDb API",
            user_message="Unable to fetch movie/TV information at the moment."
        )

        if error:
            self.safe_reply(connection, event, error)
            return False

        data = response.json()
        titles = data.get("titles", [])

        if not titles:
            self.safe_reply(connection, event, f"No results found for '{search_term}'")
            return True

        # Get first result
        title = titles[0]

        name = title.get("primaryTitle", title.get("originalTitle", "Unknown"))
        title_type = title.get("type", "").replace("_", " ").title()
        start_year = title.get("startYear", "")
        end_year = title.get("endYear", "")

        # Format year range for TV series
        if end_year and end_year != start_year:
            year_str = f"{start_year}-{end_year}"
        elif start_year:
            year_str = str(start_year)
        else:
            year_str = "N/A"

        # Rating info
        rating_obj = title.get("rating", {})
        rating = rating_obj.get("aggregateRating", "N/A")
        vote_count = rating_obj.get("voteCount", 0)

        # Genres
        genres = title.get("genres", [])
        genres_str = ", ".join(genres[:3]) if genres else "N/A"

        # Runtime
        runtime = title.get("runtimeMinutes")
        runtime_str = f"{runtime} min" if runtime else ""

        # Build response
        parts = [f"\x02{name}\x02"]  # Bold title
        if title_type:
            parts.append(f"({title_type})")
        if year_str:
            parts.append(f"[{year_str}]")

        response_text = " ".join(parts)
        response_text += f" | Rating: {rating}/10"
        if vote_count:
            response_text += f" ({vote_count:,} votes)"
        response_text += f" | Genres: {genres_str}"
        if runtime_str:
            response_text += f" | {runtime_str}"

        # Add plot if available (trimmed)
        plot = title.get("plot", "")
        if plot:
            max_plot_len = 150
            if len(plot) > max_plot_len:
                plot = plot[:max_plot_len] + "..."
            response_text += f" | {plot}"

        self.safe_reply(connection, event, response_text)
        log_module_event(self.name, "IMDb search", {"user": username, "query": search_term})

        return True

    @handle_exceptions(
        error_message="MusicBrainz API call failed",
        user_message="Unable to fetch artist information at the moment. Please try again later.",
        log_exception=True,
        reraise=False
    )
    def _cmd_music(self, connection, event, msg, username, match):
        """Look up artist/band info from MusicBrainz"""
        if not self.is_enabled(event.target):
            return False

        search_term = match.group(1).strip()

        # Validate search term
        if len(search_term) > 100:
            raise UserInputException("Search term too long", "Search term is too long. Please use a shorter name.")

        # MusicBrainz requires a proper User-Agent
        url = f"https://musicbrainz.org/ws/2/artist?query={urllib.parse.quote(search_term)}&fmt=json&limit=1"
        headers = {
            "Accept": "application/json",
            "User-Agent": "JeevesBot/1.0 (IRC Bot; contact: https://github.com/jeeves-bot)"
        }

        response, error = safe_api_call(
            self.http_session.get, url, headers=headers, timeout=10,
            api_name="MusicBrainz API",
            user_message="Unable to fetch artist information at the moment."
        )

        if error:
            self.safe_reply(connection, event, error)
            return False

        data = response.json()
        artists = data.get("artists", [])

        if not artists:
            self.safe_reply(connection, event, f"No artists found for '{search_term}'")
            return True

        # Get first result
        artist = artists[0]

        name = artist.get("name", "Unknown")
        artist_type = artist.get("type", "")  # Person, Group, Orchestra, etc.
        country = artist.get("country", "")
        disambiguation = artist.get("disambiguation", "")

        # Life span
        life_span = artist.get("life-span", {})
        begin = life_span.get("begin", "")
        end = life_span.get("end", "")
        ended = life_span.get("ended", False)

        # Tags (genres)
        tags = artist.get("tags", [])
        # Sort by count (popularity) and get top 3
        sorted_tags = sorted(tags, key=lambda t: t.get("count", 0), reverse=True)
        tag_names = [t.get("name", "") for t in sorted_tags[:3] if t.get("name")]
        genres_str = ", ".join(tag_names) if tag_names else "N/A"

        # Build response
        parts = [f"\x02{name}\x02"]  # Bold name
        if artist_type:
            parts.append(f"({artist_type})")
        if country:
            parts.append(f"[{country}]")

        response_text = " ".join(parts)

        # Add active years
        if begin:
            if ended and end:
                response_text += f" | Active: {begin}-{end}"
            elif ended:
                response_text += f" | Active: {begin} (disbanded)"
            else:
                response_text += f" | Active since {begin}"

        response_text += f" | Genre: {genres_str}"

        # Add disambiguation if helpful
        if disambiguation:
            max_disambig_len = 80
            if len(disambiguation) > max_disambig_len:
                disambiguation = disambiguation[:max_disambig_len] + "..."
            response_text += f" | {disambiguation}"

        self.safe_reply(connection, event, response_text)
        log_module_event(self.name, "MusicBrainz search", {"user": username, "query": search_term})

        return True
