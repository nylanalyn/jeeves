# modules/wordle.py
"""Daily collaborative six-letter Wordle game for IRC channels."""

from __future__ import annotations

import random
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc
WORD_LENGTH = 6
DEFAULT_MAX_ATTEMPTS = 3

Evaluation = List[str]


def setup(bot: Any) -> "Wordle":
    """Initialize the Wordle module."""
    return Wordle(bot)


class Wordle(SimpleCommandModule):
    """A daily community Wordle game with shared discoveries."""

    name = "wordle"
    version = "1.0.0"
    description = "Daily collaborative six-letter Wordle game."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        self.word_list_file = self.get_config_value(
            "word_list_file", default="wordle-six-letter-words.txt"
        )
        self.dictionary_file = self.get_config_value(
            "dictionary_file", default="/usr/share/dict/words"
        )
        self.max_attempts = int(
            self.get_config_value("max_attempts_per_user", default=DEFAULT_MAX_ATTEMPTS)
        )
        self.answer_words = self._load_word_set(self.word_list_file, required=True)
        self.valid_words = set(self.answer_words)
        self.valid_words.update(self._load_word_set(self.dictionary_file, required=False))

        if not self.answer_words:
            self.log_debug("Wordle answer list is empty; commands will report unavailability")

        self.set_state("used_words", self.get_state("used_words", []))
        self.set_state("today", self.get_state("today", None))
        self.set_state("stats", self.get_state("stats", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r"^\s*!word\s+stats\s*$",
            self._cmd_stats,
            name="word stats",
            description="Show your Wordle record.",
        )
        self.register_command(
            r"^\s*!word\s+top\s*$",
            self._cmd_top,
            name="word top",
            description="Show the Wordle leaderboard.",
        )
        self.register_command(
            r"^\s*!word\s+new\s*$",
            self._cmd_new_day,
            name="word new",
            admin_only=True,
            description="Force a new Wordle day.",
        )
        self.register_command(
            r"^\s*!word\s*$",
            self._cmd_status,
            name="word",
            description="Show today's Wordle discoveries.",
        )
        self.register_command(
            r"^\s*!word\s+(\S+)\s*$",
            self._cmd_guess,
            name="word guess",
            description="Guess today's six-letter word.",
        )

    def _load_word_set(self, configured_path: str, required: bool) -> Set[str]:
        path = self._resolve_path(configured_path)
        words: Set[str] = set()
        try:
            with path.open("r", encoding="utf-8", errors="ignore") as handle:
                for line in handle:
                    word = line.strip().lower()
                    if len(word) == WORD_LENGTH and word.isalpha():
                        words.add(word)
        except FileNotFoundError:
            severity = "ERROR" if required else "WARNING"
            self._record_error(f"Word list not found: {path}", severity=severity)
        except OSError as exc:
            severity = "ERROR" if required else "WARNING"
            self._record_error(f"Could not read word list {path}: {exc}", severity=severity)
        return words

    def _resolve_path(self, configured_path: str) -> Path:
        path = Path(configured_path).expanduser()
        if path.is_absolute():
            return path
        root = Path(getattr(self.bot, "ROOT", Path.cwd()))
        return root / path

    def _channel_available(self, channel: str) -> bool:
        joined_channels = getattr(self.bot, "joined_channels", set())
        return self.is_enabled(channel) and channel in joined_channels

    def _today_date(self) -> str:
        return datetime.now(UTC).date().isoformat()

    def _ensure_today(self, force_new: bool = False) -> Optional[Dict[str, Any]]:
        today = self.get_state("today")
        date = self._today_date()
        if not force_new and isinstance(today, dict) and today.get("date") == date:
            return today

        if not self.answer_words:
            return None

        used_words = self._normalized_used_words()
        available_words = sorted(self.answer_words - used_words)
        if not available_words:
            self._record_error("Wordle answer list exhausted; reusing from full list", severity="ERROR")
            available_words = sorted(self.answer_words)

        word = random.choice(available_words)
        used_words.add(word)
        today = {
            "date": date,
            "word": word,
            "solved": False,
            "solved_by": None,
            "guesses": {},
            "discovered": self._blank_discovered(),
        }
        self.set_state("used_words", sorted(used_words))
        self.set_state("today", today)
        self.save_state()
        return today

    def _normalized_used_words(self) -> Set[str]:
        raw = self.get_state("used_words", [])
        if isinstance(raw, dict):
            raw = raw.keys()
        if not isinstance(raw, Iterable) or isinstance(raw, (str, bytes)):
            return set()
        return {str(word).strip().lower() for word in raw if str(word).strip()}

    def _blank_discovered(self) -> Dict[str, Any]:
        return {
            "correct": [None] * WORD_LENGTH,
            "present": [],
            "absent": [],
        }

    @staticmethod
    def _evaluate_guess(guess: str, target: str) -> Evaluation:
        """Return Wordle statuses: correct, present, or absent for each letter."""
        statuses = ["absent"] * WORD_LENGTH
        remaining = Counter()

        for index, target_letter in enumerate(target):
            if guess[index] == target_letter:
                statuses[index] = "correct"
            else:
                remaining[target_letter] += 1

        for index, guess_letter in enumerate(guess):
            if statuses[index] == "correct":
                continue
            if remaining[guess_letter] > 0:
                statuses[index] = "present"
                remaining[guess_letter] -= 1

        return statuses

    def _compute_discovered(self, today: Dict[str, Any]) -> Dict[str, Any]:
        target = today.get("word", "")
        correct: List[Optional[str]] = [None] * WORD_LENGTH
        present_letters: Set[str] = set()
        absent_letters: Set[str] = set()

        guesses = today.get("guesses", {})
        if not isinstance(guesses, dict):
            guesses = {}

        for user_guesses in guesses.values():
            if not isinstance(user_guesses, list):
                continue
            for guess in user_guesses:
                if not isinstance(guess, str) or len(guess) != WORD_LENGTH:
                    continue
                statuses = self._evaluate_guess(guess, target)
                for index, status in enumerate(statuses):
                    letter = guess[index]
                    if status == "correct":
                        correct[index] = letter
                    elif status == "present":
                        present_letters.add(letter)
                    else:
                        absent_letters.add(letter)

        known_letters = set(letter for letter in correct if letter) | present_letters
        absent_letters -= known_letters
        return {
            "correct": correct,
            "present": sorted(present_letters - set(letter for letter in correct if letter)),
            "absent": sorted(absent_letters),
        }

    def _save_today(self, today: Dict[str, Any]) -> None:
        today["discovered"] = self._compute_discovered(today)
        self.set_state("today", today)
        self.save_state()

    def _format_pattern(self, correct: Sequence[Optional[str]]) -> str:
        return " ".join(letter if letter else "_" for letter in correct)

    def _format_word_list(self, letters: Sequence[str]) -> str:
        return ", ".join(letters) if letters else "none"

    def _solved_response(self, today: Dict[str, Any], username: Optional[str] = None) -> str:
        word = str(today.get("word", "")).upper()
        if username:
            title = self.bot.title_for(username)
            return f"Today's word was: {word}. Well deduced, {title}! Try again tomorrow."
        solved_by = today.get("solved_by")
        if solved_by:
            display = self._display_name_for_user(str(solved_by))
            return f"Today's word was: {word}. {display} has resolved the matter. Try again tomorrow."
        return f"Today's word was: {word}. Try again tomorrow."

    def _display_name_for_user(self, user_id: str) -> str:
        users_module = getattr(getattr(self.bot, "pm", None), "plugins", {}).get("users")
        if users_module:
            user_map = users_module.get_state("user_map", {})
            profile = user_map.get(user_id, {})
            nick = profile.get("canonical_nick")
            if nick:
                return str(nick)
        return "An unknown member of the household"

    def _get_user_stats(self, user_id: str) -> Dict[str, int]:
        stats = self.get_state("stats", {})
        user_stats = stats.get(user_id, {}) if isinstance(stats, dict) else {}
        return {
            "wins": int(user_stats.get("wins", 0)),
            "games_played": int(user_stats.get("games_played", 0)),
        }

    def _record_game_played(self, user_id: str) -> None:
        stats = self.get_state("stats", {})
        if not isinstance(stats, dict):
            stats = {}
        user_stats = stats.setdefault(user_id, {"wins": 0, "games_played": 0})
        user_stats.setdefault("wins", 0)
        user_stats["games_played"] = int(user_stats.get("games_played", 0)) + 1
        self.set_state("stats", stats)

    def _record_win(self, user_id: str) -> None:
        stats = self.get_state("stats", {})
        if not isinstance(stats, dict):
            stats = {}
        user_stats = stats.setdefault(user_id, {"wins": 0, "games_played": 0})
        user_stats["wins"] = int(user_stats.get("wins", 0)) + 1
        user_stats.setdefault("games_played", 0)
        self.set_state("stats", stats)

    def _cmd_status(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self._channel_available(event.target):
            return False
        today = self._ensure_today()
        if not today:
            self.safe_reply(connection, event, "I'm afraid the word list is unavailable, sir.")
            return True
        if today.get("solved"):
            self.safe_reply(connection, event, self._solved_response(today))
            return True

        discovered = today.get("discovered") or self._compute_discovered(today)
        pattern = self._format_pattern(discovered.get("correct", [None] * WORD_LENGTH))
        present = self._format_word_list(discovered.get("present", []))
        absent = self._format_word_list(discovered.get("absent", []))
        self.safe_reply(
            connection,
            event,
            f"Today's word: {pattern} — Letters present: {present} — Letters absent: {absent} — Solved? No",
        )
        return True

    def _cmd_guess(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self._channel_available(event.target):
            return False
        raw_guess = match.group(1).strip().lower()
        title = self.bot.title_for(username)

        if len(raw_guess) != WORD_LENGTH or not raw_guess.isalpha():
            self.safe_reply(connection, event, "A six-letter word is required, if you please, sir.")
            return True
        if raw_guess not in self.valid_words:
            self.safe_reply(connection, event, "I'm afraid that word isn't in my dictionary, sir.")
            return True

        today = self._ensure_today()
        if not today:
            self.safe_reply(connection, event, "I'm afraid the word list is unavailable, sir.")
            return True
        if today.get("solved"):
            self.safe_reply(connection, event, self._solved_response(today))
            return True

        user_id = self.bot.get_user_id(username)
        guesses = today.get("guesses")
        if not isinstance(guesses, dict):
            guesses = {}
            today["guesses"] = guesses
        user_guesses = guesses.get(user_id)
        if not isinstance(user_guesses, list):
            user_guesses = []
            guesses[user_id] = user_guesses
        if len(user_guesses) >= self.max_attempts:
            self.safe_reply(
                connection,
                event,
                f"I'm afraid you've exhausted your three attempts for today, {title}. Perhaps tomorrow will be kinder.",
            )
            return True

        if not user_guesses:
            self._record_game_played(user_id)
        user_guesses.append(raw_guess)

        statuses = self._evaluate_guess(raw_guess, today["word"])
        if raw_guess == today["word"]:
            today["solved"] = True
            today["solved_by"] = user_id
            self._record_win(user_id)
            self._save_today(today)
            self.save_state()
            self.safe_reply(connection, event, self._solved_response(today, username=username))
            return True

        self._save_today(today)
        self.save_state()
        response = self._format_guess_response(raw_guess, statuses, today["discovered"])
        self.safe_reply(connection, event, response)
        return True

    def _format_guess_response(
        self, guess: str, statuses: Evaluation, discovered: Dict[str, Any]
    ) -> str:
        matched = sum(1 for status in statuses if status in {"correct", "present"})
        exact = statuses.count("correct")
        pattern = self._format_pattern(discovered.get("correct", [None] * WORD_LENGTH))
        misplaced_letters = sorted({guess[index] for index, status in enumerate(statuses) if status == "present"})
        if misplaced_letters:
            verb = "is" if len(misplaced_letters) == 1 else "are"
            misplaced = f" and {', '.join(misplaced_letters)} {verb} in the wrong location"
        else:
            misplaced = ""
        return (
            f"The word contains {matched} of the {WORD_LENGTH} letters you picked, "
            f"{exact} of which were in the correct locations: {pattern}{misplaced}."
        )

    def _cmd_stats(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self._channel_available(event.target):
            return False
        user_id = self.bot.get_user_id(username)
        stats = self._get_user_stats(user_id)
        wins = stats["wins"]
        games = stats["games_played"]
        rate = int(round((wins / games) * 100)) if games else 0
        self.safe_reply(
            connection,
            event,
            f"{self.bot.title_for(username)}, your Wordle record stands at {wins} win{'s' if wins != 1 else ''} in {games} game{'s' if games != 1 else ''} ({rate}%).",
        )
        return True

    def _cmd_top(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self._channel_available(event.target):
            return False
        stats = self.get_state("stats", {})
        if not isinstance(stats, dict) or not stats:
            self.safe_reply(connection, event, "No Wordle laurels have yet been awarded.")
            return True

        leaders: List[Tuple[str, Dict[str, int]]] = []
        for user_id, values in stats.items():
            wins = int(values.get("wins", 0))
            games = int(values.get("games_played", 0))
            if wins > 0:
                leaders.append((user_id, {"wins": wins, "games_played": games}))

        if not leaders:
            self.safe_reply(connection, event, "No Wordle laurels have yet been awarded.")
            return True

        leaders.sort(key=lambda item: (-item[1]["wins"], item[1]["games_played"], item[0]))
        entries = []
        for user_id, values in leaders[:5]:
            entries.append(f"{self._display_name_for_user(user_id)} ({values['wins']})")
        self.safe_reply(connection, event, f"The household Wordle honours: {', '.join(entries)}")
        return True

    @admin_required
    def _cmd_new_day(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self._channel_available(event.target):
            return False
        today = self._ensure_today(force_new=True)
        if not today:
            self.safe_reply(connection, event, "I'm afraid the word list is unavailable, sir.")
            return True
        self.safe_reply(connection, event, "As you wish. A fresh Wordle has been laid out for the household.")
        return True
