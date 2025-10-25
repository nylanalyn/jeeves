# web/quest/templates.py
# HTML template generation for quest web UI

from typing import Dict, Any, List, Optional
from .utils import sanitize, get_rank_suffix, get_medal_emoji, format_xp, calculate_win_rate, format_streak, calculate_level_progress, get_player_display_name
from .themes import ThemeManager


class TemplateEngine:
    """HTML template engine for quest web UI."""

    def __init__(self, theme_manager: ThemeManager):
        self.theme = theme_manager

    def render_page(self, title: str, content: str, active_section: str = "") -> str:
        """Render complete HTML page."""
        theme_vars = self.theme.get_css_variables()
        prestige_css = self.theme.get_prestige_css()

        return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{sanitize(title)} - Jeeves Quest Leaderboard</title>
    <style>
        :root {{
            {theme_vars}
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--background);
            color: var(--foreground);
            line-height: 1.6;
            min-height: 100vh;
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
        }}

        .header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: var(--card_background);
            border: 1px solid var(--card_border);
            border-radius: 8px;
        }}

        .header h1 {{
            font-size: 2.5em;
            margin-bottom: 10px;
            color: var(--accent);
            text-shadow: 0 0 20px var(--accent);
        }}

        .header p {{
            opacity: 0.8;
            font-size: 1.1em;
        }}

        .nav {{
            display: flex;
            justify-content: center;
            gap: 20px;
            margin-bottom: 30px;
            flex-wrap: wrap;
        }}

        .nav a {{
            padding: 10px 20px;
            background: var(--card_background);
            border: 1px solid var(--card_border);
            border-radius: 6px;
            color: var(--foreground);
            text-decoration: none;
            transition: all 0.3s ease;
        }}

        .nav a:hover {{
            background: var(--accent);
            color: var(--accent_text);
            transform: translateY(-2px);
        }}

        .nav a.active {{
            background: var(--accent);
            color: var(--accent_text);
        }}

        .search-box {{
            margin-bottom: 30px;
            text-align: center;
        }}

        .search-box input {{
            padding: 12px 20px;
            font-size: 1em;
            border: 1px solid var(--card_border);
            border-radius: 6px;
            background: var(--card_background);
            color: var(--foreground);
            width: 300px;
            max-width: 100%;
        }}

        .search-box input:focus {{
            outline: none;
            border-color: var(--accent);
            box-shadow: 0 0 10px var(--accent);
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .stat-card {{
            background: var(--card_background);
            border: 1px solid var(--card_border);
            border-radius: 8px;
            padding: 20px;
            text-align: center;
        }}

        .stat-card h3 {{
            color: var(--accent);
            margin-bottom: 10px;
        }}

        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
        }}

        .card {{
            background: var(--card_background);
            border: 1px solid var(--card_border);
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 20px;
        }}

        .table {{
            width: 100%;
            border-collapse: collapse;
        }}

        .table th {{
            background: var(--table_header);
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}

        .table td {{
            padding: 12px;
            border-bottom: 1px solid var(--table_stripe);
        }}

        .table tr:last-child td {{
            border-bottom: none;
        }}

        .table tr:nth-child(even) {{
            background: var(--table_stripe);
        }}

        .player-name {{
            font-weight: 600;
        }}

        .player-info {{
            font-size: 0.9em;
            opacity: 0.8;
        }}

        .xp {{
            font-family: 'Courier New', monospace;
        }}

        .progress-bar {{
            width: 100px;
            height: 8px;
            background: var(--table_stripe);
            border-radius: 4px;
            overflow: hidden;
            margin-top: 4px;
        }}

        .progress-fill {{
            height: 100%;
            background: linear-gradient(90deg, var(--accent), var(--link));
            transition: width 0.3s ease;
        }}

        .command-reference {{
            margin-top: 40px;
            padding: 20px;
            background: var(--card_background);
            border: 1px solid var(--card_border);
            border-radius: 8px;
        }}

        .command-reference h3 {{
            color: var(--accent);
            margin-bottom: 15px;
        }}

        .commands-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 15px;
        }}

        .command {{
            padding: 15px;
            background: var(--table_stripe);
            border-radius: 6px;
        }}

        .command .cmd {{
            font-family: 'Courier New', monospace;
            font-weight: bold;
            color: var(--link);
            margin-bottom: 5px;
        }}

        .command .desc {{
            font-size: 0.9em;
            opacity: 0.9;
        }}

        .footer {{
            text-align: center;
            margin-top: 40px;
            padding: 20px;
            opacity: 0.6;
            border-top: 1px solid var(--card_border);
        }}

        /* Prestige styling */
        {prestige_css}

        /* Streak styling */
        .streak-high {{
            color: #ef4444;
            font-weight: bold;
            text-shadow: 0 0 5px #ef4444;
        }}

        .streak-medium {{
            color: #f59e0b;
            font-weight: bold;
        }}

        .streak-low {{
            color: #10b981;
        }}

        .streak-none {{
            opacity: 0.6;
        }}

        /* Responsive design */
        @media (max-width: 768px) {{
            .container {{
                padding: 10px;
            }}

            .header h1 {{
                font-size: 2em;
            }}

            .nav {{
                flex-direction: column;
                align-items: center;
            }}

            .table {{
                font-size: 0.9em;
            }}

            .table th, .table td {{
                padding: 8px;
            }}

            .commands-grid {{
                grid-template-columns: 1fr;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>⚔️ Jeeves Quest Leaderboard</h1>
            <p>Track your progress through the digital realm</p>
        </div>

        <nav class="nav">
            <a href="/" {'class="active"' if active_section == "leaderboard" else ''}>Leaderboard</a>
            <a href="/commands" {'class="active"' if active_section == "commands" else ''}>Commands</a>
        </nav>

        {content}

        <div class="footer">
            <p>Powered by Jeeves IRC Bot | Quest System v6.0</p>
        </div>
    </div>
</body>
</html>"""

    def render_leaderboard(self, players: List[Dict[str, Any]], classes: Dict[str, str],
                          search_term: str = "", challenge_info: Optional[Dict[str, Any]] = None) -> str:
        """Render the leaderboard view."""
        content = ""

        # Search box
        content += """
        <div class="search-box">
            <form method="get" action="/">
                <input type="text" name="search" placeholder="Search players..." value="{}" autofocus>
            </form>
        </div>
        """.format(sanitize(search_term))

        # Stats overview
        total_players = len(players)
        total_prestige = sum(p.get("prestige", 0) for p in players)
        avg_level = sum(p.get("level", 1) for p in players) / total_players if total_players > 0 else 1.0

        content += f"""
        <div class="stats-grid">
            <div class="stat-card">
                <h3>Total Players</h3>
                <div class="value">{total_players:,}</div>
            </div>
            <div class="stat-card">
                <h3>Total Prestige</h3>
                <div class="value">{total_prestige:,}</div>
            </div>
            <div class="stat-card">
                <h3>Average Level</h3>
                <div class="value">{avg_level:.1f}</div>
            </div>
        </div>
        """

        # Challenge info
        if challenge_info and challenge_info.get("active_path"):
            active_path = challenge_info["active_path"]
            path_data = challenge_info["paths"].get(active_path, {})
            content += f"""
            <div class="card">
                <div class="prestige-banner banner-active-challenge">
                    🎯 ACTIVE CHALLENGE: {path_data.get("name", active_path).upper()}
                </div>
            </div>
            """

        # Leaderboard table
        content += '<div class="card">'
        content += '<table class="table">'
        content += '''
        <thead>
            <tr>
                <th>Rank</th>
                <th>Player</th>
                <th>Class</th>
                <th>Level</th>
                <th>XP</th>
                <th>Win Rate</th>
                <th>Streak</th>
            </tr>
        </thead>
        <tbody>
        '''

        for i, player in enumerate(players[:50], 1):  # Top 50 players
            user_id = player.get("user_id", "unknown")
            nick = player.get("username", f"Player_{i}")
            player_class = classes.get(user_id, "no class")
            prestige = player.get("prestige", 0)

            rank_display = get_medal_emoji(i) if i <= 3 else f"{i}{get_rank_suffix(i)}"
            prestige_icons = self.theme.get_prestige_icons(prestige)

            level, xp, progress = calculate_level_progress(player)
            wins = player.get("wins", 0)
            losses = player.get("losses", 0)
            win_rate = calculate_win_rate(wins, losses)
            streak = format_streak(player.get("streak", 0))

            content += f'''
            <tr>
                <td>{rank_display}</td>
                <td>
                    <div class="player-name">{sanitize(nick)}</div>
                    <div class="player-info">{prestige_icons} Prestige {prestige}</div>
                </td>
                <td>{sanitize(player_class)}</td>
                <td>
                    Level {level}
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {progress:.0f}%"></div>
                    </div>
                </td>
                <td class="xp">{format_xp(xp)}</td>
                <td>{win_rate}</td>
                <td>{streak}</td>
            </tr>
            '''

        content += '</tbody></table></div>'

        return content

    def render_commands(self) -> str:
        """Render the commands reference."""
        commands = [
            {
                "cmd": "!quest",
                "desc": "Go on a solo quest (normal difficulty)"
            },
            {
                "cmd": "!quest easy",
                "desc": "Go on an easy quest"
            },
            {
                "cmd": "!quest hard",
                "desc": "Go on a hard quest"
            },
            {
                "cmd": "!search",
                "desc": "Search for items in the digital realm"
            },
            {
                "cmd": "!inv / !inventory",
                "desc": "View your inventory and active effects"
            },
            {
                "cmd": "!use <item>",
                "desc": "Use an item from your inventory"
            },
            {
                "cmd": "!medkit [target]",
                "desc": "Use a medkit to heal yourself or others"
            },
            {
                "cmd": "!profile / !p",
                "desc": "Show your detailed player profile"
            },
            {
                "cmd": "!leaderboard / !l",
                "desc": "Show the quest leaderboard"
            },
            {
                "cmd": "!class [name]",
                "desc": "View or set your character class"
            },
            {
                "cmd": "!prestige",
                "desc": "Prestige at max level for permanent bonuses"
            },
            {
                "cmd": "!mob start",
                "desc": "Start a mob encounter for group play"
            },
            {
                "cmd": "!join",
                "desc": "Join an active mob encounter"
            },
            {
                "cmd": "!ability [name]",
                "desc": "Show or use unlocked abilities"
            }
        ]

        content = """
        <div class="command-reference">
            <h3>📜 Quest Commands Reference</h3>
            <div class="commands-grid">
        """

        for command in commands:
            content += f"""
            <div class="command">
                <div class="cmd">{sanitize(command['cmd'])}</div>
                <div class="desc">{sanitize(command['desc'])}</div>
            </div>
            """

        content += """
            </div>

            <h3>🎯 Tips for Success</h3>
            <ul style="margin-top: 15px; padding-left: 20px;">
                <li>Use <strong>!search</strong> between quests to find useful items</li>
                <li>Save <strong>medkits</strong> for healing injuries</li>
                <li>Join <strong>mob encounters</strong> for group content and better rewards</li>
                <li>Complete <strong>challenge paths</strong> to unlock special abilities</li>
                <li>Watch your <strong>energy</strong> levels and plan accordingly</li>
                <li>Use <strong>items strategically</strong> for difficult encounters</li>
            </ul>
        </div>
        """

        return content