# modules/quest_story.py
# Story content, lore, and dynamic text generation for quest module
import json
import os
import random
from datetime import datetime
from typing import Dict, Any, List, Optional

from .quest_state import QuestStateManager


class QuestStory:
    """Story content and dynamic text generation for quest module."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def load_content(self) -> Dict[str, Any]:
        """Load quest content from appropriate themed JSON file based on month."""
        base_dir = os.path.dirname(os.path.dirname(__file__))

        # Determine which theme file to use based on current month
        current_month = datetime.now().month
        if current_month == 11:  # November - Noir theme
            content_file = os.path.join(base_dir, "quest_content_noir.json")
            theme_name = "noir"
        elif current_month == 10:  # October - Halloween theme (default)
            content_file = os.path.join(base_dir, "quest_content.json")
            theme_name = "halloween"
        else:
            # Other months - check for noir file first for testing, otherwise use default
            noir_file = os.path.join(base_dir, "quest_content_noir.json")
            default_file = os.path.join(base_dir, "quest_content.json")

            if os.path.exists(noir_file):
                content_file = noir_file
                theme_name = "noir (test mode)"
            else:
                content_file = default_file
                theme_name = "default"

        try:
            with open(content_file, 'r') as f:
                content = json.load(f)
                self.bot.log_debug(f"Loaded quest content from {content_file} (theme: {theme_name})")
                return content
        except FileNotFoundError:
            self.bot.log_debug(f"Quest content file not found at {content_file}, using config fallback")
            return {}
        except json.JSONDecodeError as e:
            self.bot.log_debug(f"Error parsing quest content JSON: {e}, using config fallback")
            return {}

    def get_content(self, key: str, channel: str = None, default: Any = None) -> Any:
        """Get content from JSON file, falling back to config if not found."""
        content = self.state.get_content()

        # Try to get from content file first
        if key in content:
            return content[key]

        # Fall back to config
        return self.bot.config.get("quest", {}).get(key, default=default)

    def get_action_text(self, username: str, channel: str = None) -> str:
        """Generate random action text for quest narrative."""
        content = self.state.get_content()
        story_beats = content.get("story_beats", {})

        openers = story_beats.get("openers", [])
        actions = story_beats.get("actions", [])

        if openers and actions:
            opener = random.choice(openers).format(user=username, monster="the foe")
            action = random.choice(actions).format(user=username, monster="the foe")
            return f"{opener} {action}"
        else:
            # Fallback to config-based narrative
            return self._get_fallback_action_text(username, channel)

    def _get_fallback_action_text(self, username: str, channel: str = None) -> str:
        """Generate fallback action text from config."""
        # Get world lore for atmosphere
        world_lore = self.get_content("world_lore", channel, default=[])
        lore_prefix = ""
        if world_lore and random.random() < 0.3:  # 30% chance to include lore
            lore_prefix = f"{random.choice(world_lore)} "

        # Generate action
        actions = [
            f"{username} ventures forth to challenge the unknown dangers lurking in the digital realm...",
            f"{username} embarks on a perilous quest through the corrupted networks...",
            f"{username} searches for valuable artifacts and experience in the forgotten servers...",
            f"{username} bravely faces the challenges that await in the shadows of the network...",
            f"{username} journeys into the depths of the system in search of glory and reward..."
        ]

        return f"{lore_prefix}{random.choice(actions)}"

    def get_world_lore(self, channel: str = None) -> Optional[str]:
        """Get a random piece of world lore."""
        world_lore = self.get_content("world_lore", channel, default=[])
        if world_lore:
            return random.choice(world_lore)
        return None

    def get_monster_flavor_text(self, monster_name: str, channel: str = None) -> Optional[str]:
        """Get flavor text for a specific monster."""
        content = self.state.get_content()
        monster_descriptions = content.get("monster_descriptions", {})

        return monster_descriptions.get(monster_name.lower())

    def get_victory_flavor_text(self, monster_name: str, is_boss: bool = False, channel: str = None) -> str:
        """Get victory flavor text for defeating a monster."""
        content = self.state.get_content()

        if is_boss:
            victory_texts = content.get("boss_victory_texts", [])
            if victory_texts:
                text = random.choice(victory_texts)
                return text.format(monster=monster_name)

        # Regular monster victory texts
        victory_texts = content.get("victory_texts", [])
        if victory_texts:
            text = random.choice(victory_texts)
            return text.format(monster=monster_name)

        # Fallback victory messages
        fallback_victories = [
            f"The {monster_name} has been defeated!",
            f"Victory against the {monster_name}!",
            f"The {monster_name} falls before your might!",
            f"You have triumphed over the {monster_name}!"
        ]

        return random.choice(fallback_victories)

    def get_defeat_flavor_text(self, monster_name: str, is_boss: bool = False, channel: str = None) -> str:
        """Get defeat flavor text for losing to a monster."""
        content = self.state.get_content()

        if is_boss:
            defeat_texts = content.get("boss_defeat_texts", [])
            if defeat_texts:
                text = random.choice(defeat_texts)
                return text.format(monster=monster_name)

        # Regular monster defeat texts
        defeat_texts = content.get("defeat_texts", [])
        if defeat_texts:
            text = random.choice(defeat_texts)
            return text.format(monster=monster_name)

        # Fallback defeat messages
        fallback_defeats = [
            f"The {monster_name} has proven too powerful...",
            f"Defeated by the {monster_name}...",
            f"The {monster_name} emerges victorious...",
            f"You have been overcome by the {monster_name}..."
        ]

        return random.choice(fallback_defeats)

    def get_item_discovery_text(self, item_type: str, channel: str = None) -> str:
        """Get discovery text for finding items."""
        content = self.state.get_content()
        item_texts = content.get("item_discovery_texts", {})

        discovery_messages = item_texts.get(item_type.lower(), [])
        if discovery_messages:
            return random.choice(discovery_messages)

        # Fallback item discovery messages
        fallback_messages = {
            "medkit": [
                "You found a medical kit! It looks well-stocked.",
                "A medkit! This could come in handy.",
                "You discovered a medkit in the debris."
            ],
            "energy_potion": [
                "An energy potion! The liquid glows with power.",
                "You found an energy potion. It buzzes with energy.",
                "A potion of energy restoration! This could help."
            ],
            "lucky_charm": [
                "A lucky charm! It seems to hum with good fortune.",
                "You found a charm that feels warm to the touch.",
                "A lucky charm! Maybe it will bring you victory."
            ],
            "armor_shard": [
                "An armor shard! It's surprisingly light but strong.",
                "You found a piece of advanced armor.",
                "An armor shard! This could provide protection."
            ],
            "xp_scroll": [
                "An XP scroll! The runes seem to shift and change.",
                "You found a scroll imbued with knowledge.",
                "An XP scroll! The writing glows with power."
            ]
        }

        messages = fallback_messages.get(item_type.lower(), [f"You found a {item_type}!"])
        return random.choice(messages)

    def get_level_up_message(self, new_level: int, channel: str = None) -> str:
        """Get a level up congratulations message."""
        content = self.state.get_content()
        level_up_messages = content.get("level_up_messages", [])

        if level_up_messages:
            message = random.choice(level_up_messages)
            return message.format(level=new_level)

        # Fallback level up messages
        fallback_messages = [
            f"🎉 **LEVEL UP!** You are now level {new_level}!",
            f"⭐ **LEVEL {new_level} ACHIEVED!** Your power grows!",
            f"🌟 **LEVEL UP!** You've reached level {new_level}!",
            f"✨ **LEVEL {new_level}!** You feel stronger!",
            f"🎯 **LEVEL UP!** You are now level {new_level}!"
        ]

        return random.choice(fallback_messages)

    def get_prestige_message(self, prestige_level: int, channel: str = None) -> str:
        """Get a prestige congratulations message."""
        prestige_messages = [
            f"🌟 **PRESTIGE {prestige_level}!** You have transcended mortal limits!",
            f"⭐ **PRESTIGE {prestige_level} ACHIEVED!** Your legend grows!",
            f"🎖️ **PRESTIGE {prestige_level}!** You have reached a new pinnacle of power!",
            f"🏆 **PRESTIGE {prestige_level}!** Your name will be remembered!",
            f"✨ **PRESTIGE {prestige_level}!** You have ascended to new heights!"
        ]

        return random.choice(prestige_messages)

    def get_injury_description(self, injury_name: str, channel: str = None) -> str:
        """Get descriptive text for an injury."""
        content = self.state.get_content()
        injury_descriptions = content.get("injury_descriptions", {})

        return injury_descriptions.get(injury_name.lower())

    def get_search_location_description(self, channel: str = None) -> str:
        """Get a description of the search location."""
        content = self.state.get_content()
        locations = content.get("search_locations", [])

        if locations:
            return random.choice(locations)

        # Fallback search locations
        fallback_locations = [
            "an abandoned server room",
            "a forgotten data archive",
            "a corrupted network sector",
            "an old maintenance tunnel",
            "a dusty terminal room",
            "a forgotten backup facility",
            "an empty office cubicle",
            "a dark network closet",
            "an abandoned workstation",
            "a forgotten storage room"
        ]

        return random.choice(fallback_locations)

    def format_quest_intro(self, username: str, monster_name: str, difficulty: str = "normal", channel: str = None) -> str:
        """Format a complete quest introduction."""
        action_text = self.get_action_text(username, channel)
        monster_flavor = self.get_monster_flavor_text(monster_name, channel)

        intro = f"{action_text}"

        if monster_flavor:
            intro += f" {monster_flavor}"

        # Add difficulty context
        if difficulty == "easy":
            intro += " This seems like it should be manageable."
        elif difficulty == "hard":
            intro += " This looks extremely dangerous!"

        return intro

    def format_mob_announcement(self, monster_name: str, is_boss: bool = False, is_rare: bool = False, channel: str = None) -> str:
        """Format mob encounter announcement."""
        if is_boss:
            prefix = "⚠️ **BOSS ENCOUNTER!**"
        elif is_rare:
            prefix = "✨ **RARE MOB ENCOUNTER!**"
        else:
            prefix = "⚔️ **MOB ENCOUNTER!**"

        monster_flavor = self.get_monster_flavor_text(monster_name, channel)

        announcement = f"{prefix} A wild {monster_name} appears!"

        if monster_flavor:
            announcement += f" {monster_flavor}"

        announcement += " Use !quest join to participate!"

        return announcement

    def get_seasonal_greeting(self, channel: str = None) -> Optional[str]:
        """Get a seasonal greeting if available."""
        content = self.state.get_content()
        seasonal_greetings = content.get("seasonal_greetings", {})

        # This could be expanded to check actual date/season
        if seasonal_greetings:
            return random.choice(list(seasonal_greetings.values()))

        return None

    def get_random_tip(self, channel: str = None) -> Optional[str]:
        """Get a random gameplay tip."""
        content = self.state.get_content()
        tips = content.get("gameplay_tips", [])

        if tips:
            return random.choice(tips)

        # Fallback tips
        fallback_tips = [
            "💡 Tip: Use !search to find useful items between quests!",
            "💡 Tip: Medkits can heal yourself or other players.",
            "💡 Tip: Energy potions restore energy when you're running low.",
            "💡 Tip: Lucky charms increase your win chance for one fight.",
            "💡 Tip: Armor shards reduce your chance of getting injured.",
            "💡 Tip: XP scrolls give bonus experience on your next victory.",
            "💡 Tip: Join mob encounters with !mob join for group content.",
            "💡 Tip: Check your progress with !profile and !leaderboard.",
            "💡 Tip: Complete challenge paths to unlock special abilities.",
            "💡 Tip: Higher prestige levels give permanent XP bonuses."
        ]

        return random.choice(fallback_tips)

    def reload_content(self) -> Tuple[bool, str]:
        """Reload quest content from file."""
        try:
            new_content = self.load_content()
            self.state.update_content(new_content)
            return True, "Quest content reloaded successfully!"
        except Exception as e:
            return False, f"Error reloading quest content: {e}"

    def get_content_stats(self) -> Dict[str, Any]:
        """Get statistics about loaded content."""
        content = self.state.get_content()

        stats = {
            "monsters": len(content.get("monsters", [])),
            "world_lore_entries": len(content.get("world_lore", [])),
            "story_beats": {
                "openers": len(content.get("story_beats", {}).get("openers", [])),
                "actions": len(content.get("story_beats", {}).get("actions", []))
            },
            "flavor_texts": {
                "victory": len(content.get("victory_texts", [])),
                "defeat": len(content.get("defeat_texts", [])),
                "level_up": len(content.get("level_up_messages", []))
            },
            "total_keys": len(content.keys())
        }

        return stats