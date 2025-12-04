"""
Cryptocurrency price checking module using CoinGecko API.
"""

from typing import Any

from .base import SimpleCommandModule

# Import shared utilities
try:
    from .http_utils import get_http_client
    from .exception_utils import safe_api_call, ExternalAPIException
    HTTP_CLIENT = get_http_client()
except ImportError:
    # Fallback for when shared utilities are not available
    import requests
    HTTP_CLIENT = None
    def safe_api_call(func, *args, **kwargs):
        return func(*args, **kwargs)
    class ExternalAPIException(Exception):
        pass

def setup(bot: Any) -> "CryptoModule":
    """Module setup function."""
    return CryptoModule(bot)


class CryptoModule(SimpleCommandModule):
    """Check cryptocurrency prices via CoinGecko API."""

    name = "crypto"
    version = "1.0.0"
    description = "Check cryptocurrency prices using CoinGecko"

    # CoinGecko free API endpoint (no key required)
    API_BASE = "https://api.coingecko.com/api/v3"

    # Common crypto symbol mappings (symbol -> coingecko ID)
    SYMBOL_MAP = {
        'btc': 'bitcoin',
        'eth': 'ethereum',
        'usdt': 'tether',
        'bnb': 'binancecoin',
        'sol': 'solana',
        'xrp': 'ripple',
        'usdc': 'usd-coin',
        'ada': 'cardano',
        'doge': 'dogecoin',
        'trx': 'tron',
        'link': 'chainlink',
        'dot': 'polkadot',
        'matic': 'matic-network',
        'ltc': 'litecoin',
        'bch': 'bitcoin-cash',
        'xlm': 'stellar',
        'etc': 'ethereum-classic',
        'atom': 'cosmos',
        'xmr': 'monero',
        'algo': 'algorand',
    }

    def _register_commands(self):
        """Register crypto price commands."""
        self.register_command(
            r"^\s*!(?:crypto|price)\s+(\S+)(?:\s+(\w+))?$",
            self._cmd_price,
            name="crypto",
            cooldown=5.0,
            description="!crypto <symbol> [currency] - Get cryptocurrency price (e.g., !crypto btc, !crypto eth usd)"
        )

    def _get_coin_id(self, identifier):
        """
        Convert symbol or name to CoinGecko coin ID.

        Args:
            identifier: Crypto symbol (btc) or name (bitcoin)

        Returns:
            CoinGecko coin ID or None if not found
        """
        identifier_lower = identifier.lower()

        # Check if it's a known symbol
        if identifier_lower in self.SYMBOL_MAP:
            return self.SYMBOL_MAP[identifier_lower]

        # Otherwise assume it's already a coin ID or full name
        return identifier_lower

    def _fetch_price(self, coin_id, currency='usd'):
        """
        Fetch price data from CoinGecko API.

        Args:
            coin_id: CoinGecko coin identifier
            currency: Target currency (default: usd)

        Returns:
            Dict with price data or None on error
        """
        url = f"{self.API_BASE}/simple/price"
        params = {
            'ids': coin_id,
            'vs_currencies': currency.lower(),
            'include_24hr_change': 'true',
            'include_market_cap': 'true',
        }

        # Use shared HTTP client if available
        if HTTP_CLIENT:
            try:
                data = HTTP_CLIENT.get_json(url, params=params)
                
                if coin_id not in data:
                    return None
                
                return data[coin_id]
            except (ExternalAPIException, KeyError, ValueError) as e:
                self.log_debug(f"CoinGecko API error: {e}")
                return None
        else:
            # Fallback to original implementation
            import requests
            try:
                session = self.requests_retry_session()
                response = session.get(url, params=params, timeout=10)
                response.raise_for_status()

                data = response.json()

                if coin_id not in data:
                    return None

                return data[coin_id]

            except requests.exceptions.RequestException as e:
                self.log_debug(f"CoinGecko API error: {e}")
                return None
            except (KeyError, ValueError) as e:
                self.log_debug(f"Error parsing CoinGecko response: {e}")
                return None

    def _format_price(self, price, currency):
        """
        Format price with appropriate precision and currency symbol.

        Args:
            price: Price value
            currency: Currency code

        Returns:
            Formatted price string
        """
        currency_upper = currency.upper()

        # Currency symbols
        symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CNY': '¥',
        }

        symbol = symbols.get(currency_upper, currency_upper + ' ')

        # Format based on price magnitude
        if price >= 1000:
            formatted = f"{price:,.2f}"
        elif price >= 1:
            formatted = f"{price:.2f}"
        elif price >= 0.01:
            formatted = f"{price:.4f}"
        else:
            formatted = f"{price:.8f}"

        return f"{symbol}{formatted}"

    def _format_change(self, change_24h):
        """
        Format 24h price change with color indicators.

        Args:
            change_24h: 24 hour price change percentage

        Returns:
            Formatted change string
        """
        if change_24h > 0:
            arrow = "↑"
            sign = "+"
        else:
            arrow = "↓"
            sign = ""

        return f"{arrow} {sign}{change_24h:.2f}%"

    def _cmd_price(self, connection, event, msg, username, match):
        """
        Handle crypto price command.

        Usage: !crypto <symbol> [currency]
        Examples: !crypto btc, !crypto eth eur
        """
        identifier = match.group(1)
        currency = match.group(2) if match.group(2) else 'usd'

        # Get CoinGecko coin ID
        coin_id = self._get_coin_id(identifier)

        # Fetch price data
        price_data = self._fetch_price(coin_id, currency)

        if not price_data:
            self.safe_reply(
                connection, event,
                f"Could not find price data for '{identifier}'. Try a common symbol like btc, eth, sol, or the full name like 'bitcoin'."
            )
            return True

        # Extract data
        currency_key = currency.lower()
        price = price_data.get(currency_key)
        change_24h_key = f"{currency_key}_24h_change"
        change_24h = price_data.get(change_24h_key)
        market_cap_key = f"{currency_key}_market_cap"
        market_cap = price_data.get(market_cap_key)

        if price is None:
            self.safe_reply(
                connection, event,
                f"Currency '{currency}' not supported. Try usd, eur, gbp, or jpy."
            )
            return True

        # Format response
        price_str = self._format_price(price, currency)
        response = f"{identifier.upper()}: {price_str}"

        # Add 24h change if available
        if change_24h is not None:
            change_str = self._format_change(change_24h)
            response += f" ({change_str} 24h)"

        # Add market cap if available (for larger coins)
        if market_cap and market_cap > 1_000_000_000:  # Show only if > 1B
            if market_cap >= 1_000_000_000_000:  # Trillions
                mcap_str = f"{market_cap / 1_000_000_000_000:.2f}T"
            elif market_cap >= 1_000_000_000:  # Billions
                mcap_str = f"{market_cap / 1_000_000_000:.2f}B"
            else:
                mcap_str = f"{market_cap / 1_000_000:.0f}M"
            response += f" | MCap: {mcap_str}"

        self.safe_reply(connection, event, response)
        return True
