# web/quest/themes.py
# Theme management for quest web UI

import html
import json
import re
from copy import deepcopy
from typing import Dict, Any, List, Optional
from pathlib import Path

import yaml


def sanitize_css_value(value: str) -> str:
    """
    Sanitize a CSS value to prevent CSS injection attacks.

    Only allows safe CSS values: colors (hex, rgb, rgba, named colors),
    numbers with units (px, em, rem, %, etc.), and a limited set of safe keywords.
    """
    if not isinstance(value, str):
        value = str(value)

    value = value.strip()

    # Allow hex colors
    if re.match(r'^#[0-9a-fA-F]{3,8}$', value):
        return value

    # Allow rgb/rgba colors with strict validation
    rgb_match = re.match(r'^(rgba?)\s*\(([^)]+)\)$', value, re.IGNORECASE)
    if rgb_match:
        func_name = rgb_match.group(1).lower()
        inner_content = rgb_match.group(2).strip()

        # Split by comma and validate each component
        components = [c.strip() for c in inner_content.split(',')]

        # RGB requires 3 components, RGBA requires 4
        expected_count = 4 if func_name == 'rgba' else 3
        if len(components) != expected_count:
            return ''

        # Validate each component
        for i, component in enumerate(components):
            # Last component of RGBA is alpha (0-1 or 0%-100%)
            if func_name == 'rgba' and i == 3:
                # Alpha: decimal 0-1 or percentage 0%-100%
                if component.endswith('%'):
                    try:
                        num = float(component[:-1])
                        if not (0 <= num <= 100):
                            return ''
                    except ValueError:
                        return ''
                else:
                    try:
                        num = float(component)
                        if not (0 <= num <= 1):
                            return ''
                    except ValueError:
                        return ''
            else:
                # RGB components: integer 0-255 or percentage 0%-100%
                if component.endswith('%'):
                    try:
                        num = float(component[:-1])
                        if not (0 <= num <= 100):
                            return ''
                    except ValueError:
                        return ''
                else:
                    # Must be integer (no decimals for RGB values)
                    if not re.match(r'^\d+$', component):
                        return ''
                    try:
                        num = int(component)
                        if not (0 <= num <= 255):
                            return ''
                    except ValueError:
                        return ''

        # All validations passed, return the original value
        return value

    # Allow numbers with units
    if re.match(r'^-?\d+\.?\d*(px|em|rem|%|vh|vw|vmin|vmax|ch|ex|cm|mm|in|pt|pc|s|ms)?$', value):
        return value

    # Allow safe CSS keywords (limited set)
    safe_keywords = {
        'inherit', 'initial', 'unset', 'auto', 'none', 'transparent',
        'bold', 'normal', 'italic', 'uppercase', 'lowercase', 'capitalize',
        'center', 'left', 'right', 'top', 'bottom', 'middle',
        'block', 'inline', 'inline-block', 'flex', 'grid', 'absolute', 'relative', 'fixed'
    }
    if value.lower() in safe_keywords:
        return value

    # If the value doesn't match any safe pattern, return empty string
    return ''


def sanitize_css_identifier(identifier: str) -> str:
    """
    Sanitize a CSS class name or identifier.

    Only allows alphanumeric characters, hyphens, and underscores.
    Must start with a letter or hyphen followed by a letter.
    """
    if not isinstance(identifier, str):
        identifier = str(identifier)

    # Remove any characters that aren't alphanumeric, hyphen, or underscore
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '', identifier)

    # Ensure it starts with a letter or hyphen+letter
    if not re.match(r'^[a-zA-Z-]', sanitized):
        sanitized = 'safe-' + sanitized

    return sanitized if sanitized else 'safe-default'


def sanitize_html_text(text: str) -> str:
    """Sanitize text for use in HTML content (not attributes)."""
    if not isinstance(text, str):
        text = str(text)
    return html.escape(text)


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
        # Sanitize all theme values to prevent XSS
        icons = sanitize_html_text(tier["icon"]) * tier["repeat"]
        class_name = sanitize_css_identifier(tier["class"])
        color = sanitize_css_value(tier["color"])
        return f'<span class="tier {class_name}" style="color: {color}">{icons}</span>'

    def get_prestige_banner(self, prestige: int) -> str:
        """Get prestige banner if applicable."""
        tier = self.get_prestige_tier(prestige)
        banner = tier.get("banner")
        if banner:
            # Sanitize banner value for use in class name and content
            banner_class = sanitize_css_identifier(str(banner))
            banner_text = sanitize_html_text(str(banner).upper())
            return f'<div class="prestige-banner banner-{banner_class}">{banner_text}</div>'
        return ""

    def get_css_variables(self) -> str:
        """Generate CSS variables from theme."""
        css_vars = []
        for key, value in self.theme.items():
            if key != "prestige_tiers":
                # Sanitize CSS variable name and value to prevent injection
                var_name = sanitize_css_identifier(key)
                var_value = sanitize_css_value(str(value))
                if var_value:  # Only include if sanitization passed
                    css_var = f"--{var_name}: {var_value};"
                    css_vars.append(css_var)
        return "\n".join(css_vars)

    def get_prestige_css(self) -> str:
        """Generate CSS for prestige tiers."""
        css_rules = []
        for tier in self.theme["prestige_tiers"]:
            # Sanitize class name and color values to prevent CSS injection
            class_name = sanitize_css_identifier(tier["class"].replace("tier-", ""))
            color = sanitize_css_value(tier["color"])

            if color:  # Only generate rule if color is valid
                rule = f""".tier-{class_name} {{
    color: {color};
    text-shadow: 0 0 10px {color};
}}"""
                css_rules.append(rule)

            # Banner styling
            banner = tier.get("banner")
            if banner:
                banner_class = sanitize_css_identifier(str(banner))
                foreground = sanitize_css_value(str(self.theme.get("foreground", "#f2f2f2")))

                if color and foreground:  # Only generate rule if both colors are valid
                    css_rules.append(f""".banner-{banner_class} {{
    background: linear-gradient(135deg, {color}, transparent);
    color: {foreground};
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
