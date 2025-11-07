# web/quest/templates.py
# HTML template generation for quest web UI

from typing import Dict, Any, List, Optional
from .utils import (
    sanitize, get_rank_suffix, get_medal_emoji, format_xp, calculate_win_rate,
    format_streak, calculate_level_progress, get_player_display_name,
    format_cooldown_timestamp, calculate_max_energy, format_injury_time_remaining, to_roman
)
from .themes import ThemeManager
import time


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
            position: relative;
            overflow-x: hidden;
        }}

        body::before {{
            content: "";
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background:
                radial-gradient(ellipse at top, rgba(157, 78, 221, 0.15) 0%, transparent 50%),
                radial-gradient(ellipse at bottom, rgba(255, 107, 53, 0.1) 0%, transparent 50%);
            pointer-events: none;
            z-index: 0;
        }}

        @keyframes flicker {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.85; }}
        }}

        @keyframes float {{
            0%, 100% {{ transform: translateY(0px); }}
            50% {{ transform: translateY(-10px); }}
        }}

        @keyframes glow-pulse {{
            0%, 100% {{ text-shadow: 0 0 20px var(--accent), 0 0 40px var(--accent); }}
            50% {{ text-shadow: 0 0 30px var(--accent), 0 0 60px var(--accent), 0 0 80px var(--accent); }}
        }}

        .container {{
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            position: relative;
            z-index: 1;
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
            animation: glow-pulse 3s ease-in-out infinite;
            letter-spacing: 2px;
        }}

        .header p {{
            opacity: 0.9;
            font-size: 1.1em;
            color: #9d4edd;
            font-style: italic;
        }}

        .noir-decoration {{
            font-size: 1.5em;
            animation: float 3s ease-in-out infinite;
            display: inline-block;
            margin: 0 10px;
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
            box-shadow: 0 2px 10px rgba(157, 78, 221, 0.1);
        }}

        .nav a:hover {{
            background: var(--accent);
            color: var(--accent_text);
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(255, 107, 53, 0.3);
        }}

        .nav a.active {{
            background: var(--accent);
            color: var(--accent_text);
            box-shadow: 0 4px 20px rgba(255, 107, 53, 0.3);
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

        .action-card {{
            margin-bottom: 30px;
        }}

        .action-card h3 {{
            margin-bottom: 10px;
            color: var(--accent);
        }}

        .action-card p.description {{
            margin-bottom: 15px;
            opacity: 0.85;
        }}

        .link-form {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            align-items: center;
        }}

        .link-form input[type="text"] {{
            padding: 10px 14px;
            border: 1px solid var(--card_border);
            border-radius: 6px;
            flex: 1 1 220px;
            background: var(--card_background);
            color: var(--foreground);
        }}

        .link-form button,
        .action-buttons button {{
            padding: 10px 16px;
            border: none;
            border-radius: 6px;
            background: var(--accent);
            color: var(--accent_text);
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
        }}

        .link-form button:hover,
        .action-buttons button:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 20px rgba(255, 107, 53, 0.3);
        }}

        .action-buttons {{
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
            flex-wrap: wrap;
        }}

        .action-output {{
            background: rgba(0, 0, 0, 0.35);
            border-radius: 6px;
            padding: 12px;
            min-height: 80px;
            white-space: pre-wrap;
            font-family: "Fira Code", "Courier New", monospace;
        }}

        .action-status {{
            margin-top: 10px;
            opacity: 0.85;
        }}

        .alert-error {{
            color: #ef4444;
        }}

        .alert-success {{
            color: #22c55e;
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
            box-shadow: 0 4px 15px rgba(157, 78, 221, 0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 8px 25px rgba(157, 78, 221, 0.2);
        }}

        .stat-card h3 {{
            color: var(--accent);
            margin-bottom: 10px;
            text-shadow: 0 0 10px rgba(255, 107, 53, 0.5);
        }}

        .stat-card .value {{
            font-size: 2em;
            font-weight: bold;
            margin-bottom: 5px;
            color: #9d4edd;
        }}

        .cooldown-section {{
            padding: 20px;
        }}

        .cooldown-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}

        .cooldown-card {{
            background: var(--table_stripe);
            border: 1px solid var(--card_border);
            border-radius: 6px;
            padding: 15px;
            text-align: center;
            transition: all 0.3s ease;
        }}

        .cooldown-card h4 {{
            margin-bottom: 8px;
            color: var(--foreground);
            font-size: 1em;
        }}

        .cooldown-value {{
            font-size: 1.3em;
            font-weight: bold;
            font-family: 'Courier New', monospace;
        }}

        .cooldown-ready {{
            border-color: #10b981;
            background: rgba(16, 185, 129, 0.1);
        }}

        .cooldown-ready .cooldown-value {{
            color: #10b981;
        }}

        .cooldown-waiting {{
            border-color: #f59e0b;
            background: rgba(245, 158, 11, 0.1);
        }}

        .cooldown-waiting .cooldown-value {{
            color: #f59e0b;
        }}

        .boss-hunt-section {{
            padding: 20px;
        }}

        .boss-buff-active {{
            background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(16, 185, 129, 0.1));
            border: 2px solid #10b981;
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 20px;
            text-align: center;
            font-size: 1.1em;
            animation: glow-pulse 2s infinite;
        }}

        .boss-info {{
            margin-top: 15px;
        }}

        .boss-info h4 {{
            font-size: 1.5em;
            color: var(--accent);
            margin-bottom: 5px;
        }}

        .boss-description {{
            color: var(--muted_foreground);
            font-style: italic;
            margin-bottom: 15px;
        }}

        .boss-hp-container {{
            margin: 15px 0;
        }}

        .boss-hp-label {{
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
            font-size: 0.9em;
            color: var(--muted_foreground);
        }}

        .boss-hp-bar-container {{
            width: 100%;
            height: 25px;
            background: var(--table_stripe);
            border: 1px solid var(--card_border);
            border-radius: 12px;
            overflow: hidden;
            position: relative;
        }}

        .boss-hp-bar {{
            height: 100%;
            background: linear-gradient(90deg, #ef4444, #dc2626);
            transition: width 0.5s ease;
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.5);
        }}

        .boss-hp-ascii {{
            font-family: 'Courier New', monospace;
            text-align: center;
            margin-top: 5px;
            font-size: 0.9em;
            color: var(--muted_foreground);
        }}

        .boss-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid var(--card_border);
        }}

        .boss-stat {{
            display: flex;
            flex-direction: column;
            text-align: center;
        }}

        .boss-stat .stat-label {{
            font-size: 0.85em;
            color: var(--muted_foreground);
            margin-bottom: 5px;
        }}

        .boss-stat .stat-value {{
            font-size: 1.3em;
            font-weight: bold;
            color: var(--accent);
        }}

        .card {{
            background: var(--card_background);
            border: 1px solid var(--card_border);
            border-radius: 8px;
            overflow: hidden;
            margin-bottom: 20px;
            position: relative;
            box-shadow: 0 4px 20px rgba(255, 107, 53, 0.1);
            transition: box-shadow 0.3s ease;
        }}

        .card:hover {{
            box-shadow: 0 6px 30px rgba(255, 107, 53, 0.2);
        }}

        .card::before {{
            content: "🔍";
            position: absolute;
            top: -5px;
            right: -5px;
            font-size: 2em;
            opacity: 0.3;
            pointer-events: none;
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
            color: var(--accent);
            text-shadow: 0 0 8px rgba(255, 107, 53, 0.3);
            border-bottom: 2px solid var(--accent);
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

        .player-name a {{
            color: var(--link);
            text-decoration: none;
            transition: color 0.2s ease;
        }}

        .player-name a:hover {{
            color: var(--accent);
            text-decoration: underline;
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
            <h1><span class="noir-decoration">🕵️</span>Jeeves Quest: Case Files<span class="noir-decoration">🔍</span></h1>
            <p>🎩 Investigate the digital mysteries... sleuth awaits 📜</p>
        </div>

        <nav class="nav">
            <a href="/" {'class="active"' if active_section == "leaderboard" else ''}>Leaderboard</a>
            <a href="/commands" {'class="active"' if active_section == "commands" else ''}>Commands</a>
        </nav>

        {content}

        <div class="footer">
            <p>🕵️ Powered by Jeeves IRC Bot | Quest System v6.0 📜</p>
            <p style="font-size: 0.9em; opacity: 0.6; margin-top: 5px;">Every mystery has a solution...</p>
        </div>
    </div>
</body>
</html>"""

    def render_leaderboard(self, players: List[Dict[str, Any]], classes: Dict[str, str],
                          search_term: str = "", challenge_info: Optional[Dict[str, Any]] = None,
                          mob_cooldowns: Optional[Dict[str, float]] = None,
                          boss_hunt_data: Optional[Dict[str, Any]] = None,
                          current_user: Optional[str] = None) -> str:
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

        link_style = "" if not current_user else "display: none;"
        action_style = "" if current_user else "display: none;"
        current_user_html = sanitize(current_user) if current_user else ""

        content += f"""
        <div class="card action-card" id="link-section" style="{link_style}">
            <h3>🔐 Link your IRC account</h3>
            <p class="description">
                Run <code>!weblink</code> in IRC to get a short-lived code, then paste it below to play from the web.
            </p>
            <form class="link-form" id="link-form">
                <input type="text" name="token" id="link-token" placeholder="Enter your link code" autocomplete="one-time-code" required>
                <button type="submit">Link account</button>
            </form>
            <div class="action-status" id="link-message"></div>
        </div>

        <div class="card action-card" id="action-section" style="{action_style}">
            <h3>⚔️ Quest from the browser</h3>
            <p class="description">
                Logged in as <strong id="action-username">{current_user_html}</strong>. Choose a difficulty to embark on a solo quest.
            </p>
            <div class="action-buttons">
                <button type="button" data-difficulty="easy">Easy Quest</button>
                <button type="button" data-difficulty="normal">Normal Quest</button>
                <button type="button" data-difficulty="hard">Hard Quest</button>
            </div>
            <div class="action-output" id="action-output">Awaiting your command...</div>
            <div class="action-status" id="action-status"></div>
        </div>
        """

        # Boss Hunt
        if boss_hunt_data:
            current_boss = boss_hunt_data.get("current_boss", {})
            buff = boss_hunt_data.get("buff", {})
            stats = boss_hunt_data.get("stats", {})

            if current_boss:
                boss_name = sanitize(current_boss.get("name", "Unknown Boss"))
                boss_desc = sanitize(current_boss.get("description", ""))
                current_hp = current_boss.get("current_hp", 0)
                max_hp = current_boss.get("max_hp", 1)
                clues = current_boss.get("clues_collected", 0)

                # Calculate HP percentage and bar
                hp_percent = int((current_hp / max_hp) * 100) if max_hp > 0 else 0
                bar_filled = int((current_hp / max_hp) * 20) if max_hp > 0 else 0
                bar_empty = 20 - bar_filled
                hp_bar = "█" * bar_filled + "░" * bar_empty

                # Check buff status
                buff_active = buff.get("active", False)
                buff_html = ""
                if buff_active:
                    from datetime import datetime, timezone
                    try:
                        expires_at_str = buff.get("expires_at")
                        if expires_at_str:
                            expires_at = datetime.fromisoformat(expires_at_str)
                            now = datetime.now(timezone.utc)
                            if now < expires_at:
                                time_left = expires_at - now
                                days = time_left.days
                                hours = time_left.seconds // 3600
                                xp_mult = buff.get("xp_multiplier", 1.0)
                                level_red = buff.get("level_reduction", 0)
                                buff_html = f"""
                                <div class="boss-buff-active">
                                    🎉 <strong>THE HEAT'S OFF!</strong> 🎉<br>
                                    Enemies -{level_red} levels | XP x{xp_mult} | {days}d {hours}h remaining
                                </div>
                                """
                    except:
                        pass

                total_defeated = stats.get("total_bosses_defeated", 0)
                total_clues = stats.get("total_clues_found", 0)

                content += f"""
                <div class="card boss-hunt-section">
                    <h3 style="margin-bottom: 15px; color: var(--accent);">🔍 Boss Hunt: The Trail</h3>
                    {buff_html}
                    <div class="boss-info">
                        <h4>{boss_name}</h4>
                        <p class="boss-description">{boss_desc}</p>
                        <div class="boss-hp-container">
                            <div class="boss-hp-label">
                                <span>HP: {current_hp:,} / {max_hp:,}</span>
                                <span>{hp_percent}%</span>
                            </div>
                            <div class="boss-hp-bar-container">
                                <div class="boss-hp-bar" style="width: {hp_percent}%"></div>
                            </div>
                            <div class="boss-hp-ascii">[{hp_bar}]</div>
                        </div>
                        <div class="boss-stats">
                            <div class="boss-stat">
                                <span class="stat-label">Clues Collected:</span>
                                <span class="stat-value">{clues}</span>
                            </div>
                            <div class="boss-stat">
                                <span class="stat-label">Total Bosses Defeated:</span>
                                <span class="stat-value">{total_defeated}</span>
                            </div>
                            <div class="boss-stat">
                                <span class="stat-label">Total Clues Found:</span>
                                <span class="stat-value">{total_clues:,}</span>
                            </div>
                        </div>
                    </div>
                </div>
                """

        # Mob cooldowns
        if mob_cooldowns:
            cooldown_cards = ""
            for channel, timestamp in mob_cooldowns.items():
                cooldown_status = format_cooldown_timestamp(timestamp)
                is_ready = timestamp <= time.time()
                status_class = "cooldown-ready" if is_ready else "cooldown-waiting"
                cooldown_cards += f"""
                <div class="cooldown-card {status_class}">
                    <h4>{sanitize(channel)}</h4>
                    <div class="cooldown-value">{'✓' if is_ready else '⏳'} {cooldown_status}</div>
                </div>
                """

            content += f"""
            <div class="card cooldown-section">
                <h3 style="margin-bottom: 15px; color: var(--accent);">🎯 Mob Encounter Cooldowns</h3>
                <div class="cooldown-grid">
                    {cooldown_cards}
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
            streak = format_streak(player.get("win_streak", 0))

            # Get XP progress to next level
            current_xp = player.get("xp", 0)
            xp_to_next = player.get("xp_to_next_level", 0)
            xp_display = f"{current_xp:,}/{xp_to_next:,}" if xp_to_next > 0 else f"{current_xp:,}"

            content += f'''
            <tr>
                <td>{rank_display}</td>
                <td>
                    <div class="player-name"><a href="/player/{sanitize(nick)}">{sanitize(nick)}</a></div>
                    <div class="player-info">{prestige_icons} Prestige {prestige}</div>
                </td>
                <td>{sanitize(player_class)}</td>
                <td>
                    Level {level}
                    <div class="progress-bar">
                        <div class="progress-fill" style="width: {progress:.0f}%"></div>
                    </div>
                </td>
                <td class="xp">{xp_display}</td>
                <td>{win_rate}</td>
                <td>{streak}</td>
            </tr>
            '''

        content += '</tbody></table></div>'

        content += """
        <script>
        (function() {
            const linkSection = document.getElementById('link-section');
            const actionSection = document.getElementById('action-section');
            const linkForm = document.getElementById('link-form');
            const linkInput = document.getElementById('link-token');
            const linkMessage = document.getElementById('link-message');
            const actionButtons = actionSection ? actionSection.querySelectorAll('button[data-difficulty]') : [];
            const actionOutput = document.getElementById('action-output');
            const actionStatus = document.getElementById('action-status');
            const actionUsername = document.getElementById('action-username');

            function setStatus(el, text, kind) {
                if (!el) return;
                el.textContent = text || '';
                el.classList.remove('alert-error', 'alert-success');
                if (kind === 'error') {
                    el.classList.add('alert-error');
                } else if (kind === 'success') {
                    el.classList.add('alert-success');
                }
            }

            if (linkForm && linkInput) {
                linkForm.addEventListener('submit', async function(ev) {
                    ev.preventDefault();
                    const token = (linkInput.value || '').trim();
                    if (!token) {
                        setStatus(linkMessage, 'Please enter your link code.', 'error');
                        return;
                    }
                    setStatus(linkMessage, 'Linking account…');
                    try {
                        const res = await fetch('/api/link/claim', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ token })
                        });
                        const data = await res.json();
                        if (!res.ok || !data.success) {
                            throw new Error(data.error || 'Unable to link account.');
                        }
                        setStatus(linkMessage, 'Linked successfully! You can quest from here now.', 'success');
                        if (linkSection && actionSection) {
                            linkSection.style.display = 'none';
                            actionSection.style.display = '';
                        }
                        if (actionUsername && data.username) {
                            actionUsername.textContent = data.username;
                        }
                    } catch (err) {
                        setStatus(linkMessage, err.message || 'Unable to link account.', 'error');
                    }
                });
            }

            if (actionButtons.length && actionOutput && actionStatus) {
                actionButtons.forEach((button) => {
                    button.addEventListener('click', async () => {
                        const difficulty = button.getAttribute('data-difficulty');
                        setStatus(actionStatus, 'Venturing forth…');
                        actionOutput.textContent = '';
                        try {
                            const res = await fetch('/api/quest/solo', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ difficulty })
                            });
                            const data = await res.json();
                            if (!res.ok || !data.success) {
                                throw new Error(data.error || 'Quest failed.');
                            }
                            const messages = Array.isArray(data.messages) ? data.messages : [];
                            actionOutput.textContent = messages.join('\\n') || 'No response from Jeeves.';
                            if (data.username && actionUsername) {
                                actionUsername.textContent = data.username;
                            }
                            setStatus(actionStatus, 'Quest complete!', 'success');
                        } catch (err) {
                            setStatus(actionStatus, err.message || 'Quest failed.', 'error');
                        }
                    });
                });
            }
        })();
        </script>
        """

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

    def render_player_detail(self, player: Dict[str, Any], player_class: str,
                            challenge_info: Optional[Dict[str, Any]] = None,
                            current_user: Optional[str] = None) -> str:
        """Render detailed player profile view."""
        username = sanitize(player.get("username", "Unknown Player"))
        prestige = player.get("prestige", 0)
        transcendence = player.get("transcendence", 0)
        level = player.get("level", 1)
        xp = player.get("xp", 0)
        xp_to_next = player.get("xp_to_next_level", 0)
        energy = player.get("energy", 0)
        max_energy = calculate_max_energy(prestige)
        wins = player.get("wins", 0)
        losses = player.get("losses", 0)
        win_streak = player.get("win_streak", 0)
        prestige_icons = self.theme.get_prestige_icons(prestige)

        # Format legend suffix for transcendence
        legend_suffix = ""
        if transcendence > 0:
            legend_suffix = " (Legend)" if transcendence == 1 else f" (Legend {to_roman(transcendence)})"

        # Format XP display
        xp_display = f"{xp:,}/{xp_to_next:,}" if xp_to_next > 0 else f"{xp:,} (MAX)"

        # Get inventory
        inventory = player.get("inventory", {})
        medkits = inventory.get("medkits", 0)
        energy_potions = inventory.get("energy_potions", 0)
        lucky_charms = inventory.get("lucky_charms", 0)
        armor_shards = inventory.get("armor_shards", 0)
        xp_scrolls = inventory.get("xp_scrolls", 0)
        dungeon_relics = inventory.get("dungeon_relics", 0)

        # Active effects
        active_effects = player.get("active_effects", [])
        active_injuries = player.get("active_injuries", [])

        # Last fight info
        last_fight = player.get("last_fight", {})
        last_fight_display = ""
        if last_fight:
            monster_name = last_fight.get("monster_name", "Unknown")
            monster_level = last_fight.get("monster_level", 1)
            was_win = last_fight.get("win", False)
            result = "✅ Victory" if was_win else "❌ Defeat"
            last_fight_display = f"{result} vs {sanitize(monster_name)} (Lvl {monster_level})"

        # Challenge path
        challenge_path = player.get("challenge_path", "None")
        challenge_path_name = challenge_path
        if challenge_info and challenge_path != "None":
            paths_data = challenge_info.get("paths", {})
            path_info = paths_data.get(challenge_path, {})
            challenge_path_name = path_info.get("name", challenge_path)
        challenge_stats = player.get("challenge_stats", {})

        # Unlocked abilities
        unlocked_abilities = player.get("unlocked_abilities", [])

        link_style = "" if not current_user else "display: none;"
        action_style = "" if current_user else "display: none;"
        current_user_html = sanitize(current_user) if current_user else ""

        content = f"""
        <div style="margin-bottom: 20px;">
            <a href="/" style="color: var(--link); text-decoration: none;">&larr; Back to Leaderboard</a>
        </div>

        <div class="card action-card" id="link-section" style="{link_style}">
            <h3>🔐 Link your IRC account</h3>
            <p class="description">
                Run <code>!weblink</code> in IRC to get a short-lived code, then paste it below to play from the web.
            </p>
            <form class="link-form" id="link-form">
                <input type="text" name="token" id="link-token" placeholder="Enter your link code" autocomplete="one-time-code" required>
                <button type="submit">Link account</button>
            </form>
            <div class="action-status" id="link-message"></div>
        </div>

        <div class="card action-card" id="action-section" style="{action_style}">
            <h3>⚔️ Quest from the browser</h3>
            <p class="description">
                Logged in as <strong id="action-username">{current_user_html}</strong>. Choose a difficulty to embark on a solo quest.
            </p>
            <div class="action-buttons">
                <button type="button" data-difficulty="easy">Easy Quest</button>
                <button type="button" data-difficulty="normal">Normal Quest</button>
                <button type="button" data-difficulty="hard">Hard Quest</button>
            </div>
            <div class="action-output" id="action-output">Awaiting your command...</div>
            <div class="action-status" id="action-status"></div>
        </div>

        <div class="card" style="margin-bottom: 20px;">
            <div style="padding: 30px; text-align: center; background: linear-gradient(135deg, var(--card_background), var(--table_stripe));">
                <h1 style="font-size: 2.5em; margin-bottom: 10px; color: var(--accent);">{username}{legend_suffix}</h1>
                <div style="font-size: 1.2em; margin-bottom: 10px;">{prestige_icons} Prestige {prestige} {sanitize(player_class).title()}</div>
                <div style="font-size: 1.5em; color: var(--link);">Level {level}</div>
                {f'<div style="font-size: 1em; margin-top: 10px; color: #9d4edd;">Transcendence: {to_roman(transcendence) if transcendence > 1 else "Legend"}</div>' if transcendence > 0 else ''}
            </div>
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <h3>⚡ Energy</h3>
                <div class="value">{energy}/{max_energy}</div>
            </div>
            <div class="stat-card">
                <h3>📊 Win/Loss</h3>
                <div class="value">{wins}/{losses}</div>
                <div style="font-size: 0.9em; opacity: 0.8;">{calculate_win_rate(wins, losses)} Win Rate</div>
            </div>
            <div class="stat-card">
                <h3>🔥 Win Streak</h3>
                <div class="value">{win_streak}</div>
            </div>
            <div class="stat-card">
                <h3>✨ XP Progress</h3>
                <div class="value" style="font-size: 1.5em;">{xp_display}</div>
            </div>
        </div>
        """

        # Hardcore mode display
        hardcore_mode = player.get("hardcore_mode", False)
        if hardcore_mode:
            hardcore_hp = player.get("hardcore_hp", 0)
            hardcore_max_hp = player.get("hardcore_max_hp", 0)
            content += f"""
        <div class="card" style="margin-top: 20px; border: 2px solid #ef4444; background: linear-gradient(135deg, var(--card_background), rgba(239, 68, 68, 0.1));">
            <div style="padding: 20px;">
                <h2 style="color: #ef4444; margin-bottom: 15px;">☠️ HARDCORE MODE ACTIVE</h2>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center;">
                        <div style="font-size: 1.2em; color: #ef4444; margin-bottom: 5px;">❤️ HP</div>
                        <div style="font-size: 2em; font-weight: bold;">{hardcore_hp}/{hardcore_max_hp}</div>
                        <div style="font-size: 0.85em; opacity: 0.7; margin-top: 5px;">Death = Permadeath!</div>
                    </div>
                </div>
            </div>
        </div>
        """

        # Hardcore stats (if player has completed or died)
        hardcore_stats = player.get("hardcore_stats", {})
        if hardcore_stats.get("completions", 0) > 0 or hardcore_stats.get("deaths", 0) > 0:
            completions = hardcore_stats.get("completions", 0)
            deaths = hardcore_stats.get("deaths", 0)
            highest_level = hardcore_stats.get("highest_level_reached", 0)
            content += f"""
        <div class="card" style="margin-top: 20px;">
            <div style="padding: 20px;">
                <h2 style="color: var(--accent); margin-bottom: 15px;">☠️ Hardcore History</h2>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                    <div style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center;">
                        <div style="font-size: 2em;">✅</div>
                        <div style="font-weight: bold; font-size: 1.5em;">{completions}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Completions</div>
                    </div>
                    <div style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center;">
                        <div style="font-size: 2em;">☠️</div>
                        <div style="font-weight: bold; font-size: 1.5em;">{deaths}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Deaths</div>
                    </div>
                    <div style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center;">
                        <div style="font-size: 2em;">📈</div>
                        <div style="font-weight: bold; font-size: 1.5em;">{highest_level}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Highest Level</div>
                    </div>
                </div>
            </div>
        </div>
        """

        # Hardcore permanent items
        hardcore_permanent_items = player.get("hardcore_permanent_items", [])
        if hardcore_permanent_items:
            item_display = ", ".join([sanitize(item.replace('_', ' ').title()) for item in hardcore_permanent_items])
            content += f"""
        <div class="card" style="margin-top: 20px;">
            <div style="padding: 20px;">
                <h2 style="color: var(--accent); margin-bottom: 15px;">✨ Hardcore Permanent Items</h2>
                <p style="color: var(--text_secondary);">These items are never locked away in hardcore mode:</p>
                <div style="margin-top: 10px; padding: 15px; background: var(--table_stripe); border-radius: 6px;">
                    <strong>{item_display}</strong>
                </div>
            </div>
        </div>
        """

        content += f"""
        <div class="card" style="margin-top: 20px;">
            <div style="padding: 20px;">
                <h2 style="color: var(--accent); margin-bottom: 15px;">🎒 Inventory</h2>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px;">
                    <div class="inventory-item" data-item="medkit" style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center; cursor: {'pointer' if medkits > 0 and current_user else 'default'}; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="if({medkits} > 0 && '{current_user_html}') this.style.transform='translateY(-3px)'; if({medkits} > 0 && '{current_user_html}') this.style.boxShadow='0 4px 15px rgba(157, 78, 221, 0.3)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                        <div style="font-size: 2em;">🩹</div>
                        <div style="font-weight: bold;">{medkits}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Medkits</div>
                        {'<div style="font-size: 0.75em; margin-top: 5px; color: var(--accent);">Click to use</div>' if medkits > 0 and current_user else ''}
                    </div>
                    <div class="inventory-item" data-item="energy_potion" style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center; cursor: {'pointer' if energy_potions > 0 and current_user else 'default'}; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="if({energy_potions} > 0 && '{current_user_html}') this.style.transform='translateY(-3px)'; if({energy_potions} > 0 && '{current_user_html}') this.style.boxShadow='0 4px 15px rgba(157, 78, 221, 0.3)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                        <div style="font-size: 2em;">⚡</div>
                        <div style="font-weight: bold;">{energy_potions}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Energy Potions</div>
                        {'<div style="font-size: 0.75em; margin-top: 5px; color: var(--accent);">Click to use</div>' if energy_potions > 0 and current_user else ''}
                    </div>
                    <div class="inventory-item" data-item="lucky_charm" style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center; cursor: {'pointer' if lucky_charms > 0 and current_user else 'default'}; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="if({lucky_charms} > 0 && '{current_user_html}') this.style.transform='translateY(-3px)'; if({lucky_charms} > 0 && '{current_user_html}') this.style.boxShadow='0 4px 15px rgba(157, 78, 221, 0.3)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                        <div style="font-size: 2em;">🍀</div>
                        <div style="font-weight: bold;">{lucky_charms}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Lucky Charms</div>
                        {'<div style="font-size: 0.75em; margin-top: 5px; color: var(--accent);">Click to use</div>' if lucky_charms > 0 and current_user else ''}
                    </div>
                    <div class="inventory-item" data-item="armor_shard" style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center; cursor: {'pointer' if armor_shards > 0 and current_user else 'default'}; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="if({armor_shards} > 0 && '{current_user_html}') this.style.transform='translateY(-3px)'; if({armor_shards} > 0 && '{current_user_html}') this.style.boxShadow='0 4px 15px rgba(157, 78, 221, 0.3)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                        <div style="font-size: 2em;">🛡️</div>
                        <div style="font-weight: bold;">{armor_shards}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Armor Shards</div>
                        {'<div style="font-size: 0.75em; margin-top: 5px; color: var(--accent);">Click to use</div>' if armor_shards > 0 and current_user else ''}
                    </div>
                    <div class="inventory-item" data-item="xp_scroll" style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center; cursor: {'pointer' if xp_scrolls > 0 and current_user else 'default'}; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="if({xp_scrolls} > 0 && '{current_user_html}') this.style.transform='translateY(-3px)'; if({xp_scrolls} > 0 && '{current_user_html}') this.style.boxShadow='0 4px 15px rgba(157, 78, 221, 0.3)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                        <div style="font-size: 2em;">📜</div>
                        <div style="font-weight: bold;">{xp_scrolls}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">XP Scrolls</div>
                        {'<div style="font-size: 0.75em; margin-top: 5px; color: var(--accent);">Click to use</div>' if xp_scrolls > 0 and current_user else ''}
                    </div>
                    {f'''<div class="inventory-item" data-item="dungeon_relic" style="padding: 15px; background: var(--table_stripe); border-radius: 6px; text-align: center; cursor: {'pointer' if dungeon_relics > 0 and current_user else 'default'}; transition: transform 0.2s, box-shadow 0.2s;" onmouseover="if({dungeon_relics} > 0 && '{current_user_html}') this.style.transform='translateY(-3px)'; if({dungeon_relics} > 0 && '{current_user_html}') this.style.boxShadow='0 4px 15px rgba(157, 78, 221, 0.3)'" onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none'">
                        <div style="font-size: 2em;">✨</div>
                        <div style="font-weight: bold;">{dungeon_relics}</div>
                        <div style="font-size: 0.9em; opacity: 0.8;">Mythic Relics</div>
                        {'<div style="font-size: 0.75em; margin-top: 5px; color: var(--accent);">Click to use</div>' if dungeon_relics > 0 and current_user else ''}
                    </div>''' if dungeon_relics > 0 else ''}
                </div>
            </div>
        </div>
        """

        # Active effects and injuries
        if active_effects or active_injuries:
            content += '<div class="card" style="margin-top: 20px;"><div style="padding: 20px;">'
            content += '<h2 style="color: var(--accent); margin-bottom: 15px;">🔮 Status Effects</h2>'

            if active_effects:
                content += '<div style="margin-bottom: 15px;"><strong style="color: #10b981;">✨ Active Buffs:</strong><ul style="margin-top: 5px; margin-left: 20px;">'
                for effect in active_effects:
                    effect_type = effect.get("type", "unknown")
                    if effect_type == "lucky_charm":
                        win_bonus = effect.get("win_bonus", 0)
                        content += f'<li style="color: #10b981;">🍀 Lucky Charm (+{int(win_bonus * 100)}% win chance)</li>'
                    elif effect_type == "armor_shard":
                        remaining = effect.get("remaining_fights", 0)
                        content += f'<li style="color: #10b981;">🛡️ Armor ({remaining} fights remaining)</li>'
                    elif effect_type == "xp_scroll":
                        content += f'<li style="color: #10b981;">📜 XP Scroll (active for next win)</li>'
                    elif effect_type == "dungeon_relic":
                        charges = effect.get("remaining_auto_wins", 0)
                        suffix = "win" if charges == 1 else "wins"
                        content += f'<li style="color: #10b981;">✨ Mythic Relic ({charges} guaranteed {suffix})</li>'
                    else:
                        content += f'<li style="color: #10b981;">{sanitize(str(effect))}</li>'
                content += '</ul></div>'

            if active_injuries:
                content += '<div><strong style="color: #ef4444;">💔 Active Injuries:</strong><ul style="margin-top: 5px; margin-left: 20px;">'
                for injury in active_injuries:
                    injury_name = injury.get("name", "Unknown Injury")
                    expires_at = injury.get("expires_at", "")
                    time_remaining = format_injury_time_remaining(expires_at) if expires_at else "Unknown"
                    content += f'<li style="color: #ef4444;">💔 {sanitize(injury_name)} ({time_remaining} remaining)</li>'
                content += '</ul></div>'

            content += '</div></div>'

        # Unlocked abilities
        if unlocked_abilities and challenge_info:
            abilities_data = challenge_info.get("abilities", {})
            content += f"""
            <div class="card" style="margin-top: 20px;">
                <div style="padding: 20px;">
                    <h2 style="color: var(--accent); margin-bottom: 15px;">⚔️ Unlocked Abilities</h2>
                    <div style="display: grid; gap: 15px;">
            """
            for ability_id in unlocked_abilities:
                ability = abilities_data.get(ability_id, {})
                ability_name = sanitize(ability.get("name", ability_id.replace("_", " ").title()))
                description = sanitize(ability.get("description", "No description available"))
                command = ability.get("command", ability_id)
                cooldown_hours = ability.get("cooldown_hours", 0)

                # Get cooldown info from player data
                ability_cooldowns = player.get("ability_cooldowns", {})
                cooldown_status = ""
                if ability_id in ability_cooldowns:
                    # We'd need to check if it's still on cooldown, but for now just show cooldown info
                    cooldown_status = f'<div style="font-size: 0.85em; opacity: 0.7; margin-top: 5px;">Cooldown: {cooldown_hours} hours</div>'
                else:
                    cooldown_status = f'<div style="font-size: 0.85em; color: #10b981; margin-top: 5px;">✓ Ready (Cooldown: {cooldown_hours} hours)</div>'

                content += f'''
                <div style="padding: 15px; background: var(--table_stripe); border-radius: 6px; border-left: 4px solid var(--accent);">
                    <div style="font-size: 1.1em; font-weight: bold; color: var(--accent); margin-bottom: 5px;">⚔️ {ability_name}</div>
                    <div style="margin-bottom: 5px;">{description}</div>
                    <div style="font-family: 'Courier New', monospace; font-size: 0.9em; color: var(--link);">!quest ability {sanitize(command)}</div>
                    {cooldown_status}
                </div>
                '''
            content += "</div></div></div>"
        elif unlocked_abilities:
            # Fallback if challenge_info not available
            content += f"""
            <div class="card" style="margin-top: 20px;">
                <div style="padding: 20px;">
                    <h2 style="color: var(--accent); margin-bottom: 15px;">⚔️ Unlocked Abilities</h2>
                    <div style="display: grid; gap: 10px;">
            """
            for ability in unlocked_abilities:
                content += f'<div style="padding: 10px; background: var(--table_stripe); border-radius: 6px;">{sanitize(str(ability))}</div>'
            content += "</div></div></div>"

        # Challenge path
        if challenge_path != "None":
            content += f"""
            <div class="card" style="margin-top: 20px;">
                <div style="padding: 20px;">
                    <h2 style="color: var(--accent); margin-bottom: 15px;">🎯 Challenge Path</h2>
                    <div style="font-size: 1.2em; margin-bottom: 10px; font-weight: bold; color: var(--link);">{sanitize(challenge_path_name)}</div>
            """
            if challenge_stats:
                content += '<div style="margin-top: 10px;"><strong>Progress:</strong><ul style="margin-top: 5px; margin-left: 20px;">'
                for stat_name, stat_value in challenge_stats.items():
                    formatted_name = stat_name.replace('_', ' ').title()
                    content += f'<li>{sanitize(formatted_name)}: {sanitize(str(stat_value))}</li>'
                content += '</ul></div>'
            content += "</div></div>"

        # Last fight
        if last_fight_display:
            content += f"""
            <div class="card" style="margin-top: 20px;">
                <div style="padding: 20px;">
                    <h2 style="color: var(--accent); margin-bottom: 15px;">⚔️ Last Fight</h2>
                    <div style="font-size: 1.1em;">{last_fight_display}</div>
                </div>
            </div>
            """

        # Add JavaScript for interactive features
        content += """
        <script>
        (function() {
            const linkSection = document.getElementById('link-section');
            const actionSection = document.getElementById('action-section');
            const linkForm = document.getElementById('link-form');
            const linkInput = document.getElementById('link-token');
            const linkMessage = document.getElementById('link-message');
            const actionButtons = actionSection ? actionSection.querySelectorAll('button[data-difficulty]') : [];
            const actionOutput = document.getElementById('action-output');
            const actionStatus = document.getElementById('action-status');
            const actionUsername = document.getElementById('action-username');
            const inventoryItems = document.querySelectorAll('.inventory-item');

            function setStatus(el, text, kind) {
                if (!el) return;
                el.textContent = text || '';
                el.classList.remove('alert-error', 'alert-success');
                if (kind === 'error') {
                    el.classList.add('alert-error');
                } else if (kind === 'success') {
                    el.classList.add('alert-success');
                }
            }

            // Link account handling
            if (linkForm && linkInput) {
                linkForm.addEventListener('submit', async function(ev) {
                    ev.preventDefault();
                    const token = (linkInput.value || '').trim();
                    if (!token) {
                        setStatus(linkMessage, 'Please enter your link code.', 'error');
                        return;
                    }
                    setStatus(linkMessage, 'Linking account…');
                    try {
                        const res = await fetch('/api/link/claim', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ token })
                        });
                        const data = await res.json();
                        if (!res.ok || !data.success) {
                            throw new Error(data.error || 'Unable to link account.');
                        }
                        setStatus(linkMessage, 'Linked successfully! Reloading page…', 'success');
                        setTimeout(() => window.location.reload(), 1000);
                    } catch (err) {
                        setStatus(linkMessage, err.message || 'Unable to link account.', 'error');
                    }
                });
            }

            // Quest button handling
            if (actionButtons.length && actionOutput && actionStatus) {
                actionButtons.forEach((button) => {
                    button.addEventListener('click', async () => {
                        const difficulty = button.getAttribute('data-difficulty');
                        setStatus(actionStatus, 'Venturing forth…');
                        actionOutput.textContent = '';
                        try {
                            const res = await fetch('/api/quest/solo', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ difficulty })
                            });
                            const data = await res.json();
                            if (!res.ok || !data.success) {
                                throw new Error(data.error || 'Quest failed.');
                            }
                            const messages = Array.isArray(data.messages) ? data.messages : [];
                            actionOutput.textContent = messages.join('\\n') || 'No response from Jeeves.';
                            if (data.username && actionUsername) {
                                actionUsername.textContent = data.username;
                            }
                            setStatus(actionStatus, 'Quest complete! Refreshing profile…', 'success');
                            setTimeout(() => window.location.reload(), 2000);
                        } catch (err) {
                            setStatus(actionStatus, err.message || 'Quest failed.', 'error');
                        }
                    });
                });
            }

            // Item usage handling
            inventoryItems.forEach((item) => {
                const itemName = item.getAttribute('data-item');
                const itemCountEl = item.querySelector('[style*="font-weight: bold"]');
                if (!itemName || !itemCountEl) return;

                const currentCount = parseInt(itemCountEl.textContent) || 0;
                if (currentCount <= 0) return;

                item.addEventListener('click', async () => {
                    if (!actionStatus || !actionOutput) {
                        alert('Please link your account to use items.');
                        return;
                    }

                    const confirmUse = confirm(`Use ${itemName.replace('_', ' ')}?`);
                    if (!confirmUse) return;

                    setStatus(actionStatus, `Using ${itemName.replace('_', ' ')}…`);
                    actionOutput.textContent = '';

                    try {
                        const res = await fetch('/api/item/use', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ item: itemName })
                        });
                        const data = await res.json();
                        if (!res.ok || !data.success) {
                            throw new Error(data.error || 'Failed to use item.');
                        }
                        const messages = Array.isArray(data.messages) ? data.messages : [];
                        actionOutput.textContent = messages.join('\\n') || 'Item used.';
                        setStatus(actionStatus, 'Item used! Refreshing profile…', 'success');
                        setTimeout(() => window.location.reload(), 1500);
                    } catch (err) {
                        setStatus(actionStatus, err.message || 'Failed to use item.', 'error');
                    }
                });
            });
        })();
        </script>
        """

        return content
