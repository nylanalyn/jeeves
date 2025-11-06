# modules/fortune.py
# Fortune cookie module with natural language support and categories
import re
import random
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from .base import SimpleCommandModule, admin_required

def setup(bot: Any) -> 'Fortune':
    return Fortune(bot)

class Fortune(SimpleCommandModule):
    name = "fortune"
    version = "2.1.0" # Made ambient trigger more specific
    description = "Provides fortunes from a fortune cookie."
    
    CATEGORIES: List[str] = ["spooky", "happy", "sad", "silly", "sexy"]

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)

        self.set_state("last_fortune_time", self.get_state("last_fortune_time", {}))
        self.save_state()
        self._fortunes: Dict[str, List[str]] = {}
        self._load_all_fortunes()

    def on_config_reload(self, config: Dict[str, Any]) -> None:
        # Settings are now fetched on-demand via get_config_value
        pass

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!fortune(?:\s+(\w+))?\s*$", self._cmd_fortune,
                              name="fortune", description="Get a fortune. Use !fortune [category] for specific fortunes.")
        self.register_command(r"^\s*!fortune\s+reload\s*$", self._cmd_reload,
                              name="fortune reload", admin_only=True, description="Reload fortune files.")
    
    def _cmd_fortune(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        user_id = self.bot.get_user_id(username)
        cooldown = self.get_config_value("cooldown_seconds", event.target, default=10.0)

        if not self.check_user_cooldown(username, "fortune", cooldown):
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, please wait a moment before requesting another fortune.")
            return True

        category = match.group(1).lower() if match.group(1) else None
        self._give_fortune(connection, event, username, category)
        return True

    @admin_required
    def _cmd_reload(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        self._load_all_fortunes()
        total_loaded = sum(len(fortunes) for fortunes in self._fortunes.values())
        self.safe_reply(connection, event, f"Fortune files reloaded. {total_loaded} fortunes available.")
        return True

    def on_ambient_message(self, connection, event, msg: str, username: str) -> bool:
        if not self.is_enabled(event.target): return False

        cooldown = self.get_config_value("cooldown_seconds", event.target, default=10.0)

        # Ambient trigger now requires mentioning Jeeves AND the word "fortune".
        if self.check_user_cooldown(username, "fortune", cooldown) and self.is_mentioned(msg) and re.search(r"\bfortune\b", msg, re.IGNORECASE):
            category = self._extract_category_from_message(msg)
            self._give_fortune(connection, event, username, category)
            return True
        return False

    def _give_fortune(self, connection: Any, event: Any, username: str, category: Optional[str]) -> None:
        fortune_text, actual_category = self._get_fortune(category)
        if actual_category == "error":
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {fortune_text}")
            return
        response = self._format_fortune_response(username, fortune_text, actual_category)
        self.safe_reply(connection, event, response)

    def _load_all_fortunes(self) -> None:
        fortune_dir = Path(self.bot.ROOT) / "fortunes"
        if not fortune_dir.exists(): return
        self._fortunes.clear()
        for category in self.CATEGORIES:
            fortune_file = fortune_dir / f"{category}.txt"
            if fortune_file.exists():
                try:
                    content = fortune_file.read_text(encoding='utf-8').strip()
                    fortunes = [f.strip() for f in re.split(r'\n%\n|\n\n', content) if f.strip()]
                    self._fortunes[category] = fortunes
                except Exception as e:
                    self.log_debug(f"Failed to load fortune file for '{category}': {e}")
                    self._fortunes[category] = []

    def _get_fortune(self, category: Optional[str] = None) -> Tuple[str, str]:
        all_fortunes = [(fortune, cat) for cat, fortunes in self._fortunes.items() for fortune in fortunes]
        if not category:
            if not all_fortunes:
                return "I'm afraid the fortune crystal ball is clouded today.", "error"
            return random.choice(all_fortunes)
        
        category = category.lower()
        if category not in self.CATEGORIES:
            return f"I'm not familiar with '{category}' fortunes. Categories: {', '.join(self.CATEGORIES)}.", "error"
        
        fortunes = self._fortunes.get(category, [])
        if not fortunes:
            return f"I have no {category} fortunes available at the moment.", "error"
        
        return random.choice(fortunes), category

    def _format_fortune_response(self, username: str, fortune: str, category: str) -> str:
        title = self.bot.title_for(username)
        intros = {
            "spooky": f"{title}, the spirits whisper:",
            "happy": f"{title}, a most pleasant fortune awaits:",
            "sad": f"{title}, the omens are rather somber:",
            "silly": f"{title}, a rather whimsical fortune:",
            "sexy": f"{title}, a sultry fortune awaits:"
        }
        intro = intros.get(category, f"{title}, your fortune:")
        return f"{username}, {intro} {fortune}"

    def _extract_category_from_message(self, msg: str) -> Optional[str]:
        msg_lower = msg.lower()
        for category in self.CATEGORIES:
            if re.search(rf"\b{category}\b", msg_lower):
                return category
        return None
