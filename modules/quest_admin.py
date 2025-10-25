# modules/quest_admin.py
# Administrative commands and debugging tools for quest module
from typing import Dict, Any, List, Tuple, Optional

from .quest_state import QuestStateManager


class QuestAdmin:
    """Administrative functions and commands for quest module."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def reload_quest_content(self) -> Tuple[bool, str]:
        """Reload quest content and challenge paths from JSON files."""
        try:
            # Reload content via story module
            from .quest_story import QuestStory
            quest_story = QuestStory(self.bot, self.state)
            content_success, content_message = quest_story.reload_content()

            # Reload challenge paths via challenges module
            from .quest_challenges import QuestChallenges
            quest_challenges = QuestChallenges(self.bot, self.state)
            new_paths = quest_challenges.load_challenge_paths()
            self.state.update_challenge_paths(new_paths)

            return True, f"✅ Quest content and challenge paths reloaded successfully! {content_message}"
        except Exception as e:
            return False, f"❌ Error reloading quest content: {e}"

    def get_quest_statistics(self) -> Dict[str, Any]:
        """Get comprehensive quest system statistics."""
        all_players = self.state.get_all_players()

        stats = {
            "total_players": len(all_players),
            "active_players": len([p for p in all_players.values() if isinstance(p, dict) and p.get("xp", 0) > 0]),
            "level_distribution": {},
            "prestige_distribution": {},
            "total_wins": 0,
            "total_losses": 0,
            "total_xp_earned": 0,
            "injury_count": 0,
            "inventory_totals": {},
            "challenge_stats": {}
        }

        # Initialize inventory totals
        inventory_totals = {
            "medkits": 0,
            "energy_potions": 0,
            "lucky_charms": 0,
            "armor_shards": 0,
            "xp_scrolls": 0
        }

        challenge_stats = {
            "total_on_challenges": 0,
            "completed_challenges": 0,
            "abilities_unlocked": 0
        }

        for player_data in all_players.values():
            if not isinstance(player_data, dict):
                continue

            level = player_data.get("level", 1)
            prestige = player_data.get("prestige", 0)

            # Level distribution
            level_key = f"Level {level}"
            stats["level_distribution"][level_key] = stats["level_distribution"].get(level_key, 0) + 1

            # Prestige distribution
            prestige_key = f"Prestige {prestige}"
            stats["prestige_distribution"][prestige_key] = stats["prestige_distribution"].get(prestige_key, 0) + 1

            # Combat stats
            stats["total_wins"] += player_data.get("wins", 0)
            stats["total_losses"] += player_data.get("losses", 0)
            stats["total_xp_earned"] += player_data.get("xp", 0)

            # Injury count
            injuries = player_data.get("active_injuries", [])
            if injuries:
                stats["injury_count"] += len(injuries)

            # Inventory totals
            inventory = player_data.get("inventory", {})
            for item_type in inventory_totals:
                inventory_totals[item_type] += inventory.get(item_type, 0)

            # Challenge stats
            if player_data.get("challenge_path"):
                challenge_stats["total_on_challenges"] += 1
                if player_data.get("challenge_stats", {}).get("completed", False):
                    challenge_stats["completed_challenges"] += 1

            unlocked_abilities = player_data.get("unlocked_abilities", [])
            challenge_stats["abilities_unlocked"] += len(unlocked_abilities)

        stats["inventory_totals"] = inventory_totals
        stats["challenge_stats"] = challenge_stats

        # Calculate win rate
        total_combats = stats["total_wins"] + stats["total_losses"]
        if total_combats > 0:
            stats["win_rate"] = round((stats["total_wins"] / total_combats) * 100, 1)
        else:
            stats["win_rate"] = 0.0

        return stats

    def get_player_details(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a specific player."""
        player = self.state.get_player_data(user_id)
        if not player:
            return None

        # Get additional details from various modules
        from .quest_energy import QuestEnergy
        from .quest_status import QuestStatus
        from .quest_challenges import QuestChallenges

        quest_energy = QuestEnergy(self.bot, self.state)
        quest_status = QuestStatus(self.bot, self.state)
        quest_challenges = QuestChallenges(self.bot, self.state)

        details = {
            "user_id": user_id,
            "nick": self.bot.get_user_nick(user_id),
            "basic_stats": {
                "level": player.get("level", 1),
                "prestige": player.get("prestige", 0),
                "xp": player.get("xp", 0),
                "wins": player.get("wins", 0),
                "losses": player.get("losses", 0),
                "streak": player.get("streak", 0),
                "max_streak": player.get("max_streak", 0)
            },
            "energy": quest_energy.get_energy_status(user_id),
            "injuries": {
                "count": len(player.get("active_injuries", [])),
                "list": quest_status.get_injury_list(user_id)
            },
            "inventory": player.get("inventory", {}),
            "active_effects": player.get("active_effects", []),
            "challenge_path": quest_challenges.get_challenge_path_info(user_id),
            "abilities": quest_challenges.get_player_abilities(user_id),
            "last_updated": {
                "quest_cooldown": player.get("quest_cooldown"),
                "search_cooldown": player.get("search_cooldown"),
                "last_energy_regen": player.get("last_energy_regen")
            }
        }

        return details

    def heal_all_players(self, channel: str = None) -> Tuple[int, str]:
        """Heal all injured players. Returns (healed_count, message)."""
        from .quest_status import QuestStatus
        quest_status = QuestStatus(self.bot, self.state)

        all_players = self.state.get_all_players()
        healed_count = 0
        healed_players = []

        for user_id, player_data in all_players.items():
            if isinstance(player_data, dict) and quest_status.has_active_injuries(user_id):
                healed_injuries = quest_status.heal_injuries(user_id, all_injuries=True)
                if healed_injuries:
                    healed_count += 1
                    healed_players.append(self.bot.get_user_nick(user_id))

        if healed_count > 0:
            message = f"✅ Healed {healed_count} player(s): {', '.join(healed_players)}"
        else:
            message = "ℹ️ No players were injured."

        return healed_count, message

    def restore_all_energy(self, channel: str = None) -> Tuple[int, str]:
        """Restore energy for all players. Returns (restored_count, message)."""
        from .quest_energy import QuestEnergy
        quest_energy = QuestEnergy(self.bot, self.state)

        all_players = self.state.get_all_players()
        restored_count = 0
        total_restored = 0

        for user_id, player_data in all_players.items():
            if isinstance(player_data, dict):
                current_energy = player_data.get("energy", 0)
                max_energy = player_data.get("max_energy", 10)

                if current_energy < max_energy:
                    # Calculate how much to restore
                    restore_amount = max_energy - current_energy
                    actual_restored = quest_energy.restore_energy(user_id, restore_amount)
                    total_restored += actual_restored
                    restored_count += 1

        if restored_count > 0:
            message = f"✅ Restored energy for {restored_count} player(s). Total energy restored: {total_restored}"
        else:
            message = "ℹ️ All players already have full energy."

        return restored_count, message

    def grant_item_to_player(self, user_id: str, item_type: str, amount: int = 1) -> Tuple[bool, str]:
        """Grant items to a specific player."""
        from .quest_items import QuestItems
        quest_items = QuestItems(self.bot, self.state)

        # Validate item type
        valid_items = ["medkit", "energy_potion", "lucky_charm", "armor_shard", "xp_scroll"]
        if item_type not in valid_items:
            return False, f"Invalid item type. Valid items: {', '.join(valid_items)}"

        # Check if player exists
        player = self.state.get_player_data(user_id)
        if not player:
            return False, "Player not found."

        # Grant items
        success = quest_items.add_item(user_id, item_type, amount)
        if success:
            return True, f"Granted {amount} {item_type}(s) to {self.bot.get_user_nick(user_id)}."
        else:
            return False, "Failed to grant items."

    def grant_xp_to_player(self, user_id: str, amount: int) -> Tuple[bool, str]:
        """Grant XP to a specific player."""
        player = self.state.get_player_data(user_id)
        if not player:
            return False, "Player not found."

        if amount <= 0:
            return False, "XP amount must be positive."

        # Grant XP
        new_level, leveled_up = self.bot.quest_core.grant_xp(user_id, amount)
        nick = self.bot.get_user_nick(user_id)

        message = f"Granted {amount} XP to {nick}. New level: {new_level}"
        if leveled_up:
            message += f" 🎉 LEVEL UP!"

        return True, message

    def reset_player_data(self, user_id: str, confirm: bool = False) -> Tuple[bool, str]:
        """Reset a player's data to default. DANGEROUS - requires confirmation."""
        if not confirm:
            return False, "⚠️ This is a dangerous operation. Use confirm=True to proceed."

        player = self.state.get_player_data(user_id)
        if not player:
            return False, "Player not found."

        nick = self.bot.get_user_nick(user_id)

        # Reset to default data
        default_player = self.state._get_default_player_data()
        self.state.update_player_data(user_id, default_player)

        return True, f"⚠️ Reset all data for {nick}. This action cannot be undone."

    def get_active_mob_info(self) -> Optional[Dict[str, Any]]:
        """Get information about currently active mob encounter."""
        return self.state.get_active_mob()

    def force_close_mob(self) -> Tuple[bool, str]:
        """Force close the current mob encounter."""
        from .quest_combat import QuestCombat
        quest_combat = QuestCombat(self.bot, self.state)

        active_mob = self.state.get_active_mob()
        if not active_mob:
            return False, "No active mob encounter."

        # Clear the mob
        self.state.update_active_mob(None)
        return True, "✅ Force closed mob encounter."

    def get_system_health(self) -> Dict[str, Any]:
        """Get system health and diagnostic information."""
        all_players = self.state.get_all_players()

        health_stats = {
            "state_manager": {
                "total_players": len(all_players),
                "valid_players": len([p for p in all_players.values() if isinstance(p, dict)]),
                "corrupted_players": len([p for p in all_players.values() if not isinstance(p, dict)])
            },
            "active_mob": self.state.get_active_mob() is not None,
            "challenge_paths": self.state.get_challenge_paths(),
            "content_loaded": bool(self.state.get_content()),
            "memory_usage": {
                "estimated_players_kb": len(str(all_players)) // 1024,
                "estimated_state_kb": len(str(self.state.get_content())) // 1024
            }
        }

        # Check for common issues
        issues = []

        # Check for corrupted players
        if health_stats["state_manager"]["corrupted_players"] > 0:
            issues.append(f"Found {health_stats['state_manager']['corrupted_players']} corrupted player records")

        # Check for stuck mobs
        if health_stats["active_mob"]:
            active_mob = self.state.get_active_mob()
            if active_mob and time.time() > active_mob.get("close_epoch", 0):
                issues.append("Active mob encounter appears to be stuck")

        # Check for missing content
        if not health_stats["content_loaded"]:
            issues.append("Quest content not loaded")

        health_stats["issues"] = issues
        health_stats["healthy"] = len(issues) == 0

        return health_stats

    def cleanup_corrupted_data(self) -> Tuple[int, str]:
        """Clean up corrupted player data."""
        all_players = self.state.get_all_players()
        cleaned_count = 0

        cleaned_players = {}
        for user_id, player_data in all_players.items():
            if isinstance(player_data, dict):
                cleaned_players[user_id] = player_data
            else:
                cleaned_count += 1
                self.bot.log_debug(f"Removed corrupted player data for {user_id}")

        if cleaned_count > 0:
            # Update the state with cleaned data
            quest_state = self.bot.state_manager.get_module_state("quest", {})
            quest_state["players"] = cleaned_players
            self.bot.state_manager.update_module_state("quest", quest_state)

        return cleaned_count, f"Cleaned up {cleaned_count} corrupted player records."

    def format_admin_report(self) -> str:
        """Format a comprehensive admin report."""
        stats = self.get_quest_statistics()
        health = self.get_system_health()
        active_mob = self.get_active_mob_info()

        report = "📊 **QUEST SYSTEM ADMIN REPORT**\n"
        report += "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n\n"

        # System Health
        health_icon = "✅" if health["healthy"] else "⚠️"
        report += f"🏥 **System Health:** {health_icon}\n"
        if health["issues"]:
            for issue in health["issues"]:
                report += f"  • {issue}\n"
        report += "\n"

        # Player Statistics
        report += f"👥 **Player Statistics:**\n"
        report += f"  • Total Players: {stats['total_players']}\n"
        report += f"  • Active Players: {stats['active_players']}\n"
        report += f"  • Win Rate: {stats['win_rate']}%\n"
        report += f"  • Total XP Earned: {stats['total_xp_earned']:,}\n"
        report += f"  • Currently Injured: {stats['injury_count']}\n\n"

        # Level Distribution (top 5)
        report += "📈 **Top Levels:**\n"
        sorted_levels = sorted(stats["level_distribution"].items(), key=lambda x: int(x[0].split()[1]), reverse=True)
        for level, count in sorted_levels[:5]:
            report += f"  • {level}: {count} players\n"
        report += "\n"

        # Prestige Distribution
        if stats["prestige_distribution"]:
            report += "🌟 **Prestige Distribution:**\n"
            sorted_prestige = sorted(stats["prestige_distribution"].items(), key=lambda x: int(x[0].split()[1]), reverse=True)
            for prestige, count in sorted_prestige[:3]:
                report += f"  • {prestige}: {count} players\n"
            report += "\n"

        # Inventory Summary
        report += "📦 **Economy Summary:**\n"
        for item_type, count in stats["inventory_totals"].items():
            if count > 0:
                report += f"  • {item_type.replace('_', ' ').title()}: {count}\n"
        report += "\n"

        # Challenge Stats
        challenge_stats = stats["challenge_stats"]
        report += "🎯 **Challenge Paths:**\n"
        report += f"  • Active on Challenges: {challenge_stats['total_on_challenges']}\n"
        report += f"  • Completed Challenges: {challenge_stats['completed_challenges']}\n"
        report += f"  • Abilities Unlocked: {challenge_stats['abilities_unlocked']}\n\n"

        # Active Status
        if active_mob:
            report += f"⚔️ **Active Mob:** {active_mob['monster']['name']} in {active_mob['channel']}\n"
        else:
            report += "⚔️ **Active Mob:** None\n"

        return report