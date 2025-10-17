#!/usr/bin/env python3
"""Lightweight web UI for the quest module.

Run with: python quest_web.py --host 127.0.0.1 --port 8080
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


def sanitize(text: str) -> str:
    return html.escape(text, quote=True)


class QuestHTTPRequestHandler(BaseHTTPRequestHandler):
    games_path: Path = DEFAULT_GAMES_PATH

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

            name = sanitize(str(player["name"]))
            player_url = f"/player/{quote(str(player['id']))}"
            cells.append(f'<td><a href="{player_url}">{name}</a></td>')
            cells.append(f"<td>{player.get('prestige', 0)}</td>")
            cells.append(f"<td>{player.get('level', 1)}</td>")
            cells.append(f"<td>{player.get('xp', 0)}</td>")

            player_class = str(player.get("player_class") or "no class")
            cells.append(f"<td>{sanitize(player_class)}</td>")
            cells.append(f"<td>{player.get('win_streak', 0)}</td>")

            row_html = "<tr>{}</tr>".format("".join(cells))
            rows_html.append(row_html)

        rows_html.append("</tbody></table>")
        return "".join(rows_html)

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

        details = ["<section class=\"card\">"]
        details.append(f"<h2>{sanitize(str(profile['name']))}</h2>")
        details.append("<ul>")
        details.append(f"<li><strong>Prestige:</strong> {profile['prestige']}</li>")
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

        back_link = '<p><a href="/">&#8592; Back to leaderboard</a></p>'
        content = "".join(details) + back_link
        return HTTPStatus.OK, self._render_layout(
            f"Adventurer | {profile['name']}", content
        )

    def _render_layout(
        self, title: str, body: str, search_term: str = ""
    ) -> str:
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<title>{sanitize(title)}</title>
<style>
body {{
    font-family: Arial, sans-serif;
    margin: 2rem auto;
    max-width: 960px;
    color: #1f2933;
    background: #f7f9fb;
}}
h1 {{
    margin-bottom: 0.5rem;
}}
header {{
    display: flex;
    flex-direction: column;
    gap: 0.75rem;
    margin-bottom: 1.5rem;
}}
form {{
    display: flex;
    gap: 0.5rem;
}}
input[type="text"] {{
    flex: 1;
    padding: 0.5rem;
}}
button {{
    padding: 0.5rem 1rem;
}}
table {{
    width: 100%;
    border-collapse: collapse;
    background: #ffffff;
}}
th, td {{
    border: 1px solid #d2d6dc;
    padding: 0.5rem;
    text-align: left;
}}
th {{
    background: #e4ebf5;
}}
tbody tr:nth-child(even) {{
    background: #f1f5f9;
}}
a {{
    color: #0b7285;
    text-decoration: none;
}}
a:hover {{
    text-decoration: underline;
}}
.card {{
    background: #ffffff;
    padding: 1rem;
    margin-bottom: 1rem;
    border: 1px solid #d2d6dc;
}}
ul {{
    padding-left: 1.25rem;
}}
</style>
</head>
<body>
<header>
  <h1>Quest Adventurers</h1>
  <form method="get" action="/">
    <input type="text" name="q" placeholder="Search by name or user id" value="{sanitize(search_term)}" />
    <button type="submit">Search</button>
  </form>
</header>
{body}
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    games_path = Path(args.games).expanduser().resolve()

    class Handler(QuestHTTPRequestHandler):
        """Request handler bound to the chosen games.json path."""
        pass

    Handler.games_path = games_path  # type: ignore[attr-defined]

    server = HTTPServer((args.host, args.port), Handler)
    print(
        f"Quest web UI running on http://{args.host}:{args.port}/ "
        f"(reading {games_path})"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
