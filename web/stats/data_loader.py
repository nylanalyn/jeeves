# web/stats/data_loader.py
# Unified data loader for all Jeeves statistics

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Any

HEATMAP_BINS = 7 * 24


class JeevesStatsLoader:
    """Loads and aggregates statistics from all Jeeves modules."""

    def __init__(self, config_path: Path):
        """Initialize the stats loader.

        Args:
            config_path: Path to the config directory
        """
        self.config_path = Path(config_path)
        self.games_path = self.config_path / "games.json"
        self.stats_path = self.config_path / "stats.json"
        self.state_path = self.config_path / "state.json"
        self.users_path = self.config_path / "users.json"
        self.absurdia_db_path = self.config_path / "absurdia.db"

    @staticmethod
    def _load_json_file(path: Path) -> Dict[str, Any]:
        if not path.exists():
            return {}
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def load_all(self) -> Dict[str, Any]:
        """Load all stats from all modules.

        Returns:
            Dictionary containing all stats organized by category
        """
        return {
            "users": self.load_users(),
            "quest": self.load_quest_stats(),
            "hunt": self.load_hunt_stats(),
            "duel": self.load_duel_stats(),
            "adventure": self.load_adventure_stats(),
            "roadtrip": self.load_roadtrip_stats(),
            "absurdia": self.load_absurdia_stats(),
            "karma": self.load_karma_stats(),
            "coffee": self.load_coffee_stats(),
            "bell": self.load_bell_stats(),
            "achievements": self.load_achievements_stats(),
            "activity": self.load_activity_stats(),
            "fishing": self.load_fishing_stats(),
        }

    def load_users(self) -> Dict[str, Dict[str, Any]]:
        """Load user information including nick history.

        Returns:
            Dict mapping user_id to user info (canonical_nick, seen_nicks, first_seen)
        """
        if not self.users_path.exists():
            return {}

        with open(self.users_path, 'r') as f:
            data = json.load(f)

        users = data.get("modules", {}).get("users", {}).get("user_map", {})

        # Add nick change count to each user
        for user_id, user_data in users.items():
            seen_nicks = user_data.get("seen_nicks", [])
            user_data["nick_change_count"] = len(seen_nicks) - 1  # -1 because first nick isn't a change

        return users

    def load_quest_stats(self) -> Dict[str, Dict[str, Any]]:
        """Load Quest module statistics.

        Returns:
            Dict mapping user_id to quest stats (level, xp, prestige, wins, losses, etc.)
        """
        if not self.games_path.exists():
            return {}

        with open(self.games_path, 'r') as f:
            data = json.load(f)

        return data.get("modules", {}).get("quest", {}).get("players", {})

    def load_hunt_stats(self) -> Dict[str, Dict[str, int]]:
        """Load Hunt module statistics.

        Returns:
            Dict mapping user_id to hunt scores (duck_hunted, duck_hugged, etc.)
        """
        if not self.games_path.exists():
            return {}

        with open(self.games_path, 'r') as f:
            data = json.load(f)

        hunt_data = data.get("modules", {}).get("hunt", {})
        scores = hunt_data.get("scores", {})

        # Calculate totals for each user
        for user_id, user_scores in scores.items():
            total_hunted = sum(v for k, v in user_scores.items() if k.endswith("_hunted"))
            total_hugged = sum(v for k, v in user_scores.items() if k.endswith("_hugged"))
            total_murdered = sum(v for k, v in user_scores.items() if k.endswith("_murdered"))
            user_scores["total_hunted"] = total_hunted
            user_scores["total_hugged"] = total_hugged
            user_scores["total_murdered"] = total_murdered
            user_scores["total_interactions"] = total_hunted + total_hugged + total_murdered

        return scores

    def load_duel_stats(self) -> Dict[str, Dict[str, Dict[str, int]]]:
        """Load Duel module statistics.

        Returns:
            Dict with stats categories (wins, losses, duels_started, duels_received)
        """
        if not self.stats_path.exists():
            return {}

        with open(self.stats_path, 'r') as f:
            data = json.load(f)

        return data.get("modules", {}).get("duel", {}).get("stats", {})

    def load_adventure_stats(self) -> Dict[str, Any]:
        """Load Adventure module statistics.

        Returns:
            Dict with global adventure stats and user inventories
        """
        if not self.games_path.exists():
            return {}

        with open(self.games_path, 'r') as f:
            data = json.load(f)

        return data.get("modules", {}).get("adventure", {})

    def load_roadtrip_stats(self) -> Dict[str, Any]:
        """Load Roadtrip module statistics.

        Returns:
            Dict with roadtrip history and participation data
        """
        if not self.games_path.exists():
            return {}

        with open(self.games_path, 'r') as f:
            data = json.load(f)

        roadtrip_data = data.get("modules", {}).get("roadtrip", {})

        # Calculate participation counts from history
        history = roadtrip_data.get("history", [])
        participation = {}

        for trip in history:
            participants = trip.get("participants", [])
            for user_id in participants:
                participation[user_id] = participation.get(user_id, 0) + 1

        roadtrip_data["participation_counts"] = participation

        return roadtrip_data

    def load_absurdia_stats(self) -> Dict[str, Any]:
        """Load Absurdia module statistics from SQLite database.

        Returns:
            Dict with player and creature stats from Absurdia
        """
        if not self.absurdia_db_path.exists():
            return {"players": {}, "creatures": {}}

        try:
            conn = sqlite3.connect(self.absurdia_db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Load player stats
            players = {}
            cursor.execute("""
                SELECT user_id, coins, total_arena_wins, total_arena_losses,
                       current_win_streak, best_win_streak
                FROM players
            """)

            for row in cursor.fetchall():
                user_id = row["user_id"]
                players[user_id] = {
                    "coins": row["coins"],
                    "total_arena_wins": row["total_arena_wins"],
                    "total_arena_losses": row["total_arena_losses"],
                    "current_win_streak": row["current_win_streak"],
                    "best_win_streak": row["best_win_streak"],
                    "win_rate": (row["total_arena_wins"] /
                               (row["total_arena_wins"] + row["total_arena_losses"])
                               if (row["total_arena_wins"] + row["total_arena_losses"]) > 0 else 0)
                }

            # Load creature counts per player
            cursor.execute("""
                SELECT owner_id, COUNT(*) as creature_count,
                       SUM(CASE WHEN rarity = 'common' THEN 1 ELSE 0 END) as common_count,
                       SUM(CASE WHEN rarity = 'uncommon' THEN 1 ELSE 0 END) as uncommon_count,
                       SUM(CASE WHEN rarity = 'rare' THEN 1 ELSE 0 END) as rare_count,
                       SUM(CASE WHEN rarity = 'epic' THEN 1 ELSE 0 END) as epic_count,
                       SUM(CASE WHEN rarity = 'legendary' THEN 1 ELSE 0 END) as legendary_count
                FROM creatures
                WHERE owner_id IS NOT NULL
                GROUP BY owner_id
            """)

            for row in cursor.fetchall():
                user_id = row["owner_id"]
                if user_id in players:
                    players[user_id].update({
                        "creature_count": row["creature_count"],
                        "common_count": row["common_count"],
                        "uncommon_count": row["uncommon_count"],
                        "rare_count": row["rare_count"],
                        "epic_count": row["epic_count"],
                        "legendary_count": row["legendary_count"],
                    })

            conn.close()

            return {"players": players}

        except sqlite3.Error as e:
            print(f"Error loading Absurdia stats: {e}")
            return {"players": {}}

    def load_karma_stats(self) -> Dict[str, int]:
        """Load Karma module statistics.

        Returns:
            Dict mapping user_id to karma score
        """
        if not self.stats_path.exists():
            return {}

        with open(self.stats_path, 'r') as f:
            data = json.load(f)

        # Karma might not exist yet
        karma_module = data.get("modules", {}).get("karma", {})
        return karma_module.get("karma_scores", {})

    def load_coffee_stats(self) -> Dict[str, Dict[str, Any]]:
        """Load Coffee module statistics.

        Returns:
            Dict mapping user_id to beverage counts
        """
        if not self.stats_path.exists():
            return {}

        with open(self.stats_path, 'r') as f:
            data = json.load(f)

        return data.get("modules", {}).get("coffee", {}).get("user_beverage_counts", {})

    def load_bell_stats(self) -> Dict[str, int]:
        """Load Bell module statistics.

        Returns:
            Dict mapping user_id to bell scores
        """
        if not self.games_path.exists():
            return {}

        with open(self.games_path, 'r') as f:
            data = json.load(f)

        return data.get("modules", {}).get("bell", {}).get("scores", {})

    def load_achievements_stats(self) -> Dict[str, Any]:
        """Load Achievements module statistics.

        Returns:
            Dict containing user achievements data and global stats
        """
        # Achievements state is stored under the "achievements" module. Historically this
        # has lived in `state.json` (default bucket), but some deployments may map it to
        # `stats.json`. Read both and merge, preferring `stats.json` when present.
        stats_data = self._load_json_file(self.stats_path)
        state_data = self._load_json_file(self.state_path)

        achievements_from_stats = (stats_data.get("modules", {}) or {}).get("achievements", {})
        achievements_from_state = (state_data.get("modules", {}) or {}).get("achievements", {})

        if not isinstance(achievements_from_stats, dict):
            achievements_from_stats = {}
        if not isinstance(achievements_from_state, dict):
            achievements_from_state = {}

        user_achievements: Dict[str, Any] = {}
        global_first_unlocks: Dict[str, Any] = {}

        state_user_achievements = achievements_from_state.get("user_achievements", {})
        stats_user_achievements = achievements_from_stats.get("user_achievements", {})
        if isinstance(state_user_achievements, dict):
            user_achievements.update(state_user_achievements)
        if isinstance(stats_user_achievements, dict):
            user_achievements.update(stats_user_achievements)

        state_firsts = achievements_from_state.get("global_first_unlocks", {})
        stats_firsts = achievements_from_stats.get("global_first_unlocks", {})
        if isinstance(state_firsts, dict):
            global_first_unlocks.update(state_firsts)
        if isinstance(stats_firsts, dict):
            global_first_unlocks.update(stats_firsts)

        return {"user_achievements": user_achievements, "global_first_unlocks": global_first_unlocks}

    def load_activity_stats(self) -> Dict[str, Any]:
        """Load Activity module statistics.

        Returns:
            Dict containing global/channel/user heatmap buckets.
        """
        if not self.stats_path.exists():
            return {"global": {"grid": [0] * HEATMAP_BINS, "total": 0}, "channels": {}, "users": {}}

        with open(self.stats_path, "r") as f:
            data = json.load(f)

        activity = data.get("modules", {}).get("activity", {})
        if not isinstance(activity, dict):
            return {"global": {"grid": [0] * HEATMAP_BINS, "total": 0}, "channels": {}, "users": {}}

        global_bucket = activity.get("global") or {"grid": [0] * HEATMAP_BINS, "total": 0}
        channels = activity.get("channels") or {}
        users = activity.get("users") or {}

        if not isinstance(channels, dict):
            channels = {}
        if not isinstance(users, dict):
            users = {}

        return {"global": global_bucket, "channels": channels, "users": users}

    def load_fishing_stats(self) -> Dict[str, Dict[str, Any]]:
        """Load Fishing module statistics.

        Returns:
            Dict mapping user_id to fishing stats (level, xp, total_fish, etc.)
        """
        if not self.games_path.exists():
            return {}

        with open(self.games_path, 'r') as f:
            data = json.load(f)

        players = data.get("modules", {}).get("fishing", {}).get("players", {})

        # Calculate some aggregate stats for each player
        for user_id, player_data in players.items():
            if isinstance(player_data, dict):
                # Count rare and legendary catches
                rare_catches = player_data.get("rare_catches", [])
                player_data["rare_count"] = sum(1 for c in rare_catches if c.get("rarity") == "rare")
                player_data["legendary_count"] = sum(1 for c in rare_catches if c.get("rarity") == "legendary")
                # Count unique fish species
                catches = player_data.get("catches", {})
                player_data["unique_species"] = len(catches)

        return players


class StatsAggregator:
    """Aggregates and calculates cross-module statistics."""

    def __init__(self, all_stats: Dict[str, Any]):
        """Initialize aggregator with all loaded stats.

        Args:
            all_stats: Dict from JeevesStatsLoader.load_all()
        """
        self.stats = all_stats

    def get_active_users_count(self, days: int = 90) -> int:
        """Get count of users who have been active in the last N days.

        Args:
            days: Number of days to look back for activity

        Returns:
            Count of unique users with activity in the time period
        """
        from datetime import datetime, timezone, timedelta

        cutoff_timestamp = (datetime.now(timezone.utc) - timedelta(days=days)).timestamp()
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=days)).date()

        active_users = set()

        # Check coffee module (has unix timestamps)
        for user_id, coffee_data in self.stats["coffee"].items():
            if isinstance(coffee_data, dict):
                timestamp = coffee_data.get("timestamp", 0)
                if timestamp > cutoff_timestamp:
                    active_users.add(user_id)

        # Check quest module (has last_win_date as string)
        for user_id, quest_data in self.stats["quest"].items():
            last_win = quest_data.get("last_win_date")
            if last_win:
                try:
                    last_win_date = datetime.fromisoformat(last_win.replace('Z', '+00:00')).date()
                    if last_win_date >= cutoff_date:
                        active_users.add(user_id)
                except (ValueError, AttributeError):
                    pass

        # Check roadtrip history
        for trip in self.stats["roadtrip"].get("history", []):
            started = trip.get("started")
            if started:
                try:
                    trip_date = datetime.fromisoformat(started.replace('Z', '+00:00'))
                    if trip_date.timestamp() > cutoff_timestamp:
                        for participant in trip.get("participants", []):
                            active_users.add(participant)
                except (ValueError, AttributeError):
                    pass

        # Hunt, duel, absurdia, and bell don't have timestamps currently,
        # so we can't determine recent activity from them

        return len(active_users)

    def get_top_users_by_activity(self, limit: int = 10) -> List[Tuple[str, int]]:
        """Get top users by overall activity across all modules.

        Activity is calculated as a weighted sum of participation in different modules.

        Args:
            limit: Maximum number of users to return

        Returns:
            List of (user_id, activity_score) tuples
        """
        activity_scores = {}

        for user_id in self.stats["users"].keys():
            score = 0

            # Quest activity (10 points per prestige, 1 per level)
            if user_id in self.stats["quest"]:
                quest_data = self.stats["quest"][user_id]
                score += quest_data.get("prestige", 0) * 10
                score += quest_data.get("level", 0)

            # Hunt activity (1 point per interaction)
            if user_id in self.stats["hunt"]:
                hunt_data = self.stats["hunt"][user_id]
                score += hunt_data.get("total_interactions", 0)

            # Duel activity (2 points per duel)
            duel_started = self.stats["duel"].get("duels_started", {}).get(user_id, 0)
            duel_received = self.stats["duel"].get("duels_received", {}).get(user_id, 0)
            score += (duel_started + duel_received) * 2

            # Absurdia activity (5 points per creature, 1 per arena fight)
            if user_id in self.stats["absurdia"].get("players", {}):
                abs_data = self.stats["absurdia"]["players"][user_id]
                score += abs_data.get("creature_count", 0) * 5
                score += abs_data.get("total_arena_wins", 0) + abs_data.get("total_arena_losses", 0)

            # Roadtrip participation (3 points per trip)
            roadtrip_count = self.stats["roadtrip"].get("participation_counts", {}).get(user_id, 0)
            score += roadtrip_count * 3

            # Coffee drinking (0.5 points per coffee)
            if user_id in self.stats["coffee"]:
                score += self.stats["coffee"][user_id].get("count", 0) * 0.5

            # Bell ringing (1 point per bell)
            score += self.stats["bell"].get(user_id, 0)

            if score > 0:
                activity_scores[user_id] = score

        # Sort by score and return top N
        sorted_users = sorted(activity_scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_users[:limit]

    def get_user_display_name(self, user_id: str) -> str:
        """Get the display name for a user.

        Args:
            user_id: The user's UUID

        Returns:
            The user's canonical nickname or user_id if not found
        """
        user_data = self.stats["users"].get(user_id)
        if user_data:
            return user_data.get("canonical_nick", user_id)
        return user_id

    def get_leaderboard(self, category: str, stat_key: str, limit: int = 10) -> List[Tuple[str, Any]]:
        """Get a leaderboard for a specific stat.

        Args:
            category: Module category (e.g., "quest", "hunt", "duel")
            stat_key: The stat to sort by
            limit: Maximum number of entries

        Returns:
            List of (user_id, stat_value) tuples
        """
        results = []

        if category == "duel":
            # Duel stats have a different structure
            stat_dict = self.stats["duel"].get(stat_key, {})
            results = list(stat_dict.items())
        elif category in self.stats:
            # For other categories, iterate through users
            for user_id, user_data in self.stats[category].items():
                if isinstance(user_data, dict) and stat_key in user_data:
                    results.append((user_id, user_data[stat_key]))

        # Sort by value (descending) and return top N
        sorted_results = sorted(results, key=lambda x: x[1], reverse=True)
        return sorted_results[:limit]

    def find_user_id(self, query: str) -> Optional[str]:
        """Best-effort lookup of a user_id from a nick/user_id string."""
        if not query:
            return None

        query_norm = str(query).strip().lower()
        if not query_norm:
            return None

        if query in self.stats.get("users", {}):
            return query

        for user_id, user_data in self.stats.get("users", {}).items():
            if not isinstance(user_data, dict):
                continue
            canonical = str(user_data.get("canonical_nick", "")).lower()
            if canonical and canonical == query_norm:
                return user_id
            for nick in user_data.get("seen_nicks", []) or []:
                if str(nick).lower() == query_norm:
                    return user_id

        return None

    def _normalize_bucket(self, bucket: Any) -> Dict[str, Any]:
        default = {"grid": [0] * HEATMAP_BINS, "total": 0, "updated_at": None}
        if not isinstance(bucket, dict):
            return default
        grid = bucket.get("grid")
        if not isinstance(grid, list) or len(grid) != HEATMAP_BINS:
            bucket = dict(bucket)
            bucket["grid"] = [0] * HEATMAP_BINS
        bucket.setdefault("total", 0)
        bucket.setdefault("updated_at", None)
        return bucket

    def get_activity_bucket_global(self) -> Dict[str, Any]:
        return self._normalize_bucket(self.stats.get("activity", {}).get("global"))

    def get_activity_bucket_channel(self, channel: str) -> Dict[str, Any]:
        return self._normalize_bucket(self.stats.get("activity", {}).get("channels", {}).get(channel))

    def get_activity_bucket_user(self, user_id: str) -> Dict[str, Any]:
        return self._normalize_bucket(self.stats.get("activity", {}).get("users", {}).get(user_id))

    def get_heatmap_matrix(self, bucket: Dict[str, Any]) -> List[List[int]]:
        grid = self._normalize_bucket(bucket).get("grid", [0] * HEATMAP_BINS)
        rows: List[List[int]] = []
        for dow in range(7):
            start = dow * 24
            rows.append([int(x or 0) for x in grid[start:start + 24]])
        return rows

    def get_heatmap_max(self, bucket: Dict[str, Any]) -> int:
        grid = self._normalize_bucket(bucket).get("grid", [0] * HEATMAP_BINS)
        try:
            return max(int(x or 0) for x in grid) if grid else 0
        except Exception:
            return 0

    def get_top_hours(self, bucket: Dict[str, Any], limit: int = 5) -> List[Tuple[int, int]]:
        grid = self._normalize_bucket(bucket).get("grid", [0] * HEATMAP_BINS)
        totals = [(hour, 0) for hour in range(24)]
        for dow in range(7):
            for hour in range(24):
                idx = (dow * 24) + hour
                totals[hour] = (hour, totals[hour][1] + int(grid[idx] or 0))
        return sorted(totals, key=lambda x: x[1], reverse=True)[:limit]

    def get_top_days(self, bucket: Dict[str, Any], limit: int = 3) -> List[Tuple[int, int]]:
        grid = self._normalize_bucket(bucket).get("grid", [0] * HEATMAP_BINS)
        totals: List[Tuple[int, int]] = []
        for dow in range(7):
            start = dow * 24
            totals.append((dow, sum(int(x or 0) for x in grid[start:start + 24])))
        return sorted(totals, key=lambda x: x[1], reverse=True)[:limit]
