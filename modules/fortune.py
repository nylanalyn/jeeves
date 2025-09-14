# modules/fortune.py
# Fortune cookie module with natural language support and categories
import re
import random
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

def setup(bot):
    return Fortune(bot)

class Fortune:
    name = "fortune"
    version = "1.0.0"
    
    # Configuration
    FORTUNE_DIR = Path(__file__).parent.parent / "fortunes"  # ../fortunes/ from modules/
    COOLDOWN_SECONDS = 10.0  # Per-user cooldown to prevent spam
    
    # Valid categories
    CATEGORIES = ["spooky", "happy", "sad", "silly"]
    
    def __init__(self, bot):
        self.bot = bot
        self.st = bot.get_module_state(self.name)
        
        # Initialize state
        self.st.setdefault("fortunes_given", 0)
        self.st.setdefault("category_counts", {cat: 0 for cat in self.CATEGORIES})
        self.st.setdefault("users_served", [])
        self.st.setdefault("last_fortune_time", {})
        
        # Fortune storage
        self._fortunes = {}
        self._last_reload = 0
        
        # Setup patterns
        self._setup_patterns()
        
        # Load fortunes
        self._load_all_fortunes()
        
        bot.save()
    
    def _setup_patterns(self):
        """Setup regex patterns for command and natural language detection."""
        name_pat = getattr(self.bot, "JEEVES_NAME_RE", r"(?:jeeves|jeevesbot)")
        
        # Command patterns
        self.RE_FORTUNE_SIMPLE = re.compile(r"^\s*!fortune\s*$", re.IGNORECASE)
        self.RE_FORTUNE_CATEGORY = re.compile(r"^\s*!fortune\s+(\w+)\s*$", re.IGNORECASE)
        
        # Natural language patterns
        category_pattern = "|".join(self.CATEGORIES)
        
        # "Jeeves, I would like a fortune please"
        self.RE_NL_FORTUNE_SIMPLE = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:i\s+(?:would\s+)?like|give\s+me|tell\s+me)\s+(?:a\s+)?fortune(?:\s+please)?\b",
            re.IGNORECASE
        )
        
        # "Jeeves, I would like a spooky fortune"
        self.RE_NL_FORTUNE_CATEGORY = re.compile(
            rf"\b{name_pat}[,!\s]*\s*(?:i\s+(?:would\s+)?like|give\s+me|tell\s+me)\s+(?:a\s+)?(?:({category_pattern})\s+)?fortune(?:\s+(?:that\s+is\s+)?({category_pattern}))?\b",
            re.IGNORECASE
        )
        
        # "Jeeves, fortune please" (shorter form)
        self.RE_NL_FORTUNE_SHORT = re.compile(
            rf"\b{name_pat}[,!\s]*\s*fortune(?:\s+please)?\b",
            re.IGNORECASE
        )
    
    def _load_all_fortunes(self):
        """Load all fortune files from the fortunes directory."""
        if not self.FORTUNE_DIR.exists():
            print(f"[fortune] Warning: Fortune directory {self.FORTUNE_DIR} does not exist")
            return
        
        self._fortunes.clear()
        
        for category in self.CATEGORIES:
            fortune_file = self.FORTUNE_DIR / f"{category}.txt"
            if fortune_file.exists():
                try:
                    with open(fortune_file, 'r', encoding='utf-8') as f:
                        content = f.read().strip()
                    
                    # Split on double newlines or % signs (traditional fortune format)
                    if '\n%\n' in content:
                        fortunes = [f.strip() for f in content.split('\n%\n') if f.strip()]
                    else:
                        fortunes = [f.strip() for f in content.split('\n\n') if f.strip()]
                    
                    self._fortunes[category] = fortunes
                    print(f"[fortune] Loaded {len(fortunes)} {category} fortunes")
                    
                except Exception as e:
                    print(f"[fortune] Error loading {category} fortunes: {e}")
                    self._fortunes[category] = []
            else:
                print(f"[fortune] Warning: {fortune_file} not found")
                self._fortunes[category] = []
        
        self._last_reload = os.path.getmtime(self.FORTUNE_DIR) if self.FORTUNE_DIR.exists() else 0
    
    def _reload_if_needed(self):
        """Reload fortunes if files have been modified."""
        if not self.FORTUNE_DIR.exists():
            return
        
        try:
            current_mtime = os.path.getmtime(self.FORTUNE_DIR)
            if current_mtime > self._last_reload:
                print("[fortune] Fortune files modified, reloading...")
                self._load_all_fortunes()
        except OSError:
            pass  # Directory may not exist or be inaccessible
    
    def _can_give_fortune(self, username: str) -> bool:
        """Check if user is off cooldown for fortune requests."""
        if self.COOLDOWN_SECONDS <= 0:
            return True
        
        import time
        now = time.time()
        last_times = self.st.get("last_fortune_time", {})
        last_time = last_times.get(username.lower(), 0)
        
        return now - last_time >= self.COOLDOWN_SECONDS
    
    def _mark_fortune_given(self, username: str, category: Optional[str] = None):
        """Mark that a fortune was given to this user."""
        import time
        
        # Update cooldown
        last_times = self.st.get("last_fortune_time", {})
        last_times[username.lower()] = time.time()
        self.st["last_fortune_time"] = last_times
        
        # Update stats
        self.st["fortunes_given"] = self.st.get("fortunes_given", 0) + 1
        
        if category:
            counts = self.st.get("category_counts", {})
            counts[category] = counts.get(category, 0) + 1
            self.st["category_counts"] = counts
        
        # Track unique users
        users = self.st.get("users_served", [])
        username_lower = username.lower()
        if username_lower not in users:
            users.append(username_lower)
            self.st["users_served"] = users
        
        self.bot.save()
    
    def _get_fortune(self, category: Optional[str] = None) -> Tuple[str, str]:
        """Get a fortune, optionally from a specific category."""
        self._reload_if_needed()
        
        # If no category specified, pick randomly from all
        if not category:
            all_fortunes = []
            all_categories = []
            
            for cat, fortunes in self._fortunes.items():
                if fortunes:  # Only include categories that have fortunes
                    all_fortunes.extend(fortunes)
                    all_categories.extend([cat] * len(fortunes))
            
            if not all_fortunes:
                return "I'm afraid the fortune crystal ball is clouded today.", "unknown"
            
            idx = random.randint(0, len(all_fortunes) - 1)
            return all_fortunes[idx], all_categories[idx]
        
        # Specific category requested
        category = category.lower()
        if category not in self.CATEGORIES:
            return f"I'm not familiar with {category} fortunes. Available categories: {', '.join(self.CATEGORIES)}.", "error"
        
        fortunes = self._fortunes.get(category, [])
        if not fortunes:
            return f"I'm afraid I have no {category} fortunes available at the moment.", "error"
        
        fortune = random.choice(fortunes)
        return fortune, category
    
    def _format_fortune_response(self, username: str, fortune: str, category: str) -> str:
        """Format the fortune response with appropriate butler flair."""
        title = self.bot.title_for(username)
        
        if category == "error":
            return f"{username}, {fortune}"
        
        # Butler-style introductions based on category
        intros = {
            "spooky": [
                f"{username}, the spirits whisper this to me, {title}:",
                f"{username}, from the shadows comes this wisdom, {title}:",
                f"{username}, a most unsettling fortune, {title}:",
                f"{username}, the crystal ball grows dark and reveals, {title}:"
            ],
            "happy": [
                f"{username}, a most pleasant fortune awaits, {title}:",
                f"{username}, the stars smile favorably upon you, {title}:",
                f"{username}, here's a delightful prospect, {title}:",
                f"{username}, fortune smiles brightly today, {title}:"
            ],
            "sad": [
                f"{username}, I'm afraid the omens are rather somber, {title}:",
                f"{username}, with gentle sympathy I share this, {title}:",
                f"{username}, the cards reveal a melancholy truth, {title}:",
                f"{username}, a bittersweet fortune, {title}:"
            ],
            "silly": [
                f"{username}, a rather whimsical fortune, {title}:",
                f"{username}, the cosmic jesters have spoken, {title}:",
                f"{username}, here's something delightfully absurd, {title}:",
                f"{username}, fortune has a sense of humor today, {title}:"
            ]
        }
        
        intro_options = intros.get(category, [f"{username}, your fortune, {title}:"])
        intro = random.choice(intro_options)
        
        return f"{intro} {fortune}"
    
    def _extract_category_from_message(self, msg: str) -> Optional[str]:
        """Extract category from natural language message."""
        msg_lower = msg.lower()
        
        # Look for category words in the message
        for category in self.CATEGORIES:
            if category in msg_lower:
                return category
        
        return None
    
    def on_load(self):
        self._load_all_fortunes()
    
    def on_unload(self):
        self._fortunes.clear()
    
    def on_pubmsg(self, connection, event, msg, username):
        room = event.target
        
        # Admin stats command
        if self.bot.is_admin(username) and msg.strip().lower() == "!fortune stats":
            stats = self.st
            total_given = stats.get("fortunes_given", 0)
            unique_users = len(stats.get("users_served", []))
            
            lines = [f"Total fortunes given: {total_given}", f"Unique users served: {unique_users}"]
            
            # Category breakdown
            counts = stats.get("category_counts", {})
            if counts and any(counts.values()):
                category_stats = ", ".join(f"{cat}:{count}" for cat, count in counts.items() if count > 0)
                lines.append(f"By category: {category_stats}")
            
            # Fortune availability
            available = sum(len(fortunes) for fortunes in self._fortunes.values())
            lines.append(f"Available fortunes: {available}")
            
            connection.privmsg(room, f"Fortune stats: {'; '.join(lines)}")
            return True
        
        # Admin reload command
        if self.bot.is_admin(username) and msg.strip().lower() == "!fortune reload":
            self._load_all_fortunes()
            total_loaded = sum(len(fortunes) for fortunes in self._fortunes.values())
            connection.privmsg(room, f"Fortune files reloaded. {total_loaded} fortunes available.")
            return True
        
        # Check cooldown
        if not self._can_give_fortune(username):
            return False
        
        category = None
        handled = False
        
        # Simple command: !fortune
        if self.RE_FORTUNE_SIMPLE.match(msg):
            handled = True
        
        # Category command: !fortune spooky
        elif match := self.RE_FORTUNE_CATEGORY.match(msg):
            category = match.group(1).lower()
            if category in self.CATEGORIES:
                handled = True
        
        # Natural language: "Jeeves, I would like a fortune please"
        elif self.RE_NL_FORTUNE_SIMPLE.search(msg):
            handled = True
            category = self._extract_category_from_message(msg)
        
        # Natural language with category: "Jeeves, I would like a spooky fortune"
        elif match := self.RE_NL_FORTUNE_CATEGORY.search(msg):
            handled = True
            # Could have category in either capture group
            category = match.group(1) or match.group(2)
            if category:
                category = category.lower()
                if category not in self.CATEGORIES:
                    category = None
        
        # Short form: "Jeeves, fortune please"
        elif self.RE_NL_FORTUNE_SHORT.search(msg):
            handled = True
            category = self._extract_category_from_message(msg)
        
        if handled:
            fortune, actual_category = self._get_fortune(category)
            response = self._format_fortune_response(username, fortune, actual_category)
            
            if actual_category != "error":
                self._mark_fortune_given(username, actual_category)
            
            connection.privmsg(room, response)
            return True
        
        return False