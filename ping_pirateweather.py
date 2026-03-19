#!/usr/bin/env python3
# noqa — standalone diagnostic script, no project imports
"""Quick connectivity check for the PirateWeather API.

Usage:
    python ping_pirateweather.py
    PIRATEWEATHER=your_key python ping_pirateweather.py

Reads the API key from the PIRATEWEATHER environment variable (same name
used in config.yaml via ${pirateweather}).  Falls back to a keyless probe
of the host if the variable is not set.
"""

import os
import sys
import time
import socket
import urllib.request
import urllib.error

HOST = "api.pirateweather.net"
# Tampa Bay coords (same as the failing request in logs)
TEST_LAT, TEST_LON = "27.9378010", "-82.2859247"


def check_dns():
    print(f"DNS lookup for {HOST} ... ", end="", flush=True)
    try:
        ip = socket.gethostbyname(HOST)
        print(f"OK ({ip})")
        return ip
    except socket.gaierror as e:
        print(f"FAILED: {e}")
        return None


def check_tcp(ip, port=443):
    """Connect by IP to avoid a second DNS round-trip obscuring the result."""
    print(f"TCP connect to {ip}:{port} ({HOST}) ... ", end="", flush=True)
    try:
        start = time.monotonic()
        with socket.create_connection((ip, port), timeout=10):
            elapsed = time.monotonic() - start
        print(f"OK ({elapsed*1000:.0f} ms)")
        return True
    except OSError as e:
        print(f"FAILED: {e}")
        return False


def check_api(api_key):
    url = f"https://{HOST}/forecast/{api_key}/{TEST_LAT},{TEST_LON}?units=us&exclude=minutely,hourly,daily,alerts"
    print(f"API request ({HOST}) ... ", end="", flush=True)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "JeevesBot/ping"})
        start = time.monotonic()
        with urllib.request.urlopen(req, timeout=15) as resp:
            elapsed = time.monotonic() - start
            body = resp.read(200)
        print(f"OK {resp.status} ({elapsed*1000:.0f} ms) — {body[:80]!r}...")
        return True
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.reason}")
        return False
    except urllib.error.URLError as e:
        print(f"FAILED: {e.reason}")
        return False


def main():
    api_key = os.environ.get("PIRATEWEATHER", "").strip()

    print("=== PirateWeather connectivity check ===\n")

    resolved_ip = check_dns()
    if not resolved_ip:
        print("\nDNS failed — check /etc/resolv.conf or your nameserver.")
        sys.exit(1)

    tcp_ok = check_tcp(resolved_ip)
    if not tcp_ok:
        print("\nTCP failed — routing or firewall issue (DNS is fine, IP is reachable but port 443 is blocked).")
        sys.exit(1)

    if api_key:
        check_api(api_key)
    else:
        print("API request skipped (set PIRATEWEATHER env var to test with a real key)")

    print("\nDone.")


if __name__ == "__main__":
    main()
