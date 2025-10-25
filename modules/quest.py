# modules/quest_final.py
# Final refactored quest module - complete integration of all subsystems
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
from .quest_combat import QuestCombat
from .quest_challenges import QuestChallenges
from .quest_story import QuestStory
from .quest_admin import QuestAdmin
from .quest_legacy import QuestLegacy

UTC = timezone.utc

def setup(bot):
    """Initializes the final refactored Quest module."""
    return QuestFinal(bot)

class QuestFinal(SimpleCommandModule):
    """Final refactored quest module with complete subsystem integration."""
    name = "quest"
    version = "6.0.0" # Complete modular architecture with all subsystems
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot):
        """Initialize the complete refactored quest module."""
        super().__init__(bot)

        # Initialize shared state manager
        self.state_manager = QuestStateManager(bot)

        # Initialize all subsystems
        self.core = QuestCore(bot, self.state_manager)
        self.items = QuestItems(bot, self.state_manager)
        self.status = QuestStatus(bot, self.state_manager)
        self.energy = QuestEnergy(bot, self.state_manager)
        self.combat = QuestCombat(bot, self.state_manager)
        self.challenges = QuestChallenges(bot, self.state_manager)
        self.story = QuestStory(bot, self.state_manager)
        self.admin = QuestAdmin(bot, self.state_manager)
        self.legacy = QuestLegacy(bot, self.state_manager)

        # Initialize locks and state
        self.mob_lock = threading.Lock()
        self._is_loaded = False

        # Load content and challenge paths
        self.content = self.story.load_content()
        self.challenge_paths = self.challenges.load_challenge_paths()

        # Initialize legacy state for compatibility
        self.set_state("players", self.state_manager.get_all_players())
        self.set_state("active_mob", self.state_manager.get_active_mob())
        self.set_state("player_classes", self.state_manager.get_player_classes())
        self.save_state()

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
                self.combat._close_mob_window()
            else:
                remaining = close_time - now
                if remaining > 0:
                    schedule.every(remaining).seconds.do(self.combat._close_mob_window).tag(f"{self.name}-mob_close")

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
        self.register_command(r"^\s*!quest\s+legacy\s*$", self._cmd_legacy, name="legacy",
                              description="View the Legacy Hall of Fame")
        self.register_command(r"^\s*!quest\s+prestige(?:\s+(.+))?\s*$", self._cmd_prestige, name="prestige",
                              description="Prestige at max level for permanent bonuses")
        self.register_command(r"^\s*!quest\s+transcend\s*$", self._cmd_transcend, name="transcend",
                              description="Transcend at prestige 10 to become a Legacy Boss")

        # Class system
        self.register_command(r"^\s*!quest\s+class(?:\s+(.+))?\s*$", self._cmd_class, name="class",
                              description="Show or assign player class")

        # Quest commands with difficulty
        self.register_command(r"^\s*!quest\s+(?:start|begin|go|quest|adventure)\s*$", self._cmd_quest,
                              name="quest", cooldown_seconds=300, description="Go on a solo quest (normal difficulty)")
        self.register_command(r"^\s*!quest\s+easy\s*$", self._cmd_quest_easy, name="quest_easy",
                              cooldown_seconds=300, description="Go on an easy quest")
        self.register_command(r"^\s*!quest\s+hard\s*$", self._cmd_quest_hard, name="quest_hard",
                              cooldown_seconds=300, description="Go on a hard quest")

        # Search and inventory
        self.register_command(r"^\s*!quest\s+search\s*$", self._cmd_search, name="search",
                              cooldown_seconds=300, description="Search for items")
        self.register_command(r"^\s*!quest\s+inv(?:entory)?\s*$", self._cmd_inventory, name="inventory",
                              description="View your inventory and active effects")
        self.register_command(r"^\s*!quest\s+use\s+(.+)$", self._cmd_use_item, name="use_item",
                              description="Use an item from your inventory")

        # Medkit commands
        self.register_command(r"^\s*!quest\s+medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit",
                              description="Use a medkit to heal yourself or another player")

        # Challenge path commands
        self.register_command(r"^\s*!quest\s+ability(?:\s+(.+))?\s*$", self._cmd_ability, name="ability",
                              description="Show or use unlocked abilities")

        # Group content commands
        self.register_command(r"^\s*!mob\s+(?:start|begin|go)\s*$", self._cmd_mob_start, name="mob_start",
                              admin_only=False, description="Start a mob encounter")
        self.register_command(r"^\s*!mob\s+join\s*$", self._cmd_mob_join, name="mob_join",
                              description="Join an active mob encounter")
        self.register_command(r"^\s*!mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping",
                              description="Toggle mob notifications")

        # Admin commands
        self.register_command(r"^\s*!quest\s+reload\s*$", self._cmd_quest_reload, name="quest_reload",
                              admin_only=True, description="Reload quest content from JSON files")
        self.register_command(r"^\s*!quest\s+stats\s*$", self._cmd_quest_stats, name="quest_stats",
                              admin_only=True, description="Show quest system statistics")
        self.register_command(r"^\s*!quest\s+heal_all\s*$", self._cmd_heal_all, name="heal_all",
                              admin_only=True, description="Heal all injured players")
        self.register_command(r"^\s*!quest\s+energy_all\s*$", self._cmd_energy_all, name="energy_all",
                              admin_only=True, description="Restore energy for all players")

        # Challenge admin commands
        self.register_command(r"^\s*!quest\s+challenge\s+activate\s+(\S+)\s*$", self._cmd_challenge_activate, name="challenge_activate",
                              admin_only=True, description="Activate a challenge path by name")
        self.register_command(r"^\s*!quest\s+challenge\s+deactivate\s*$", self._cmd_challenge_deactivate, name="challenge_deactivate",
                              admin_only=True, description="Deactivate the current challenge path")
        self.register_command(r"^\s*!quest\s+challenge\s+list\s*$", self._cmd_challenge_list, name="challenge_list",
                              admin_only=True, description="List all available challenge paths")

        # Short aliases
        self.register_command(r"^\s*!q\s*$", self._cmd_quest, name="quest_alias")
        self.register_command(r"^\s*!p\s*$", self._cmd_profile, name="profile_alias")
        self.register_command(r"^\s*!l(?:b)?\s*$", self._cmd_leaderboard, name="leaderboard_alias")
        self.register_command(r"^\s*!qi\s*$", self._cmd_inventory, name="quest_inventory_alias")
        self.register_command(r"^\s*!search\s*$", self._cmd_search, name="search_alias")
        self.register_command(r"^\s*!medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit_legacy")
        self.register_command(r"^\s*!inv(?:entory)?\s*$", self._cmd_inventory, name="inventory_legacy")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob_legacy")
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join_legacy")

    # Core Command Handlers
    def _cmd_quest_info(self, connection, event, msg, username, match):
        """Show basic quest info and quick stats."""
        user_id = self.bot.get_user_id(username)
        player = self.core.get_player(user_id)

        # Basic stats
        energy_status = self.energy.format_energy_bar(user_id)
        injuries_text = self.status.format_injury_status(user_id)
        challenge_info = self.challenges.get_challenge_path_info(user_id)

        # Quick summary
        response = f"⚔️ **{self.bot.title_for(username)}'s Quest Status**\n"
        response += f"📊 Level {player['level']} (Prestige {player.get('prestige', 0)}) - {player['xp']} XP\n"
        response += f"{energy_status}\n"
        response += f"🏆 Wins: {player['wins']} | Losses: {player['losses']} | Streak: {player['streak']}\n"

        if injuries_text:
            response += f"🩹 {injuries_text}\n"

        if challenge_info:
            response += f"{challenge_info}\n"

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

    def _cmd_legacy(self, connection, event, msg, username, match):
        """Show the Legacy Hall of Fame."""
        from .quest_legacy import QuestLegacy
        legacy = QuestLegacy(self.bot, self.state_manager)

        hall_of_fame = legacy.get_legacy_hall_of_fame()

        if not hall_of_fame:
            self.safe_reply(connection, event, "No players have transcended yet! Be the first to reach prestige 10 and use `!quest transcend`.")
            return

        response = "🌟 **Legacy Hall of Fame** 🌟\n"
        response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        response += "Players who have transcended and live on as Legacy Bosses!\n\n"

        for i, legacy_info in enumerate(hall_of_fame, 1):
            username = legacy_info["username"]
            title = legacy_info["title"]
            original_class = legacy_info["original_class"]
            transcend_num = legacy_info["transcendence_number"]
            defeat_count = legacy_info["defeat_count"]
            total_wins = legacy_info["total_wins"]
            created_at = legacy_info["created_at"]

            # Format date
            try:
                from datetime import datetime
                dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                date_str = dt.strftime("%Y-%m-%d")
            except:
                date_str = "Unknown"

            response += f"**{i}. {username} {title}**\n"
            response += f"   Class: {original_class} | Transcendence #{transcend_num}\n"
            response += f"   Legacy Wins: {total_wins} | Defeated as Boss: {defeat_count} times\n"
            response += f"   Transcended: {date_str}\n"

            # Show last defeated by info
            if legacy_info.get("last_defeated_by"):
                last_defeat = legacy_info["last_defeated_by"]
                response += f"   Last defeated by: {last_defeat['username']}\n"

            response += "\n"

        response += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        response += "Legacy Bosses can appear in random encounters. Defeating them grants bonus XP!"

        self.safe_reply(connection, event, response)

    def _cmd_prestige(self, connection, event, msg, username, match):
        """Handle prestige command."""
        user_id = self.bot.get_user_id(username)
        args = match.group(1) if match.group(1) else ""

        # Check for challenge prestige
        is_challenge = args.lower() == "challenge"
        if is_challenge:
            return self._handle_challenge_prestige(connection, event, username, user_id)

        # Normal prestige
        success, message = self.core.handle_prestige(user_id)

        if success:
            # Reset energy
            self.energy.reset_energy_on_prestige(user_id)
            # Clear any active injuries
            self.status.heal_injuries(user_id, all_injuries=True)

        self.safe_reply(connection, event, message)

    def _cmd_transcend(self, connection, event, msg, username, match):
        """Handle transcend command for prestige 10 players."""
        user_id = self.bot.get_user_id(username)

        # Import here to avoid circular imports
        from .quest_legacy import QuestLegacy
        legacy = QuestLegacy(self.bot, self.state_manager)

        # Check if player can transcend
        can_transcend, message = legacy.can_transcend(user_id)
        if not can_transcend:
            self.safe_reply(connection, event, message)
            return

        # Create the legacy boss
        success, message = legacy.create_legacy_boss(user_id, username)
        if not success:
            self.safe_reply(connection, event, message)
            return

        # Reset the player
        reset_success, reset_message = legacy.reset_player_for_transcendence(user_id)
        if not reset_success:
            self.safe_reply(connection, event, f"Legacy boss created but reset failed: {reset_message}")
            return

        # Reset energy after transcendence
        self.energy.reset_energy_on_prestige(user_id)
        # Clear any active injuries
        self.status.heal_injuries(user_id, all_injuries=True)

        # Send transcendence message
        full_message = f"🌟 **{message}**\n\n{reset_message}\n\nYou now live on as a Legend that other players may encounter in their adventures!"
        self.safe_reply(connection, event, full_message)

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
        """Handle solo quest command (normal difficulty)."""
        self._handle_solo_quest(connection, event, username, "normal")

    def _cmd_quest_easy(self, connection, event, msg, username, match):
        """Handle easy quest command."""
        self._handle_solo_quest(connection, event, username, "easy")

    def _cmd_quest_hard(self, connection, event, msg, username, match):
        """Handle hard quest command."""
        self._handle_solo_quest(connection, event, username, "hard")

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
                location = self.story.get_search_location_description(event.target)
                response = f"You search through {location}... {result['message']}"
                self.safe_reply(connection, event, response)
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

    def _cmd_ability(self, connection, event, msg, username, match):
        """Handle ability commands."""
        user_id = self.bot.get_user_id(username)
        args_str = match.group(1) if match.group(1) else ""

        if not args_str:
            # Show available abilities
            abilities_text = self.challenges.format_abilities_display(user_id)
            self.safe_reply(connection, event, abilities_text)
            return

        # Use ability
        ability_name = args_str.strip()
        success, message = self.challenges.use_ability(user_id, username, ability_name)

        if success:
            # Make announcement to channel
            self.safe_say(message, event.target)
        else:
            self.safe_reply(connection, event, message)

    # Group Content Handlers
    def _cmd_mob_start(self, connection, event, msg, username, match):
        """Handle mob start command."""
        user_id = self.bot.get_user_id(username)
        success, message = self.combat.start_mob_encounter(username, user_id, event.target)
        self.safe_reply(connection, event, message)

    def _cmd_mob_join(self, connection, event, msg, username, match):
        """Handle mob join command."""
        user_id = self.bot.get_user_id(username)
        success, message = self.combat.join_mob_encounter(username, user_id, event.target)
        self.safe_reply(connection, event, message)

    def _cmd_mob_ping(self, connection, event, msg, username, match):
        """Handle mob ping toggle."""
        user_id = self.bot.get_user_id(username)
        action = match.group(1)
        message = self.combat.toggle_mob_ping(user_id, username, event.target, action)
        self.safe_reply(connection, event, message)

    # Admin Command Handlers
    def _cmd_quest_reload(self, connection, event, msg, username, match):
        """Reload quest content and challenge paths."""
        success, message = self.admin.reload_quest_content()
        self.safe_reply(connection, event, message)

    def _cmd_quest_stats(self, connection, event, msg, username, match):
        """Show quest system statistics."""
        report = self.admin.format_admin_report()
        # Send in chunks to avoid IRC message length limits
        lines = report.split('\n')
        chunk = []
        for line in lines:
            chunk.append(line)
            if len(chunk) >= 20:  # Send chunks of 20 lines
                self.safe_reply(connection, event, '\n'.join(chunk))
                chunk = []
        if chunk:
            self.safe_reply(connection, event, '\n'.join(chunk))

    def _cmd_heal_all(self, connection, event, msg, username, match):
        """Heal all injured players."""
        healed_count, message = self.admin.heal_all_players(event.target)
        self.safe_reply(connection, event, message)

    def _cmd_energy_all(self, connection, event, msg, username, match):
        """Restore energy for all players."""
        restored_count, message = self.admin.restore_all_energy(event.target)
        self.safe_reply(connection, event, message)

    # Challenge Admin Commands
    def _cmd_challenge_activate(self, connection, event, msg, username, match):
        """Activate a challenge path."""
        path_name = match.group(1)
        success, message = self.challenges.activate_challenge_path(path_name)
        self.safe_reply(connection, event, message)

    def _cmd_challenge_deactivate(self, connection, event, msg, username, match):
        """Deactivate the current challenge path."""
        success, message = self.challenges.deactivate_challenge_path()
        self.safe_reply(connection, event, message)

    def _cmd_challenge_list(self, connection, event, msg, username, match):
        """List all challenge paths."""
        paths_list, active_path = self.challenges.list_challenge_paths()

        if not paths_list:
            self.safe_reply(connection, event, "No challenge paths defined.")
            return

        response = "🎯 **Challenge Paths:**\n"
        for path in paths_list:
            status = "✅ ACTIVE" if path["active"] else "   Available"
            response += f"{status} {path['name']}: {path['description']}\n"

        self.safe_reply(connection, event, response)

    # Quest System Methods
    def _handle_solo_quest(self, connection, event, username, difficulty):
        """Handle a solo quest attempt."""
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

        # Get difficulty modifiers
        diff_mods = self.combat.calculate_combat_difficulty_modifiers(difficulty)

        # Execute quest
        self._execute_solo_quest(connection, event, username, user_id, difficulty, diff_mods)

        # Set cooldown
        cooldown_seconds = self.config.get("cooldown_seconds", 300)
        player["quest_cooldown"] = time.time() + cooldown_seconds
        self.state_manager.update_player_data(user_id, player)

    def _execute_solo_quest(self, connection, event, username, user_id, difficulty, diff_mods):
        """Execute a solo quest with the given difficulty."""
        player = self.core.get_player(user_id)

        # Consume energy
        self.energy.consume_energy(user_id, 1)

        # Generate quest narrative
        story_intro = self.story.format_quest_intro(username, "the foe", difficulty, event.target)

        # Get monster
        monster = self.combat.get_random_monster(player["level"] + diff_mods["level_modifier"])
        if not monster:
            self.safe_reply(connection, event, "No suitable monsters found for your level!")
            return

        # Calculate win chance
        base_win_chance = self.combat.calculate_win_chance(
            player["level"],
            monster["min_level"] + diff_mods["level_modifier"],
            prestige_level=player.get("effective_prestige", player.get("prestige", 0))
        )

        # Apply injury effects
        injury_effects = self.status.get_injury_effects(user_id)
        win_chance = base_win_chance * injury_effects.get("xp_multiplier", 1.0)

        # Apply active effects
        for effect in player.get("active_effects", []):
            if effect["type"] == "lucky_charm" and effect.get("expires") == "next_fight":
                win_bonus = effect.get("win_bonus", 0) / 100
                win_chance += win_bonus

        # Determine outcome
        is_win = random.random() < win_chance

        # Send quest intro
        self.safe_reply(connection, event, story_intro)

        # Process outcome
        if is_win:
            self._handle_quest_victory(connection, event, username, user_id, monster, diff_mods)
        else:
            self._handle_quest_defeat(connection, event, username, user_id, monster)

        # Check for boss encounter trigger
        if is_win and not self.state_manager.get_active_mob():
            self.combat.trigger_boss_encounter(user_id, username, event.target)

    def _handle_quest_victory(self, connection, event, username, user_id, monster, diff_mods):
        """Handle quest victory."""
        player = self.core.get_player(user_id)

        # Calculate XP reward
        base_xp = random.randint(monster["xp_win_min"], monster["xp_win_max"])
        xp_mult = diff_mods["xp_multiplier"]

        # Apply injury effects
        injury_effects = self.status.get_injury_effects(user_id)
        xp_mult *= injury_effects.get("xp_multiplier", 1.0)

        # Apply active effects
        for effect in player.get("active_effects", []):
            if effect["type"] == "xp_scroll" and effect.get("expires") == "next_win":
                xp_mult = effect.get("xp_multiplier", 1.5)

        # Grant XP and handle level up
        new_level, leveled_up = self.core.grant_xp(user_id, int(base_xp * xp_mult), xp_mult)

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
        victory_text = self.story.get_victory_flavor_text(monster["name"])
        total_xp = int(base_xp * xp_mult)
        response = f"{victory_text} +{total_xp} XP"

        if leveled_up:
            level_up_msg = self.story.get_level_up_message(new_level)
            response += f"\n{level_up_msg}"

        if player["streak"] > 1:
            response += f"\n🔥 Win streak: {player['streak']}!"

        # Check for challenge completion
        completed, messages = self.challenges.check_challenge_completion(user_id, username)
        if completed:
            response += "\n" + "\n".join(messages)

        self.safe_reply(connection, event, response)

    def _handle_quest_defeat(self, connection, event, username, user_id, monster):
        """Handle quest defeat."""
        player = self.core.get_player(user_id)

        # Update stats
        player["losses"] += 1
        player["streak"] = 0

        # Deduct XP
        xp_loss_percentage = self.config.get("xp_loss_percentage", 0.25)
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
        defeat_text = self.story.get_defeat_flavor_text(monster["name"])
        response = f"{defeat_text}"

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

    def _handle_challenge_prestige(self, connection, event, username, user_id):
        """Handle challenge path prestige."""
        player = self.core.get_player(user_id)

        # Check if player meets requirements
        if player["level"] < self.config.get("level_cap", 20):
            self.safe_reply(connection, event, "You must reach level 20 before entering a challenge path!")
            return

        # Enter challenge path
        success, message = self.challenges.enter_challenge_path(user_id, username)

        if success:
            # Reset energy
            self.energy.reset_energy_on_prestige(user_id)
            # Clear injuries
            self.status.heal_injuries(user_id, all_injuries=True)

        self.safe_reply(connection, event, message)