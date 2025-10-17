#!/usr/bin/env python3
"""Lightweight web UI for the quest module with seasonal theming.

Run with: python quest_web.py --host 127.0.0.1 --port 8080 --games config/games.json --content quest_content.json
"""

from __future__ import annotations

import argparse
import html
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Dict, List, Tuple
from urllib.parse import parse_qs, quote, unquote, urlparse


DEFAULT_GAMES_PATH = Path(__file__).resolve().parent / "config" / "games.json"
DEFAULT_CONTENT_PATH = Path(__file__).resolve().parent / "quest_content.json"

DEFAULT_THEME: Dict[str, object] = {
    "name": "midnight-spire",
    "background": "#050712",
    "foreground": "#f8fafc",
    "accent": "#f97316",
    "accent_text": "#0b0f19",
    "card_background": "#0f1526",
    "card_border": "#f97316",
    "table_header": "#162040",
    "table_stripe": "#121a33",
    "link": "#fb923c",
    "link_hover": "#fbbf24",
    "prestige_tiers": [
        {
            "max": 3,
            "icon": "\u2605",
            "class": "tier-star",
            "color": "#fb923c",
            "repeat": 3,
            "banner": None,
        },
        {
            "max": 6,
            "icon": "\u2620",
            "class": "tier-skull",
            "color": "#facc15",
            "repeat": 3,
            "banner": "shroud",
        },
        {
            "max": None,
            "icon": "\ud83c\udfc5",
            "class": "tier-laurel",
            "color": "#a855f7",
            "repeat": 2,
            "banner": "laurel",
        },
    ],
}



def load_quest_state(games_path: Path) -> Tuple[Dict[str, dict], Dict[str, str]]:
    """Read quest players and class selections from games.json."""
    try:
        with games_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        return {}, {}
    except json.JSONDecodeError:
        return {}, {}

    modules = data.get("modules", {})
    quest_state = modules.get("quest", {})
    raw_players = quest_state.get("players", {})
    player_classes = quest_state.get("player_classes", {})

    players: Dict[str, dict] = {}
    for user_id, payload in raw_players.items():
        if isinstance(payload, dict):
            players[user_id] = payload
    return players, player_classes if isinstance(player_classes, dict) else {}


def load_theme(content_path: Path) -> Dict[str, object]:
    """Load theme configuration from quest content file."""
    theme: Dict[str, object] = DEFAULT_THEME.copy()
    try:
        with content_path.open("r", encoding="utf-8") as f:
            content = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return theme

    file_theme = content.get("theme")
    if isinstance(file_theme, dict):
        for key, value in file_theme.items():
            theme[key] = value
    return theme


def sanitize(text: str) -> str:
    return html.escape(text, quote=True)


class QuestHTTPRequestHandler(BaseHTTPRequestHandler):
    games_path: Path = DEFAULT_GAMES_PATH
    theme: Dict[str, object] = DEFAULT_THEME

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        route = parsed.path.rstrip("/") or "/"
        query_params = parse_qs(parsed.query)

        if route == "/":
            search_term = (query_params.get("q") or [""])[0].strip()
            self._respond_with(
                HTTPStatus.OK,
                self._render_leaderboard(search_term=search_term),
            )
            return

        if route.startswith("/player"):
            segments = route.split("/")
            if len(segments) == 3 and segments[2]:
                user_id = unquote(segments[2])
                status, content = self._render_player_detail(user_id)
                self._respond_with(status, content)
                return

        self._respond_with(
            HTTPStatus.NOT_FOUND,
            self._render_layout("Not Found", "<p>Path not found.</p>"),
        )

    def log_message(self, format: str, *args) -> None:  # noqa: A003 pylint: disable=redefined-builtin
        """Reduce default logging noise."""
        return

    # Rendering ----------------------------------------------------------------

    def _render_leaderboard(self, search_term: str = "") -> str:
        players, player_classes = load_quest_state(self.games_path)
        if not players:
            body = "<p>No quest data found. Has anyone played yet?</p>"
            return self._render_layout("Quest Leaderboard", body, search_term)

        enriched = []
        for user_id, payload in players.items():
            enriched.append(
                {
                    "id": user_id,
                    "name": payload.get("name", "Unknown"),
                    "level": payload.get("level", 1),
                    "xp": payload.get("xp", 0),
                    "xp_to_next": payload.get("xp_to_next_level"),
                    "prestige": payload.get("prestige", 0),
                    "energy": payload.get("energy"),
                    "win_streak": payload.get("win_streak", 0),
                    "last_win_date": payload.get("last_win_date"),
                    "player_class": player_classes.get(user_id, "no class"),
                }
            )

        if search_term:
            lowered = search_term.lower()
            filtered = [
                player
                for player in enriched
                if lowered in player["name"].lower()
                or lowered in player["id"].lower()
            ]
            filtered.sort(key=lambda p: p["name"].lower())
            heading = f"<h2>Search results for {sanitize(search_term)}</h2>"
            rows = self._render_player_rows(filtered, show_rank=False)
            if not filtered:
                rows = "<p>No adventurers match that search.</p>"
            body = heading + rows
        else:
            enriched.sort(
                key=lambda p: (p["prestige"], p["level"], p["xp"]),
                reverse=True,
            )
            top_players = enriched[:10]
            heading = "<h2>Leaderboard</h2>"
            rows = self._render_player_rows(top_players, show_rank=True)
            body = heading + rows

        return self._render_layout("Quest Leaderboard", body, search_term)

    def _render_player_rows(self, players: List[Dict[str, object]], show_rank: bool) -> str:
        if not players:
            return "<p>No adventurers to display.</p>"

        columns: List[Tuple[str, bool]] = [
            ("Rank", show_rank),
            ("Adventurer", True),
            ("Prestige", True),
            ("Level", True),
            ("XP", True),
            ("Class", True),
            ("Win Streak", True),
        ]
        headers = "".join(
            f"<th>{title}</th>" for title, visible in columns if visible
        )
        rows_html = ["<table><thead><tr>{}</tr></thead><tbody>".format(headers)]

        for idx, player in enumerate(players, start=1):
            cells = []
            if show_rank:
                cells.append(f"<td>{idx}</td>")

            prestige_value = self._to_int(player.get("prestige", 0))
            tier_info = self._tier_for_prestige(prestige_value)
            prestige_color = tier_info.get("color")
            prestige_color = prestige_color if isinstance(prestige_color, str) else ""
            name_html = self._render_player_name(player, prestige_value, tier_info)
            player_url = f"/player/{quote(str(player['id']))}"
            cells.append(f'<td><a href="{player_url}">{name_html}</a></td>')
            cells.append(f"<td>{prestige_value}</td>")
            cells.append(f"<td>{player.get('level', 1)}</td>")
            cells.append(f"<td>{player.get('xp', 0)}</td>")

            player_class = str(player.get("player_class") or "no class")
            cells.append(f"<td>{sanitize(player_class)}</td>")
            cells.append(f"<td>{player.get('win_streak', 0)}</td>")

            row_class = ["prestige-row"]
            if tier := tier_info.get("class"):
                row_class.append(str(tier))
            row_style = ""
            if prestige_value > 0:
                row_class.append("glow")
                if prestige_color:
                    row_style = f' style="--glow-color: {prestige_color};"'

            row_html = "<tr class=\"{}\" data-prestige=\"{}\"{}>{}</tr>".format(
                " ".join(row_class),
                prestige_value,
                row_style,
                "".join(cells),
            )
            rows_html.append(row_html)

        rows_html.append("</tbody></table>")
        return "".join(rows_html)

    def _calculate_prestige_bonuses(self, prestige: int) -> Dict[str, int]:
        """Return prestige bonuses mirroring modules/quest.py thresholds."""
        return {
            "win": self._prestige_win_bonus_percent(prestige),
            "xp": self._prestige_xp_bonus_percent(prestige),
            "energy": self._prestige_energy_bonus(prestige),
        }

    def _prestige_win_bonus_percent(self, prestige: int) -> int:
        if prestige <= 0:
            return 0
        if prestige <= 3:
            return 5
        if prestige <= 6:
            return 10
        if prestige <= 9:
            return 15
        return 20

    def _prestige_xp_bonus_percent(self, prestige: int) -> int:
        if prestige < 2:
            return 0
        if prestige < 5:
            return 25
        if prestige < 8:
            return 50
        if prestige < 10:
            return 75
        return 100

    def _prestige_energy_bonus(self, prestige: int) -> int:
        if prestige < 3:
            return 0
        if prestige < 6:
            return 1
        if prestige < 9:
            return 2
        return 3

    def _render_player_detail(self, user_id: str) -> Tuple[HTTPStatus, str]:
        players, player_classes = load_quest_state(self.games_path)
        player = players.get(user_id)
        if not player:
            body = self._render_layout(
                "Adventurer Not Found",
                "<p>That adventurer could not be located.</p>",
            )
            return HTTPStatus.NOT_FOUND, body

        profile = {
            "name": player.get("name", "Unknown"),
            "level": player.get("level", 1),
            "xp": player.get("xp", 0),
            "xp_to_next": player.get("xp_to_next_level"),
            "prestige": player.get("prestige", 0),
            "energy": player.get("energy"),
            "win_streak": player.get("win_streak", 0),
            "last_win_date": player.get("last_win_date"),
            "inventory": player.get("inventory", {}),
            "active_effects": player.get("active_effects", []),
            "active_injuries": player.get("active_injuries", []),
            "last_fight": player.get("last_fight"),
            "class": player_classes.get(user_id, "no class"),
        }

        prestige_value = self._to_int(profile["prestige"], 0)
        tier_info = self._tier_for_prestige(prestige_value)
        name_heading = self._render_player_name(
            {"name": profile["name"], "prestige": prestige_value, "id": user_id},
            prestige_value,
            tier_info,
        )

        details = ["<section class=\"card\">"]
        details.append(f"<h2 class=\"detail-name\">{name_heading}</h2>")
        details.append("<ul>")
        details.append(f"<li><strong>Prestige:</strong> {profile['prestige']}</li>")

        # Add prestige bonuses section
        if prestige_value > 0:
            bonuses = self._calculate_prestige_bonuses(prestige_value)
            bonus_parts = []
            if bonuses.get("win", 0) > 0:
                bonus_parts.append(f"+{bonuses['win']}% win chance")
            if bonuses.get("xp", 0) > 0:
                bonus_parts.append(f"+{bonuses['xp']}% XP")
            if bonuses.get("energy", 0) > 0:
                bonus_parts.append(f"+{bonuses['energy']} max energy")

            if bonus_parts:
                bonus_text = ", ".join(bonus_parts)
                details.append(f"<li><strong>Prestige Bonuses:</strong> {bonus_text}</li>")

        details.append(f"<li><strong>Level:</strong> {profile['level']}</li>")

        xp_to_next = profile["xp_to_next"]
        if xp_to_next is None:
            xp_display = f"{profile['xp']} (max)"
        else:
            xp_display = f"{profile['xp']} / {xp_to_next}"
        details.append(f"<li><strong>XP:</strong> {xp_display}</li>")

        details.append(
            f"<li><strong>Class:</strong> {sanitize(str(profile['class']))}</li>"
        )

        if profile["energy"] is not None:
            details.append(f"<li><strong>Energy:</strong> {profile['energy']}</li>")

        details.append(
            f"<li><strong>Win Streak:</strong> {profile['win_streak']}</li>"
        )

        last_win = profile["last_win_date"] or "Never"
        details.append(f"<li><strong>Last Win:</strong> {sanitize(str(last_win))}</li>")

        details.append("</ul>")
        details.append("</section>")

        if profile["last_fight"]:
            lf = profile["last_fight"]
            outcome = "Victory" if lf.get("win") else "Defeat"
            fight_html = (
                "<section class=\"card\">"
                "<h3>Last Encounter</h3>"
                f"<p>Outcome: {outcome}</p>"
                f"<p>Opponent: Level {lf.get('monster_level', '?')} "
                f"{sanitize(str(lf.get('monster_name', 'Unknown')))}</p>"
                "</section>"
            )
            details.append(fight_html)

        inventory = profile["inventory"] or {}
        if inventory:
            rows = "".join(
                f"<tr><td>{sanitize(str(item))}</td><td>{amount}</td></tr>"
                for item, amount in sorted(inventory.items())
            )
            inventory_html = (
                "<section class=\"card\">"
                "<h3>Inventory</h3>"
                "<table><thead><tr><th>Item</th><th>Quantity</th></tr></thead>"
                f"<tbody>{rows}</tbody></table>"
                "</section>"
            )
            details.append(inventory_html)

        if profile["active_effects"]:
            effects_list = "".join(
                f"<li>{sanitize(str(effect))}</li>" for effect in profile["active_effects"]
            )
            effects_html = (
                "<section class=\"card\">"
                "<h3>Active Effects</h3>"
                f"<ul>{effects_list}</ul>"
                "</section>"
            )
            details.append(effects_html)

        injuries = profile["active_injuries"] or []
        if injuries:
            injury_rows = []
            for injury in injuries:
                name = sanitize(str(injury.get("name", "Unknown injury")))
                expires = sanitize(str(injury.get("expires_at", "Unknown")))
                injury_rows.append(f"<tr><td>{name}</td><td>{expires}</td></tr>")

            injuries_html = (
                "<section class=\"card\">"
                "<h3>Active Injuries</h3>"
                "<table><thead><tr><th>Injury</th><th>Expires</th></tr></thead>"
                f"<tbody>{''.join(injury_rows)}</tbody></table>"
                "</section>"
            )
            details.append(injuries_html)

        back_link = '<p class="back-link"><a href="/">&#8592; Back to leaderboard</a></p>'
        content = "".join(details) + back_link
        return HTTPStatus.OK, self._render_layout(
            f"Adventurer | {profile['name']}", content
        )

    def _render_layout(
        self, title: str, body: str, search_term: str = ""
    ) -> str:
        theme = getattr(self, "theme", DEFAULT_THEME)
        palette = {
            "background": str(theme.get("background", DEFAULT_THEME["background"])),
            "foreground": str(theme.get("foreground", DEFAULT_THEME["foreground"])),
            "accent": str(theme.get("accent", DEFAULT_THEME["accent"])),
            "accent_text": str(theme.get("accent_text", DEFAULT_THEME["accent_text"])),
            "card_background": str(theme.get("card_background", DEFAULT_THEME["card_background"])),
            "card_border": str(theme.get("card_border", DEFAULT_THEME["card_border"])),
            "table_header": str(theme.get("table_header", DEFAULT_THEME["table_header"])),
            "table_stripe": str(theme.get("table_stripe", DEFAULT_THEME["table_stripe"])),
            "link": str(theme.get("link", DEFAULT_THEME["link"])),
            "link_hover": str(theme.get("link_hover", DEFAULT_THEME["link_hover"])),
        }

        prestige_css = ""

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{sanitize(title)}</title>
<style>
body {{
    font-family: "Trebuchet MS", "Segoe UI", sans-serif;
    margin: 0;
    padding: 2rem;
    color: {palette['foreground']};
    background: radial-gradient(circle at top, rgba(249, 115, 22, 0.08), transparent 55%), {palette['background']};
}}
main {{
    margin: 0 auto;
    max-width: 960px;
}}
h1 {{
    margin: 0;
    font-size: 2.5rem;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    text-shadow: 0 0 8px rgba(249, 115, 22, 0.6);
}}
header {{
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 2rem;
    padding: 1.5rem;
    background: rgba(12, 16, 29, 0.8);
    border: 1px solid {palette['card_border']};
    box-shadow: 0 12px 28px rgba(0, 0, 0, 0.45);
}}
header p {{
    margin: 0;
    color: rgba(248, 250, 252, 0.8);
}}
form {{
    display: flex;
    gap: 0.5rem;
}}
input[type="text"] {{
    flex: 1;
    padding: 0.75rem 1rem;
    border-radius: 0.5rem;
    border: 1px solid rgba(251, 146, 60, 0.4);
    background: rgba(12, 16, 29, 0.85);
    color: {palette['foreground']};
}}
input[type="text"]:focus {{
    outline: none;
    border-color: {palette['accent']};
    box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.25);
}}
button {{
    padding: 0.75rem 1.5rem;
    background: linear-gradient(135deg, {palette['accent']} 0%, #fb5607 100%);
    border: none;
    border-radius: 0.5rem;
    color: {palette['accent_text']};
    font-weight: 600;
    cursor: pointer;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    transition: transform 0.2s ease, box-shadow 0.2s ease;
}}
button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 10px 18px rgba(249, 115, 22, 0.3);
}}
table {{
    width: 100%;
    border-collapse: collapse;
    background: rgba(12, 16, 29, 0.85);
    backdrop-filter: blur(4px);
    border-radius: 0.75rem;
    overflow: hidden;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.5);
}}
th, td {{
    padding: 0.85rem 1rem;
    text-align: left;
    border-bottom: 1px solid rgba(15, 21, 38, 0.75);
}}
th {{
    background: {palette['table_header']};
    text-transform: uppercase;
    letter-spacing: 0.08em;
    font-size: 0.8rem;
    color: rgba(248, 250, 252, 0.75);
}}
tbody tr:nth-child(even) {{
    background: {palette['table_stripe']};
}}
tbody tr:last-child td {{
    border-bottom: none;
}}
.prestige-row {{
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    border-left: 4px solid transparent;
}}
.prestige-row.glow {{
    transform: translateX(4px);
    box-shadow: 0 0 18px var(--glow-color, rgba(249, 115, 22, 0.4));
    border-left-color: var(--glow-color, {palette['accent']});
}}
.prestige-row:hover {{
    transform: translateX(6px);
}}
a {{
    color: {palette['link']};
    text-decoration: none;
}}
a:hover {{
    color: {palette['link_hover']};
}}
.player-name {{
    display: inline-flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 600;
    text-shadow: 0 0 6px rgba(0, 0, 0, 0.6);
}}
.player-name.glow {{
    color: var(--glow-color, {palette['accent']});
    text-shadow: 0 0 12px var(--glow-color, rgba(249, 115, 22, 0.55));
}}
.player-name .icons {{
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    letter-spacing: 0.08rem;
    color: var(--glow-color, {palette['accent']});
    filter: drop-shadow(0 0 6px rgba(249, 115, 22, 0.45));
}}
.player-name .icon {{
    font-size: 1.2rem;
    line-height: 1;
}}
.player-name .overflow {{
    font-size: 0.75rem;
    opacity: 0.8;
    color: rgba(248, 250, 252, 0.75);
}}
.player-name .name {{
    position: relative;
}}
.player-name .banner {{
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    background: rgba(15, 21, 38, 0.65);
    border: 1px solid rgba(248, 250, 252, 0.12);
    box-shadow: inset 0 0 8px rgba(15, 21, 38, 0.65);
}}
.player-name .banner.banner-shroud {{
    background: linear-gradient(135deg, rgba(10, 10, 17, 0.8), rgba(45, 32, 54, 0.85));
    border-color: rgba(250, 204, 21, 0.45);
}}
.player-name .banner.banner-laurel {{
    background: linear-gradient(135deg, rgba(30, 16, 56, 0.85), rgba(168, 85, 247, 0.55));
    border-color: rgba(168, 85, 247, 0.6);
}}
.player-name .banner::after {{
    content: '';
}}
.card {{
    background: {palette['card_background']};
    padding: 1.5rem;
    margin-bottom: 1.5rem;
    border: 1px solid {palette['card_border']};
    border-radius: 0.75rem;
    box-shadow: 0 12px 30px rgba(0, 0, 0, 0.45);
}}
.card h3 {{
    margin-top: 0;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    color: {palette['accent']};
}}
.card table {{
    border-radius: 0.5rem;
    box-shadow: none;
}}
.card th, .card td {{
    border: 1px solid rgba(248, 250, 252, 0.06);
}}
.detail-name {{
    font-size: 2rem;
    margin: 0 0 1rem 0;
}}
.back-link {{
    text-align: right;
    font-size: 0.95rem;
}}
.back-link a {{
    color: {palette['link']};
}}
.back-link a:hover {{
    color: {palette['link_hover']};
}}
{prestige_css}
</style>
</head>
<body>
<main>
<header>
  <h1>Quest Adventurers</h1>
  <p>Seasonal whispers echo through the halls. Track the bravest souls facing the horrors beyond the veil.</p>
  <form method="get" action="/">
    <input type="text" name="q" placeholder="Search by name or user id" value="{sanitize(search_term)}" />
    <button type="submit">Search</button>
  </form>
</header>
{body}
</main>
</body>
</html>
"""

    def _respond_with(self, status: HTTPStatus, content: str) -> None:
        payload = content.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _to_int(self, value: object, default: int = 0) -> int:
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def _prestige_tiers(self) -> List[Dict[str, object]]:
        tiers = getattr(self, "theme", {}).get("prestige_tiers")
        if not isinstance(tiers, list) or not tiers:
            return DEFAULT_THEME["prestige_tiers"]  # type: ignore[index]
        parsed: List[Dict[str, object]] = []
        for entry in tiers:
            if isinstance(entry, dict):
                parsed.append(entry)
        return parsed or DEFAULT_THEME["prestige_tiers"]  # type: ignore[index]

    def _tier_for_prestige(self, prestige: int) -> Dict[str, object]:
        tiers = self._prestige_tiers()
        floor = 0
        for tier in tiers:
            max_value = tier.get("max")
            try:
                within = prestige <= int(max_value) if max_value is not None else True
            except (TypeError, ValueError):
                within = True if max_value is None else False
            if within:
                tier = dict(tier)  # shallow copy to avoid mutating theme
                tier["floor"] = floor
                tier["level_in_tier"] = max(0, prestige - floor)
                return tier
            try:
                floor = int(max_value)
            except (TypeError, ValueError):
                floor = prestige
        fallback = dict(tiers[-1]) if tiers else {}
        fallback["floor"] = floor
        fallback["level_in_tier"] = max(0, prestige - floor)
        return fallback

    def _render_player_name(
        self,
        player: Dict[str, object],
        prestige: int,
        tier_info: Dict[str, object],
    ) -> str:
        name = sanitize(str(player.get("name", "Unknown")))
        color = tier_info.get("color")
        style_attr = f' style="--glow-color: {color};"' if isinstance(color, str) else ""
        classes = ["player-name"]
        if tier_class := tier_info.get("class"):
            classes.append(str(tier_class))

        segments: List[str] = []
        if prestige > 0:
            classes.append("glow")
            repeat = max(1, self._to_int(tier_info.get("repeat"), 3))
            floor = self._to_int(tier_info.get("floor"), 0)
            level_in_tier = max(1, prestige - floor)
            icon_count = max(1, min(level_in_tier, repeat))
            overflow = max(0, level_in_tier - repeat)
            icon = sanitize(str(tier_info.get("icon", "★")))
            icons = "".join(f'<span class="icon">{icon}</span>' for _ in range(icon_count))
            segments.append(f'<span class="icons">{icons}</span>')
            if overflow > 0:
                segments.append(f'<span class="overflow">+{overflow}</span>')

        banner_name = f'<span class="name">{name}</span>'
        banner_type = tier_info.get("banner")
        if isinstance(banner_type, str) and banner_type:
            banner_name = f'<span class="name banner banner-{banner_type}">{name}</span>'
        segments.append(banner_name)

        return (
            f'<span class="{" ".join(classes)}" data-prestige="{prestige}"{style_attr}>'
            + "".join(segments)
            + "</span>"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a lightweight quest leaderboard UI."
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Interface to bind (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8080,
        help="Port to bind (default: 8080)",
    )
    parser.add_argument(
        "--games",
        default=str(DEFAULT_GAMES_PATH),
        help="Path to games.json (default: config/games.json)",
    )
    parser.add_argument(
        "--content",
        default=str(DEFAULT_CONTENT_PATH),
        help="Path to quest_content.json (default: quest_content.json)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    games_path = Path(args.games).expanduser().resolve()
    content_path = Path(args.content).expanduser().resolve()
    theme = load_theme(content_path)

    class Handler(QuestHTTPRequestHandler):
        """Request handler bound to the chosen games.json path."""
        pass

    Handler.games_path = games_path  # type: ignore[attr-defined]
    Handler.theme = theme  # type: ignore[attr-defined]

    server = HTTPServer((args.host, args.port), Handler)
    print(
        f"Quest web UI running on http://{args.host}:{args.port}/ "
        f"(reading {games_path}, theme {content_path})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
