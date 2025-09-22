# modules/fortune.py
# Fortune cookie module with natural language support and categories
import re
import random
import os
import functools
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .base import SimpleCommandModule, admin_required

def setup(bot, config):
    return Fortune(bot, config)

class Fortune(SimpleCommandModule):
    name = "fortune"
    version = "1.3.0"
    description = "Provides fortunes from a fortune cookie."
    
    FORTUNE_DIR = Path(__file__).parent.parent / "fortunes"
    CATEGORIES = ["spooky", "happy", "sad", "silly"]
    
    def __init__(self, bot, config):
        super().__init__(bot)
        self.COOLDOWN_SECONDS = config.get("cooldown_seconds", 10.0)
        self.set_state("fortunes_given", self.get_state("fortunes_given", 0))
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
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, please wait a moment before requesting another fortune.")
            return True
        category = match.group(1).lower() if match.group(1) else None
        self._give_fortune(connection, event, username, category)
        return True

    @admin_required
    def _cmd_stats(self, connection, event, msg, username, match):
        total_given = self.get_state("fortunes_given", 0)
        available = sum(len(fortunes) for fortunes in self._fortunes.values())
        self.safe_reply(connection, event, f"Fortune stats: {total_given} fortunes given, {available} available.")
        return True

    @admin_required
    def _cmd_reload(self, connection, event, msg, username, match):
        self._load_all_fortunes()
        total_loaded = sum(len(fortunes) for fortunes in self._fortunes.values())
        self.safe_reply(connection, event, f"Fortune files reloaded. {total_loaded} fortunes available.")
        return True

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if self._can_give_fortune(username) and self.is_mentioned(msg):
            category = self._extract_category_from_message(msg)
            if category or re.search(r"\bfortune", msg, re.IGNORECASE):
                self._give_fortune(connection, event, username, category)
                return True
        return False

    def _give_fortune(self, connection, event, username, category):
        fortune_text, actual_category = self._get_fortune(category)
        if actual_category == "error":
            self.safe_reply(connection, event, fortune_text)
            return
        response = self._format_fortune_response(username, fortune_text, actual_category)
        self._mark_fortune_given(username)
        self.safe_reply(connection, event, response)

    def _load_all_fortunes(self):
        if not self.FORTUNE_DIR.exists(): return
        self._fortunes.clear()
        for category in self.CATEGORIES:
            fortune_file = self.FORTUNE_DIR / f"{category}.txt"
            if fortune_file.exists():
                try:
                    content = fortune_file.read_text(encoding='utf-8').strip()
                    if '\n%\n' in content:
                        fortunes = [f.strip() for f in content.split('\n%\n') if f.strip()]
                    else:
                        fortunes = [f.strip() for f in content.split('\n\n') if f.strip()]
                    self._fortunes[category] = fortunes
                except Exception:
                    self._fortunes[category] = []
        self._last_reload = os.path.getmtime(self.FORTUNE_DIR) if self.FORTUNE_DIR.exists() else 0

    def _reload_if_needed(self):
        if not self.FORTUNE_DIR.exists(): return
        try:
            if os.path.getmtime(self.FORTUNE_DIR) > self._last_reload:
                self._load_all_fortunes()
        except OSError: pass

    def _can_give_fortune(self, username: str) -> bool:
        if self.COOLDOWN_SECONDS <= 0: return True
        now = time.time()
        last_times = self.get_state("last_fortune_time", {})
        return now - last_times.get(username.lower(), 0) >= self.COOLDOWN_SECONDS

    def _mark_fortune_given(self, username: str):
        last_times = self.get_state("last_fortune_time", {})
        last_times[username.lower()] = time.time()
        self.set_state("last_fortune_time", last_times)
        self.set_state("fortunes_given", self.get_state("fortunes_given", 0) + 1)
        self.save_state()

    def _get_fortune(self, category: Optional[str] = None) -> Tuple[str, str]:
        self._reload_if_needed()
        if not category:
            all_fortunes = [(fortune, cat) for cat, fortunes in self._fortunes.items() for fortune in fortunes]
            if not all_fortunes:
                return "I'm afraid the fortune crystal ball is clouded today.", "error"
            return random.choice(all_fortunes)
        
        category = category.lower()
        if category not in self.CATEGORIES:
            return f"I'm not familiar with {category} fortunes. Available categories: {', '.join(self.CATEGORIES)}.", "error"
        
        fortunes = self._fortunes.get(category, [])
        if not fortunes:
            return f"I'm afraid I have no {category} fortunes available at the moment.", "error"
        
        return random.choice(fortunes), category

    def _format_fortune_response(self, username: str, fortune: str, category: str) -> str:
        title = self.bot.title_for(username)
        intros = {"spooky": f"{title}, the spirits whisper:", "happy": f"{title}, a most pleasant fortune awaits:", "sad": f"{title}, the omens are rather somber:", "silly": f"{title}, a rather whimsical fortune:"}
        intro = intros.get(category, f"{title}, your fortune:")
        return f"{username}, {intro} {fortune}"

    def _extract_category_from_message(self, msg: str) -> Optional[str]:
        msg_lower = msg.lower()
        for category in self.CATEGORIES:
            if category in msg_lower:
                return category
        return None

