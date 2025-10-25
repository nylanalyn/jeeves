# modules/quest_refactored.py
# Refactored quest module - main orchestrator for quest system
import random
import time
import re
import schedule
import threading
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List, Tuple

from .base import SimpleCommandModule, admin_required
from .quest_state import QuestStateManager
from .quest_core import QuestCore
from .quest_items import QuestItems
from .quest_status import QuestStatus
from .quest_energy import QuestEnergy

UTC = timezone.utc

def setup(bot):
    """Initializes the refactored Quest module."""
    return QuestRefactored(bot)

class QuestRefactored(SimpleCommandModule):
    """Refactored quest module orchestrating all quest subsystems."""
    name = "quest"
    version = "5.0.0" # Refactored modular architecture
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot):
        """Initialize the refactored quest module."""
        super().__init__(bot)

        # Initialize shared state manager
        self.state_manager = QuestStateManager(bot)

        # Initialize subsystems
        self.core = QuestCore(bot, self.state_manager)
        self.items = QuestItems(bot, self.state_manager)
        self.status = QuestStatus(bot, self.state_manager)
        self.energy = QuestEnergy(bot, self.state_manager)

        # Initialize locks and state
        self.mob_lock = threading.Lock()
        self._is_loaded = False

        # Load content and challenge paths
        self.content = self._load_content()
        self.challenge_paths = self._load_challenge_paths()

        # Initialize legacy state for compatibility
        self.set_state("players", self.state_manager.get_all_players())
        self.set_state("active_mob", self.state_manager.get_active_mob())
        self.set_state("player_classes", self.state_manager.get_player_classes())
        self.save_state()

    def _load_content(self) -> Dict[str, Any]:
        """Load quest content from quest_content.json file."""
        content_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "quest_content.json")

        try:
            with open(content_file, 'r') as f:
                content = json.load(f)
                self.log_debug(f"Loaded quest content from {content_file}")
                return content
        except FileNotFoundError:
            self.log_debug(f"Quest content file not found at {content_file}, using config fallback")
            return {}
        except json.JSONDecodeError as e:
            self.log_debug(f"Error parsing quest content JSON: {e}, using config fallback")
            return {}

    def _load_challenge_paths(self) -> Dict[str, Any]:
        """Load challenge paths from challenge_paths.json file."""
        paths_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "challenge_paths.json")

        try:
            with open(paths_file, 'r') as f:
                paths = json.load(f)
                self.log_debug(f"Loaded challenge paths from {paths_file}")
                return paths
        except FileNotFoundError:
            self.log_debug(f"Challenge paths file not found at {paths_file}")
            return {"paths": {}, "active_path": None}
        except json.JSONDecodeError as e:
            self.log_debug(f"Error parsing challenge paths JSON: {e}")
            return {"paths": {}, "active_path": None}

    def _get_content(self, key: str, channel: str = None, default: Any = None) -> Any:
        """Get content from JSON file, falling back to config if not found."""
        # Try to get from content file first
        if key in self.content:
            return self.content[key]
        # Fall back to config
        return self.get_config_value(key, channel, default=default)

    def on_load(self):
        """Called when module is loaded."""
        super().on_load()
        self._is_loaded = True

        # Schedule energy regeneration
        self.energy.schedule_energy_regeneration()

        # Check for active mob windows
        active_mob = self.state_manager.get_active_mob()
        if active_mob:
            close_time = active_mob.get("close_epoch", 0)
            now = time.time()
            if now >= close_time:
                self._close_mob_window()
            else:
                remaining = close_time - now
                if remaining > 0:
                    schedule.every(remaining).seconds.do(self._close_mob_window).tag(f"{self.name}-mob_close")

    def on_unload(self):
        """Called when module is unloaded."""
        super().on_unload()
        schedule.clear(self.name)

    def _register_commands(self):
        """Register all quest commands."""
        # Core quest commands
        self.register_command(r"^\s*!quest\s*$", self._cmd_quest_info, name="quest_info",
                              description="Show your quest profile and stats")
        self.register_command(r"^\s*!quest\s+profile\s*$", self._cmd_profile, name="profile",
                              description="Show detailed player profile")
        self.register_command(r"^\s*!quest\s+leaderboard\s*$", self._cmd_leaderboard, name="leaderboard",
                              description="Show the quest leaderboard")
        self.register_command(r"^\s*!quest\s+prestige\s*$", self._cmd_prestige, name="prestige",
                              description="Prestige at max level for permanent bonuses")

        # Class system
        self.register_command(r"^\s*!quest\s+class(?:\s+(.+))?\s*$", self._cmd_class, name="class",
                              description="Show or assign player class")

        # Quest commands
        self.register_command(r"^\s*!quest\s+(?:start|begin|go|quest|adventure)\s*$", self._cmd_quest,
                              name="quest", cooldown_seconds=300, description="Go on a solo quest")
        self.register_command(r"^\s*!quest\s+search\s*$", self._cmd_search, name="search",
                              cooldown_seconds=300, description="Search for items")

        # Inventory and items
        self.register_command(r"^\s*!quest\s+inv(?:entory)?\s*$", self._cmd_inventory, name="inventory",
                              description="View your inventory and active effects")
        self.register_command(r"^\s*!quest\s+use\s+(.+)$", self._cmd_use_item, name="use_item",
                              description="Use an item from your inventory")

        # Medkit commands
        self.register_command(r"^\s*!quest\s+medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit",
                              description="Use a medkit to heal yourself or another player")

        # Group content
        self.register_command(r"^\s*!mob\s+(?:start|begin|go)\s*$", self._cmd_mob_start, name="mob_start",
                              admin_only=False, description="Start a mob encounter")
        self.register_command(r"^\s*!mob\s+join\s*$", self._cmd_mob_join, name="mob_join",
                              description="Join an active mob encounter")

        # Admin commands
        self.register_command(r"^\s*!quest\s+reload\s*$", self._cmd_quest_reload, name="quest_reload",
                              admin_only=True, description="Reload quest content from JSON files")

        # Short aliases
        self.register_command(r"^\s*!q\s*$", self._cmd_quest, name="quest_alias")
        self.register_command(r"^\s*!p\s*$", self._cmd_profile, name="profile_alias")
        self.register_command(r"^\s*!l(?:b)?\s*$", self._cmd_leaderboard, name="leaderboard_alias")
        self.register_command(r"^\s*!qi\s*$", self._cmd_inventory, name="quest_inventory_alias")
        self.register_command(r"^\s*!search\s*$", self._cmd_search, name="search_alias")
        self.register_command(r"^\s*!medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit_legacy")
        self.register_command(r"^\s*!inv(?:entory)?\s*$", self._cmd_inventory, name="inventory_legacy")

    # Core Command Handlers
    def _cmd_quest_info(self, connection, event, msg, username, match):
        """Show basic quest info and quick stats."""
        user_id = self.bot.get_user_id(username)
        player = self.core.get_player(user_id)

        # Basic stats
        energy_status = self.energy.format_energy_bar(user_id)
        injuries_text = self.status.format_injury_status(user_id)

        # Quick summary
        response = f"⚔️ **{self.bot.title_for(username)}'s Quest Status**\n"
        response += f"📊 Level {player['level']} (Prestige {player.get('prestige', 0)}) - {player['xp']} XP\n"
        response += f"{energy_status}\n"
        response += f"🏆 Wins: {player['wins']} | Losses: {player['losses']} | Streak: {player['streak']}\n"

        if injuries_text:
            response += f"🩹 {injuries_text}\n"

        # Show available actions
        response += f"\n**Commands:** !quest (adventure) | !search | !inv | !profile"

        self.safe_reply(connection, event, response)

    def _cmd_profile(self, connection, event, msg, username, match):
        """Show detailed player profile."""
        user_id = self.bot.get_user_id(username)
        profile = self.core.format_player_profile(user_id)

        # Add inventory info
        inventory_text = self.items.format_inventory_display(user_id)
        profile += f"\n\n{inventory_text}"

        self.safe_reply(connection, event, profile)

    def _cmd_leaderboard(self, connection, event, msg, username, match):
        """Show the quest leaderboard."""
        leaderboard = self.core.get_leaderboard(limit=10)

        if not leaderboard:
            self.safe_reply(connection, event, "No players on the leaderboard yet!")
            return

        response = "🏆 **Quest Leaderboard** (Top 10)\n"
        response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"

        for i, (user_id, player_data) in enumerate(leaderboard, 1):
            nick = self.bot.get_user_nick(user_id)
            prestige = player_data.get('prestige', 0)
            level = player_data.get('level', 1)
            xp = player_data.get('xp', 0)
            wins = player_data.get('wins', 0)

            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i:2d}."
            prestige_text = f"★{prestige} " if prestige > 0 else "   "

            response += f"{medal} {prestige_text}{nick:<20} Lvl {level:<2} ({xp:<4} XP) Wins: {wins}\n"

        self.safe_reply(connection, event, response)

    def _cmd_prestige(self, connection, event, msg, username, match):
        """Handle prestige command."""
        user_id = self.bot.get_user_id(username)
        success, message = self.core.handle_prestige(user_id)

        if success:
            # Reset energy
            self.energy.reset_energy_on_prestige(user_id)
            # Clear any active injuries
            self.status.heal_injuries(user_id, all_injuries=True)

        self.safe_reply(connection, event, message)

    def _cmd_class(self, connection, event, msg, username, match):
        """Handle class assignment."""
        user_id = self.bot.get_user_id(username)
        class_name = match.group(1)

        if not class_name:
            # Show available classes
            available_classes = self.core.get_available_classes()
            player = self.core.get_player(user_id)
            current_class = player.get("class", "None")

            response = f"🎭 **Class System**\n"
            response += f"Current Class: {current_class}\n\n"
            response += f"Available Classes: {', '.join(available_classes)}\n\n"
            response += f"Usage: !quest class <classname>"

            self.safe_reply(connection, event, response)
            return

        # Assign class
        success, message = self.core.assign_class(user_id, class_name.strip())
        self.safe_reply(connection, event, message)

    # Quest Command Handlers
    def _cmd_quest(self, connection, event, msg, username, match):
        """Handle solo quest command."""
        user_id = self.bot.get_user_id(username)
        player = self.core.get_player(user_id)

        # Check cooldowns
        if player.get("quest_cooldown") and time.time() < player["quest_cooldown"]:
            remaining = int(player["quest_cooldown"] - time.time())
            self.safe_reply(connection, event, f"You're still recovering! Wait {remaining // 60}m {remaining % 60}s before your next quest.")
            return

        # Check energy
        energy_check = self.energy.check_energy_for_quest(user_id)
        if not energy_check["has_energy"]:
            self.safe_reply(connection, event, f"You don't have enough energy! You need {energy_check['required_energy']} energy but only have {energy_check['current_energy']}.")
            return

        # Check injuries
        if self.status.has_active_injuries(user_id):
            injuries = self.status.get_injury_list(user_id)
            if len(injuries) == 1:
                self.safe_reply(connection, event, f"You're still recovering from {injuries[0]}! Use a medkit or rest first.")
            else:
                self.safe_reply(connection, event, f"You're still recovering from: {', '.join(injuries)}! Use a medkit or rest first.")
            return

        # Execute quest
        self._handle_solo_quest(connection, event, username, user_id)

    def _cmd_search(self, connection, event, msg, username, match):
        """Handle search command."""
        user_id = self.bot.get_user_id(username)

        # Check if player is injured
        if self.status.has_active_injuries(user_id):
            injuries = self.status.get_injury_list(user_id)
            if len(injuries) == 1:
                self.safe_reply(connection, event, f"You're still recovering from {injuries[0]}! Searching while injured is dangerous.")
            else:
                self.safe_reply(connection, event, f"You're still recovering from: {', '.join(injuries)}! Searching while injured is dangerous.")
            return

        # Perform search
        result = self.items.perform_search(user_id)

        if result["success"]:
            if result["type"] == "injury":
                # Apply injury
                injury_result = self.status.apply_injury_from_search(user_id)
                self.safe_reply(connection, event, injury_result["message"])
            else:
                # Show search result
                self.safe_reply(connection, event, result["message"])
        else:
            self.safe_reply(connection, event, result["message"])

    def _cmd_inventory(self, connection, event, msg, username, match):
        """Show player inventory."""
        user_id = self.bot.get_user_id(username)
        inventory_text = self.items.format_inventory_display(user_id)
        self.safe_reply(connection, event, inventory_text)

    def _cmd_use_item(self, connection, event, msg, username, match):
        """Handle using items."""
        user_id = self.bot.get_user_id(username)
        item_name = match.group(1).strip().lower()

        # Parse target for medkit
        target_arg = None
        if item_name.startswith("medkit "):
            target_arg = item_name[7:].strip()
            item_name = "medkit"
        elif item_name == "medkit" and " " in msg:
            # Handle !quest use medkit target format
            parts = msg.split()
            if len(parts) > 3:
                target_arg = " ".join(parts[3:]).strip()

        # Use item
        kwargs = {}
        if target_arg:
            target_user_id = self.bot.get_user_id(target_arg)
            if target_user_id:
                kwargs["target_user_id"] = target_user_id

        result = self.items.use_item(user_id, item_name, **kwargs)

        if result["success"]:
            if result.get("xp_reward"):
                # Grant XP if applicable
                self.core.grant_xp(user_id, result["xp_reward"])

            if result.get("healed_injuries"):
                # Injuries were healed via the items module
                pass

        self.safe_reply(connection, event, result["message"])

    def _cmd_medkit(self, connection, event, msg, username, match):
        """Handle medkit command."""
        user_id = self.bot.get_user_id(username)
        target_arg = match.group(1) if match.group(1) else None

        # Use medkit via items system
        kwargs = {}
        if target_arg:
            target_user_id = self.bot.get_user_id(target_arg)
            if target_user_id:
                kwargs["target_user_id"] = target_user_id

        result = self.items.use_item(user_id, "medkit", **kwargs)

        if result["success"] and result.get("xp_reward"):
            # Grant XP for healing
            self.core.grant_xp(user_id, result["xp_reward"])

        self.safe_reply(connection, event, result["message"])

    # Group Content Handlers (simplified for now)
    def _cmd_mob_start(self, connection, event, msg, username, match):
        """Handle mob start command."""
        self.safe_reply(connection, event, "Mob encounters are coming soon in the refactored version!")

    def _cmd_mob_join(self, connection, event, msg, username, match):
        """Handle mob join command."""
        self.safe_reply(connection, event, "Mob encounters are coming soon in the refactored version!")

    # Admin Commands
    def _cmd_quest_reload(self, connection, event, msg, username, match):
        """Reload quest content and challenge paths."""
        # Reload content
        self.content = self._load_content()
        self.challenge_paths = self._load_challenge_paths()

        # Update state manager
        self.state_manager.update_content(self.content)
        self.state_manager.update_challenge_paths(self.challenge_paths)

        self.safe_reply(connection, event, "✅ Quest content and challenge paths reloaded successfully!")

    # Quest System Methods
    def _handle_solo_quest(self, connection, event, username, user_id):
        """Handle a solo quest attempt."""
        player = self.core.get_player(user_id)

        # Consume energy
        self.energy.consume_energy(user_id, 1)

        # Calculate quest outcome
        story_action = self._get_action_text(username, event.target)
        monster = self._get_random_monster(player["level"])

        # Calculate win chance
        base_win_chance = self.get_config_value("combat.base_win_chance", event.target, default=0.50)
        level_modifier = self.get_config_value("combat.win_chance_level_modifier", event.target, default=0.10)
        min_win_chance = self.get_config_value("combat.min_win_chance", event.target, default=0.05)
        max_win_chance = self.get_config_value("combat.max_win_chance", event.target, default=0.95)

        level_diff = player["level"] - monster["min_level"]
        win_chance = base_win_chance + (level_diff * level_modifier)
        win_chance = max(min_win_chance, min(max_win_chance, win_chance))

        # Apply injury effects
        injury_effects = self.status.get_injury_effects(user_id)
        win_chance *= injury_effects.get("xp_multiplier", 1.0)

        # Apply active effects
        for effect in player.get("active_effects", []):
            if effect["type"] == "lucky_charm" and effect.get("expires") == "next_fight":
                win_bonus = effect.get("win_bonus", 0) / 100
                win_chance += win_bonus

        # Determine outcome
        is_win = random.random() < win_chance

        # Process outcome
        if is_win:
            self._handle_quest_victory(connection, event, username, user_id, monster, story_action)
        else:
            self._handle_quest_defeat(connection, event, username, user_id, monster, story_action)

        # Set cooldown
        cooldown_seconds = self.get_config_value("cooldown_seconds", event.target, default=300)
        player["quest_cooldown"] = time.time() + cooldown_seconds
        self.state_manager.update_player_data(user_id, player)

    def _handle_quest_victory(self, connection, event, username, user_id, monster, action):
        """Handle quest victory."""
        player = self.core.get_player(user_id)

        # Calculate XP reward
        base_xp = random.randint(monster["xp_win_min"], monster["xp_win_max"])
        xp_mult = 1.0

        # Apply injury effects
        injury_effects = self.status.get_injury_effects(user_id)
        xp_mult *= injury_effects.get("xp_multiplier", 1.0)

        # Apply active effects
        for effect in player.get("active_effects", []):
            if effect["type"] == "xp_scroll" and effect.get("expires") == "next_win":
                xp_mult = effect.get("xp_multiplier", 1.5)

        # Grant XP and handle level up
        new_level, leveled_up = self.core.grant_xp(user_id, base_xp, xp_mult)

        # Update stats
        player["wins"] += 1
        player["streak"] += 1
        if player["streak"] > player["max_streak"]:
            player["max_streak"] = player["streak"]

        # Process active effects
        self._process_active_effects(player, is_win=True)

        # Update max energy on level up
        if leveled_up:
            self.energy.update_max_energy_on_level_up(user_id, new_level)

        self.state_manager.update_player_data(user_id, player)

        # Send victory message
        total_xp = int(base_xp * xp_mult)
        response = f"{action}. Victory! You defeated the {monster['name']} and earned {total_xp} XP!"

        if leveled_up:
            response += f" 🎉 **LEVEL UP!** You are now level {new_level}!"

        if player["streak"] > 1:
            response += f" 🔥 Win streak: {player['streak']}!"

        self.safe_reply(connection, event, response)

    def _handle_quest_defeat(self, connection, event, username, user_id, monster, action):
        """Handle quest defeat."""
        player = self.core.get_player(user_id)

        # Update stats
        player["losses"] += 1
        player["streak"] = 0

        # Deduct XP
        xp_loss_percentage = self.get_config_value("xp_loss_percentage", event.target, default=0.25)
        xp_for_current_level = self.core.calculate_xp_for_level(player["level"])
        max_xp_loss = int((player["xp"] - xp_for_current_level) * xp_loss_percentage)
        actual_xp_loss = self.core.deduct_xp(user_id, max_xp_loss)

        # Apply injury
        injury_reduction = self.status.get_injury_reduction(user_id)
        injury_msg = self.status.apply_injury(user_id, username, event.target, injury_reduction=injury_reduction)

        # Process active effects
        self._process_active_effects(player, is_win=False)

        self.state_manager.update_player_data(user_id, player)

        # Send defeat message
        response = f"{action}. Defeat! You were overcome by the {monster['name']}."

        if actual_xp_loss > 0:
            response += f" Lost {actual_xp_loss} XP."

        if injury_msg:
            response += f" {injury_msg}"

        self.safe_reply(connection, event, response)

    def _process_active_effects(self, player, is_win):
        """Process active effects after combat."""
        remaining_effects = []

        for effect in player.get("active_effects", []):
            keep_effect = True

            if effect["type"] == "lucky_charm" and effect.get("expires") == "next_fight":
                keep_effect = False  # Consume effect
            elif effect["type"] == "xp_scroll" and effect.get("expires") == "next_win" and is_win:
                keep_effect = False  # Consume effect
            elif effect["type"] == "armor_shard":
                remaining_fights = effect.get("remaining_fights", 0) - 1
                if remaining_fights > 0:
                    effect["remaining_fights"] = remaining_fights
                else:
                    keep_effect = False  # Consume effect

            if keep_effect:
                remaining_effects.append(effect)

        player["active_effects"] = remaining_effects

    # Content Helper Methods
    def _get_random_monster(self, level):
        """Get a random monster appropriate for the player's level."""
        monsters = self._get_content("monsters", default=[])
        suitable_monsters = []

        for monster in monsters:
            if monster["min_level"] <= level <= monster["max_level"]:
                suitable_monsters.append(monster)

        if not suitable_monsters:
            # Fallback to any monster
            suitable_monsters = monsters

        return random.choice(suitable_monsters) if suitable_monsters else {
            "name": "Glitched Packet",
            "min_level": 1,
            "max_level": 3,
            "xp_win_min": 15,
            "xp_win_max": 30
        }

    def _get_action_text(self, username, channel):
        """Get random action text for quest narrative."""
        openers = self._get_content("story_beats", {}).get("openers", [])
        actions = self._get_content("story_beats", {}).get("actions", [])

        if openers and actions:
            opener = random.choice(openers).format(user=username, monster="the foe")
            action = random.choice(actions).format(user=username, monster="the foe")
            return f"{opener} {action}"
        else:
            # Fallback narrative
            return f"{username} ventures forth to challenge the unknown dangers lurking in the digital realm..."

    def _close_mob_window(self):
        """Close active mob window (placeholder)."""
        active_mob = self.state_manager.get_active_mob()
        if active_mob:
            self.state_manager.update_active_mob(None)
            self.log_debug("Mob window closed")