# modules/darts.py
# A 301 darts game with bust mechanics and butler-style celebrations.

import random
import time
from typing import Any, Dict, List, Tuple

from .base import SimpleCommandModule, admin_required


def setup(bot: Any) -> "Darts":
    """Initialize the darts module."""
    return Darts(bot)


class Darts(SimpleCommandModule):
    name = "darts"
    version = "1.0.0"
    description = "A 301 darts game. Throw darts, race to zero, bust if you overshoot."

    STARTING_SCORE = 301

    # Dartboard segments: (label, point_value, weight)
    # Built at class initialization
    DARTBOARD_SEGMENTS: List[Tuple[str, int, int]] = []

    # Flavor message pools
    THROW_MESSAGES: List[str] = [
        "{title} throws a dart — it sails through the air and...",
        "The dart leaves {title}'s hand with purpose...",
        "{title} takes aim and releases...",
        "A focused stance, a flick of the wrist — {title}'s dart...",
        "The oche holds {title} as the dart flies...",
    ]

    BUST_MESSAGES: List[str] = [
        "Bust! {title} threw {points} but only needed {remaining}. No score this turn.",
        "Overcooked! {title} needed {remaining} but threw {points}. The oche is a cruel place.",
        "Ah, too much! {title} had {remaining} left but scored {points}. Score stands.",
        "So close, yet so far — {title} overshot with {points} when {remaining} was needed.",
    ]

    WIN_MESSAGES: List[str] = [
        "Magnificent! {title} has reached zero with the precision of a Swiss timepiece! The household rises in applause!",
        "A masterful checkout! {title} hits the mark with unerring accuracy! I shall inform the press at once.",
        "Victory! {title} completes the 301 in sterling fashion! The board shall be retired in honor of this moment.",
        "Bravo! {title} finishes with the grace of a champion! The silverware polishes itself in celebration!",
        "Exemplary! {title} achieves the perfect finish! I'll prepare the victory tea at once!",
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        # Build dartboard segments at init
        self._build_dartboard()
        # State: { channel: { players: { user_id: { remaining: int, joined_at: float } }, created_at: float } }
        self.set_state("games", self.get_state("games", {}))
        self.save_state()

    def _build_dartboard(self) -> None:
        """Build the dartboard segments with weights."""
        segments = []
        # Singles 1-20: weight 2 each (most of the board)
        for i in range(1, 21):
            segments.append((str(i), i, 2))
        # Doubles 2-40 (even): weight 1 each (thin ring)
        for i in range(1, 21):
            segments.append((f"double {i}", i * 2, 1))
        # Triples 3-60 (multiples of 3): weight 0.5 each (even thinner)
        for i in range(1, 21):
            segments.append((f"triple {i}", i * 3, 0.5))
        # Outer bull (25): weight 1
        segments.append(("outer bull", 25, 1))
        # Inner bullseye (50): weight 0.5
        segments.append(("bullseye", 50, 0.5))
        # Miss (0): weight 1
        segments.append(("miss", 0, 1))

        self.DARTBOARD_SEGMENTS = segments

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!darts\s*$",
            self._cmd_throw,
            name="darts",
            description="Throw a dart in the 301 game",
        )
        self.register_command(
            r"^\s*!darts\s+score\s*$",
            self._cmd_score,
            name="darts score",
            description="Show the current 301 scoreboard",
        )
        self.register_command(
            r"^\s*!darts\s+reset\s*$",
            self._cmd_reset,
            name="darts reset",
            admin_only=True,
            description="Reset the current darts game",
        )

    def _get_or_create_game(self, channel: str) -> Dict[str, Any]:
        """Get existing game for channel or create a new one."""
        games = self.get_state("games", {})
        if channel not in games:
            games[channel] = {
                "players": {},
                "created_at": time.time(),
            }
            self.set_state("games", games)
            self.save_state()
        return games[channel]

    def _simulate_throw(self) -> Tuple[str, int]:
        """Simulate a dart throw, returning (label, points)."""
        labels = [seg[0] for seg in self.DARTBOARD_SEGMENTS]
        weights = [seg[2] for seg in self.DARTBOARD_SEGMENTS]
        points_map = {seg[0]: seg[1] for seg in self.DARTBOARD_SEGMENTS}

        chosen_label = random.choices(labels, weights=weights, k=1)[0]
        points = points_map[chosen_label]
        return chosen_label, points

    def _cmd_throw(self, connection: Any, event: Any, msg: str, username: str, match) -> bool:
        """Handle !darts command - throw a dart."""
        channel = event.target
        user_id = self.bot.get_user_id(username)
        title = self.bot.title_for(username)

        # Get or create game
        game = self._get_or_create_game(channel)
        players = game["players"]

        # Join player if not already in
        if user_id not in players:
            players[user_id] = {
                "remaining": self.STARTING_SCORE,
                "joined_at": time.time(),
            }
            games = self.get_state("games", {})
            games[channel] = game
            self.set_state("games", games)
            self.save_state()

        player = players[user_id]
        remaining = player["remaining"]

        # Simulate throw
        label, points = self._simulate_throw()

        # Check for bust
        if points > remaining:
            # Bust - score unchanged
            # Escalating bust messaging by proximity to 0
            if remaining <= 5:
                bust_msg = f"So very close! {title} needed exactly {remaining} but scored {points}. Agony."
            elif remaining <= 20:
                bust_msg = f"Overcooked! {title} needed {remaining} but threw {points}. The oche is a cruel place."
            else:
                bust_msg = f"Bust! {title} threw {points} but only needed {remaining}. No score this turn."
            
            throw_template = random.choice(self.THROW_MESSAGES)
            self.safe_reply(connection, event, f"{throw_template} {label} ({points} points). {bust_msg}")
            return True

        # Deduct points
        new_remaining = remaining - points
        player["remaining"] = new_remaining

        # Check for win
        if new_remaining == 0:
            win_msg = random.choice(self.WIN_MESSAGES).format(title=title)
            throw_template = random.choice(self.THROW_MESSAGES)
            self.safe_reply(
                connection,
                event,
                f"{throw_template} {label} ({points} points). EXACTLY ZERO!\n{win_msg}"
            )
            # Reset game - remove channel from games
            games = self.get_state("games", {})
            if channel in games:
                del games[channel]
                self.set_state("games", games)
                self.save_state()
            return True

        # Normal throw - show remaining
        throw_template = random.choice(self.THROW_MESSAGES)
        self.safe_reply(
            connection,
            event,
            f"{throw_template} {label} ({points} points). {title} has {new_remaining} remaining."
        )

        # Save state
        games = self.get_state("games", {})
        games[channel] = game
        self.set_state("games", games)
        self.save_state()

        return True

    def _cmd_score(self, connection: Any, event: Any, msg: str, username: str, match) -> bool:
        """Handle !darts score - show scoreboard."""
        channel = event.target
        games = self.get_state("games", {})

        if channel not in games or not games[channel]["players"]:
            self.safe_reply(connection, event, "No active darts game in this channel. Throw a dart with !darts to start!")
            return True

        game = games[channel]
        players = game["players"]

        if not players:
            self.safe_reply(connection, event, "No players in the current game.")
            return True

        # Sort by remaining (ascending - closer to 0 is better)
        sorted_players = sorted(players.items(), key=lambda x: x[1]["remaining"])

        score_parts = []
        for user_id, data in sorted_players:
            nick = self.bot.get_nick_for_id(user_id)
            if nick:
                score_parts.append(f"{self.bot.title_for(nick)}: {data['remaining']}")

        if not score_parts:
            self.safe_reply(connection, event, "No players found.")
            return True

        self.safe_reply(connection, event, " | ".join(score_parts))
        return True

    @admin_required
    def _cmd_reset(self, connection: Any, event: Any, msg: str, username: str, match) -> bool:
        """Handle !darts reset - admin-only game reset."""
        channel = event.target
        games = self.get_state("games", {})

        if channel not in games:
            self.safe_reply(connection, event, "No active darts game to reset.")
            return True

        del games[channel]
        self.set_state("games", games)
        self.save_state()

        self.safe_reply(connection, event, "Darts game has been reset. Next !darts starts a fresh match.")
        return True
