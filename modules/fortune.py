# modules/fortune.py
# Fortune cookie module with natural language support and categories
import re
import random
import os
import functools
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .base import SimpleCommandModule, ResponseModule, admin_required

def setup(bot, config):
    return Fortune(bot, config)

class Fortune(SimpleCommandModule):
    name = "fortune"
    version = "1.3.0" # version bumped for refactor
    description = "Provides fortunes from a fortune cookie."
    
    FORTUNE_DIR = Path(__file__).parent.parent / "fortunes"
    CATEGORIES = ["spooky", "happy", "sad", "silly"]
    
    def __init__(self, bot, config):
        super().__init__(bot)
        self.COOLDOWN_SECONDS = config.get("cooldown_seconds", 10.0)
        self.set_state("fortunes_given", self.get_state("fortunes_given", 0))
        self.set_state("category_counts", self.get_state("category_counts", {cat: 0 for cat in self.CATEGORIES}))
        self.set_state("users_served", self.get_state("users_served", []))
        self.set_state("last_fortune_time", self.get_state("last_fortune_time", {}))
        self.save_state()
        self._fortunes = {}
        self._last_reload = 0
        self._load_all_fortunes()

    def _register_commands(self):
        self.register_command(r"^\s*!fortune(?:\s+(\w+))?\s*$", self._cmd_fortune, 
                              name="fortune", description="Get a fortune. Use !fortune [category] for specific fortunes.")
        self.register_command(r"^\s*!fortune\s+stats\s*$", self._cmd_stats,
                              name="fortune stats", admin_only=True, description="Show fortune statistics.")
        self.register_command(r"^\s*!fortune\s+reload\s*$", self._cmd_reload,
                              name="fortune reload", admin_only=True, description="Reload fortune files.")
    
    def _cmd_fortune(self, connection, event, msg, username, match):
        if not self._can_give_fortune(username):
            self.safe_reply(connection, event, f"{username}, please wait a moment before requesting another fortune.")
            return True
        category = match.group(1).lower() if match.group(1) else None
        fortune_text, actual_category = self._get_fortune(category)
        if actual_category == "error":
            self.safe_reply(connection, event, fortune_text)
            return True
        response = self._format_fortune_response(username, fortune_text, actual_category)
        self._mark_fortune_given(username, actual_category)
        self.safe_reply(connection, event, response)
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        stats = self.get_state()
        total_given = stats.get("fortunes_given", 0)
        unique_users = len(stats.get("users_served", []))
        lines = [f"Total fortunes given: {total_given}", f"Unique users served: {unique_users}"]
        counts = stats.get("category_counts", {})
        if counts and any(counts.values()):
            category_stats = ", ".join(f"{cat}:{count}" for cat, count in counts.items() if count > 0)
            lines.append(f"By category: {category_stats}")
        available = sum(len(fortunes) for fortunes in self._fortunes.values())
        lines.append(f"Available fortunes: {available}")
        self.safe_reply(connection, event, f"Fortune stats: {'; '.join(lines)}")
        return True

    @admin_required
    def _cmd_reload(self, connection, event, msg, username, match):
        self._load_all_fortunes()
        total_loaded = sum(len(fortunes) for fortunes in self._fortunes.values())
        self.safe_reply(connection, event, f"Fortune files reloaded. {total_loaded} fortunes available.")
        return True

    def on_ambient_message(self, connection, event, msg, username):
        if self._can_give_fortune(username) and self.is_mentioned(msg):
            category = self._extract_category_from_message(msg)
            if category or re.search(r"\bfortune", msg, re.IGNORECASE):
                fortune_text, actual_category = self._get_fortune(category)
                if actual_category == "error":
                    self.safe_reply(connection, event, fortune_text)
                    return True
                response = self._format_fortune_response(username, fortune_text, actual_category)
                self._mark_fortune_given(username, actual_category)
                self.safe_reply(connection, event, response)
                return True
        return False

    def _load_all_fortunes(self):
        if not self.FORTUNE_DIR.exists(): return
        self._fortunes.clear()
        for category in self.CATEGORIES:
            fortune_file = self.FORTUNE_DIR / f"{category}.txt"
            if fortune_file.exists():
                try:
                    with open(fortune_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    if '\n%\n' in content:
                        fortunes = [f.strip() for f in content.split('\n%\n') if f.strip()]
                    else:
                        fortunes = [f.strip() for f in content.split('\n\n') if f.strip()]
                    self._fortunes[category] = fortunes
                except Exception as e:
                    self._fortunes[category] = []
        self._last_reload = os.path.getmtime(self.FORTUNE_DIR) if self.FORTUNE_DIR.exists() else 0

    def _reload_if_needed(self):
        if not self.FORTUNE_DIR.exists(): return
        try:
            current_mtime = os.path.getmtime(self.FORTUNE_DIR)
            if current_mtime > self._last_reload:
                self._load_all_fortunes()
        except OSError: pass

    def _can_give_fortune(self, username: str) -> bool:
        if self.COOLDOWN_SECONDS <= 0: return True
        now = time.time()
        last_times = self.get_state("last_fortune_time", {})
        last_time = last_times.get(username.lower(), 0)
        return now - last_time >= self.COOLDOWN_SECONDS

    def _mark_fortune_given(self, username: str, category: Optional[str] = None):
        last_times = self.get_state("last_fortune_time", {})
        last_times[username.lower()] = time.time()
        self.set_state("last_fortune_time", last_times)
        self.set_state("fortunes_given", self.get_state("fortunes_given", 0) + 1)
        if category:
            counts = self.get_state("category_counts", {})
            counts[category] = counts.get(category, 0) + 1
            self.set_state("category_counts", counts)
        users = self.get_state("users_served", [])
        username_lower = username.lower()
        if username_lower not in users:
            users.append(username_lower)
            self.set_state("users_served", users)
        self.save_state()

    def _get_fortune(self, category: Optional[str] = None) -> Tuple[str, str]:
        self._reload_if_needed()
        if not category:
            all_fortunes = []
            all_categories = []
            for cat, fortunes in self._fortunes.items():
                if fortunes:
                    all_fortunes.extend(fortunes)
                    all_categories.extend([cat] * len(fortunes))
            if not all_fortunes:
                return "I'm afraid the fortune crystal ball is clouded today.", "error"
            idx = random.randint(0, len(all_fortunes) - 1)
            return all_fortunes[idx], all_categories[idx]
        category = category.lower()
        if category not in self.CATEGORIES:
            return f"I'm not familiar with {category} fortunes. Available categories: {', '.join(self.CATEGORIES)}.", "error"
        fortunes = self._fortunes.get(category, [])
        if not fortunes:
            return f"I'm afraid I have no {category} fortunes available at the moment.", "error"
        fortune = random.choice(fortunes)
        return fortune, category

    def _format_fortune_response(self, username: str, fortune: str, category: str) -> str:
        title = self.bot.title_for(username)
        if category == "error": return f"{username}, {fortune}"
        intros = {"spooky": [f"{username}, the spirits whisper this to me, {title}:", f"{username}, from the shadows comes this wisdom, {title}:", f"{username}, a most unsettling fortune, {title}:", f"{username}, the crystal ball grows dark and reveals, {title}:"],"happy": [f"{username}, a most pleasant fortune awaits, {title}:", f"{username}, the stars smile favorably upon you, {title}:", f"{username}, here's a delightful prospect, {title}:", f"{username}, fortune smiles brightly today, {title}:"],"sad": [f"{username}, I'm afraid the omens are rather somber, {title}:", f"{username}, with gentle sympathy I share this, {title}:", f"{username}, the cards reveal a melancholy truth, {title}:", f"{username}, a bittersweet fortune, {title}:"],"silly": [f"{username}, a rather whimsical fortune, {title}:", f"{username}, the cosmic jesters have spoken, {title}:", f"{username}, here's something delightfully absurd, {title}:", f"{username}, fortune has a sense of humor today, {title}:"]}
        intro_options = intros.get(category, [f"{username}, your fortune, {title}:"])
        intro = random.choice(intro_options)
        return f"{intro} {fortune}"

    def _extract_category_from_message(self, msg: str) -> Optional[str]:
        msg_lower = msg.lower()
        for category in self.CATEGORIES:
            if category in msg_lower:
                return category
        return None
