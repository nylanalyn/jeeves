# modules/quest_items.py
# Inventory and search system for quest module
import random
import time
from typing import Dict, Any, List, Tuple, Optional

from .quest_state import QuestStateManager


class QuestItems:
    """Item and inventory management for quest system."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def add_item(self, user_id: str, item_type: str, count: int = 1) -> bool:
        """Add items to player inventory."""
        player = self.state.get_player_data(user_id)

        inventory_key = f"{item_type}s" if not item_type.endswith('s') else item_type
        if inventory_key == "medkit":  # Special case
            inventory_key = "medkits"
        elif inventory_key == "xp_scroll":  # Special case
            inventory_key = "xp_scrolls"

        if "inventory" not in player:
            player["inventory"] = {}

        player["inventory"][inventory_key] = player["inventory"].get(inventory_key, 0) + count
        self.state.update_player_data(user_id, player)
        return True

    def remove_item(self, user_id: str, item_type: str, count: int = 1) -> bool:
        """Remove items from player inventory. Returns True if successful."""
        player = self.state.get_player_data(user_id)

        inventory_key = self._get_inventory_key(item_type)

        if not inventory_key:
            return False

        current_count = player.get("inventory", {}).get(inventory_key, 0)
        if current_count < count:
            return False

        player["inventory"][inventory_key] = current_count - count
        self.state.update_player_data(user_id, player)
        return True

    def get_item_count(self, user_id: str, item_type: str) -> int:
        """Get count of specific item in player inventory."""
        player = self.state.get_player_data(user_id)
        inventory_key = self._get_inventory_key(item_type)

        if not inventory_key:
            return 0

        return player.get("inventory", {}).get(inventory_key, 0)

    def _get_inventory_key(self, item_type: str) -> Optional[str]:
        """Convert user-friendly item name to inventory key."""
        item_map = {
            "medkit": "medkits",
            "energy_potion": "energy_potions",
            "potion": "energy_potions",
            "lucky_charm": "lucky_charms",
            "charm": "lucky_charms",
            "armor_shard": "armor_shards",
            "armor": "armor_shards",
            "xp_scroll": "xp_scrolls",
            "scroll": "xp_scrolls"
        }
        return item_map.get(item_type.lower())

    def perform_search(self, user_id: str) -> Dict[str, Any]:
        """Perform a single search attempt. Returns result dictionary."""
        player = self.state.get_player_data(user_id)

        # Get search configuration
        search_config = self.config.get("search_system", {})
        energy_cost = search_config.get("energy_cost", 1)

        # Check if player has enough energy
        if player["energy"] < energy_cost:
            return {
                "success": False,
                "message": f"You don't have enough energy! You need {energy_cost} energy to search."
            }

        # Deduct energy cost
        player["energy"] -= energy_cost

        # Determine search result
        result = self._perform_single_search_result(player)

        if result["success"]:
            # Update inventory if item found
            if result["type"] == "item":
                item_key = result["item"] + "s" if not result["item"].endswith('s') else result["item"]
                if item_key == "medkit":  # Special case
                    item_key = "medkits"
                elif item_key == "xp_scroll":  # Special case
                    item_key = "xp_scrolls"

                player["inventory"][item_key] = player["inventory"].get(item_key, 0) + 1

        # Set search cooldown
        cooldown_seconds = self.config.get("cooldown_seconds", 300)
        player["search_cooldown"] = time.time() + cooldown_seconds

        self.state.update_player_data(user_id, player)
        return result

    def _perform_single_search_result(self, player: Dict[str, Any]) -> Dict[str, Any]:
        """Determine what (if anything) is found during search."""
        search_config = self.config.get("search_system", {})

        # Get drop chances
        medkit_chance = search_config.get("medkit_chance", 0.25)
        energy_potion_chance = search_config.get("energy_potion_chance", 0.15)
        lucky_charm_chance = search_config.get("lucky_charm_chance", 0.15)
        armor_shard_chance = search_config.get("armor_shard_chance", 0.10)
        xp_scroll_chance = search_config.get("xp_scroll_chance", 0.10)
        injury_chance = search_config.get("injury_chance", 0.05)

        # Roll for outcome
        roll = random.random()
        cumulative = 0.0

        # Check for injury first (bad outcome)
        if roll < injury_chance:
            return {
                "success": True,
                "type": "injury",
                "message": "Ouch! You got hurt while searching and found nothing.",
                "xp_change": 0
            }

        # Check for items in order of rarity/value
        items = [
            ("medkit", medkit_chance, "a MEDKIT"),
            ("energy_potion", energy_potion_chance, "an ENERGY POTION"),
            ("lucky_charm", lucky_charm_chance, "a LUCKY CHARM"),
            ("armor_shard", armor_shard_chance, "an ARMOR SHARD"),
            ("xp_scroll", xp_scroll_chance, "an XP SCROLL")
        ]

        for item_name, chance, display_name in items:
            cumulative += chance
            if roll < cumulative:
                return {
                    "success": True,
                    "type": "item",
                    "item": item_name,
                    "message": f"You found {display_name}!",
                    "xp_change": 0
                }

        # Nothing found
        return {
            "success": True,
            "type": "nothing",
            "message": "You search carefully but find nothing of value.",
            "xp_change": 0
        }

    def use_item(self, user_id: str, item_type: str, **kwargs) -> Dict[str, Any]:
        """Use an item from inventory. Returns result dictionary."""
        player = self.state.get_player_data(user_id)
        inventory_key = self._get_inventory_key(item_type)

        if not inventory_key:
            return {
                "success": False,
                "message": f"Unknown item: {item_type}. Available: medkit, energy_potion, lucky_charm, armor_shard, xp_scroll"
            }

        if self.get_item_count(user_id, item_type) < 1:
            return {
                "success": False,
                "message": f"You don't have any {item_type}s!"
            }

        # Handle different item types
        if inventory_key == "medkits":
            return self._use_medkit(user_id, **kwargs)
        elif inventory_key == "energy_potions":
            return self._use_energy_potion(user_id)
        elif inventory_key == "lucky_charms":
            return self._use_lucky_charm(user_id)
        elif inventory_key == "armor_shards":
            return self._use_armor_shard(user_id)
        elif inventory_key == "xp_scrolls":
            return self._use_xp_scroll(user_id)

        return {
            "success": False,
            "message": f"Unable to use {item_type}."
        }

    def _use_medkit(self, user_id: str, target_user_id: Optional[str] = None, **kwargs) -> Dict[str, Any]:
        """Use medkit to heal injuries."""
        # Import QuestStatus here to avoid circular imports
        from .quest_status import QuestStatus

        player = self.state.get_player_data(user_id)
        quest_status = QuestStatus(self.bot, self.state)

        # Determine target
        if target_user_id:
            target_player = self.state.get_player_data(target_user_id)
            target_nick = self.bot.get_user_nick(target_user_id)
            is_self = False
        else:
            target_player = player
            target_user_id = user_id
            target_nick = self.bot.get_user_nick(user_id)
            is_self = True

        # Check if target has injuries
        if not target_player.get("injuries"):
            return {
                "success": False,
                "message": "Target is not injured! Save your medkit for when it's needed."
            }

        # Use medkit
        if not self.remove_item(user_id, "medkit"):
            return {
                "success": False,
                "message": "Failed to use medkit."
            }

        # Heal injuries
        healed_injuries = quest_status.heal_injuries(target_user_id, all_injuries=True)

        # Track medkit usage for challenge paths
        if "challenge_stats" not in player:
            player["challenge_stats"] = {}
        player["challenge_stats"]["medkits_used_this_prestige"] = player["challenge_stats"].get("medkits_used_this_prestige", 0) + 1
        self.state.update_player_data(user_id, player)

        # Calculate XP reward
        base_xp = self.config.get("base_xp_reward", 50)
        if is_self:
            xp_reward = int(base_xp * self.config.get("medic_quests", {}).get("self_heal_xp_multiplier", 0.75))
        else:
            xp_reward = int(base_xp * self.config.get("medic_quests", {}).get("altruistic_heal_xp_multiplier", 3.0))

        # Grant XP to healer
        if is_self:
            injury_names = [injury["name"] for injury in healed_injuries]
            if len(injury_names) == 1:
                message = f"You use a medkit and recover from {injury_names[0]}! (+{xp_reward} XP)"
            else:
                message = f"You use a medkit and recover from all injuries ({', '.join(injury_names)})! (+{xp_reward} XP)"
        else:
            injury_names = [injury["name"] for injury in healed_injuries]
            if len(injury_names) == 1:
                message = f"You use a medkit to heal {target_nick}'s {injury_names[0]}! Such selflessness is rewarded with +{xp_reward} XP!"
            else:
                message = f"You use a medkit to heal all of {target_nick}'s injuries ({', '.join(injury_names)})! Such selflessness is rewarded with +{xp_reward} XP!"

        return {
            "success": True,
            "type": "heal",
            "message": message,
            "xp_reward": xp_reward,
            "healed_injuries": healed_injuries
        }

    def _use_energy_potion(self, user_id: str) -> Dict[str, Any]:
        """Use energy potion to restore energy."""
        player = self.state.get_player_data(user_id)
        max_energy = player["max_energy"]

        if player["energy"] >= max_energy:
            return {
                "success": False,
                "message": "Your energy is already full! Save the potion for later."
            }

        # Use potion
        if not self.remove_item(user_id, "energy_potion"):
            return {
                "success": False,
                "message": "Failed to use energy potion."
            }

        # Restore 2-4 energy
        restore_range = random.randint(2, 4)
        actual_restore = min(restore_range, max_energy - player["energy"])
        player["energy"] = min(player["energy"] + restore_range, max_energy)

        self.state.update_player_data(user_id, player)

        return {
            "success": True,
            "type": "energy_restore",
            "message": f"You drink the energy potion and feel refreshed! +{actual_restore} energy ({player['energy']}/{max_energy}).",
            "energy_restored": actual_restore
        }

    def _use_lucky_charm(self, user_id: str) -> Dict[str, Any]:
        """Use lucky charm for next combat."""
        player = self.state.get_player_data(user_id)

        # Check if already has lucky charm effect
        has_charm = any(eff["type"] == "lucky_charm" for eff in player.get("active_effects", []))
        if has_charm:
            return {
                "success": False,
                "message": "You already have a lucky charm active! The effects don't stack."
            }

        # Use charm
        if not self.remove_item(user_id, "lucky_charm"):
            return {
                "success": False,
                "message": "Failed to use lucky charm."
            }

        # Add effect
        if "active_effects" not in player:
            player["active_effects"] = []

        effect = {
            "type": "lucky_charm",
            "expires": "next_fight",
            "win_bonus": 15,  # +15% win chance
            "description": "Lucky Charm (+15% win chance)"
        }
        player["active_effects"].append(effect)
        self.state.update_player_data(user_id, player)

        return {
            "success": True,
            "type": "combat_bonus",
            "message": f"You activate the lucky charm! Your next fight will have +15% win chance.",
            "effect": effect
        }

    def _use_armor_shard(self, user_id: str) -> Dict[str, Any]:
        """Use armor shard to reduce injury chance."""
        player = self.state.get_player_data(user_id)

        # Check if already has armor effect
        has_armor = any(eff["type"] == "armor_shard" for eff in player.get("active_effects", []))
        if has_armor:
            return {
                "success": False,
                "message": "You already have armor shard protection active!"
            }

        # Use shard
        if not self.remove_item(user_id, "armor_shard"):
            return {
                "success": False,
                "message": "Failed to use armor shard."
            }

        # Add effect
        if "active_effects" not in player:
            player["active_effects"] = []

        effect = {
            "type": "armor_shard",
            "remaining_fights": 3,
            "injury_reduction": 0.30,  # 30% reduction
            "description": "Armor Shard (30% injury reduction, 3 fights)"
        }
        player["active_effects"].append(effect)
        self.state.update_player_data(user_id, player)

        return {
            "success": True,
            "type": "defense_bonus",
            "message": "You equip the armor shard! Injury chance reduced by 30% for the next 3 fights.",
            "effect": effect
        }

    def _use_xp_scroll(self, user_id: str) -> Dict[str, Any]:
        """Use XP scroll for bonus XP on next win."""
        player = self.state.get_player_data(user_id)

        # Check if already has scroll effect
        has_scroll = any(eff["type"] == "xp_scroll" for eff in player.get("active_effects", []))
        if has_scroll:
            return {
                "success": False,
                "message": "You already have an XP scroll active! The effects don't stack."
            }

        # Use scroll
        if not self.remove_item(user_id, "xp_scroll"):
            return {
                "success": False,
                "message": "Failed to use XP scroll."
            }

        # Add effect
        if "active_effects" not in player:
            player["active_effects"] = []

        effect = {
            "type": "xp_scroll",
            "expires": "next_win",
            "xp_multiplier": 1.5,  # 1.5x XP
            "description": "XP Scroll (1.5x XP on next win)"
        }
        player["active_effects"].append(effect)
        self.state.update_player_data(user_id, player)

        return {
            "success": True,
            "type": "xp_bonus",
            "message": "You read the XP scroll! Your next victory will grant 1.5x XP.",
            "effect": effect
        }

    def format_inventory_display(self, user_id: str) -> str:
        """Format player inventory for display."""
        player = self.state.get_player_data(user_id)
        inventory = player.get("inventory", {})

        # Build inventory display
        items = []
        if inventory.get("medkits", 0) > 0:
            items.append(f"Medkits: {inventory['medkits']}")
        if inventory.get("energy_potions", 0) > 0:
            items.append(f"Energy Potions: {inventory['energy_potions']}")
        if inventory.get("lucky_charms", 0) > 0:
            items.append(f"Lucky Charms: {inventory['lucky_charms']}")
        if inventory.get("armor_shards", 0) > 0:
            items.append(f"Armor Shards: {inventory['armor_shards']}")
        if inventory.get("xp_scrolls", 0) > 0:
            items.append(f"XP Scrolls: {inventory['xp_scrolls']}")

        if not items:
            return "📦 Your inventory is empty."

        inventory_text = "📦 **Inventory:**\n" + " | ".join(items)

        # Show active effects
        active_effects = player.get("active_effects", [])
        if active_effects:
            effects_text = "\n✨ **Active Effects:**\n"
            for effect in active_effects:
                if effect["type"] == "lucky_charm":
                    effects_text += f"• {effect.get('description', 'Lucky Charm')}\n"
                elif effect["type"] == "armor_shard":
                    remaining = effect.get("remaining_fights", 0)
                    effects_text += f"• {effect.get('description', 'Armor Shard')} ({remaining} fights remaining)\n"
                elif effect["type"] == "xp_scroll":
                    effects_text += f"• {effect.get('description', 'XP Scroll')}\n"
            inventory_text += effects_text

        return inventory_text

    def get_available_items(self) -> List[str]:
        """Get list of usable items."""
        return ["medkit", "energy_potion", "lucky_charm", "armor_shard", "xp_scroll"]