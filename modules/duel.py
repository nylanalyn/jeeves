# modules/duel.py
# Duel challenges with !slap and !accept plus lightweight stats.

import random
import time
from typing import Any, Dict, List, Optional, Tuple

from .base import SimpleCommandModule


def setup(bot: Any) -> "Duel":
    """Initialize the duel module."""
    return Duel(bot)


class Duel(SimpleCommandModule):
    name = "duel"
    version = "1.0.0"
    description = "Challenge other users to quick duels and track bragging rights."

    WEAPONS: List[Tuple[str, str]] = [
        ("polished sabres", "Steel rings out as sparks leap from every clash."),
        ("antique flintlock pistols", "Ten measured paces, a turn, and powder smoke blankets the field."),
        ("dueling revolvers", "Two sharp cracks echo before the dust settles."),
        ("lance and shield", "The charge kicks up dirt as splinters fly."),
        ("foam longswords", "The duel is fierce, squeaky, and only slightly ridiculous."),
        ("paintball pistols", "A riot of color decides the matter."),
        ("nerf darts", "Honor is defended under a hail of foam."),
        ("bananas", "Slapstick technique prevails over martial form."),
    ]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.set_state("pending_duels", self.get_state("pending_duels", {}))
        self.set_state("stats", self.get_state("stats", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!slap\s+(\S+)\s*$", self._cmd_slap, name="slap", description="Challenge someone to a duel")
        self.register_command(r"^\s*!accept(?:\s+(\S+))?\s*$", self._cmd_accept, name="accept", description="Accept a pending duel")
        self.register_command(r"^\s*!duelstats\s*$", self._cmd_duelstats, name="duelstats", description="Show duel leaders")

    def _cmd_slap(self, connection, event, msg: str, username: str, match) -> bool:
        target_raw = match.group(1).strip()
        target_nick = target_raw.lstrip("@+%&~").rstrip(",.!").strip()
        if not target_nick:
            return True

        if target_nick.lower() == username.lower():
            self.safe_reply(connection, event, "A duel with oneself is merely practice, not sport.")
            return True

        if target_nick.lower() == self.bot.connection.get_nickname().lower():
            self.safe_reply(connection, event, "I must decline; a butler should never duel his guests.")
            return True

        if self.bot.is_user_ignored(target_nick):
            self.safe_reply(connection, event, f"{target_nick} cannot be challenged right now.")
            return True

        if not self._allow_flavor_off_targets(event.target) and not self.has_flavor_enabled(target_nick):
            self.safe_reply(connection, event, f"{target_nick} has flavor turned off, and duel invitations are disabled for them in the config.")
            return True

        challenger_id = self.bot.get_user_id(username)
        target_id = self.bot.get_user_id(target_nick)

        pending = self._prune_expired()
        channel_pending = pending.get(event.target, {})
        existing = channel_pending.get(target_id)
        if existing:
            existing_from = existing.get("challenger_nick", "someone")
            self.safe_reply(connection, event, f"{target_nick} already has a pending challenge from {existing_from}.")
            return True

        channel_pending[target_id] = {
            "challenger_id": challenger_id,
            "challenger_nick": username,
            "target_nick": target_nick,
            "created_at": time.time(),
        }
        pending[event.target] = channel_pending
        self.set_state("pending_duels", pending)
        self._bump_stat("duels_started", challenger_id)
        self._bump_stat("duels_received", target_id)
        self.save_state()

        timeout = int(self._challenge_timeout_seconds(event.target))
        challenger_display = self._display_nick(challenger_id, username)
        target_display = self._display_nick(target_id, target_nick)
        self.safe_reply(
            connection,
            event,
            f"{challenger_display} slaps {target_display} with a white glove, issuing a challenge to a duel! "
            f"{target_display}, type !accept to answer. Challenge expires in {timeout} seconds.",
        )
        return True

    def _cmd_accept(self, connection, event, msg: str, username: str, match) -> bool:
        challenger_filter = match.group(1)
        target_id = self.bot.get_user_id(username)

        pending = self._prune_expired()
        channel_pending = pending.get(event.target, {})
        challenge = channel_pending.get(target_id)

        if not challenge:
            self.safe_reply(connection, event, "You have no pending duel challenges.")
            return True

        if challenger_filter and challenge.get("challenger_nick", "").lower() != challenger_filter.lower():
            self.safe_reply(connection, event, f"Your pending challenge is from {challenge.get('challenger_nick', 'someone')}, not {challenger_filter}.")
            return True

        challenger_id = challenge["challenger_id"]
        challenger_nick = challenge.get("challenger_nick", "someone")
        challenger_display = self._display_nick(challenger_id, challenger_nick)
        target_display = self._display_nick(target_id, username)

        winner_id = random.choice([challenger_id, target_id])
        loser_id = target_id if winner_id == challenger_id else challenger_id

        weapon, flourish = random.choice(self.WEAPONS)

        duel_intro = f"{challenger_display} and {target_display} take their places. The chosen weapons: {weapon}."

        winner_fallback = challenger_display if winner_id == challenger_id else target_display
        duel_outcome = f"{flourish} Victory goes to {self._display_nick(winner_id, winner_fallback)}!"

        del channel_pending[target_id]
        if channel_pending:
            pending[event.target] = channel_pending
        else:
            pending.pop(event.target, None)

        self.set_state("pending_duels", pending)
        self._bump_stat("wins", winner_id)
        self._bump_stat("losses", loser_id)
        self.save_state()

        self.safe_reply(connection, event, f"{duel_intro} {duel_outcome}")
        return True

    def _cmd_duelstats(self, connection, event, msg: str, username: str, match) -> bool:
        stats = self.get_state("stats", {})
        wins = self._top_bucket(stats.get("wins", {}))
        targets = self._top_bucket(stats.get("duels_received", {}))

        if not wins and not targets:
            self.safe_reply(connection, event, "No duels have been recorded yet.")
            return True

        parts = []
        if wins:
            win_str = ", ".join(f"{self._nick_for_user_id(uid)} ({count})" for uid, count in wins)
            parts.append(f"Top duelers: {win_str}")
        if targets:
            target_str = ", ".join(f"{self._nick_for_user_id(uid)} ({count})" for uid, count in targets)
            parts.append(f"Most challenged: {target_str}")

        self.safe_reply(connection, event, " | ".join(parts))
        return True

    def _bump_stat(self, bucket: str, user_id: str) -> None:
        stats = self.get_state("stats", {})
        bucket_map = stats.get(bucket, {})
        bucket_map[user_id] = bucket_map.get(user_id, 0) + 1
        stats[bucket] = bucket_map
        self.set_state("stats", stats)

    def _top_bucket(self, bucket: Dict[str, int], limit: int = 3) -> List[Tuple[str, int]]:
        return sorted(bucket.items(), key=lambda pair: pair[1], reverse=True)[:limit]

    def _nick_for_user_id(self, user_id: str) -> str:
        users_module = self.bot.pm.plugins.get("users")
        if users_module and hasattr(users_module, "get_user_nick"):
            return users_module.get_user_nick(user_id)
        return user_id

    def _display_nick(self, user_id: str, fallback: Optional[str] = None) -> str:
        """Prefer a stored nick, fall back to the provided name."""
        nick = self._nick_for_user_id(user_id)
        if nick == user_id and fallback:
            return fallback
        return nick

    def _allow_flavor_off_targets(self, channel: Optional[str]) -> bool:
        return bool(self.get_config_value("include_flavor_off_users", channel, False))

    def _challenge_timeout_seconds(self, channel: Optional[str]) -> float:
        return float(self.get_config_value("challenge_timeout_seconds", channel, 180))

    def _prune_expired(self) -> Dict[str, Dict[str, Dict[str, Any]]]:
        pending = self.get_state("pending_duels", {})
        now = time.time()
        changed = False

        for channel, channel_pending in list(pending.items()):
            timeout = self._challenge_timeout_seconds(channel)
            for target_id, challenge in list(channel_pending.items()):
                created_at = challenge.get("created_at", 0)
                if created_at and now - created_at > timeout:
                    del channel_pending[target_id]
                    changed = True

            if channel_pending:
                pending[channel] = channel_pending
            elif channel in pending:
                del pending[channel]
                changed = True

        if changed:
            self.set_state("pending_duels", pending)
            self.save_state()

        return pending
