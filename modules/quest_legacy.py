# modules/quest_legacy.py
# Legacy Boss system for prestige 10+ players
import random
import time
from typing import Dict, Any, List, Tuple, Optional
from datetime import datetime, timezone

UTC = timezone.utc

class QuestLegacy:
    """Legacy Boss system for managing transcended players as permanent bosses."""

    def __init__(self, bot, state_manager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def get_legacy_data(self) -> Dict:
        """Get legacy system data."""
        return self.state.get_module_state("legacy", {
            "legacy_bosses": {},  # user_id -> legacy data
            "transcendence_count": {},  # user_id -> number of times transcended
            "legacy_titles": {},  # user_id -> current legacy title
            "boss_defeat_records": {}  # user_id -> times defeated as boss
        })

    def save_legacy_data(self, data: Dict):
        """Save legacy system data."""
        self.state.update_module_state("legacy", data)

    def can_transcend(self, user_id: str) -> Tuple[bool, str]:
        """Check if player can transcend (reach prestige 10 and choose to become a legacy boss)."""
        player = self.state.get_player_data(user_id)
        if not player:
            return False, "Player not found."

        current_prestige = player.get("prestige", 0)
        max_prestige = self.config.get("max_prestige", 10)

        if current_prestige < max_prestige:
            return False, f"You must reach prestige {max_prestige} to transcend."

        # Check if already transcended
        legacy_data = self.get_legacy_data()
        if user_id in legacy_data["legacy_bosses"]:
            return False, "You have already transcended and become a Legacy Boss!"

        return True, "You are ready to transcend!"

    def get_legacy_title(self, user_id: str) -> str:
        """Get the legacy title based on transcendence count."""
        legacy_data = self.get_legacy_data()
        transcend_count = legacy_data["transcendence_count"].get(user_id, 0)

        titles = [
            "the Legend",      # 1st transcendence
            "the Mythic",      # 2nd transcendence
            "the Eternal",     # 3rd transcendence
            "the Immortal",    # 4th transcendence
            "the Godlike",     # 5th transcendence
            "the Transcendent", # 6th+ transcendence
        ]

        return titles[min(transcend_count, len(titles) - 1)]

    def create_legacy_boss(self, user_id: str, username: str) -> Tuple[bool, str]:
        """Transform a prestige 10 player into a Legacy Boss."""
        can_transcend, message = self.can_transcend(user_id)
        if not can_transcend:
            return False, message

        player = self.state.get_player_data(user_id)
        legacy_data = self.get_legacy_data()

        # Create legacy boss data
        legacy_title = self.get_legacy_title(user_id)
        legacy_boss = {
            "username": username,
            "original_class": player.get("class", "Fighter"),
            "original_level": player.get("level", 20),
            "original_prestige": player.get("prestige", 10),
            "total_wins": player.get("wins", 0),
            "total_losses": player.get("losses", 0),
            "max_streak": player.get("max_streak", 0),
            "created_at": datetime.now(UTC).isoformat(),
            "legacy_title": legacy_title,
            "transcendence_number": legacy_data["transcendence_count"].get(user_id, 0) + 1,
            "boss_traits": self._generate_boss_traits(player),
            "special_abilities": self._generate_boss_abilities(player),
            "defeat_count": 0,
            "last_defeated_by": None,
            "defeat_history": []
        }

        # Add to legacy system
        legacy_data["legacy_bosses"][user_id] = legacy_boss
        legacy_data["transcendence_count"][user_id] = legacy_data["transcendence_count"].get(user_id, 0) + 1
        legacy_data["legacy_titles"][user_id] = legacy_title

        self.save_legacy_data(legacy_data)

        return True, f"🌟 **TRANSCENDENCE COMPLETE!** You have become {username} {legacy_title} and now live forever as a Legacy Boss!"

    def _generate_boss_traits(self, player: Dict) -> List[str]:
        """Generate boss traits based on player's original class and achievements."""
        traits = []
        player_class = player.get("class", "Fighter")
        wins = player.get("wins", 0)
        max_streak = player.get("max_streak", 0)

        # Class-based traits
        class_traits = {
            "Fighter": ["Brutal Strikes", "Armor Mastery"],
            "Mage": ["Arcane Power", "Elemental Control"],
            "Rogue": ["Shadow Strike", "Critical Mastery"],
            "Cleric": ["Divine Protection", "Healing Aura"],
            "Ranger": ["Precision Shots", "Beast Mastery"],
            "Barbarian": ["Rage Powers", "Unstoppable Force"],
            "Monk": ["Inner Focus", "Martial Arts Mastery"],
            "Druid": ["Nature's Wrath", "Shape Shifting"],
            "Necromancer": ["Dark Magic", "Undead Command"],
            "Paladin": ["Holy Strike", "Divine Shield"]
        }

        if player_class in class_traits:
            traits.extend(random.sample(class_traits[player_class], min(2, len(class_traits[player_class]))))

        # Achievement-based traits
        if wins >= 100:
            traits.append("Seasoned Warrior")
        if wins >= 500:
            traits.append("Legendary Champion")
        if max_streak >= 10:
            traits.append("On a Roll")
        if max_streak >= 25:
            traits.append("Unstoppable Force")

        return traits[:3]  # Max 3 traits

    def _generate_boss_abilities(self, player: Dict) -> List[str]:
        """Generate special boss abilities based on player's original class."""
        player_class = player.get("class", "Fighter")

        abilities = {
            "Fighter": ["Power Strike", "Whirlwind Attack"],
            "Mage": ["Fireball", "Lightning Bolt"],
            "Rogue": ["Backstab", "Smoke Bomb"],
            "Cleric": ["Heal", "Divine Smite"],
            "Ranger": ["Arrow Rain", "Beast Call"],
            "Barbarian": ["Berserker Rage", "Ground Slam"],
            "Monk": ["Flurry of Blows", "Meditative Focus"],
            "Druid": ["Entangle", "Wild Shape"],
            "Necromancer": ["Life Drain", "Summon Skeleton"],
            "Paladin": ["Holy Strike", "Blessing of Protection"]
        }

        return abilities.get(player_class, ["Basic Attack", "Special Move"])

    def get_random_legacy_boss(self, player_level: int = 20) -> Optional[Dict]:
        """Get a random legacy boss for encounters."""
        legacy_data = self.get_legacy_data()
        available_bosses = list(legacy_data["legacy_bosses"].values())

        if not available_bosses:
            return None

        # Select random boss
        boss = random.choice(available_bosses)

        # Scale boss to appropriate level
        scaled_boss = {
            "name": f"{boss['username']} {boss['legacy_title']}",
            "level": max(player_level - 2, 15),  # Slightly lower than player but challenging
            "is_legacy": True,
            "original_user_id": next(uid for uid, data in legacy_data["legacy_bosses"].items() if data["username"] == boss["username"]),
            "traits": boss["boss_traits"],
            "abilities": boss["special_abilities"],
            "class": boss["original_class"],
            "xp_reward": int(player_level * 150 * (1 + boss["transcendence_number"] * 0.2)),  # Bonus XP for higher transcendence
            "win_chance": min(0.4 + (boss["transcendence_number"] * 0.05), 0.7)  # Harder but not impossible
        }

        return scaled_boss

    def record_legacy_boss_defeat(self, boss_data: Dict, defeated_by: str, defeated_by_id: str):
        """Record when a legacy boss is defeated."""
        legacy_data = self.get_legacy_data()
        boss_user_id = boss_data.get("original_user_id")

        if boss_user_id and boss_user_id in legacy_data["legacy_bosses"]:
            boss = legacy_data["legacy_bosses"][boss_user_id]
            boss["defeat_count"] += 1
            boss["last_defeated_by"] = {
                "username": defeated_by,
                "user_id": defeated_by_id,
                "defeated_at": datetime.now(UTC).isoformat()
            }
            boss["defeat_history"].append({
                "defeated_by": defeated_by,
                "defeated_by_id": defeated_by_id,
                "defeated_at": datetime.now(UTC).isoformat(),
                "player_level": self.state.get_player_data(defeated_by_id).get("level", 1)
            })

            # Keep only last 10 defeats in history
            boss["defeat_history"] = boss["defeat_history"][-10:]

            self.save_legacy_data(legacy_data)

    def get_legacy_hall_of_fame(self) -> List[Dict]:
        """Get the Legacy Hall of Fame - all transcended players."""
        legacy_data = self.get_legacy_data()
        bosses = []

        for user_id, boss_data in legacy_data["legacy_bosses"].items():
            bosses.append({
                "username": boss_data["username"],
                "title": boss_data["legacy_title"],
                "original_class": boss_data["original_class"],
                "original_prestige": boss_data["original_prestige"],
                "transcendence_number": boss_data["transcendence_number"],
                "defeat_count": boss_data["defeat_count"],
                "total_wins": boss_data["total_wins"],
                "created_at": boss_data["created_at"],
                "traits": boss_data["boss_traits"],
                "last_defeated_by": boss_data.get("last_defeated_by")
            })

        # Sort by transcendence number, then by creation date
        bosses.sort(key=lambda x: (-x["transcendence_number"], x["created_at"]))
        return bosses

    def reset_player_for_transcendence(self, user_id: str) -> Tuple[bool, str]:
        """Reset player data after transcendence."""
        player = self.state.get_player_data(user_id)
        if not player:
            return False, "Player not found."

        # Store current prestige bonuses
        old_prestige = player.get("prestige", 10)
        old_class = player.get("class", "Fighter")
        old_prestige_bonuses = player.get("prestige_bonuses", []).copy()
        transcendence_count = player.get("transcendence_count", 0) + 1

        player.update({
            "prestige": 1,  # Reset to prestige 1, but keep the XP bonus equivalent
            "level": 1,
            "xp": 0,
            "energy": 10,
            "max_energy": 10,
            "wins": 0,
            "losses": 0,
            "streak": 0,
            "max_streak": 0,
            "injuries": [],
            "inventory": {
                "medkits": 0,
                "energy_potions": 0,
                "lucky_charms": 0,
                "armor_shards": 0,
                "xp_scrolls": 0
            },
            "active_effects": [],
            "quest_cooldown": None,
            "search_cooldown": None,
            "legacy_bonus": True,  # Mark as having legacy bonuses
            "transcendence_count": transcendence_count,
            "original_class": old_class,
            "transcended_at": datetime.now(UTC).isoformat(),
            "effective_prestige": old_prestige,  # Keep the effective prestige for XP calculations
            "prestige_bonuses": old_prestige_bonuses  # Keep all previous prestige bonuses
        })

        # Add new transcendence bonus
        player["prestige_bonuses"].append(f"+{15 + (transcendence_count - 1) * 5}% XP gain (Transcended {transcendence_count}x)")
        player["prestige_bonuses"].append(f"Legacy Aura: Your boss form grants bonus XP when defeated")

        self.state.update_player_data(user_id, player)

        total_xp_bonus = old_prestige * 10 + 15 + (transcendence_count - 1) * 5
        return True, f"Your journey begins anew with transcendent powers! You retain your +{old_prestige * 10}% prestige bonus and gain +{15 + (transcendence_count - 1) * 5}% transcendence bonus (Total: +{total_xp_bonus}% XP gain)!"