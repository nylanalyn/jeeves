# modules/fishing.py
# A fishing mini-game where users cast lines and reel in catches over time.

import random
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .base import SimpleCommandModule
from . import achievement_hooks

UTC = timezone.utc


def setup(bot: Any) -> 'Fishing':
    return Fishing(bot)


# Fishing locations unlocked by level (0-9)
LOCATIONS = [
    {"name": "Puddle", "level": 0, "max_distance": 5, "type": "terrestrial"},
    {"name": "Pond", "level": 1, "max_distance": 15, "type": "terrestrial"},
    {"name": "Lake", "level": 2, "max_distance": 30, "type": "terrestrial"},
    {"name": "River", "level": 3, "max_distance": 50, "type": "terrestrial"},
    {"name": "Ocean", "level": 4, "max_distance": 100, "type": "terrestrial"},
    {"name": "Deep Sea", "level": 5, "max_distance": 200, "type": "terrestrial"},
    {"name": "Moon", "level": 6, "max_distance": 500, "type": "space"},
    {"name": "Mars", "level": 7, "max_distance": 1000, "type": "space"},
    {"name": "Jupiter", "level": 8, "max_distance": 2000, "type": "space"},
    {"name": "The Void", "level": 9, "max_distance": 5000, "type": "space"},
]

# Fish database organized by location
# Each fish has: name, min_weight, max_weight, rarity
FISH_DATABASE: Dict[str, List[Dict[str, Any]]] = {
    "Puddle": [
        # Common
        {"name": "Minnow", "min_weight": 0.1, "max_weight": 0.5, "rarity": "common"},
        {"name": "Tadpole", "min_weight": 0.05, "max_weight": 0.2, "rarity": "common"},
        {"name": "Guppy", "min_weight": 0.1, "max_weight": 0.3, "rarity": "common"},
        {"name": "Water Beetle", "min_weight": 0.01, "max_weight": 0.1, "rarity": "common"},
        # Uncommon
        {"name": "Goldfish", "min_weight": 0.5, "max_weight": 2.0, "rarity": "uncommon"},
        {"name": "Small Frog", "min_weight": 0.3, "max_weight": 1.0, "rarity": "uncommon"},
        # Rare
        {"name": "Koi", "min_weight": 2.0, "max_weight": 5.0, "rarity": "rare"},
        # Legendary
        {"name": "The Puddle King", "min_weight": 8.0, "max_weight": 15.0, "rarity": "legendary"},
    ],
    "Pond": [
        # Common
        {"name": "Bluegill", "min_weight": 0.5, "max_weight": 2.0, "rarity": "common"},
        {"name": "Perch", "min_weight": 0.5, "max_weight": 3.0, "rarity": "common"},
        {"name": "Sunfish", "min_weight": 0.3, "max_weight": 1.5, "rarity": "common"},
        {"name": "Crayfish", "min_weight": 0.1, "max_weight": 0.5, "rarity": "common"},
        # Uncommon
        {"name": "Largemouth Bass", "min_weight": 2.0, "max_weight": 8.0, "rarity": "uncommon"},
        {"name": "Catfish", "min_weight": 3.0, "max_weight": 10.0, "rarity": "uncommon"},
        # Rare
        {"name": "Golden Perch", "min_weight": 5.0, "max_weight": 12.0, "rarity": "rare"},
        # Legendary
        {"name": "Old Whiskers", "min_weight": 20.0, "max_weight": 40.0, "rarity": "legendary"},
    ],
    "Lake": [
        # Common
        {"name": "Trout", "min_weight": 1.0, "max_weight": 5.0, "rarity": "common"},
        {"name": "Crappie", "min_weight": 0.5, "max_weight": 3.0, "rarity": "common"},
        {"name": "Walleye", "min_weight": 2.0, "max_weight": 8.0, "rarity": "common"},
        {"name": "Pike", "min_weight": 3.0, "max_weight": 12.0, "rarity": "common"},
        # Uncommon
        {"name": "Lake Sturgeon", "min_weight": 10.0, "max_weight": 30.0, "rarity": "uncommon"},
        {"name": "Muskie", "min_weight": 8.0, "max_weight": 25.0, "rarity": "uncommon"},
        # Rare
        {"name": "Albino Sturgeon", "min_weight": 20.0, "max_weight": 50.0, "rarity": "rare"},
        # Legendary
        {"name": "Nessie's Cousin", "min_weight": 100.0, "max_weight": 200.0, "rarity": "legendary"},
    ],
    "River": [
        # Common
        {"name": "Salmon", "min_weight": 5.0, "max_weight": 15.0, "rarity": "common"},
        {"name": "Steelhead", "min_weight": 4.0, "max_weight": 12.0, "rarity": "common"},
        {"name": "River Carp", "min_weight": 3.0, "max_weight": 20.0, "rarity": "common"},
        {"name": "Smallmouth Bass", "min_weight": 2.0, "max_weight": 6.0, "rarity": "common"},
        # Uncommon
        {"name": "King Salmon", "min_weight": 15.0, "max_weight": 40.0, "rarity": "uncommon"},
        {"name": "Paddlefish", "min_weight": 20.0, "max_weight": 60.0, "rarity": "uncommon"},
        # Rare
        {"name": "Golden Salmon", "min_weight": 25.0, "max_weight": 50.0, "rarity": "rare"},
        # Legendary
        {"name": "The River Guardian", "min_weight": 80.0, "max_weight": 150.0, "rarity": "legendary"},
    ],
    "Ocean": [
        # Common
        {"name": "Tuna", "min_weight": 20.0, "max_weight": 80.0, "rarity": "common"},
        {"name": "Mackerel", "min_weight": 5.0, "max_weight": 15.0, "rarity": "common"},
        {"name": "Sea Bass", "min_weight": 10.0, "max_weight": 40.0, "rarity": "common"},
        {"name": "Flounder", "min_weight": 3.0, "max_weight": 12.0, "rarity": "common"},
        # Uncommon
        {"name": "Swordfish", "min_weight": 50.0, "max_weight": 150.0, "rarity": "uncommon"},
        {"name": "Mahi-Mahi", "min_weight": 15.0, "max_weight": 50.0, "rarity": "uncommon"},
        {"name": "Barracuda", "min_weight": 20.0, "max_weight": 60.0, "rarity": "uncommon"},
        # Rare
        {"name": "Blue Marlin", "min_weight": 100.0, "max_weight": 300.0, "rarity": "rare"},
        {"name": "Sailfish", "min_weight": 80.0, "max_weight": 200.0, "rarity": "rare"},
        # Legendary
        {"name": "Moby Dick Jr.", "min_weight": 500.0, "max_weight": 1000.0, "rarity": "legendary"},
    ],
    "Deep Sea": [
        # Common
        {"name": "Anglerfish", "min_weight": 5.0, "max_weight": 20.0, "rarity": "common"},
        {"name": "Viperfish", "min_weight": 2.0, "max_weight": 8.0, "rarity": "common"},
        {"name": "Gulper Eel", "min_weight": 3.0, "max_weight": 15.0, "rarity": "common"},
        {"name": "Lanternfish", "min_weight": 0.5, "max_weight": 3.0, "rarity": "common"},
        # Uncommon
        {"name": "Giant Squid", "min_weight": 50.0, "max_weight": 200.0, "rarity": "uncommon"},
        {"name": "Oarfish", "min_weight": 30.0, "max_weight": 100.0, "rarity": "uncommon"},
        {"name": "Goblin Shark", "min_weight": 100.0, "max_weight": 300.0, "rarity": "uncommon"},
        # Rare
        {"name": "Colossal Squid", "min_weight": 200.0, "max_weight": 500.0, "rarity": "rare"},
        {"name": "Megamouth Shark", "min_weight": 300.0, "max_weight": 600.0, "rarity": "rare"},
        # Legendary
        {"name": "The Kraken", "min_weight": 1000.0, "max_weight": 2500.0, "rarity": "legendary"},
    ],
    "Moon": [
        # Common
        {"name": "Moon Jellyfish", "min_weight": 1.0, "max_weight": 5.0, "rarity": "common"},
        {"name": "Lunar Shrimp", "min_weight": 0.5, "max_weight": 2.0, "rarity": "common"},
        {"name": "Crater Minnow", "min_weight": 0.3, "max_weight": 1.5, "rarity": "common"},
        {"name": "Dust Swimmer", "min_weight": 1.0, "max_weight": 4.0, "rarity": "common"},
        # Uncommon
        {"name": "Crater Crab", "min_weight": 5.0, "max_weight": 15.0, "rarity": "uncommon"},
        {"name": "Void Eel", "min_weight": 10.0, "max_weight": 30.0, "rarity": "uncommon"},
        {"name": "Selenite Fish", "min_weight": 8.0, "max_weight": 25.0, "rarity": "uncommon"},
        # Rare
        {"name": "Cosmic Whale", "min_weight": 50.0, "max_weight": 200.0, "rarity": "rare"},
        {"name": "Starlight Serpent", "min_weight": 40.0, "max_weight": 150.0, "rarity": "rare"},
        # Legendary
        {"name": "The Leviathan of Tranquility", "min_weight": 500.0, "max_weight": 1000.0, "rarity": "legendary"},
    ],
    "Mars": [
        # Common
        {"name": "Rust Minnow", "min_weight": 0.5, "max_weight": 2.0, "rarity": "common"},
        {"name": "Red Silt Crawler", "min_weight": 1.0, "max_weight": 5.0, "rarity": "common"},
        {"name": "Iron Guppy", "min_weight": 0.5, "max_weight": 3.0, "rarity": "common"},
        {"name": "Dust Devil Fish", "min_weight": 2.0, "max_weight": 8.0, "rarity": "common"},
        # Uncommon
        {"name": "Olympus Bass", "min_weight": 10.0, "max_weight": 30.0, "rarity": "uncommon"},
        {"name": "Valles Trout", "min_weight": 15.0, "max_weight": 40.0, "rarity": "uncommon"},
        {"name": "Phobos Flounder", "min_weight": 8.0, "max_weight": 25.0, "rarity": "uncommon"},
        # Rare
        {"name": "Martian Kraken", "min_weight": 100.0, "max_weight": 300.0, "rarity": "rare"},
        {"name": "Red Planet Leviathan", "min_weight": 150.0, "max_weight": 400.0, "rarity": "rare"},
        # Legendary
        {"name": "The Ancient One", "min_weight": 1000.0, "max_weight": 2000.0, "rarity": "legendary"},
    ],
    "Jupiter": [
        # Common
        {"name": "Gas Giant Jellyfish", "min_weight": 2.0, "max_weight": 10.0, "rarity": "common"},
        {"name": "Storm Swimmer", "min_weight": 5.0, "max_weight": 15.0, "rarity": "common"},
        {"name": "Ammonia Minnow", "min_weight": 1.0, "max_weight": 5.0, "rarity": "common"},
        {"name": "Cloud Drifter", "min_weight": 3.0, "max_weight": 12.0, "rarity": "common"},
        # Uncommon
        {"name": "Red Spot Ray", "min_weight": 20.0, "max_weight": 60.0, "rarity": "uncommon"},
        {"name": "Ammonia Eel", "min_weight": 30.0, "max_weight": 80.0, "rarity": "uncommon"},
        {"name": "Io Salmon", "min_weight": 25.0, "max_weight": 70.0, "rarity": "uncommon"},
        # Rare
        {"name": "Jovian Leviathan", "min_weight": 200.0, "max_weight": 500.0, "rarity": "rare"},
        {"name": "Europa Ice Beast", "min_weight": 250.0, "max_weight": 600.0, "rarity": "rare"},
        # Legendary
        {"name": "The Great Red Serpent", "min_weight": 2000.0, "max_weight": 4000.0, "rarity": "legendary"},
    ],
    "The Void": [
        # Common
        {"name": "Void Mite", "min_weight": 1.0, "max_weight": 5.0, "rarity": "common"},
        {"name": "Dark Matter Shrimp", "min_weight": 3.0, "max_weight": 10.0, "rarity": "common"},
        {"name": "Null Fish", "min_weight": 2.0, "max_weight": 8.0, "rarity": "common"},
        {"name": "Entropy Minnow", "min_weight": 1.0, "max_weight": 6.0, "rarity": "common"},
        # Uncommon
        {"name": "Entropy Eel", "min_weight": 25.0, "max_weight": 75.0, "rarity": "uncommon"},
        {"name": "Singularity Squid", "min_weight": 50.0, "max_weight": 150.0, "rarity": "uncommon"},
        {"name": "Dimensional Drifter", "min_weight": 40.0, "max_weight": 120.0, "rarity": "uncommon"},
        # Rare
        {"name": "Reality Warper", "min_weight": 300.0, "max_weight": 800.0, "rarity": "rare"},
        {"name": "Event Horizon Eel", "min_weight": 400.0, "max_weight": 900.0, "rarity": "rare"},
        # Legendary
        {"name": "The Cosmic Horror", "min_weight": 5000.0, "max_weight": 10000.0, "rarity": "legendary"},
        {"name": "Cthulhu's Cousin", "min_weight": 8000.0, "max_weight": 15000.0, "rarity": "legendary"},
    ],
}

# Junk items by location type
JUNK_ITEMS: Dict[str, List[str]] = {
    "terrestrial": [
        "Old Boot", "Rusty Tin Can", "Soggy Newspaper", "Tangled Fishing Line",
        "Broken Sunglasses", "Waterlogged Book", "Deflated Beach Ball", "Lost Flip-Flop",
        "Shopping Cart Wheel", "Plastic Bottle", "Tire", "Underwear", "License Plate",
        "Broken Umbrella", "Moldy Wallet", "Damp Cigarette Pack", "Fishing Bobber",
    ],
    "space": [
        "Space Debris", "Frozen Oxygen Chunk", "Abandoned Satellite", "Lost Astronaut Glove",
        "Alien Artifact", "Meteor Fragment", "Cosmic Dust Bunny", "Derelict Probe",
        "Ancient Star Map", "Fossilized Moonrock", "Mysterious Orb", "Quantum Fluctuation",
        "Void Crystal", "Broken Warp Core", "Lost Space Buoy", "Crystallized Stardust",
    ],
}

# Random events that can trigger
EVENTS: Dict[str, Dict[str, Any]] = {
    "full_moon": {
        "name": "Full Moon",
        "description": "The full moon rises! Rare fish are more active.",
        "effect": "rare_boost",
        "multiplier": 2.0,
        "duration_minutes": 30,
    },
    "solar_flare": {
        "name": "Solar Flare",
        "description": "A solar flare energizes the waters! Double XP!",
        "effect": "xp_boost",
        "multiplier": 2.0,
        "duration_minutes": 20,
        "locations": ["Moon", "Mars", "Jupiter", "The Void"],
    },
    "feeding_frenzy": {
        "name": "Feeding Frenzy",
        "description": "The fish are hungry! Catches are easier.",
        "effect": "time_boost",
        "multiplier": 0.5,  # Halves effective required time
        "duration_minutes": 25,
    },
    "murky_waters": {
        "name": "Murky Waters",
        "description": "The waters are murky... more junk than usual.",
        "effect": "junk_boost",
        "multiplier": 2.0,
        "duration_minutes": 15,
    },
    "meteor_shower": {
        "name": "Meteor Shower",
        "description": "A meteor shower brings strange creatures from beyond!",
        "effect": "alien_fish",
        "duration_minutes": 20,
        "locations": ["Moon", "Mars", "Jupiter", "The Void"],
    },
}

# Rarity weights for fish selection
RARITY_WEIGHTS = {
    "common": 70,
    "uncommon": 20,
    "rare": 8,
    "legendary": 2,
}

# XP multipliers by rarity
RARITY_XP_MULTIPLIER = {
    "common": 1,
    "uncommon": 2,
    "rare": 5,
    "legendary": 20,
}

# Cast flavor messages
CAST_MESSAGES = [
    "You cast your line, it goes {distance}m and floats quietly...",
    "With a practiced flick, your line sails {distance}m into the {location}.",
    "Your line arcs gracefully, landing {distance}m away in the {location}.",
    "The line whips through the air, settling {distance}m out.",
    "You send your line sailing {distance}m. Now we wait...",
]

# Reel too early messages
TOO_EARLY_MESSAGES = [
    "You reel in too soon - the line is empty. Perhaps patience is a virtue?",
    "Nothing but an empty hook. The fish need more time to find your bait.",
    "Your line comes back bare. Try waiting a bit longer next time.",
    "Too hasty! The fish haven't even noticed your bait yet.",
    "An empty catch. Good things come to those who wait.",
]

# Danger zone messages (over 24 hours)
DANGER_ZONE_MESSAGES = {
    "line_break": [
        "The line finally snaps from the strain! It was out there too long.",
        "Your line, weakened by time, breaks as you try to reel in.",
        "The elements have taken their toll - your line breaks clean off!",
    ],
    "fish_escaped": [
        "The fish got tired of waiting and swam away ages ago.",
        "Whatever was on the line has long since escaped.",
        "You reel in... nothing. The fish left hours ago.",
    ],
    "junk": [
        "After all that time, you only catch some waterlogged junk.",
        "The long wait rewards you with... garbage. How fitting.",
    ],
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
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r'^\s*!cast\s*$',
            self._cmd_cast,
            name="cast",
            description="Cast your fishing line"
        )
        self.register_command(
            r'^\s*!reel\s*$',
            self._cmd_reel,
            name="reel",
            description="Reel in your catch"
        )
        self.register_command(
            r'^\s*!fish(?:ing|stats)?\s*$',
            self._cmd_fishing_stats,
            name="fishing",
            description="Show your fishing statistics"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+top\s*$',
            self._cmd_fishing_top,
            name="fishing top",
            description="Show fishing leaderboards"
        )
        self.register_command(
            r'^\s*!fish(?:ing)?\s+location\s*$',
            self._cmd_fishing_location,
            name="fishing location",
            description="Show your current fishing location"
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
                "rare_catches": [],
                "locations_fished": [],
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

    def _get_location_for_level(self, level: int) -> Dict[str, Any]:
        """Get the location a player can fish at based on their level."""
        # Player fishes at their max unlocked location
        for loc in reversed(LOCATIONS):
            if loc["level"] <= level:
                return loc
        return LOCATIONS[0]

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
            achievement_hooks.record_achievement(self.bot, username, "fishing_level", current_level)
            return current_level

        player["xp"] = xp
        return None

    def _get_cast_distance(self, level: int, location: Dict[str, Any]) -> float:
        """Generate a random cast distance based on level and location."""
        max_dist = location["max_distance"]
        # Base distance is 30-70% of max, with level adding potential
        min_dist = max_dist * 0.3
        level_bonus = (level / 9) * 0.3  # Up to 30% bonus at max level
        base_max = max_dist * (0.7 + level_bonus)
        return round(random.uniform(min_dist, base_max), 1)

    def _select_rarity(self, wait_hours: float, event: Optional[Dict[str, Any]] = None) -> str:
        """Select a rarity tier based on wait time and active events."""
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

        # Weighted random selection
        total = sum(weights.values())
        roll = random.randint(1, total)
        cumulative = 0
        for rarity, weight in weights.items():
            cumulative += weight
            if roll <= cumulative:
                return rarity
        return "common"

    def _select_fish(self, location: str, rarity: str) -> Optional[Dict[str, Any]]:
        """Select a fish from the location's pool matching the rarity."""
        fish_pool = FISH_DATABASE.get(location, [])
        matching = [f for f in fish_pool if f["rarity"] == rarity]
        if not matching:
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
        location = self._get_location_for_level(player["level"])
        distance = self._get_cast_distance(player["level"], location)

        # Record the cast
        active_casts[user_id] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "distance": distance,
            "location": location["name"],
            "channel": event.target,
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
        cast_msg = random.choice(CAST_MESSAGES).format(
            distance=distance,
            location=location["name"]
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
        if wait_hours > self.DANGER_THRESHOLD_HOURS:
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

        # Junk check (base chance, boosted by murky waters)
        junk_chance = 0.10
        if active_event and active_event.get("effect") == "junk_boost":
            junk_chance *= active_event.get("multiplier", 1.0)

        if random.random() < junk_chance:
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
        rarity = self._select_rarity(effective_wait, active_event)
        fish = self._select_fish(location_name, rarity)

        if not fish:
            # Fallback - shouldn't happen
            self.safe_reply(connection, event, "The fish got away at the last moment!")
            return True

        weight = self._calculate_weight(fish, effective_wait)

        # Line break check - bigger fish = higher chance
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

        # Track catches
        catches = player.get("catches", {})
        catches[fish["name"]] = catches.get(fish["name"], 0) + 1
        player["catches"] = catches

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

        player["xp"] += xp_gain
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
            f"weighing {weight:.2f} lbs after waiting {wait_hours:.1f} hours! (+{xp_gain} XP)"
        )

        if new_level:
            new_location = self._get_location_for_level(new_level)
            response += f" LEVEL UP! You're now level {new_level} and can fish at {new_location['name']}!"

        self.safe_reply(connection, event, response)
        return True

    def _cmd_fishing_stats(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)
        location = self._get_location_for_level(player["level"])

        xp_needed = self._get_xp_for_level(player["level"])
        xp_progress = f"{player['xp']}/{xp_needed}"

        stats = (
            f"Fishing Stats for {self.bot.title_for(username)}: "
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

    def _cmd_fishing_help(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        help_lines = [
            "Fishing Commands:",
            "!cast - Cast your line (wait 1-24 hours for best results)",
            "!reel - Reel in your catch",
            "!fishing - Show your stats",
            "!fishing top - Leaderboards",
            "!fishing location - Current location and level progress",
            "!aquarium - View your rare/legendary catches",
        ]

        for line in help_lines:
            self.safe_privmsg(username, line)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)}, I've sent you the fishing guide."
        )
        return True
