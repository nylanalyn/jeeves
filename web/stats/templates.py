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
    total_users = len(stats["users"])
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

        <div class="summary-stats">
            <div class="summary-card">
                <div class="number">{total_users}</div>
                <div class="label">Total Users</div>
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
