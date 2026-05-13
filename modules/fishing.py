# modules/fishing.py
# A fishing mini-game where users cast lines and reel in catches over time.

import json
import os
import random
import re
import schedule
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import SimpleCommandModule
from . import achievement_hooks

UTC = timezone.utc

XP_BONUS_SMALL_CHANCE = 0.04
XP_BONUS_LARGE_CHANCE = 0.01
XP_BONUS_SMALL_RANGE = (8, 20)
XP_BONUS_LARGE_RANGE = (40, 90)
XP_BOOST_ROD_CHANCE = 0.007
XP_BOOST_ROD_CATCHES = 5
ARTIFACT_CHANCE = 0.15

# Quarter boundary dates for seasonal reset scheduling
QUARTER_STARTS = [(1, 1), (4, 1), (7, 1), (10, 1)]  # month, day


def _next_quarter_start(now: datetime) -> datetime:
    """Return the next quarter boundary datetime after `now`."""
    for month, day in QUARTER_STARTS:
        candidate = datetime(now.year, month, day, tzinfo=UTC)
        if candidate > now:
            return candidate
    return datetime(now.year + 1, 1, 1, tzinfo=UTC)


def _compute_reset_season(reset_date: Optional[datetime] = None) -> str:
    """Compute the concluded season label from a reset date.

    A reset on Jan 1 concludes Q4 of the previous year.
    A reset on Apr 1 concludes Q1.
    A reset on Jul 1 concludes Q2.
    A reset on Oct 1 concludes Q3.
    """
    if reset_date is None:
        reset_date = datetime.now(UTC)
    month = reset_date.month
    year = reset_date.year
    if month == 1:
        return f"Q4 {year - 1}"
    elif month == 4:
        return f"Q1 {year}"
    elif month == 7:
        return f"Q2 {year}"
    elif month == 10:
        return f"Q3 {year}"
    # Fallback — should not occur if called at a quarter boundary
    return f"Q? {year}"


def setup(bot: Any) -> 'Fishing':
    return Fishing(bot)




# Fishing config loaded from JSON
def _load_fishing_config() -> Dict[str, Any]:
    """Load fishing configuration from JSON config file."""
    config_path = os.path.join(os.path.dirname(__file__), "..", "config", "fish_database.json")
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        # Fallback to empty dict if file doesn't exist or is invalid
        print(f"Warning: Could not load fishing config from {config_path}: {e}")
        return {}

_FISHING_CONFIG = _load_fishing_config()

# Extract config sections with fallbacks
LOCATIONS: List[Dict[str, Any]] = _FISHING_CONFIG.get("locations", [])
JUNK_ITEMS: Dict[str, List[str]] = _FISHING_CONFIG.get("junk_items", {})
EVENTS: Dict[str, Dict[str, Any]] = _FISHING_CONFIG.get("events", {})
ARTIFACTS: List[Dict[str, Any]] = _FISHING_CONFIG.get("artifacts", [])
RARITY_WEIGHTS: Dict[str, int] = _FISHING_CONFIG.get("rarity_weights", {})
RARITY_XP_MULTIPLIER: Dict[str, int] = _FISHING_CONFIG.get("rarity_xp_multiplier", {})
REAL_FACTS: List[str] = _FISHING_CONFIG.get("real_facts", [])
CAST_MESSAGES: List[str] = _FISHING_CONFIG.get("cast_messages", [])
TOO_EARLY_MESSAGES: List[str] = _FISHING_CONFIG.get("too_early_messages", [])
DANGER_ZONE_MESSAGES: Dict[str, List[str]] = _FISHING_CONFIG.get("danger_zone_messages", {})

# Build fish database from remaining top-level keys (exclude config metadata)
_CONFIG_KEYS = {
    "locations", "junk_items", "events", "artifacts",
    "rarity_weights", "rarity_xp_multiplier", "real_facts",
    "cast_messages", "too_early_messages", "danger_zone_messages",
}
FISH_DATABASE: Dict[str, List[Dict[str, Any]]] = {
    k: v for k, v in _FISHING_CONFIG.items() if k not in _CONFIG_KEYS
}

class Fishing(SimpleCommandModule):
    name = "fishing"
    version = "1.0.0"
    description = "A fishing mini-game with locations, leveling, and rare catches."

    # Time thresholds in hours
    MIN_WAIT_HOURS = 1.0
    OPTIMAL_WAIT_HOURS = 24.0
    DANGER_THRESHOLD_HOURS = 24.0
    MAX_DANGER_HOURS = 48.0

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

        # Initialize state
        if not self.get_state("active_casts"):
            self.set_state("active_casts", {})
        if not self.get_state("players"):
            self.set_state("players", {})
        if not self.get_state("active_event"):
            self.set_state("active_event", None)
        if self.get_state("chum_state") is None:
            self.set_state("chum_state", None)
        self.save_state()

    def _schedule_next_reset(self) -> None:
        """Cancel any existing reset jobs and schedule the next quarterly reset at midnight UTC."""
        for job in schedule.get_jobs():
            if any(tag.startswith(f"{self.name}-") for tag in job.tags):
                schedule.cancel_job(job)

        now = datetime.now(UTC)
        next_reset = _next_quarter_start(now)

        seconds_until = (next_reset - now).total_seconds()
        (
            schedule.every(seconds_until)
            .seconds
            .do(self._reset_and_reschedule)
            .tag(f"{self.name}-season-reset")
        )

    def _reset_and_reschedule(self):
        """Fire the seasonal reset then schedule the next one. Returns CancelJob to stop repeating."""
        try:
            self._run_season_reset()
        except Exception as e:
            self.log_debug(f"Seasonal reset failed: {e}")
        finally:
            self._schedule_next_reset()
        return schedule.CancelJob

    def on_load(self) -> None:
        super().on_load()
        self._schedule_next_reset()

    def on_unload(self) -> None:
        super().on_unload()
        for job in schedule.get_jobs():
            if any(tag.startswith(f"{self.name}-") for tag in job.tags):
                schedule.cancel_job(job)

    def house_status(self, channel: str = None) -> str:
        players = self.get_state("players", {})
        active_casts = self.get_state("active_casts", {})
        champions = self.get_state("fishing_champions", {})

        parts = []
        season = champions.get("season")
        if season:
            parts.append(f"season {season}")
        if isinstance(players, dict) and players:
            parts.append(f"{len(players)} fishers")
        if isinstance(active_casts, dict) and active_casts:
            parts.append(f"{len(active_casts)} lines out")
        if not parts:
            return ""
        return "Fishing: " + ", ".join(parts) + "."

    def welcome_summary(self, channel: str = None) -> str:
        return "Fish with !cast and !reel; see !fishing, !fishing top, and !fishing champions."

    def contextual_hint(self, msg: str, username: str, channel: str) -> Optional[str]:
        if re.search(r"\b(fish|fishing|reel|cast)\b", msg, re.IGNORECASE):
            return "Fishing starts with !cast. Come back later and use !reel."
        return None

    def _register_commands(self) -> None:
        self.register_command(
            r'^\s*!cast(?:\s+(.+))?\s*$',
            self._cmd_cast,
            name="cast",
            description="Cast your fishing line (optionally specify location)"
        )
        self.register_command(
            r'^\s*!reel\s*$',
            self._cmd_reel,
            name="reel",
            description="Reel in your catch"
        )
        self.register_command(
            r'^\s*!fish(?:ing|stats)?(?:\s+(\S+))?\s*$',
            self._cmd_fishing_stats,
            name="fishing",
            description="Show your (or another user's) fishing statistics"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+top\s*$',
            self._cmd_fishing_top,
            name="fishing top",
            description="Show fishing leaderboards"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+champions?\s*$',
            self._cmd_fishing_champions,
            name="fishing champions",
            description="Show current fishing champions and their winning stats"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+location\s*$',
            self._cmd_fishing_location,
            name="fishing location",
            description="Show your current fishing location"
        )
        self.register_command(
            r'^\s*!fishinfo(?:\s+(.+))?\s*$',
            self._cmd_fishinfo,
            name="fishinfo",
            description="Show fish caught in a specific location"
        )
        self.register_command(
            r'^\s*!aquarium\s*$',
            self._cmd_aquarium,
            name="aquarium",
            description="Show your rare and legendary catches"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+help\s*$',
            self._cmd_fishing_help,
            name="fishing help",
            description="Show fishing help"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+bless\s+(\S+)\s*$',
            self._cmd_fishing_bless,
            name="fishing bless",
            admin_only=True,
            description="[Admin] Guarantee a user's next catch is rare or legendary"
        )
        self.register_command(
            r'^\s*!lure\s*$',
            self._cmd_lure,
            name="lure",
            description="Spend 30 XP to rig a mystery lure (rarity or size boost)"
        )
        self.register_command(
            r'^\s*!chum\s*$',
            self._cmd_chum,
            name="chum",
            description="Spend 250 XP to chum the water, boosting fish size for everyone for 20 minutes"
        )
        self.register_command(
            r'^\s*!discard\s*$',
            self._cmd_discard,
            name="discard",
            description="Discard your current fishing artifact"
        )
        self.register_command(
            r'^\s*!water\s*$',
            self._cmd_water,
            name="water",
            description="..."
        )
        self.register_command(
            r'^\s*!dynamite\s*$',
            self._cmd_dynamite,
            name="dynamite",
            description="A risky gambit. What could possibly go wrong?"
        )

    def _get_player(self, user_id: str) -> Dict[str, Any]:
        """Get or create a player record."""
        players = self.get_state("players", {})
        if user_id not in players:
            players[user_id] = {
                "level": 0,
                "xp": 0,
                "total_fish": 0,
                "biggest_fish": 0.0,
                "biggest_fish_name": None,
                "total_casts": 0,
                "furthest_cast": 0.0,
                "lines_broken": 0,
                "junk_collected": 0,
                "catches": {},
                "catches_by_location": {},  # {"location_name": {"fish_name": count}}
                "rare_catches": [],
                "locations_fished": [],
                "xp_boost_catches": 0,
                "force_rare_legendary": False,
                "artifact": None,
                "junk_curse_date": None,
                "active_lure": None,
                "dynamite_banned_until": None,
            }
            self.set_state("players", players)
            self.save_state()
        return players[user_id]

    def _save_player(self, user_id: str, player: Dict[str, Any]) -> None:
        """Save a player record."""
        players = self.get_state("players", {})
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

    @staticmethod
    def _compute_season_champions(players: Dict[str, Any]) -> Dict[str, Any]:
        """Compute the three season champions from player data. Pure function."""
        def best(key_fn, filter_fn=None):
            candidates = [(uid, p) for uid, p in players.items() if filter_fn is None or filter_fn(p)]
            if not candidates:
                return None
            return max(candidates, key=lambda x: (key_fn(x[1]), x[1].get("total_fish", 0)))[0]

        return {
            "traveler": best(lambda p: p.get("level", 0), lambda p: p.get("level", 0) > 0),
            "caster": best(lambda p: p.get("furthest_cast", 0.0), lambda p: p.get("furthest_cast", 0.0) > 0),
            "collector": best(lambda p: len(p.get("rare_catches", [])), lambda p: len(p.get("rare_catches", [])) > 0),
        }

    def _get_champion_bonuses(self, user_id: str) -> Dict[str, float]:
        """Return active champion bonuses for a user. All values 0.0 if not a champion."""
        champions = self.get_state("fishing_champions", {})
        return {
            "xp": 0.20 if champions.get("traveler") == user_id else 0.0,
            "distance": 0.20 if champions.get("caster") == user_id else 0.0,
            "rarity": 0.20 if champions.get("collector") == user_id else 0.0,
        }

    def get_fishing_suffix_for_user(self, user_id: str) -> str:
        """Return champion title suffix for display in title_for(). Empty string if none."""
        champions = self.get_state("fishing_champions", {})
        parts = []
        if champions.get("traveler") == user_id:
            parts.append("the Traveler")
        if champions.get("caster") == user_id:
            parts.append("the Caster")
        if champions.get("collector") == user_id:
            parts.append("the Collector")
        return " ".join(parts)

    def _get_location_for_level(self, level: int) -> Dict[str, Any]:
        """Get the location a player can fish at based on their level."""
        # Player fishes at their max unlocked location
        for loc in reversed(LOCATIONS):
            if loc["level"] <= level:
                return loc
        return LOCATIONS[0]

    def _find_location_by_name(self, location_query: str) -> Optional[Dict[str, Any]]:
        """Find a location by name (case-insensitive, supports partial matches)."""
        query = location_query.strip().lower()
        
        # Try exact match first
        for loc in LOCATIONS:
            if loc["name"].lower() == query:
                return loc
        
        # Try partial match
        for loc in LOCATIONS:
            if query in loc["name"].lower():
                return loc
        
        return None

    def _location_prep(self, location: Dict[str, Any]) -> str:
        """Return a grammatically correct prepositional phrase for a location."""
        name = location["name"]
        loc_type = location.get("type", "terrestrial")
        if loc_type == "space":
            if name == "The Void":
                return "into The Void"
            if name == "Moon":
                return "toward the Moon"
            return f"toward {name}"
        return f"into the {name}"

    def _get_xp_for_level(self, level: int) -> int:
        """Calculate XP needed for a level."""
        return int(100 * ((level + 1) ** 1.5))

    def _check_level_up(self, user_id: str, player: Dict[str, Any], username: str) -> Optional[int]:
        """Check if player leveled up, return new level if so."""
        current_level = player["level"]
        xp = player["xp"]

        while current_level < 9:  # Max level is 9
            xp_needed = self._get_xp_for_level(current_level)
            if xp >= xp_needed:
                xp -= xp_needed
                current_level += 1
            else:
                break

        if current_level > player["level"]:
            player["level"] = current_level
            player["xp"] = xp
            self._save_player(user_id, player)
            # Record achievement progress
            achievement_hooks.record_fishing_level(self.bot, username, current_level)
            return current_level

        player["xp"] = xp
        return None

    @staticmethod
    def _get_cast_distance(level: int, location: Dict[str, Any], artifact_bonus: float = 0.0, champion_bonus: float = 0.0) -> float:
        """Generate a random cast distance based on level and location."""
        max_dist = location["max_distance"]
        min_dist = max_dist * 0.3
        level_bonus = (level / 9) * 0.3
        base_max = max_dist * (0.7 + level_bonus)
        distance = random.uniform(min_dist, base_max)
        # Apply artifact distance bonus
        distance *= (1.0 + artifact_bonus)
        distance *= (1.0 + champion_bonus)
        return round(distance, 1)

    def _select_rarity(self, wait_hours: float, event: Optional[Dict[str, Any]] = None, artifact_rarity_boost: float = 0.0, champion_rarity_boost: float = 0.0, lure_rarity_boost: float = 0.0) -> str:
        """Select a rarity tier based on wait time, active events, and artifact bonuses."""
        weights = RARITY_WEIGHTS.copy()

        # Adjust weights based on wait time
        # < 6 hours: only common really
        # 6-12: uncommon possible
        # 12-18: rare possible
        # 18-24: legendary possible

        if wait_hours < 6:
            weights["uncommon"] = 5
            weights["rare"] = 0
            weights["legendary"] = 0
        elif wait_hours < 12:
            weights["rare"] = 2
            weights["legendary"] = 0
        elif wait_hours < 18:
            weights["legendary"] = 0
        # else: full weights at 18+ hours

        # Apply event bonuses
        if event and event.get("effect") == "rare_boost":
            weights["rare"] = int(weights["rare"] * event.get("multiplier", 1))
            weights["legendary"] = int(weights["legendary"] * event.get("multiplier", 1))

        # Apply artifact rarity boost
        if artifact_rarity_boost > 0:
            common_reduction = weights["common"] * artifact_rarity_boost
            weights["common"] = max(1, int(weights["common"] - common_reduction))
            weights["rare"] = int(weights["rare"] + common_reduction * 0.6)
            weights["legendary"] = int(weights["legendary"] + common_reduction * 0.4)

        # Apply champion rarity boost (same logic as artifact boost)
        if champion_rarity_boost > 0:
            common_reduction = weights["common"] * champion_rarity_boost
            weights["common"] = max(1, int(weights["common"] - common_reduction))
            weights["rare"] = int(weights["rare"] + common_reduction * 0.6)
            weights["legendary"] = int(weights["legendary"] + common_reduction * 0.4)

        # Apply lure rarity boost (same logic as artifact/champion boost)
        if lure_rarity_boost > 0:
            common_reduction = weights["common"] * lure_rarity_boost
            weights["common"] = max(1, int(weights["common"] - common_reduction))
            weights["rare"] = int(weights["rare"] + common_reduction * 0.6)
            weights["legendary"] = int(weights["legendary"] + common_reduction * 0.4)

        # Weighted random selection
        total = sum(weights.values())
        roll = random.randint(1, total)
        cumulative = 0
        for rarity, weight in weights.items():
            cumulative += weight
            if roll <= cumulative:
                return rarity
        return "common"

    def _select_fish(
        self,
        location: str,
        rarity: str,
        eligible_locations: Optional[List[str]] = None,
        allow_fallback: bool = True,
    ) -> Optional[Dict[str, Any]]:
        """Select a fish from the eligible location pools matching the rarity."""
        if eligible_locations:
            fish_pool = []
            for loc_name in eligible_locations:
                fish_pool.extend(FISH_DATABASE.get(loc_name, []))
        else:
            fish_pool = FISH_DATABASE.get(location, [])
        matching = [f for f in fish_pool if f["rarity"] == rarity]
        if not matching and allow_fallback:
            # Fall back to common if no fish of that rarity
            matching = [f for f in fish_pool if f["rarity"] == "common"]
        if not matching:
            return None
        return random.choice(matching)

    def _calculate_weight(self, fish: Dict[str, Any], wait_hours: float) -> float:
        """Calculate actual fish weight based on wait time."""
        min_w = fish["min_weight"]
        max_w = fish["max_weight"]

        # Weight scales with wait time up to 24 hours
        time_factor = min(wait_hours / self.OPTIMAL_WAIT_HOURS, 1.0)

        # Random variance within the range, biased by time factor
        base_weight = min_w + (max_w - min_w) * time_factor
        variance = (max_w - min_w) * 0.2  # 20% variance
        weight = base_weight + random.uniform(-variance, variance)

        return round(max(min_w, min(max_w, weight)), 2)

    def _get_junk(self, location_type: str) -> str:
        """Get a random junk item."""
        items = JUNK_ITEMS.get(location_type, JUNK_ITEMS["terrestrial"])
        return random.choice(items)

    def _check_event_trigger(self, channel: str, location: str) -> Optional[Dict[str, Any]]:
        """5% chance to trigger a random event on cast."""
        if random.random() > 0.05:
            return None

        # Select a random event
        available_events = []
        for event_id, event in EVENTS.items():
            # Check if event is location-restricted
            if "locations" in event and location not in event["locations"]:
                continue
            available_events.append((event_id, event))

        if not available_events:
            return None

        event_id, event = random.choice(available_events)
        expires = datetime.now(UTC) + timedelta(minutes=event["duration_minutes"])

        active_event = {
            "type": event_id,
            "name": event["name"],
            "description": event["description"],
            "effect": event.get("effect"),
            "multiplier": event.get("multiplier", 1.0),
            "expires": expires.isoformat(),
            "announced_channels": [channel],
        }

        self.set_state("active_event", active_event)
        self.save_state()

        return active_event

    def _get_active_event(self, location: str) -> Optional[Dict[str, Any]]:
        """Get the currently active event if any and valid for location."""
        event = self.get_state("active_event")
        if not event:
            return None

        # Check if expired
        expires = datetime.fromisoformat(event["expires"])
        if datetime.now(UTC) >= expires:
            self.set_state("active_event", None)
            self.save_state()
            return None

        # Check location restriction
        event_data = EVENTS.get(event["type"], {})
        if "locations" in event_data and location not in event_data["locations"]:
            return None

        return event

    def _cmd_cast(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        active_casts = self.get_state("active_casts", {})

        # Check if already has active cast
        if user_id in active_casts:
            cast = active_casts[user_id]
            cast_time = datetime.fromisoformat(cast["timestamp"])
            elapsed = datetime.now(UTC) - cast_time
            hours = elapsed.total_seconds() / 3600
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you already have a line in the water at {cast['location']}! "
                f"It's been {hours:.1f} hours. Use !reel to bring it in."
            )
            return True

        player = self._get_player(user_id)

        # Check dynamite ban
        banned_until = player.get("dynamite_banned_until")
        if banned_until:
            ban_dt = datetime.fromisoformat(banned_until)
            if datetime.now(UTC) < ban_dt:
                days_left = (ban_dt - datetime.now(UTC)).days + 1
                stump_messages = [
                    f"{self.bot.title_for(username)} stares at the fishing hole wistfully, "
                    f"wiggling the stump where their hand used to be. ({days_left} day(s) remaining on the ban)",
                    f"{self.bot.title_for(username)} gazes longingly at the water, "
                    f"a single tear rolling down their cheek. The stump itches. ({days_left} day(s) remaining)",
                    f"{self.bot.title_for(username)} approaches the water's edge, holds up the stump "
                    f"in quiet contemplation, and shuffles back home. ({days_left} day(s) remaining)",
                    f"{self.bot.title_for(username)} tries to grip a rod with the stump. "
                    f"It doesn't work. It never works. ({days_left} day(s) remaining)",
                ]
                self.safe_reply(connection, event, random.choice(stump_messages))
                return True
            else:
                player["dynamite_banned_until"] = None
                self._save_player(user_id, player)

        # Check if location argument was provided
        location_arg = match.group(1)
        if location_arg:
            # Try to find the requested location
            requested_location = self._find_location_by_name(location_arg)
            
            if not requested_location:
                # List all available locations
                available_locs = [l["name"] for l in LOCATIONS if l["level"] <= player["level"]]
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)}, location '{location_arg}' not found. "
                    f"Available locations: {', '.join(available_locs)}"
                )
                return True
            
            # Check if player has unlocked this location
            if requested_location["level"] > player["level"]:
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)}, you haven't unlocked {requested_location['name']} yet! "
                    f"You need to be level {requested_location['level']} (currently level {player['level']})."
                )
                return True
            
            location = requested_location
        else:
            # No location specified, use current level's default location
            location = self._get_location_for_level(player["level"])
        
        # Apply artifact distance bonus if applicable
        artifact = player.get("artifact")
        artifact_distance_bonus = 0.0
        if artifact and artifact.get("bonus_type") == "distance":
            artifact_distance_bonus = artifact.get("bonus_value", 0.0)
        champion_bonuses = self._get_champion_bonuses(user_id)
        distance = self._get_cast_distance(player["level"], location, artifact_distance_bonus, champion_bonuses["distance"])

        # Record the cast
        active_casts[user_id] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "distance": distance,
            "location": location["name"],
            "channel": event.target,
            "allow_lower_fish": not location_arg,
        }
        self.set_state("active_casts", active_casts)

        # Update player stats
        player["total_casts"] += 1
        if distance > player["furthest_cast"]:
            player["furthest_cast"] = distance
        self._save_player(user_id, player)

        # Check for event trigger
        triggered_event = self._check_event_trigger(event.target, location["name"])

        # Send cast message
        if artifact:
            cast_msg = (
                f"{artifact['cast_text']}, it sails {distance}m {self._location_prep(location)}, "
                f"{artifact['float_text']}..."
            )
        else:
            cast_msg = random.choice(CAST_MESSAGES).format(
                distance=distance,
                loc=self._location_prep(location)
            )
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cast_msg}")

        # Announce event if triggered
        if triggered_event:
            self.safe_say(
                f"** {triggered_event['name']} ** - {triggered_event['description']}",
                target=event.target
            )

        return True

    def _cmd_reel(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        active_casts = self.get_state("active_casts", {})

        # Check if has active cast
        if user_id not in active_casts:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you don't have a line in the water. Use !cast first."
            )
            return True

        cast = active_casts[user_id]
        cast_time = datetime.fromisoformat(cast["timestamp"])
        now = datetime.now(UTC)
        elapsed = now - cast_time
        wait_hours = elapsed.total_seconds() / 3600

        location_name = cast["location"]
        location = next((l for l in LOCATIONS if l["name"] == location_name), LOCATIONS[0])
        player = self._get_player(user_id)
        forced_rare_flag = player.get("force_rare_legendary", False)

        # Remove the cast
        del active_casts[user_id]
        self.set_state("active_casts", active_casts)
        self.save_state()

        # Get active event
        active_event = self._get_active_event(location_name)

        # Apply time boost event if active
        effective_wait = wait_hours
        if active_event and active_event.get("effect") == "time_boost":
            effective_wait = wait_hours / active_event.get("multiplier", 1.0)

        # Too early - nothing caught
        if effective_wait < self.MIN_WAIT_HOURS:
            self.safe_reply(connection, event, random.choice(TOO_EARLY_MESSAGES))
            return True

        # Danger zone - chance of bad outcome
        if wait_hours > self.DANGER_THRESHOLD_HOURS and not forced_rare_flag:
            hours_over = wait_hours - self.DANGER_THRESHOLD_HOURS
            bad_chance = min(0.1 + (hours_over * 0.05), 0.9)

            if random.random() < bad_chance:
                # Bad outcome
                bad_type = random.choice(["line_break", "fish_escaped", "junk"])

                if bad_type == "line_break":
                    player["lines_broken"] += 1
                    self._save_player(user_id, player)
                    achievement_hooks.record_achievement(self.bot, username, "lines_broken", 1)
                    self.safe_reply(
                        connection, event,
                        random.choice(DANGER_ZONE_MESSAGES["line_break"])
                    )
                elif bad_type == "fish_escaped":
                    self.safe_reply(
                        connection, event,
                        random.choice(DANGER_ZONE_MESSAGES["fish_escaped"])
                    )
                else:  # junk
                    junk = self._get_junk(location["type"])
                    player["junk_collected"] += 1
                    self._save_player(user_id, player)
                    achievement_hooks.record_achievement(self.bot, username, "junk_collected", 1)
                    self.safe_reply(
                        connection, event,
                        f"After waiting {wait_hours:.1f} hours, you reel in... {junk}. "
                        "Maybe don't leave your line out so long next time."
                    )
                return True

        # Junk curse check — !water punishment, bypasses all protections
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        if player.get("junk_curse_date") == today:
            junk = self._get_junk(location["type"])
            player["junk_collected"] += 1
            self._save_player(user_id, player)
            achievement_hooks.record_achievement(self.bot, username, "junk_collected", 1)
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)} reels in... {junk}. The curse holds."
            )
            return True

        # Junk check (base chance, boosted by murky waters)
        if not forced_rare_flag:
            junk_chance = 0.10
            if active_event and active_event.get("effect") == "junk_boost":
                junk_chance *= active_event.get("multiplier", 1.0)
            # Apply artifact junk shield
            artifact = player.get("artifact")
            if artifact and artifact.get("bonus_type") == "junk_shield":
                junk_chance *= (1.0 - artifact.get("bonus_value", 0.0))

            if random.random() < junk_chance:
                # Chance for artifact instead of junk
                if random.random() < ARTIFACT_CHANCE:
                    new_artifact = random.choice(ARTIFACTS)
                    old_artifact = player.get("artifact")
                    player["artifact"] = new_artifact.copy()
                    self._save_player(user_id, player)
                    response = (
                        f"{self.bot.title_for(username)} reels in... wait, something else is tangled in the line! "
                        f"You found the {new_artifact['name']}! Your casts will never be the same."
                    )
                    if old_artifact:
                        response += f" (Replaced: {old_artifact['name']})"
                    self.safe_reply(connection, event, response)
                    return True
                junk = self._get_junk(location["type"])
                player["junk_collected"] += 1
                self._save_player(user_id, player)
                achievement_hooks.record_achievement(self.bot, username, "junk_collected", 1)
                xp_gain = 5  # Small XP for junk
                player["xp"] += xp_gain
                self._save_player(user_id, player)
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)} reels in... {junk}. "
                    f"Well, at least you're cleaning up! (+{xp_gain} XP)"
                )
                return True

        # Successful catch!
        lure_type = None
        if player.get("active_lure"):
            lure_type = player["active_lure"]["type"]

        artifact = player.get("artifact")
        artifact_rarity_boost = 0.0
        if artifact and artifact.get("bonus_type") == "rarity":
            artifact_rarity_boost = artifact.get("bonus_value", 0.0)
        champion_bonuses = self._get_champion_bonuses(user_id)
        lure_rarity_boost = 0.40 if lure_type == "rarity" else 0.0
        rarity = self._select_rarity(effective_wait, active_event, artifact_rarity_boost, champion_bonuses["rarity"], lure_rarity_boost)
        eligible_locations = None
        if cast.get("allow_lower_fish"):
            eligible_locations = [l["name"] for l in LOCATIONS if l["level"] <= player["level"]]
        fish = None
        forced_rare = player.get("force_rare_legendary", False)
        forced_rare_applied = False
        if forced_rare:
            forced_rarities = ["rare", "legendary"]
            random.shuffle(forced_rarities)
            for forced in forced_rarities:
                fish = self._select_fish(
                    location_name,
                    forced,
                    eligible_locations,
                    allow_fallback=False,
                )
                if fish:
                    rarity = forced
                    forced_rare_applied = True
                    break

        if not fish:
            fish = self._select_fish(location_name, rarity, eligible_locations)

        if not fish:
            # Fallback - shouldn't happen
            self.safe_reply(connection, event, "The fish got away at the last moment!")
            return True

        weight = self._calculate_weight(fish, effective_wait)

        # Apply size lure boost
        if lure_type == "size":
            weight = round(weight * 1.30, 2)

        # Apply chum boost
        chum_active = False
        chum_state = self.get_state("chum_state")
        if chum_state:
            chum_expires = datetime.fromisoformat(chum_state["expires"])
            if datetime.utcnow() < chum_expires:
                weight = round(weight * 1.40, 2)
                chum_active = True
            elif datetime.utcnow() >= datetime.fromisoformat(chum_state["cooldown_until"]):
                self.set_state("chum_state", None)
                self.save_state()

        # Line break check - bigger fish = higher chance
        if not forced_rare_applied:
            break_chance = 0.02 + (weight / 1000) * 0.15
            if random.random() < break_chance:
                player["lines_broken"] += 1
                self._save_player(user_id, player)
                achievement_hooks.record_achievement(self.bot, username, "lines_broken", 1)
                self.safe_reply(
                    connection, event,
                    f"You feel a massive tug - it's a {fish['name']}! But the weight is too much... "
                    f"SNAP! The line breaks! It got away..."
                )
                return True

        # Successful catch!
        player["total_fish"] += 1
        if weight > player["biggest_fish"]:
            player["biggest_fish"] = weight
            player["biggest_fish_name"] = fish["name"]

        if forced_rare_applied:
            player["force_rare_legendary"] = False

        # Track catches (global)
        catches = player.get("catches", {})
        catches[fish["name"]] = catches.get(fish["name"], 0) + 1
        player["catches"] = catches

        # Track catches by location
        catches_by_location = player.get("catches_by_location", {})
        if location_name not in catches_by_location:
            catches_by_location[location_name] = {}
        catches_by_location[location_name][fish["name"]] = catches_by_location[location_name].get(fish["name"], 0) + 1
        player["catches_by_location"] = catches_by_location

        # Track location
        if location_name not in player.get("locations_fished", []):
            player.setdefault("locations_fished", []).append(location_name)

        # Track rare/legendary for aquarium
        if rarity in ("rare", "legendary"):
            rare_catches = player.get("rare_catches", [])
            rare_catches.append({
                "name": fish["name"],
                "weight": weight,
                "rarity": rarity,
                "location": location_name,
                "caught_at": now.isoformat(),
            })
            player["rare_catches"] = rare_catches

        # Calculate XP
        base_xp = 10
        rarity_mult = RARITY_XP_MULTIPLIER.get(rarity, 1)
        weight_bonus = 1 + (weight / 50)
        xp_gain = int(base_xp * rarity_mult * weight_bonus)

        # Event XP boost
        if active_event and active_event.get("effect") == "xp_boost":
            xp_gain = int(xp_gain * active_event.get("multiplier", 1.0))

        # Artifact XP boost
        artifact = player.get("artifact")
        if artifact and artifact.get("bonus_type") == "xp":
            xp_gain = int(xp_gain * (1.0 + artifact.get("bonus_value", 0.0)))

        bonus_messages = []
        boost_catches = player.get("xp_boost_catches", 0)
        if boost_catches > 0:
            xp_gain = int(xp_gain * XP_BOOST_MULTIPLIER)
            boost_catches -= 1
            player["xp_boost_catches"] = boost_catches
            bonus_messages.append(f"Rod boost! x{XP_BOOST_MULTIPLIER} XP.")
            if boost_catches == 0:
                bonus_messages.append("The rod's glow fades.")

        extra_xp = 0
        roll = random.random()
        if roll < XP_BONUS_LARGE_CHANCE:
            extra_xp = random.randint(*XP_BONUS_LARGE_RANGE)
            bonus_messages.append(f"Treasure haul! +{extra_xp} XP.")
        elif roll < XP_BONUS_LARGE_CHANCE + XP_BONUS_SMALL_CHANCE:
            extra_xp = random.randint(*XP_BONUS_SMALL_RANGE)
            bonus_messages.append(f"Lucky find! +{extra_xp} XP.")

        if player.get("xp_boost_catches", 0) == 0 and random.random() < XP_BOOST_ROD_CHANCE:
            player["xp_boost_catches"] = XP_BOOST_ROD_CATCHES
            bonus_messages.append(
                f"You found a better rod! Next {XP_BOOST_ROD_CATCHES} catches give double XP."
            )

        total_xp = xp_gain + extra_xp

        # Traveler champion XP bonus — reuse champion_bonuses fetched earlier
        if champion_bonuses["xp"] > 0:
            total_xp = int(total_xp * (1.0 + champion_bonuses["xp"]))
            bonus_messages.append("Traveler's blessing: +20% XP.")

        player["xp"] += total_xp
        self._save_player(user_id, player)

        # Record achievements
        achievement_hooks.record_achievement(self.bot, username, "fish_caught", 1)
        if rarity == "rare":
            achievement_hooks.record_achievement(self.bot, username, "rare_fish_caught", 1)
        elif rarity == "legendary":
            achievement_hooks.record_achievement(self.bot, username, "legendary_fish_caught", 1)

        # Perfect wait achievement (18-24 hours)
        if 18.0 <= wait_hours <= 24.0:
            achievement_hooks.record_achievement(self.bot, username, "perfect_waits", 1)

        # Consume lure on successful catch and build reveal text
        lure_reveal = ""
        if lure_type:
            player["active_lure"] = None
            self._save_player(user_id, player)
            if lure_type == "rarity":
                lure_reveal = " The rarity lure pays off!"
            else:
                lure_reveal = " The size lure pays off!"

        # Check level up
        new_level = self._check_level_up(user_id, player, username)

        # Build response
        rarity_prefix = ""
        if rarity == "uncommon":
            rarity_prefix = "an uncommon "
        elif rarity == "rare":
            rarity_prefix = "a RARE "
        elif rarity == "legendary":
            rarity_prefix = "a LEGENDARY "
        else:
            rarity_prefix = "a "

        response = (
            f"{self.bot.title_for(username)} reels in {rarity_prefix}{fish['name']} "
            f"weighing {weight:.2f} lbs after waiting {wait_hours:.1f} hours! (+{total_xp} XP)"
        )
        if bonus_messages:
            response += " " + " ".join(bonus_messages)
        if forced_rare_applied:
            response += " A rare blessing guides your catch."
        if lure_reveal:
            response += lure_reveal

        if new_level:
            new_location = self._get_location_for_level(new_level)
            response += f" LEVEL UP! You're now level {new_level} and can fish at {new_location['name']}!"

        self.safe_reply(connection, event, response)
        return True

    def _cmd_fishing_bless(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        target = match.group(1).strip()
        target_id = self.bot.get_user_id(target)
        player = self._get_player(target_id)
        player["force_rare_legendary"] = True
        self._save_player(target_id, player)

        self.safe_reply(
            connection,
            event,
            f"{self.bot.title_for(target)}, your next catch will be rare or legendary."
        )
        return True

    # ── Matrix admin integration ──────────────────────────────

    @property
    def matrix_admin_commands(self) -> dict:
        return {
            "!fish bless": (self._matrix_bless, "!fish bless <nick> — guarantee rare/legendary next catch"),
        }

    def _matrix_bless(self, args: str) -> str:
        nick = args.strip()
        if not nick:
            return "Usage: !fish bless <nick>"
        target_id = self.bot.get_user_id(nick)
        player = self._get_player(target_id)
        player["force_rare_legendary"] = True
        self._save_player(target_id, player)
        return f"Blessed {nick} — their next catch will be rare or legendary."

    def _cmd_fishing_stats(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)
        if target_nick:
            target_id = self.bot.get_user_id(target_nick)
            players = self.get_state("players", {})
            if target_id not in players:
                self.safe_reply(connection, event, f"{target_nick} hasn't gone fishing yet.")
                return True
            display_name = self.bot.title_for(target_nick)
        else:
            target_nick = username
            target_id = self.bot.get_user_id(username)
            display_name = self.bot.title_for(username)

        player = self._get_player(target_id)
        location = self._get_location_for_level(player["level"])

        xp_needed = self._get_xp_for_level(player["level"])
        xp_progress = f"{player['xp']}/{xp_needed}"

        stats = (
            f"Fishing Stats for {display_name}: "
            f"Level {player['level']} ({location['name']}) | "
            f"XP: {xp_progress} | "
            f"Fish: {player['total_fish']} | "
            f"Biggest: {player['biggest_fish']:.2f} lbs"
        )

        if player.get("biggest_fish_name"):
            stats += f" ({player['biggest_fish_name']})"

        stats += f" | Casts: {player['total_casts']} | Junk: {player['junk_collected']}"

        self.safe_reply(connection, event, stats)
        return True

    def _cmd_fishing_top(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        players = self.get_state("players", {})
        if not players:
            self.safe_reply(connection, event, "No one has gone fishing yet!")
            return True

        # Get user map for display names
        user_map = self.bot.get_module_state("users").get("user_map", {})

        # Top by total fish
        by_fish = sorted(
            [(uid, p) for uid, p in players.items() if p.get("total_fish", 0) > 0],
            key=lambda x: x[1]["total_fish"],
            reverse=True
        )[:5]

        # Top by biggest fish
        by_size = sorted(
            [(uid, p) for uid, p in players.items() if p.get("biggest_fish", 0) > 0],
            key=lambda x: x[1]["biggest_fish"],
            reverse=True
        )[:5]

        response_parts = ["Fishing Leaderboards:"]

        if by_fish:
            fish_list = []
            for i, (uid, p) in enumerate(by_fish):
                name = user_map.get(uid, {}).get("canonical_nick", "Unknown")
                fish_list.append(f"#{i+1} {name} ({p['total_fish']})")
            response_parts.append("Most Fish: " + ", ".join(fish_list))

        if by_size:
            size_list = []
            for i, (uid, p) in enumerate(by_size):
                name = user_map.get(uid, {}).get("canonical_nick", "Unknown")
                fish_name = p.get("biggest_fish_name", "fish")
                size_list.append(f"#{i+1} {name} ({p['biggest_fish']:.1f} lbs - {fish_name})")
            response_parts.append("Biggest Catch: " + ", ".join(size_list))

        self.safe_reply(connection, event, " | ".join(response_parts))
        return True

    def _cmd_fishing_champions(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        champions = self.get_state("fishing_champions", {})
        if not champions or not any(champions.get(k) for k in ("traveler", "caster", "collector")):
            self.safe_reply(
                connection, event,
                "No champions yet — the first champions will be crowned at the next season reset!"
            )
            return True

        season = champions.get("season", "?")
        players = self.get_state("players", {})
        user_map = self.bot.get_module_state("users").get("user_map", {})

        parts = [f"Fishing Champions ({season}):"]

        traveler_id = champions.get("traveler")
        if traveler_id:
            name = user_map.get(traveler_id, {}).get("canonical_nick", traveler_id)
            # Use snapshot stats if available, otherwise fall back to live player data
            snapshot_level = champions.get("traveler_level")
            level = snapshot_level if snapshot_level is not None else players.get(traveler_id, {}).get("level", 0)
            location = champions.get("traveler_location") or self._get_location_for_level(level)["name"]
            parts.append(f"the Traveler: {name} (level {level}, {location})")

        caster_id = champions.get("caster")
        if caster_id:
            name = user_map.get(caster_id, {}).get("canonical_nick", caster_id)
            snapshot_dist = champions.get("caster_distance")
            distance = snapshot_dist if snapshot_dist is not None else players.get(caster_id, {}).get("furthest_cast", 0.0)
            parts.append(f"the Caster: {name} ({distance:.1f}m)")

        collector_id = champions.get("collector")
        if collector_id:
            name = user_map.get(collector_id, {}).get("canonical_nick", collector_id)
            snapshot_count = champions.get("collector_count")
            count = snapshot_count if snapshot_count is not None else len(players.get(collector_id, {}).get("rare_catches", []))
            parts.append(f"the Collector: {name} ({count} rare/legendary catches)")

        self.safe_reply(connection, event, " | ".join(parts))
        return True

    def _run_season_reset(self, reset_season: Optional[str] = None) -> None:
        """Execute the seasonal reset: crown champions, announce, wipe player data."""
        if reset_season is None:
            reset_season = _compute_reset_season()

        players = self.get_state("players", {})
        user_map = self.bot.get_module_state("users").get("user_map", {})

        # Exclude configured nicks from championship consideration.
        # Managed via the "champion_excluded_nicks" state key (list of lowercase nicks).
        excluded_nicks = {n.lower() for n in self.get_state("champion_excluded_nicks", [])}
        excluded_ids = {
            uid for uid, info in user_map.items()
            if info.get("canonical_nick", "").lower() in excluded_nicks
        }
        eligible_players = {uid: p for uid, p in players.items() if uid not in excluded_ids}

        # Compute champions from eligible player data
        champion_ids = self._compute_season_champions(eligible_players)

        # Snapshot winning stats before wiping players
        champions = {
            "season": reset_season,
            "traveler": champion_ids["traveler"],
            "caster": champion_ids["caster"],
            "collector": champion_ids["collector"],
        }

        traveler_id = champion_ids["traveler"]
        if traveler_id and traveler_id in players:
            p = players[traveler_id]
            champions["traveler_level"] = p["level"]
            champions["traveler_location"] = self._get_location_for_level(p["level"])["name"]

        caster_id = champion_ids["caster"]
        if caster_id and caster_id in players:
            p = players[caster_id]
            champions["caster_distance"] = p["furthest_cast"]

        collector_id = champion_ids["collector"]
        if collector_id and collector_id in players:
            p = players[collector_id]
            champions["collector_count"] = len(p["rare_catches"])

        self.set_state("fishing_champions", champions)

        # Build announcement lines
        lines = [f"** SEASON RESET ** The sea has been cleared! {reset_season} champions:"]

        if traveler_id:
            name = user_map.get(traveler_id, {}).get("canonical_nick", traveler_id)
            loc_name = champions.get("traveler_location", "?")
            level = champions.get("traveler_level", 0)
            lines.append(
                f"the Traveler: {name} (reached {loc_name}, level {level}) "
                "— carries a +20% XP blessing into the new season"
            )
        else:
            lines.append("the Traveler: unclaimed (no one leveled up this season)")

        if caster_id:
            name = user_map.get(caster_id, {}).get("canonical_nick", caster_id)
            dist = champions.get("caster_distance", 0.0)
            lines.append(
                f"the Caster: {name} (cast {dist:.1f}m) "
                "— carries a +20% distance blessing"
            )
        else:
            lines.append("the Caster: unclaimed (no casts recorded this season)")

        if collector_id:
            name = user_map.get(collector_id, {}).get("canonical_nick", collector_id)
            count = champions.get("collector_count", 0)
            lines.append(
                f"the Collector: {name} ({count} rare/legendary catches) "
                "— carries a +20% rare blessing"
            )
        else:
            lines.append("the Collector: unclaimed (no rare catches this season)")

        lines.append("Good luck to all in the new season!")

        # Broadcast to all enabled channels
        channels = [ch for ch in self.bot.joined_channels if self.is_enabled(ch)]
        for channel in channels:
            for line in lines:
                self.safe_say(line, target=channel)

        # Wipe player data
        self.set_state("players", {})
        self.set_state("active_casts", {})
        self.set_state("active_event", None)
        self.save_state()

    def _cmd_fishing_location(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)
        current_loc = self._get_location_for_level(player["level"])

        # Check for active cast
        active_casts = self.get_state("active_casts", {})
        if user_id in active_casts:
            cast = active_casts[user_id]
            cast_time = datetime.fromisoformat(cast["timestamp"])
            elapsed = datetime.now(UTC) - cast_time
            hours = elapsed.total_seconds() / 3600
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}: Currently fishing at {cast['location']} "
                f"(line out for {hours:.1f} hours). Level {player['level']}."
            )
            return True

        # Build location progress
        unlocked = [l for l in LOCATIONS if l["level"] <= player["level"]]
        next_loc = next((l for l in LOCATIONS if l["level"] > player["level"]), None)

        response = (
            f"{self.bot.title_for(username)}: Level {player['level']}, "
            f"currently at {current_loc['name']}. "
            f"Unlocked: {', '.join(l['name'] for l in unlocked)}."
        )

        if next_loc:
            xp_needed = self._get_xp_for_level(player["level"])
            response += f" Next: {next_loc['name']} at level {next_loc['level']} ({player['xp']}/{xp_needed} XP)."

        self.safe_reply(connection, event, response)
        return True

    def _cmd_aquarium(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)
        rare_catches = player.get("rare_catches", [])

        if not rare_catches:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}'s aquarium is empty. "
                "Catch some rare or legendary fish to display them here!"
            )
            return True

        # Group by rarity
        legendaries = [c for c in rare_catches if c["rarity"] == "legendary"]
        rares = [c for c in rare_catches if c["rarity"] == "rare"]

        response_parts = [f"{self.bot.title_for(username)}'s Aquarium:"]

        if legendaries:
            leg_display = ", ".join(
                f"{c['name']} ({c['weight']:.1f} lbs)"
                for c in legendaries[-5:]  # Last 5
            )
            response_parts.append(f"LEGENDARY: {leg_display}")

        if rares:
            rare_display = ", ".join(
                f"{c['name']} ({c['weight']:.1f} lbs)"
                for c in rares[-5:]  # Last 5
            )
            response_parts.append(f"Rare: {rare_display}")

        self.safe_reply(connection, event, " | ".join(response_parts))
        return True

    def _cmd_fishinfo(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)

        # Get location argument
        location_arg = match.group(1)
        
        if not location_arg:
            # No location specified - show available locations
            locations_fished = player.get("locations_fished", [])
            if not locations_fished:
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)}, you haven't caught any fish yet! "
                    "Use !cast and !reel to start fishing."
                )
                return True
            
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, locations you've fished: {', '.join(locations_fished)}. "
                "Use !fishinfo <location> to see fish caught there."
            )
            return True
        
        # Find the location
        location = self._find_location_by_name(location_arg)
        if not location:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, location '{location_arg}' not found."
            )
            return True
        
        location_name = location["name"]
        
        # Get catches for this location
        catches_by_location = player.get("catches_by_location", {})
        location_catches = catches_by_location.get(location_name, {})
        
        if not location_catches:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you haven't caught any fish at {location_name} yet!"
            )
            return True
        
        # Get all fish available at this location for completion stats
        all_fish = FISH_DATABASE.get(location_name, [])
        total_species = len(all_fish)
        caught_species = len(location_catches)
        
        # Group by rarity
        caught_by_rarity = {"common": [], "uncommon": [], "rare": [], "legendary": []}
        for fish_name, count in location_catches.items():
            # Find the fish in the database to get its rarity
            fish_data = next((f for f in all_fish if f["name"] == fish_name), None)
            if fish_data:
                rarity = fish_data["rarity"]
                caught_by_rarity[rarity].append(f"{fish_name} ({count})")
        
        # Build response
        total_caught = sum(location_catches.values())
        response_parts = [
            f"{self.bot.title_for(username)}'s {location_name} catches: "
            f"{total_caught} fish, {caught_species}/{total_species} species"
        ]
        
        # Add fish by rarity
        for rarity in ["legendary", "rare", "uncommon", "common"]:
            if caught_by_rarity[rarity]:
                rarity_label = rarity.upper() if rarity in ["legendary", "rare"] else rarity.capitalize()
                fish_list = ", ".join(caught_by_rarity[rarity])
                response_parts.append(f"{rarity_label}: {fish_list}")
        
        # Send as multiple messages if too long
        full_response = " | ".join(response_parts)
        if len(full_response) > 400:
            # Send in parts
            self.safe_reply(connection, event, response_parts[0])
            for part in response_parts[1:]:
                self.safe_say(part, target=event.target)
        else:
            self.safe_reply(connection, event, full_response)
        
        return True

    def _cmd_fishing_help(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        help_lines = [
            "Fishing Commands:",
            "!cast - Cast at your current level (can catch fish from any unlocked lower levels)",
            "!cast <location> - Cast at a specific unlocked location (e.g., !cast pond)",
            "!reel - Reel in your catch (wait 1-24 hours for best results)",
            "!fishing - Show your stats",
            "!fishing top - Leaderboards",
            "!fishing champions - Show this year's title holders and their winning stats",
            "!fishing location - Current location and level progress",
            "!fishinfo - List locations you've fished",
            "!fishinfo <location> - Show fish caught at a specific location (e.g., !fishinfo pond)",
            "!aquarium - View your rare/legendary catches",
            "!discard - Discard your current artifact and return to normal casts",
            "!lure - Spend 30 XP to rig a mystery lure (one-catch bonus: rarity boost or size boost)",
            "!chum - Spend 250 XP to chum the water, boosting fish size for everyone for 20 minutes",
            "",
            "Tips: !cast pulls fish from your current level and any lower unlocked levels.",
            "You can also travel back to previous locations to hunt for rare fish you missed!",
            "Artifacts: Rare finds hidden among the junk! They change your cast style and grant small bonuses.",
        ]

        for line in help_lines:
            self.safe_privmsg(username, line)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, I've sent you the fishing guide."
        )
        return True

    def _cmd_lure(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)

        if player.get("active_lure") is not None:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you already have a lure rigged up!"
            )
            return True

        if player["xp"] < 30:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, not enough XP (need 30, have {player['xp']})."
            )
            return True

        player["xp"] -= 30
        lure_type = random.choice(["rarity", "size"])
        player["active_lure"] = {"type": lure_type}
        self._save_player(user_id, player)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)} spends 30 XP and rigs up a mystery lure. Let's see what it attracts!"
        )
        return True

    def _cmd_chum(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        chum_state = self.get_state("chum_state")

        if chum_state:
            now = datetime.utcnow()
            expires = datetime.fromisoformat(chum_state["expires"])
            cooldown_until = datetime.fromisoformat(chum_state["cooldown_until"])
            if now < expires:
                remaining = int((expires - now).total_seconds() / 60) + 1
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)}, the water is already chummed! {remaining} minute(s) remaining."
                )
                return True
            if now < cooldown_until:
                remaining = int((cooldown_until - now).total_seconds() / 60) + 1
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)}, the chum is on cooldown. {remaining} minute(s) until it can be used again."
                )
                return True

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)

        if player["xp"] < 250:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, not enough XP (need 250, have {player['xp']})."
            )
            return True

        player["xp"] -= 250
        self._save_player(user_id, player)

        now = datetime.utcnow()
        expires = now + timedelta(minutes=20)
        cooldown_until = now + timedelta(minutes=50)
        self.set_state("chum_state", {
            "expires": expires.isoformat(),
            "cooldown_until": cooldown_until.isoformat(),
            "activated_by": user_id,
            "activated_by_name": username,
        })
        self.save_state()

        display_name = self.bot.title_for(username)
        self.safe_say(
            f"{display_name} tosses a handful of chum into the water! "
            "Fish should be running large for the next 20 minutes!",
            target=event.target
        )
        return True

    def _cmd_discard(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)
        artifact = player.get("artifact")

        if not artifact:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you don't have an artifact to discard."
            )
            return True

        artifact_name = artifact["name"]
        player["artifact"] = None
        self._save_player(user_id, player)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)} tosses the {artifact_name} into the water. "
            "All bonuses lost. Your casts return to normal."
        )
        return True

    def _cmd_dynamite(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)

        # Check if already banned
        banned_until = player.get("dynamite_banned_until")
        if banned_until:
            ban_dt = datetime.fromisoformat(banned_until)
            if datetime.now(UTC) < ban_dt:
                days_left = (ban_dt - datetime.now(UTC)).days + 1
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)} reaches into the tackle box with the stump. "
                    f"There's no dynamite there. There's no hand either. ({days_left} day(s) remaining)"
                )
                return True
            else:
                player["dynamite_banned_until"] = None
                self._save_player(user_id, player)

        roll = random.random()

        # 10% — player thinks better of it
        if roll < 0.10:
            chicken_messages = [
                f"{self.bot.title_for(username)} pulls out the dynamite, stares at it for a long moment... "
                "and puts it back. Some decisions don't need to be made today. Goes to get a cup of tea.",
                f"{self.bot.title_for(username)} hefts the dynamite thoughtfully, then sets it gently on a rock. "
                "The tea is calling. The fish can wait.",
                f"{self.bot.title_for(username)} gets halfway through lighting the fuse before reconsidering. "
                "Honestly, a nice biscuit sounds better right now.",
                f"{self.bot.title_for(username)} holds the dynamite aloft dramatically... "
                "then pockets it and wanders off in search of a kettle.",
                f"{self.bot.title_for(username)} considers the dynamite. Considers the fish. "
                "Considers their own mortality. Decides tea is the wiser investment.",
            ]
            self.safe_reply(connection, event, random.choice(chicken_messages))
            return True

        # 20% — glorious success
        if roll < 0.30:
            # Calculate XP needed for two level-ups from current position
            temp_level = player["level"]
            temp_xp = player["xp"]
            xp_to_grant = 0
            levels_possible = 0
            while levels_possible < 2 and temp_level < 9:
                needed = self._get_xp_for_level(temp_level)
                xp_to_grant += max(0, needed - temp_xp)
                temp_xp = 0
                temp_level += 1
                levels_possible += 1
            xp_to_grant += random.randint(80, 200)  # extra for good measure

            # Grant a haul of rare/legendary fish
            eligible_locations = [l["name"] for l in LOCATIONS if l["level"] <= player["level"]]
            haul = []
            haul_count = random.randint(3, 6)
            now = datetime.now(UTC)
            for _ in range(haul_count):
                rarity = random.choice(["rare", "rare", "legendary"])
                fish = self._select_fish(
                    eligible_locations[-1] if eligible_locations else "Puddle",
                    rarity,
                    eligible_locations if eligible_locations else None,
                    allow_fallback=True,
                )
                if fish:
                    weight = round(random.uniform(fish["max_weight"] * 0.7, fish["max_weight"]), 2)
                    haul.append((fish, rarity, weight))
                    # Add to player records
                    catches = player.get("catches", {})
                    catches[fish["name"]] = catches.get(fish["name"], 0) + 1
                    player["catches"] = catches
                    player["total_fish"] = player.get("total_fish", 0) + 1
                    if weight > player.get("biggest_fish", 0.0):
                        player["biggest_fish"] = weight
                        player["biggest_fish_name"] = fish["name"]
                    rare_catches = player.get("rare_catches", [])
                    rare_catches.append({
                        "name": fish["name"],
                        "weight": weight,
                        "rarity": rarity,
                        "location": eligible_locations[-1] if eligible_locations else "Puddle",
                        "caught_at": now.isoformat(),
                    })
                    player["rare_catches"] = rare_catches

            player["xp"] = player.get("xp", 0) + xp_to_grant
            self._save_player(user_id, player)

            new_level = self._check_level_up(user_id, player, username)

            haul_str = ", ".join(
                f"{fish['name']} ({weight:.1f} lbs, {rarity})"
                for fish, rarity, weight in haul
            ) if haul else "an eerie silence"

            boom_lines = [
                f"💥 KABOOM! 💥 {self.bot.title_for(username)} hurls the dynamite into the fishing hole! "
                f"The water ERUPTS. Fish rain from the sky. Locals flee. "
                f"Belly-up on the surface: {haul_str}. "
                f"+{xp_to_grant} XP from the sheer audacity of it.",
                f"🧨 {self.bot.title_for(username)} lights the fuse. The hole detonates. "
                f"A geyser of fish launches forty feet into the air. "
                f"Floating to the surface: {haul_str}. "
                f"+{xp_to_grant} XP. Completely worth it.",
                f"💥 THE WATER SURRENDERS. {self.bot.title_for(username)}'s dynamite leaves nothing to chance. "
                f"Every fish within a mile radius is rethinking its life choices. "
                f"Haul: {haul_str}. "
                f"+{xp_to_grant} XP. A triumph of raw power over finesse.",
            ]
            response = random.choice(boom_lines)
            if new_level:
                new_location = self._get_location_for_level(new_level)
                response += f" 🎉 LEVEL UP x{levels_possible}! Now level {new_level} — {new_location['name']} awaits!"
            self.safe_say(response, target=event.target)
            return True

        # 70% — catastrophic failure, 7-day ban
        ban_until = datetime.now(UTC) + timedelta(days=7)
        player["dynamite_banned_until"] = ban_until.isoformat()
        # Remove any active cast
        active_casts = self.get_state("active_casts", {})
        if user_id in active_casts:
            del active_casts[user_id]
            self.set_state("active_casts", active_casts)
        self._save_player(user_id, player)

        disaster_lines = [
            f"💀 {self.bot.title_for(username)} lights the dynamite. The dynamite does not wait. "
            "There is a flash. A bang. A smell of singed eyebrows and regret. "
            "The hand is gone. A 7-day fishing ban has been issued by the local authority. "
            "Please reflect on your choices.",
            f"🤦 {self.bot.title_for(username)} fumbles the dynamite. "
            "It goes off immediately. In their hand. "
            "The fish are fine. The hand is not. "
            "Banned from fishing for 7 days. The stump will serve as a reminder.",
            f"💥 A detonation occurs. It is not in the water. "
            f"{self.bot.title_for(username)} stares at the smoking crater where their hand was. "
            "A duck watches from a safe distance, unimpressed. "
            "7-day ban. No appeals.",
            f"🧨 The fuse on {self.bot.title_for(username)}'s dynamite is... shorter than expected. "
            "Much shorter. Comically, tragically shorter. "
            "7-day fishing ban. The stump is now their most interesting feature.",
            f"📛 {self.bot.title_for(username)} has made a terrible mistake. "
            "The fish know. The lake knows. Everyone within earshot knows. "
            "7 days, no fishing, no exceptions. Touch grass (carefully, with the remaining hand).",
        ]
        self.safe_say(random.choice(disaster_lines), target=event.target)
        return True

    def _cmd_water(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        if player.get("junk_curse_date") == today:
            return True

        player["junk_curse_date"] = today
        self._save_player(user_id, player)
        self.safe_reply(
            connection, event,
            f"Cheaters never prosper, {self.bot.title_for(username)}. "
            "I curse you with junk for the remainder of the day."
        )
        return True
