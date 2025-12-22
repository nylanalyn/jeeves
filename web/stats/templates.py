# web/stats/templates.py
# HTML templates for stats web UI

from typing import Dict, Any, List, Tuple


def render_overview_page(stats: Dict[str, Any], aggregator) -> str:
    """Render the main overview/dashboard page.

    Args:
        stats: All loaded stats from JeevesStatsLoader
        aggregator: StatsAggregator instance

    Returns:
        HTML string
    """
    # Get top users by activity
    top_active = aggregator.get_top_users_by_activity(limit=10)

    # Get various leaderboards
    top_quest = aggregator.get_leaderboard("quest", "prestige", limit=5)
    top_hunters = aggregator.get_leaderboard("hunt", "total_interactions", limit=5)
    top_duelists = aggregator.get_leaderboard("duel", "wins", limit=5)

    # Get nick change leaders
    nick_changers = sorted(
        [(uid, data.get("nick_change_count", 0)) for uid, data in stats["users"].items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]

    # Get roadtrip participants
    roadtrip_participants = sorted(
        stats["roadtrip"].get("participation_counts", {}).items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    # Get absurdia leaders
    absurdia_arena = sorted(
        [(uid, data.get("total_arena_wins", 0)) for uid, data in stats["absurdia"].get("players", {}).items()],
        key=lambda x: x[1],
        reverse=True
    )[:5]

    # Get karma leaders
    karma_leaders = sorted(
        stats["karma"].items(),
        key=lambda x: x[1],
        reverse=True
    )[:5]

    # Count stats
    total_nicks = len(stats["users"])
    active_users_90d = aggregator.get_active_users_count(days=90)
    quest_players = len(stats["quest"])
    hunt_players = len(stats["hunt"])
    duel_players = len(set(
        list(stats["duel"].get("wins", {}).keys()) +
        list(stats["duel"].get("losses", {}).keys())
    ))
    absurdia_players = len(stats["absurdia"].get("players", {}))

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jeeves Stats Dashboard</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            color: white;
            margin-bottom: 2rem;
        }}

        header h1 {{
            font-size: 3rem;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }}

        header p {{
            font-size: 1.2rem;
            opacity: 0.9;
        }}

        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }}

        .stat-card {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .stat-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.15);
        }}

        .stat-card h2 {{
            font-size: 1.5rem;
            margin-bottom: 1rem;
            color: #667eea;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}

        .stat-card .icon {{
            font-size: 1.8rem;
        }}

        .leaderboard {{
            list-style: none;
        }}

        .leaderboard li {{
            padding: 0.75rem;
            margin-bottom: 0.5rem;
            background: #f8f9fa;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: background 0.2s;
        }}

        .leaderboard li:hover {{
            background: #e9ecef;
        }}

        .rank {{
            font-weight: bold;
            color: #667eea;
            min-width: 2rem;
        }}

        .username {{
            flex: 1;
            font-weight: 500;
            color: #495057;
        }}

        .score {{
            font-weight: bold;
            color: #28a745;
            min-width: 4rem;
            text-align: right;
        }}

        .summary-stats {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}

        .summary-card {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 1.5rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .summary-card .number {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #667eea;
            margin-bottom: 0.5rem;
        }}

        .summary-card .label {{
            font-size: 0.9rem;
            color: #6c757d;
            text-transform: uppercase;
            letter-spacing: 1px;
        }}

        .empty-state {{
            text-align: center;
            color: #6c757d;
            font-style: italic;
            padding: 1rem;
        }}

        .highlight {{
            background: linear-gradient(135deg, #ffd89b 0%, #19547b 100%);
            color: white;
            padding: 1rem;
            border-radius: 5px;
            margin-bottom: 1rem;
            text-align: center;
            font-size: 1.1rem;
            font-weight: 500;
        }}

        footer {{
            text-align: center;
            color: white;
            margin-top: 3rem;
            opacity: 0.8;
            font-size: 0.9rem;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📊 Jeeves Stats Dashboard</h1>
            <p>Comprehensive statistics across all modules</p>
        </header>

        <nav style="text-align:center; margin-bottom: 1.5rem;">
            <a href="/" style="color:white; text-decoration:none; margin: 0 0.75rem; font-weight:600;">📊 Overview</a>
            <a href="/activity" style="color:white; text-decoration:none; margin: 0 0.75rem; font-weight:600;">🗓️ Activity</a>
            <a href="/achievements" style="color:white; text-decoration:none; margin: 0 0.75rem; font-weight:600;">🏆 Achievements</a>
        </nav>

        <div class="summary-stats">
            <div class="summary-card">
                <div class="number">{total_nicks}</div>
                <div class="label">Total Nicks Tracked</div>
            </div>
            <div class="summary-card">
                <div class="number">{active_users_90d}</div>
                <div class="label">Active Users (90d)</div>
            </div>
            <div class="summary-card">
                <div class="number">{quest_players}</div>
                <div class="label">Quest Players</div>
            </div>
            <div class="summary-card">
                <div class="number">{hunt_players}</div>
                <div class="label">Hunters</div>
            </div>
            <div class="summary-card">
                <div class="number">{duel_players}</div>
                <div class="label">Duelists</div>
            </div>
            <div class="summary-card">
                <div class="number">{absurdia_players}</div>
                <div class="label">Absurdia Players</div>
            </div>
        </div>

        <div class="stats-grid">
            <!-- Most Active Users -->
            <div class="stat-card">
                <h2><span class="icon">🏆</span> Most Active Users</h2>
                {_render_leaderboard_list(top_active, aggregator, score_label="Activity Score")}
            </div>

            <!-- Top Quest Players -->
            <div class="stat-card">
                <h2><span class="icon">⚔️</span> Quest Leaders</h2>
                {_render_quest_leaderboard(top_quest, stats, aggregator)}
            </div>

            <!-- Top Hunters -->
            <div class="stat-card">
                <h2><span class="icon">🦆</span> Top Hunters</h2>
                {_render_leaderboard_list(top_hunters, aggregator, score_label="Interactions")}
            </div>

            <!-- Duel Champions -->
            <div class="stat-card">
                <h2><span class="icon">🤺</span> Duel Champions</h2>
                {_render_leaderboard_list(top_duelists, aggregator, score_label="Wins")}
            </div>

            <!-- Nick Change Leaders -->
            <div class="stat-card">
                <h2><span class="icon">🎭</span> Most Nick Changes</h2>
                {_render_nick_changes(nick_changers, stats, aggregator)}
            </div>

            <!-- Roadtrip Enthusiasts -->
            <div class="stat-card">
                <h2><span class="icon">🚗</span> Roadtrip Enthusiasts</h2>
                {_render_leaderboard_list(roadtrip_participants, aggregator, score_label="Trips")}
            </div>

            <!-- Absurdia Arena Champions -->
            <div class="stat-card">
                <h2><span class="icon">🐉</span> Arena Champions</h2>
                {_render_leaderboard_list(absurdia_arena, aggregator, score_label="Arena Wins")}
            </div>

            <!-- Karma Leaders -->
            <div class="stat-card">
                <h2><span class="icon">⭐</span> Karma Leaders</h2>
                {_render_karma_leaderboard(karma_leaders, aggregator)}
            </div>
        </div>

        <footer>
            <p>Jeeves Stats Dashboard | Data refreshes on page load</p>
        </footer>
    </div>
</body>
</html>"""

    return html


def render_activity_page(stats: Dict[str, Any], aggregator, channels: List[str],
                         selected_channel: str | None = None, user_query: str | None = None) -> str:
    channel_bucket = (aggregator.get_activity_bucket_channel(selected_channel)
                      if selected_channel else aggregator.get_activity_bucket_global())
    channel_title = selected_channel or "All Channels (Combined)"

    user_id = aggregator.find_user_id(user_query or "")
    user_bucket = aggregator.get_activity_bucket_user(user_id) if user_id else None
    user_name = aggregator.get_user_display_name(user_id) if user_id else None

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jeeves Activity</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 2rem;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        header {{ text-align: center; color: white; margin-bottom: 1rem; }}
        header h1 {{ font-size: 2.6rem; margin-bottom: 0.5rem; text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3); }}
        header p {{ font-size: 1.1rem; opacity: 0.9; }}
        nav {{
            text-align: center;
            margin-bottom: 1.5rem;
        }}
        nav a {{
            color: white;
            text-decoration: none;
            margin: 0 0.75rem;
            font-weight: 600;
        }}
        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(360px, 1fr));
            gap: 1.5rem;
            margin-top: 1.5rem;
        }}
        .card {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 1.5rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        .card h2 {{
            font-size: 1.4rem;
            margin-bottom: 1rem;
            color: #667eea;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }}
        .note {{
            color: #6c757d;
            font-size: 0.95rem;
            margin-bottom: 1rem;
            line-height: 1.4;
        }}
        .controls {{
            display: grid;
            grid-template-columns: 1fr;
            gap: 0.75rem;
            margin-bottom: 1rem;
        }}
        .controls label {{
            font-weight: 600;
            color: #495057;
            margin-bottom: 0.25rem;
            display: block;
        }}
        .controls input, .controls select {{
            width: 100%;
            padding: 0.6rem 0.75rem;
            border: 1px solid #dee2e6;
            border-radius: 8px;
            font-size: 1rem;
        }}
        .controls button {{
            padding: 0.7rem 0.9rem;
            border: none;
            border-radius: 8px;
            background: #667eea;
            color: white;
            font-weight: 700;
            cursor: pointer;
        }}
        .heatmap {{
            width: 100%;
            overflow-x: auto;
        }}
        table.heatmap-table {{
            border-collapse: collapse;
            width: max-content;
            min-width: 100%;
        }}
        table.heatmap-table th, table.heatmap-table td {{
            border: 1px solid #e9ecef;
            text-align: center;
            padding: 0;
            font-size: 0.75rem;
            color: #495057;
        }}
        table.heatmap-table th.label {{
            background: #f8f9fa;
            position: sticky;
            left: 0;
            z-index: 1;
            min-width: 3.2rem;
        }}
        table.heatmap-table th.hour {{
            background: #f8f9fa;
            min-width: 1.2rem;
            padding: 0.2rem 0.15rem;
        }}
        table.heatmap-table td.cell {{
            width: 18px;
            height: 18px;
        }}
        .meta {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 0.75rem;
            margin-top: 1rem;
        }}
        .meta-box {{
            background: #f8f9fa;
            border-radius: 8px;
            padding: 0.75rem;
        }}
        .meta-box .title {{
            font-weight: 700;
            color: #667eea;
            margin-bottom: 0.4rem;
        }}
        .meta-box ul {{ margin-left: 1.1rem; }}
        .meta-box li {{ margin: 0.2rem 0; }}
        .empty {{
            padding: 1rem;
            background: #f8f9fa;
            border-radius: 8px;
            color: #6c757d;
            font-style: italic;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🗓️ Activity</h1>
            <p>Heatmaps and active-time summaries (UTC)</p>
        </header>

        <nav>
            <a href="/">📊 Overview</a>
            <a href="/activity">🗓️ Activity</a>
            <a href="/achievements">🏆 Achievements</a>
        </nav>

        <div class="grid">
            <div class="card">
                <h2>🌡️ Channel Activity Heatmap</h2>
                <div class="note">Tracks non-command channel messages (ambient chat only). Commands are excluded.</div>
                <form class="controls" method="GET" action="/activity">
                    <div>
                        <label for="channel">Channel</label>
                        <select id="channel" name="channel">
                            <option value="" {"selected" if not selected_channel else ""}>All Channels (Combined)</option>
                            {"".join([f'<option value=\"{_escape_html(ch)}\" ' + ('selected' if ch == selected_channel else '') + f'> {_escape_html(ch)}</option>' for ch in channels])}
                        </select>
                    </div>
                    <div>
                        <label for="user">User (nick or user id)</label>
                        <input id="user" name="user" value="{_escape_html(user_query or '')}" placeholder="e.g. alice">
                    </div>
                    <button type="submit">Update</button>
                </form>
                <div class="note"><b>Viewing:</b> {_escape_html(channel_title)}</div>
                {_render_heatmap_table(aggregator, channel_bucket)}
                {_render_heatmap_meta(aggregator, channel_bucket)}
            </div>

            <div class="card">
                <h2>👤 User Activity</h2>
                {(_render_user_activity(aggregator, user_id, user_name, user_bucket) if user_id and user_bucket else '<div class=\"empty\">Enter a nick above to view a user heatmap.</div>')}
            </div>
        </div>
    </div>
</body>
</html>"""

    return html


def _render_heatmap_table(aggregator, bucket: Dict[str, Any]) -> str:
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    matrix = aggregator.get_heatmap_matrix(bucket)
    max_val = aggregator.get_heatmap_max(bucket)

    def color_for(value: int) -> str:
        if max_val <= 0 or value <= 0:
            return "#f1f3f5"
        ratio = value / max_val
        alpha = 0.15 + (0.85 * ratio)
        return f"rgba(102, 126, 234, {alpha:.3f})"

    header_cells = "".join([f'<th class="hour">{h}</th>' for h in range(24)])
    rows_html = ""
    for dow, row in enumerate(matrix):
        cells = ""
        for hour, value in enumerate(row):
            title = f"{days[dow]} {hour:02d}:00 — {value}"
            cells += f'<td class="cell" title="{_escape_html(title)}" style="background:{color_for(int(value))};"></td>'
        rows_html += f'<tr><th class="label">{days[dow]}</th>{cells}</tr>'

    return f"""
<div class="heatmap">
  <table class="heatmap-table">
    <thead><tr><th class="label"></th>{header_cells}</tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</div>"""


def _render_heatmap_meta(aggregator, bucket: Dict[str, Any]) -> str:
    total = int((bucket or {}).get("total", 0) or 0)
    updated_at = (bucket or {}).get("updated_at")

    top_hours = aggregator.get_top_hours(bucket, limit=5)
    top_days = aggregator.get_top_days(bucket, limit=3)

    def hour_label(h: int) -> str:
        return f"{h:02d}:00"

    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

    hours_list = "".join([f"<li>{hour_label(h)} — {c}</li>" for h, c in top_hours if c > 0]) or "<li>—</li>"
    days_list = "".join([f"<li>{days[d]} — {c}</li>" for d, c in top_days if c > 0]) or "<li>—</li>"

    updated = _escape_html(str(updated_at)) if updated_at else "—"

    return f"""
<div class="meta">
  <div class="meta-box"><div class="title">Total Messages Tracked</div>{total}</div>
  <div class="meta-box"><div class="title">Last Updated</div>{updated}</div>
  <div class="meta-box"><div class="title">Top Hours (UTC)</div><ul>{hours_list}</ul></div>
  <div class="meta-box"><div class="title">Top Days</div><ul>{days_list}</ul></div>
</div>"""


def _render_user_activity(aggregator, user_id: str, user_name: str, bucket: Dict[str, Any]) -> str:
    safe_name = _escape_html(user_name or user_id)
    safe_id = _escape_html(user_id)
    return f"""
<div class="note"><b>User:</b> {safe_name} <span style="color:#6c757d;">({safe_id})</span></div>
{_render_heatmap_table(aggregator, bucket)}
{_render_heatmap_meta(aggregator, bucket)}
"""


def _render_leaderboard_list(entries: List[Tuple[str, Any]], aggregator, score_label: str = "Score") -> str:
    """Render a leaderboard list.

    Args:
        entries: List of (user_id, score) tuples
        aggregator: StatsAggregator instance
        score_label: Label for the score column

    Returns:
        HTML string
    """
    if not entries:
        return '<div class="empty-state">No data available</div>'

    html = '<ul class="leaderboard">'
    for i, (user_id, score) in enumerate(entries, 1):
        username = aggregator.get_user_display_name(user_id)
        # Format score based on type
        if isinstance(score, float):
            score_str = f"{score:.1f}"
        else:
            score_str = str(int(score))

        html += f'''
            <li>
                <span class="rank">#{i}</span>
                <span class="username">{_escape_html(username)}</span>
                <span class="score">{score_str}</span>
            </li>'''

    html += '</ul>'
    return html


def _render_quest_leaderboard(entries: List[Tuple[str, int]], stats: Dict[str, Any], aggregator) -> str:
    """Render quest leaderboard with level info.

    Args:
        entries: List of (user_id, prestige) tuples
        stats: All stats
        aggregator: StatsAggregator instance

    Returns:
        HTML string
    """
    if not entries:
        return '<div class="empty-state">No quest players yet</div>'

    html = '<ul class="leaderboard">'
    for i, (user_id, prestige) in enumerate(entries, 1):
        username = aggregator.get_user_display_name(user_id)
        quest_data = stats["quest"].get(user_id, {})
        level = quest_data.get("level", 0)

        if prestige > 0:
            score_str = f"P{prestige} L{level}"
        else:
            score_str = f"Level {level}"

        html += f'''
            <li>
                <span class="rank">#{i}</span>
                <span class="username">{_escape_html(username)}</span>
                <span class="score">{score_str}</span>
            </li>'''

    html += '</ul>'
    return html


def _render_nick_changes(entries: List[Tuple[str, int]], stats: Dict[str, Any], aggregator) -> str:
    """Render nick change leaderboard with highlight.

    Args:
        entries: List of (user_id, change_count) tuples
        stats: All stats
        aggregator: StatsAggregator instance

    Returns:
        HTML string
    """
    if not entries or entries[0][1] == 0:
        return '<div class="empty-state">No nick changes recorded</div>'

    # Get the top user
    top_user_id, top_count = entries[0]
    top_username = aggregator.get_user_display_name(top_user_id)

    html = f'<div class="highlight">{_escape_html(top_username)} has the most nick changes: {top_count}!</div>'

    # Show the leaderboard
    html += '<ul class="leaderboard">'
    for i, (user_id, count) in enumerate(entries, 1):
        if count == 0:
            break
        username = aggregator.get_user_display_name(user_id)
        html += f'''
            <li>
                <span class="rank">#{i}</span>
                <span class="username">{_escape_html(username)}</span>
                <span class="score">{count} changes</span>
            </li>'''

    html += '</ul>'
    return html


def _render_karma_leaderboard(entries: List[Tuple[str, int]], aggregator) -> str:
    """Render karma leaderboard.

    Args:
        entries: List of (user_id, karma) tuples
        aggregator: StatsAggregator instance

    Returns:
        HTML string
    """
    if not entries:
        return '<div class="empty-state">No karma data</div>'

    html = '<ul class="leaderboard">'
    for i, (user_id, karma) in enumerate(entries, 1):
        username = aggregator.get_user_display_name(user_id)
        score_class = "score"
        prefix = "+" if karma > 0 else ""

        html += f'''
            <li>
                <span class="rank">#{i}</span>
                <span class="username">{_escape_html(username)}</span>
                <span class="{score_class}">{prefix}{karma}</span>
            </li>'''

    html += '</ul>'
    return html


def _escape_html(text: str) -> str:
    """Escape HTML special characters.

    Args:
        text: Text to escape

    Returns:
        Escaped text
    """
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#x27;"))


def render_achievements_page(stats: Dict[str, Any]) -> str:
    """Render the achievements page.

    Args:
        stats: All loaded stats from JeevesStatsLoader

    Returns:
        HTML string
    """
    # Achievement definitions (copied from modules/achievements.py)
    ACHIEVEMENTS = {
        # Quest Achievements
        "quest_novice": {"name": "Quest Novice", "description": "Complete 10 quests", "category": "quest", "requirement": {"quests_completed": 10}, "secret": False, "tier": 1},
        "quest_adept": {"name": "Quest Adept", "description": "Complete 50 quests", "category": "quest", "requirement": {"quests_completed": 50}, "secret": False, "tier": 2},
        "quest_master": {"name": "Quest Master", "description": "Complete 100 quests", "category": "quest", "requirement": {"quests_completed": 100}, "secret": False, "tier": 3},
        "quest_legend": {"name": "Quest Legend", "description": "Complete 500 quests", "category": "quest", "requirement": {"quests_completed": 500}, "secret": False, "tier": 4},
        "quest_mythic": {"name": "Quest Mythic", "description": "Complete 1000 quests", "category": "quest", "requirement": {"quests_completed": 1000}, "secret": False, "tier": 5},
        "prestige_1": {"name": "First Prestige", "description": "Reach Prestige 1", "category": "quest", "requirement": {"prestige": 1}, "secret": False},
        "prestige_5": {"name": "Prestige Elite", "description": "Reach Prestige 5", "category": "quest", "requirement": {"prestige": 5}, "secret": False},
        "prestige_10": {"name": "Prestige Master", "description": "Reach Prestige 10", "category": "quest", "requirement": {"prestige": 10}, "secret": False},
        "win_streak_5": {"name": "On a Roll", "description": "Win 5 quests in a row", "category": "quest", "requirement": {"win_streak": 5}, "secret": False},
        "win_streak_10": {"name": "Unstoppable", "description": "Win 10 quests in a row", "category": "quest", "requirement": {"win_streak": 10}, "secret": False},
        "win_streak_25": {"name": "Legendary Streak", "description": "Win 25 quests in a row", "category": "quest", "requirement": {"win_streak": 25}, "secret": False},
        "unlucky": {"name": "Unlucky", "description": "Lose 10 quests in a row", "category": "quest", "requirement": {"loss_streak": 10}, "secret": True},

        # Creature/Animal Achievements
        "hunter_1": {"name": "Hunter", "description": "Hunt 10 creatures", "category": "creatures", "requirement": {"animals_hunted": 10}, "secret": False, "tier": 1},
        "hunter_2": {"name": "Hunter II", "description": "Hunt 50 creatures", "category": "creatures", "requirement": {"animals_hunted": 50}, "secret": False, "tier": 2},
        "hunter_3": {"name": "Hunter III", "description": "Hunt 100 creatures", "category": "creatures", "requirement": {"animals_hunted": 100}, "secret": False, "tier": 3},
        "apex_predator": {"name": "Apex Predator", "description": "Hunt 250 creatures", "category": "creatures", "requirement": {"animals_hunted": 250}, "secret": False, "tier": 4},
        "lover_1": {"name": "Animal Lover", "description": "Hug 10 creatures", "category": "creatures", "requirement": {"animals_hugged": 10}, "secret": False, "tier": 1},
        "lover_2": {"name": "Animal Lover II", "description": "Hug 50 creatures", "category": "creatures", "requirement": {"animals_hugged": 50}, "secret": False, "tier": 2},
        "lover_3": {"name": "Animal Lover III", "description": "Hug 100 creatures", "category": "creatures", "requirement": {"animals_hugged": 100}, "secret": False, "tier": 3},
        "pacifist": {"name": "Pacifist", "description": "Hug 100 creatures without hunting any", "category": "creatures", "requirement": {"animals_hugged": 100, "animals_hunted": 0}, "secret": True},
        "bloodthirsty": {"name": "Bloodthirsty", "description": "Hunt 100 creatures without hugging any", "category": "creatures", "requirement": {"animals_hunted": 100, "animals_hugged": 0}, "secret": True},

        # Coffee Achievements
        "coffee_drinker": {"name": "Coffee Drinker", "description": "Order 25 coffees", "category": "social", "requirement": {"coffees_ordered": 25}, "secret": False, "tier": 1},
        "coffee_addict": {"name": "Coffee Addict", "description": "Order 100 coffees", "category": "social", "requirement": {"coffees_ordered": 100}, "secret": False, "tier": 2},
        "caffeine_overload": {"name": "Caffeine Overload", "description": "Order 500 coffees", "category": "social", "requirement": {"coffees_ordered": 500}, "secret": False, "tier": 3},

        # Social/Usage Achievements
        "weatherwatcher": {"name": "Weatherwatcher", "description": "Check weather 50 times", "category": "social", "requirement": {"weather_checks": 50}, "secret": False},
        "meteorologist": {"name": "Meteorologist", "description": "Check weather 200 times", "category": "social", "requirement": {"weather_checks": 200}, "secret": False},
        "polite": {"name": "Polite", "description": "Send 50 courtesy messages", "category": "social", "requirement": {"courtesy_messages": 50}, "secret": False},
        "karma_farmer": {"name": "Karma Farmer", "description": "Give 100 karma points", "category": "social", "requirement": {"karma_given": 100}, "secret": False},
        "translator": {"name": "Translator", "description": "Use translation 25 times", "category": "social", "requirement": {"translations_used": 25}, "secret": False},
        "scare_tactics": {"name": "Scare Tactics", "description": "Scare 25 people", "category": "fun", "requirement": {"scares_sent": 25}, "secret": False},
        "gif_master": {"name": "GIF Master", "description": "Post 50 GIFs", "category": "fun", "requirement": {"gifs_posted": 50}, "secret": False},

        # Meta Achievements
        "achievement_hunter": {"name": "Achievement Hunter", "description": "Unlock 5 achievements", "category": "meta", "requirement": {"achievements_unlocked": 5}, "secret": False, "tier": 1},
        "achievement_master": {"name": "Achievement Master", "description": "Unlock 15 achievements", "category": "meta", "requirement": {"achievements_unlocked": 15}, "secret": False, "tier": 2},
        "completionist": {"name": "Completionist", "description": "Unlock 30 achievements", "category": "meta", "requirement": {"achievements_unlocked": 30}, "secret": True, "tier": 3},
        "first_blood": {"name": "First!", "description": "Be the first to unlock any achievement globally", "category": "meta", "requirement": "special", "secret": True},
        "trendsetter": {"name": "Trendsetter", "description": "Be the first to unlock 5 different achievements globally", "category": "meta", "requirement": "special", "secret": True},
    }

    # Get achievement data
    achievements_data = stats.get("achievements", {})
    user_achievements = achievements_data.get("user_achievements", {})
    global_first_unlocks = achievements_data.get("global_first_unlocks", {})

    # Calculate stats
    total_users_tracking = len(user_achievements)
    total_achievements_unlocked = sum(len(user_data.get("unlocked", [])) for user_data in user_achievements.values())

    # Group achievements by category
    categories = {"quest": [], "creatures": [], "social": [], "fun": [], "meta": []}
    for ach_id, ach_data in ACHIEVEMENTS.items():
        category = ach_data.get("category", "other")
        if category in categories:
            categories[category].append((ach_id, ach_data))

    # Build category sections HTML
    category_sections = ""
    category_icons = {
        "quest": "⚔️",
        "creatures": "🦌",
        "social": "👥",
        "fun": "🎉",
        "meta": "🏆"
    }

    for cat_name, cat_achievements in categories.items():
        if not cat_achievements:
            continue

        icon = category_icons.get(cat_name, "🎯")
        category_sections += f"""
        <div class="achievement-category">
            <h3>{icon} {cat_name.title()} Achievements</h3>
            <div class="achievement-grid">
        """

        for ach_id, ach_data in cat_achievements:
            tier = ach_data.get("tier", 0)
            tier_badge = f'<span class="tier-badge tier-{tier}">Tier {tier}</span>' if tier > 0 else ''
            secret_badge = '<span class="secret-badge">🤫 Secret</span>' if ach_data.get("secret") else ''

            # Check who has this
            unlock_count = sum(1 for user_data in user_achievements.values() if ach_id in user_data.get("unlocked", []))
            first_unlock = global_first_unlocks.get(ach_id, {})
            first_user = stats["users"].get(first_unlock.get("user_id", ""), {}).get("canonical_nick", "Unknown") if first_unlock else None

            rarity_pct = (unlock_count / total_users_tracking * 100) if total_users_tracking > 0 else 0
            rarity_class = "legendary" if rarity_pct < 5 else "epic" if rarity_pct < 20 else "rare" if rarity_pct < 50 else "common"

            first_text = f'<div class="first-unlock">🥇 First: {escape_html(first_user)}</div>' if first_user else ''

            category_sections += f"""
            <div class="achievement-card {rarity_class}">
                <div class="achievement-header">
                    <h4>{escape_html(ach_data['name'])}</h4>
                    {tier_badge}
                    {secret_badge}
                </div>
                <p class="achievement-desc">{escape_html(ach_data['description'])}</p>
                <div class="achievement-stats">
                    <div class="unlock-count">{unlock_count} / {total_users_tracking} unlocked ({rarity_pct:.1f}%)</div>
                    {first_text}
                </div>
            </div>
            """

        category_sections += """
            </div>
        </div>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Jeeves Achievements</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: #333;
            min-height: 100vh;
            padding: 2rem;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            color: white;
            margin-bottom: 2rem;
        }}

        header h1 {{
            font-size: 3rem;
            margin-bottom: 0.5rem;
            text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
        }}

        nav {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 1rem;
            margin-bottom: 2rem;
            text-align: center;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        nav a {{
            color: #764ba2;
            text-decoration: none;
            margin: 0 1rem;
            font-weight: 600;
            transition: color 0.3s;
        }}

        nav a:hover {{
            color: #667eea;
        }}

        .stats-summary {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 1.5rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            display: flex;
            justify-content: space-around;
            flex-wrap: wrap;
        }}

        .stat-box {{
            text-align: center;
            padding: 1rem;
        }}

        .stat-box .number {{
            font-size: 2.5rem;
            font-weight: bold;
            color: #764ba2;
        }}

        .stat-box .label {{
            font-size: 0.9rem;
            color: #666;
            margin-top: 0.5rem;
        }}

        .achievement-category {{
            background: rgba(255, 255, 255, 0.95);
            border-radius: 10px;
            padding: 2rem;
            margin-bottom: 2rem;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}

        .achievement-category h3 {{
            font-size: 1.8rem;
            margin-bottom: 1.5rem;
            color: #764ba2;
        }}

        .achievement-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
            gap: 1rem;
        }}

        .achievement-card {{
            background: white;
            border-radius: 8px;
            padding: 1.5rem;
            box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
            border-left: 4px solid #ccc;
            transition: transform 0.2s, box-shadow 0.2s;
        }}

        .achievement-card:hover {{
            transform: translateY(-2px);
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.15);
        }}

        .achievement-card.legendary {{
            border-left-color: #ff6b35;
            background: linear-gradient(to right, #fff9f0, white);
        }}

        .achievement-card.epic {{
            border-left-color: #9c27b0;
            background: linear-gradient(to right, #f9f0ff, white);
        }}

        .achievement-card.rare {{
            border-left-color: #2196f3;
            background: linear-gradient(to right, #f0f8ff, white);
        }}

        .achievement-card.common {{
            border-left-color: #4caf50;
        }}

        .achievement-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 0.75rem;
        }}

        .achievement-header h4 {{
            font-size: 1.2rem;
            color: #333;
        }}

        .tier-badge {{
            background: linear-gradient(135deg, #ffd700, #ffed4e);
            color: #333;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: bold;
        }}

        .tier-badge.tier-2 {{ background: linear-gradient(135deg, #c0c0c0, #e8e8e8); }}
        .tier-badge.tier-3 {{ background: linear-gradient(135deg, #cd7f32, #e9b872); }}
        .tier-badge.tier-4 {{ background: linear-gradient(135deg, #9c27b0, #ce93d8); }}
        .tier-badge.tier-5 {{ background: linear-gradient(135deg, #ff6b35, #ff9f80); }}

        .secret-badge {{
            background: #333;
            color: white;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            margin-left: 0.5rem;
        }}

        .achievement-desc {{
            color: #666;
            margin-bottom: 1rem;
            font-size: 0.95rem;
        }}

        .achievement-stats {{
            border-top: 1px solid #eee;
            padding-top: 0.75rem;
            font-size: 0.85rem;
            color: #888;
        }}

        .unlock-count {{
            font-weight: 600;
            color: #764ba2;
        }}

        .first-unlock {{
            margin-top: 0.5rem;
            font-style: italic;
            color: #ff6b35;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 Jeeves Achievements</h1>
            <p>Track your progress across all Jeeves activities</p>
        </header>

        <nav>
            <a href="/">📊 Overview</a>
            <a href="/activity">🗓️ Activity</a>
            <a href="/achievements">🏆 Achievements</a>
        </nav>

        <div class="stats-summary">
            <div class="stat-box">
                <div class="number">{len(ACHIEVEMENTS)}</div>
                <div class="label">Total Achievements</div>
            </div>
            <div class="stat-box">
                <div class="number">{total_users_tracking}</div>
                <div class="label">Users Tracking</div>
            </div>
            <div class="stat-box">
                <div class="number">{total_achievements_unlocked}</div>
                <div class="label">Total Unlocks</div>
            </div>
        </div>

        {category_sections}
    </div>
</body>
</html>"""

    return html
