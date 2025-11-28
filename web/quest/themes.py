# web/quest/themes.py
# Theme management for quest web UI

import json
from copy import deepcopy
from typing import Dict, Any, List, Optional
from pathlib import Path

import yaml


DEFAULT_THEME: Dict[str, Any] = {
    "name": "noir_november",
    "background": "#070708",
    "foreground": "#f2f2f2",
    "accent": "#c5a880",
    "accent_text": "#111113",
    "card_background": "#121316",
    "card_border": "#c5a880",
    "table_header": "#1d1e22",
    "table_stripe": "#151619",
    "link": "#d8c3a5",
    "link_hover": "#f1dcc1",
    "prestige_tiers": [
        {
            "max": 3,
            "icon": "📜",
            "class": "tier-casefile",
            "color": "#c5a880",
            "repeat": 3,
            "banner": None,
        },
        {
            "max": 6,
            "icon": "🔍",
            "class": "tier-magnifier",
            "color": "#f2f2f2",
            "repeat": 3,
            "banner": "shadow",
        },
        {
            "max": None,
            "icon": "🛡️",
            "class": "tier-shield",
            "color": "#ffd166",
            "repeat": 2,
            "banner": "badge",
        },
    ],
}


class ThemeManager:
    """Manages themes for the quest web UI."""

    def __init__(self, content_path: Path):
        self.content_path = content_path
        self.active_theme_key: Optional[str] = None
        self.available_theme_keys: List[str] = []
        self.theme = self._load_theme()

    def _load_theme(self) -> Dict[str, Any]:
        """Load theme configuration with graceful fallback."""
        theme = self._load_from_quest_content()
        if theme:
            return theme

        theme = self._load_from_legacy_theme_file()
        if theme:
            return theme

        return deepcopy(DEFAULT_THEME)

    def _load_from_quest_content(self) -> Optional[Dict[str, Any]]:
        """Attempt to load theme data from quest_content.json consolidated themes."""
        content_file = self.content_path / "quest_content.json"

        if not content_file.exists():
            return None

        try:
            with open(content_file, "r", encoding="utf-8") as f:
                content = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        if not isinstance(content, dict):
            return None

        themes = content.get("themes")
        if isinstance(themes, dict) and themes:
            self.available_theme_keys = list(themes.keys())
            default_theme = content.get("default_theme")
            configured_theme = self._read_configured_theme(default_theme)
            selected_theme = configured_theme or default_theme

            if selected_theme not in themes:
                # Fall back gracefully to default or first entry
                selected_theme = default_theme or next(iter(themes.keys()))

            theme_bundle = themes.get(selected_theme)
            if isinstance(theme_bundle, dict):
                theme_data = theme_bundle.get("theme")
                merged = self._merge_theme(theme_data)
                if merged:
                    self.active_theme_key = selected_theme
                    return merged

        # Legacy structure: quest_content.json already contains theme dict at top-level
        legacy_theme = content.get("theme")
        merged = self._merge_theme(legacy_theme)
        if merged:
            self.active_theme_key = legacy_theme.get("name") if isinstance(legacy_theme, dict) else None
            return merged

        return None

    def _load_from_legacy_theme_file(self) -> Optional[Dict[str, Any]]:
        """Fallback to standalone theme.json if present."""
        theme_file = self.content_path / "theme.json"
        if not theme_file.exists():
            return None

        try:
            with open(theme_file, "r", encoding="utf-8") as f:
                loaded_theme = json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

        self.active_theme_key = loaded_theme.get("name") if isinstance(loaded_theme, dict) else None
        return self._merge_theme(loaded_theme)

    def _merge_theme(self, override: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Merge provided theme override with defaults."""
        if not isinstance(override, dict):
            return None

        theme = deepcopy(DEFAULT_THEME)
        for key, value in override.items():
            if key == "prestige_tiers" and isinstance(value, list):
                theme["prestige_tiers"] = value
            else:
                theme[key] = value
        theme.setdefault("name", override.get("name"))
        return theme

    def _read_configured_theme(self, fallback: Optional[str]) -> Optional[str]:
        """Read the active theme key from config.yaml if available."""
        config_candidates = [
            self.content_path / "config" / "config.yaml",
            self.content_path / "config.yaml",
        ]

        for config_path in config_candidates:
            if not config_path.exists():
                continue
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_data = yaml.safe_load(f) or {}
            except yaml.YAMLError:
                continue
            except OSError:
                continue

            quest_config = config_data.get("quest")
            if isinstance(quest_config, dict):
                theme_key = quest_config.get("theme")
                if isinstance(theme_key, str) and theme_key.strip():
                    return theme_key.strip()

        return fallback

    def get_theme(self) -> Dict[str, Any]:
        """Get the current theme."""
        return self.theme

    def get_prestige_tier(self, prestige: int) -> Dict[str, Any]:
        """Get prestige tier information for a given prestige level."""
        # Iterate forward through tiers to find the first tier that fits
        for tier in self.theme["prestige_tiers"]:
            max_val = tier.get("max")
            if max_val is None or prestige <= max_val:
                return tier
        # If prestige exceeds all tiers, return the highest tier
        return self.theme["prestige_tiers"][-1]

    def get_prestige_icons(self, prestige: int) -> str:
        """Get formatted prestige icons for display."""
        tier = self.get_prestige_tier(prestige)
        icons = tier["icon"] * tier["repeat"]
        return f'<span class="tier {tier["class"]}" style="color: {tier["color"]}">{icons}</span>'

    def get_prestige_banner(self, prestige: int) -> str:
        """Get prestige banner if applicable."""
        tier = self.get_prestige_tier(prestige)
        if tier.get("banner"):
            return f'<div class="prestige-banner banner-{tier["banner"]}">{tier["banner"].upper()}</div>'
        return ""

    def get_css_variables(self) -> str:
        """Generate CSS variables from theme."""
        css_vars = []
        for key, value in self.theme.items():
            if key != "prestige_tiers":
                css_var = f"--{key}: {value};"
                css_vars.append(css_var)
        return "\n".join(css_vars)

    def get_prestige_css(self) -> str:
        """Generate CSS for prestige tiers."""
        css_rules = []
        for i, tier in enumerate(self.theme["prestige_tiers"]):
            # Fix class name extraction to remove "tier-" prefix if already in class
            class_name = tier["class"].replace("tier-", "")
            rule = f""".tier-{class_name} {{
    color: {tier["color"]};
    text-shadow: 0 0 10px {tier["color"]};
}}"""
            css_rules.append(rule)

            # Banner styling
            if tier.get("banner"):
                css_rules.append(f""".banner-{tier["banner"]} {{
    background: linear-gradient(135deg, {tier["color"]}, transparent);
    color: {self.theme["foreground"]};
    padding: 4px 12px;
    border-radius: 4px;
    font-weight: bold;
    text-transform: uppercase;
    font-size: 0.8em;
    margin: 8px 0;
}}""")

        return "\n".join(css_rules)

    def get_website_title(self) -> str:
        """Get website title from theme."""
        return self.theme.get("website_title", "Jeeves Quest")

    def get_website_subtitle(self) -> str:
        """Get website subtitle from theme."""
        return self.theme.get("website_subtitle", "Adventure awaits!")

    def get_website_decoration_left(self) -> str:
        """Get left decoration emoji/symbol from theme."""
        return self.theme.get("website_decoration_left", "⚔️")

    def get_website_decoration_right(self) -> str:
        """Get right decoration emoji/symbol from theme."""
        return self.theme.get("website_decoration_right", "🛡️")

    def get_website_footer(self) -> str:
        """Get website footer text from theme."""
        return self.theme.get("website_footer", "Powered by Jeeves IRC Bot | Quest System v6.0")

    def get_website_footer_tagline(self) -> str:
        """Get website footer tagline from theme."""
        return self.theme.get("website_footer_tagline", "Adventure awaits...")


def load_theme(content_path: Path) -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    theme_manager = ThemeManager(content_path)
    return theme_manager.get_theme()
