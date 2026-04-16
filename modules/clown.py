# modules/clown.py
# A fishing game exclusively for boomer. Circus-themed. No bonuses. No rares. Just clowns.

import random
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

from .base import SimpleCommandModule

UTC = timezone.utc


def setup(bot: Any) -> 'Clown':
    return Clown(bot)


CIRCUS_CATCHES = [
    "Rubber Chicken",
    "Oversized Polka-Dot Bow Tie",
    "Tiny Clown Car Wheel",
    "Honking Horn",
    "Deflated Balloon Animal",
    "Greasepaint Tube",
    "Sad Mime Glove",
    "Juggling Pin",
    "Confetti Cannon Casing",
    "Squirting Flower",
    "Big Red Nose",
    "Trick Handkerchief",
    "Cotton Candy Stick",
    "Unicycle Pedal",
    "Broken Stilts",
    "Floppy Clown Hat",
    "Seltzer Bottle",
    "Tiny Bicycle Horn",
    "Circus Tent Stake",
    "Tatty Clown Wig",
    "Banana Peel (fresh)",
    "Sad Trombone",
    "Exploding Cigar Stub",
    "Pratfall Mat",
    "Oversized Novelty Key",
    "Pie Tin",
    "Spring Snake Canister",
    "Comedically Large Shoe",
    "Whoopee Cushion",
    "Trick Bouquet",
    "Magic Scarf (knotted)",
    "Tiny Umbrella",
    "Clown Nose (used)",
    "Confetti Pile",
    "Ladder with Banana Peel on Rung",
    "Rubber Mallet",
    "Striped Suspenders",
    "Tuba (miniature)",
    "Face Paint Compact",
    "Very Small Bicycle",
]

CAST_MESSAGES = [
    "You cast your line out over the sawdust. It lands {distance}m away with a squeak.",
    "Your line arcs through the big top, settling {distance}m into the ring.",
    "With a honk, your line sails {distance}m. The spotlight follows. Then it doesn't.",
    "You cast your line. It goes {distance}m. A clown watches from the shadows.",
    "The line sails {distance}m and lands in a pile of confetti. Something stirs.",
]

TOO_EARLY_MESSAGES = [
    "You reel in too soon. The clown hasn't found your hook yet.",
    "Nothing. You can hear clown shoes squeaking somewhere out there. Wait.",
    "Too hasty! The circus is a slow business. Try waiting a bit longer.",
    "Empty hook. A distant honk. Patience, friend.",
    "You reel in and find only a single sad balloon. But it floats away before you can grab it.",
]

MIN_WAIT_HOURS = 1.0


class Clown(SimpleCommandModule):
    name = "clown"
    version = "1.0.0"
    description = "A fishing game exclusively for boomer. Circus-themed."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        if not self.get_state("active_casts"):
            self.set_state("active_casts", {})
        if not self.get_state("players"):
            self.set_state("players", {})
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r'^\s*!cast(?:\s+.+)?\s*$',
            self._cmd_cast,
            name="clown_cast",
            description="[boomer only] Cast your line into the big top"
        )
        self.register_command(
            r'^\s*!reel\s*$',
            self._cmd_reel,
            name="clown_reel",
            description="[boomer only] Reel in your circus catch"
        )
        self.register_command(
            r'^\s*!fish(?:ing|stats)?(?:\s+\S+)?\s*$',
            self._cmd_stats,
            name="clown_stats",
            description="[boomer only] Show your clown fishing stats"
        )
        self.register_command(
            r'^\s*!clown\s*$',
            self._cmd_stats,
            name="clown_stats_direct",
            description="[boomer only] Show your clown fishing stats"
        )

    def _get_player(self, user_id: str) -> Dict[str, Any]:
        players = self.get_state("players", {})
        if user_id not in players:
            players[user_id] = {
                "total_catches": 0,
                "total_casts": 0,
                "catches": {},
                "biggest": 0.0,
                "biggest_name": None,
            }
            self.set_state("players", players)
            self.save_state()
        return players[user_id]

    def _save_player(self, user_id: str, player: Dict[str, Any]) -> None:
        players = self.get_state("players", {})
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

    def _cmd_cast(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False
        if username.lower() != "boomer":
            return False

        user_id = self.bot.get_user_id(username)
        active_casts = self.get_state("active_casts", {})

        if user_id in active_casts:
            cast = active_casts[user_id]
            cast_time = datetime.fromisoformat(cast["timestamp"])
            elapsed = datetime.now(UTC) - cast_time
            hours = elapsed.total_seconds() / 3600
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you already have a line in the big top! "
                f"It's been {hours:.1f} hours. Use !reel to bring it in."
            )
            return True

        player = self._get_player(user_id)
        distance = round(random.uniform(5, 40), 1)

        active_casts[user_id] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "distance": distance,
            "channel": event.target,
        }
        self.set_state("active_casts", active_casts)
        self.save_state()

        player["total_casts"] += 1
        self._save_player(user_id, player)

        cast_msg = random.choice(CAST_MESSAGES).format(distance=distance)
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cast_msg}")
        return True

    def _cmd_reel(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False
        if username.lower() != "boomer":
            return False

        user_id = self.bot.get_user_id(username)
        active_casts = self.get_state("active_casts", {})

        if user_id not in active_casts:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you don't have a line in the big top. Use !cast first."
            )
            return True

        cast = active_casts[user_id]
        cast_time = datetime.fromisoformat(cast["timestamp"])
        now = datetime.now(UTC)
        elapsed = now - cast_time
        wait_hours = elapsed.total_seconds() / 3600

        del active_casts[user_id]
        self.set_state("active_casts", active_casts)
        self.save_state()

        if wait_hours < MIN_WAIT_HOURS:
            self.safe_reply(connection, event, random.choice(TOO_EARLY_MESSAGES))
            return True

        item = random.choice(CIRCUS_CATCHES)
        weight = round(random.uniform(0.1, 8.5), 2)

        player = self._get_player(user_id)
        player["total_catches"] += 1
        player["catches"][item] = player["catches"].get(item, 0) + 1
        if weight > player["biggest"]:
            player["biggest"] = weight
            player["biggest_name"] = item
        self._save_player(user_id, player)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)} reels in... a {item} weighing {weight:.2f} lbs "
            f"after waiting {wait_hours:.1f} hours!"
        )
        return True

    def _cmd_stats(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False
        if username.lower() != "boomer":
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)

        response = (
            f"Clown Fishing Stats for {self.bot.title_for(username)}: "
            f"Catches: {player['total_catches']} | "
            f"Casts: {player['total_casts']}"
        )
        if player.get("biggest_name"):
            response += f" | Biggest: {player['biggest']:.2f} lbs ({player['biggest_name']})"

        self.safe_reply(connection, event, response)
        return True
