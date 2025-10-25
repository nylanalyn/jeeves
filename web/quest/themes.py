# web/quest/themes.py
# Theme management for quest web UI

from typing import Dict, Any, List
from pathlib import Path


DEFAULT_THEME: Dict[str, Any] = {
    "name": "midnight-spire",
    "background": "#050712",
    "foreground": "#f8fafc",
    "accent": "#f97316",
    "accent_text": "#0b0f19",
    "card_background": "#0f1526",
    "card_border": "#f97316",
    "table_header": "#162040",
    "table_stripe": "#121a33",
    "link": "#fb923c",
    "link_hover": "#fbbf24",
    "prestige_tiers": [
        {
            "max": 3,
            "icon": "★",
            "class": "tier-star",
            "color": "#fb923c",
            "repeat": 3,
            "banner": None,
        },
        {
            "max": 6,
            "icon": "☠",
            "class": "tier-skull",
            "color": "#facc15",
            "repeat": 3,
            "banner": "shroud",
        },
        {
            "max": 10,
            "icon": "♚",
            "class": "tier-crown",
            "color": "#c084fc",
            "repeat": 4,
            "banner": "imperial",
        },
    ],
}


class ThemeManager:
    """Manages themes for the quest web UI."""

    def __init__(self, content_path: Path):
        self.content_path = content_path
        self.theme = self._load_theme()

    def _load_theme(self) -> Dict[str, Any]:
        """Load theme from content file or use default."""
        theme_file = self.content_path / "theme.json"

        if theme_file.exists():
            try:
                import json
                with open(theme_file, 'r') as f:
                    loaded_theme = json.load(f)
                    # Merge with default to ensure all required keys exist
                    theme = DEFAULT_THEME.copy()
                    theme.update(loaded_theme)
                    return theme
            except (json.JSONDecodeError, IOError):
                # Fall back to default theme
                pass

        return DEFAULT_THEME.copy()

    def get_theme(self) -> Dict[str, Any]:
        """Get the current theme."""
        return self.theme

    def get_prestige_tier(self, prestige: int) -> Dict[str, Any]:
        """Get prestige tier information for a given prestige level."""
        for tier in reversed(self.theme["prestige_tiers"]):
            if prestige <= tier["max"]:
                return tier
        return self.theme["prestige_tiers"][-1]  # Return highest tier

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
            rule = f""".tier-{tier["class"]} {{
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


def load_theme(content_path: Path) -> Dict[str, Any]:
    """Legacy function for backward compatibility."""
    theme_manager = ThemeManager(content_path)
    return theme_manager.get_theme()