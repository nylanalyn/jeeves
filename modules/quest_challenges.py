# modules/quest_challenges.py
# Challenge path system and abilities for quest module
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Tuple

from .quest_state import QuestStateManager

UTC = timezone.utc


class QuestChallenges:
    """Challenge path system and abilities management for quest module."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()

    def load_challenge_paths(self) -> Dict[str, Any]:
        """Load challenge paths from challenge_paths.json file."""
        paths_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "challenge_paths.json")

        try:
            with open(paths_file, 'r') as f:
                paths = json.load(f)
                self.bot.log_debug(f"Loaded challenge paths from {paths_file}")
                return paths
        except FileNotFoundError:
            self.bot.log_debug(f"Challenge paths file not found at {paths_file}")
            return {"paths": {}, "abilities": {}, "active_path": None}
        except json.JSONDecodeError as e:
            self.bot.log_debug(f"Error parsing challenge paths JSON: {e}")
            return {"paths": {}, "abilities": {}, "active_path": None}

    def save_challenge_paths(self, paths: Dict[str, Any]) -> bool:
        """Save challenge paths back to challenge_paths.json file."""
        paths_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "challenge_paths.json")
        try:
            with open(paths_file, 'w') as f:
                json.dump(paths, f, indent=2)
            self.bot.log_debug(f"Saved challenge paths to {paths_file}")
            return True
        except Exception as e:
            self.bot.log_debug(f"Error saving challenge paths: {e}")
            return False

    def get_active_challenge_path(self) -> Optional[str]:
        """Get the currently active challenge path ID."""
        paths = self.state.get_challenge_paths()
        return paths.get("active_path")

    def activate_challenge_path(self, path_name: str) -> Tuple[bool, str]:
        """Activate a challenge path by name."""
        paths = self.load_challenge_paths()

        if path_name not in paths.get("paths", {}):
            available = list(paths.get("paths", {}).keys())
            return False, f"Challenge path '{path_name}' not found. Available: {', '.join(available)}"

        path_data = paths["paths"][path_name]

        # Validate path structure
        required_fields = ["name", "description", "requirements", "rewards"]
        missing_fields = [field for field in required_fields if field not in path_data]
        if missing_fields:
            return False, f"Challenge path '{path_name}' is missing required fields: {', '.join(missing_fields)}"

        # Activate the path
        paths["active_path"] = path_name
        if not self.save_challenge_paths(paths):
            return False, f"Failed to save challenge paths configuration."

        # Update state
        self.state.update_challenge_paths(paths)

        return True, f"Challenge path '{path_name}' activated! Players at level 20 can now use !quest prestige challenge to enter this path."

    def deactivate_challenge_path(self) -> Tuple[bool, str]:
        """Deactivate the current challenge path."""
        paths = self.load_challenge_paths()
        active_path = paths.get("active_path")

        if not active_path:
            return False, "No challenge path is currently active."

        old_path = active_path
        paths["active_path"] = None

        if not self.save_challenge_paths(paths):
            return False, "Failed to save challenge paths configuration."

        # Update state
        self.state.update_challenge_paths(paths)

        return True, f"Challenge path '{old_path}' deactivated."

    def list_challenge_paths(self) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """List all available challenge paths. Returns (paths_list, active_path_name)."""
        paths = self.load_challenge_paths()
        paths_list = []
        active_path = paths.get("active_path")

        for path_id, path_data in paths.get("paths", {}).items():
            path_info = {
                "id": path_id,
                "name": path_data.get("name", path_id),
                "description": path_data.get("description", "No description"),
                "active": path_id == active_path
            }
            paths_list.append(path_info)

        return paths_list, active_path

    def can_enter_challenge_path(self, user_id: str) -> Tuple[bool, str]:
        """Check if player can enter challenge path and return requirements."""
        active_path_id = self.get_active_challenge_path()
        if not active_path_id:
            return False, "No challenge path is currently available."

        paths = self.load_challenge_paths()
        path_data = paths["paths"].get(active_path_id)
        if not path_data:
            return False, "Challenge path data not found."

        player = self.state.get_player_data(user_id)
        requirements = path_data.get("requirements", {})

        # Check prestige requirements
        min_prestige = requirements.get("min_prestige", 0)
        max_prestige = requirements.get("max_prestige", 999)

        current_prestige = player.get("prestige", 0)
        if current_prestige < min_prestige:
            return False, f"You need at least Prestige {min_prestige} to enter this challenge path."
        if current_prestige > max_prestige:
            return False, f"You have exceeded the maximum prestige ({max_prestige}) for this challenge path."

        return True, f"Requirements met. Ready to enter {path_data.get('name', active_path_id)}!"

    def enter_challenge_path(self, user_id: str, username: str) -> Tuple[bool, str]:
        """Enter a challenge path (challenge prestige)."""
        can_enter, message = self.can_enter_challenge_path(user_id)
        if not can_enter:
            return False, message

        # Get challenge path data
        active_path_id = self.get_active_challenge_path()
        paths = self.load_challenge_paths()
        path_data = paths["paths"][active_path_id]

        # Reset player for challenge path
        player = self.state.get_player_data(user_id)

        # Reset basic stats
        player["xp"] = 0
        player["level"] = 1
        player["energy"] = player["max_energy"]
        player["wins"] = 0
        player["losses"] = 0
        player["streak"] = 0
        player["max_streak"] = 0

        # Clear injuries and effects
        from .quest_status import QuestStatus
        quest_status = QuestStatus(self.bot, self.state)
        quest_status.heal_injuries(user_id, all_injuries=True)
        player["active_effects"] = []

        # Set challenge path tracking
        player["challenge_path"] = active_path_id

        # Reset challenge stats for new prestige
        player["challenge_stats"] = {
            "path": active_path_id,
            "prestige_count": player.get("prestige", 0),
            "medkits_used_this_prestige": 0,
            "completed": False
        }

        # Reset inventory based on challenge rules
        requirements = path_data.get("requirements", {})
        if requirements.get("no_medkits", False):
            player["inventory"] = {
                "medkits": 0,
                "energy_potions": player["inventory"].get("energy_potions", 0),
                "lucky_charms": player["inventory"].get("lucky_charms", 0),
                "armor_shards": player["inventory"].get("armor_shards", 0),
                "xp_scrolls": player["inventory"].get("xp_scrolls", 0)
            }

        # Update prestige count
        player["prestige"] += 1

        self.state.update_player_data(user_id, player)

        return True, f"🎯 **CHALLENGE PATH ENTERED!** You are now on the {path_data.get('name')} challenge path!"

    def check_challenge_completion(self, user_id: str, username: str) -> Tuple[bool, List[str]]:
        """Check if player completed challenge path requirements. Returns (completed, messages)."""
        player = self.state.get_player_data(user_id)
        challenge_path_id = player.get("challenge_path")

        if not challenge_path_id or player.get("level", 1) < 20:
            return False, []

        paths = self.load_challenge_paths()
        path_data = paths["paths"].get(challenge_path_id)
        if not path_data:
            return False, []

        requirements = path_data.get("requirements", {})
        rewards = path_data.get("rewards", {})
        messages = []

        # Check completion requirements
        completed = True
        completion_issues = []

        # Check medkit usage limit
        if requirements.get("no_medkits", False):
            medkits_used = player.get("challenge_stats", {}).get("medkits_used_this_prestige", 0)
            if medkits_used > 0:
                completed = False
                completion_issues.append(f"used {medkits_used} medkit(s)")

        if not completed:
            messages.append("❌ **Challenge Failed**")
            messages.append("You reached level 20, but you did not complete the challenge requirements:")
            for issue in completion_issues:
                messages.append(f"• {issue}")
            messages.append("You can still use !quest prestige challenge to continue, but you won't earn the challenge rewards.")
            return False, messages

        # Player completed the challenge! Grant rewards
        player["challenge_stats"]["completed"] = True
        messages.append("🎉 **CHALLENGE COMPLETED!**")
        messages.append(f"You have successfully completed the {path_data.get('name', challenge_path_id)} challenge!")

        # Unlock ability
        if "ability_unlock" in rewards:
            ability_id = rewards["ability_unlock"]
            if "unlocked_abilities" not in player:
                player["unlocked_abilities"] = []
            if ability_id not in player["unlocked_abilities"]:
                player["unlocked_abilities"].append(ability_id)

                ability_data = paths.get("abilities", {}).get(ability_id, {})
                ability_name = ability_data.get("name", ability_id)
                messages.append(f"✨ **NEW ABILITY UNLOCKED: {ability_name}!**")
                messages.append(f"Use !quest ability {ability_data.get('command', ability_id)} to activate it.")

        # Grant other rewards
        if "prestige_bonus" in rewards:
            bonus = rewards["prestige_bonus"]
            if "prestige_bonuses" not in player:
                player["prestige_bonuses"] = []
            player["prestige_bonuses"].append(bonus)
            messages.append(f"🎁 **Reward:** {bonus}")

        self.state.update_player_data(user_id, player)
        return True, messages

    def use_ability(self, user_id: str, username: str, ability_name: str) -> Tuple[bool, str]:
        """Use an unlocked ability."""
        player = self.state.get_player_data(user_id)
        unlocked_abilities = player.get("unlocked_abilities", [])

        if not unlocked_abilities:
            return False, f"{username}, you haven't unlocked any abilities yet. Complete challenge paths to earn them!"

        # Find the ability by command name
        paths = self.load_challenge_paths()
        abilities_data = paths.get("abilities", {})

        ability_id = None
        ability_data = None

        for aid, adata in abilities_data.items():
            if adata.get("command", "").lower() == ability_name.lower():
                ability_id = aid
                ability_data = adata
                break

        if not ability_id or ability_id not in unlocked_abilities:
            return False, f"You don't have the '{ability_name}' ability unlocked."

        # Check cooldown
        cooldowns = player.get("ability_cooldowns", {})
        if ability_id in cooldowns:
            cooldown_expires = datetime.fromisoformat(cooldowns[ability_id])
            if cooldown_expires > datetime.now(UTC):
                time_left = cooldown_expires - datetime.now(UTC)
                hours = int(time_left.total_seconds() // 3600)
                minutes = int((time_left.total_seconds() % 3600) // 60)
                return False, f"That ability is on cooldown for {hours}h {minutes}m."

        # Execute the ability
        effect = ability_data.get("effect")
        if effect == "heal_all_injuries":
            success = self._execute_heal_all_effect(username, ability_data)
        elif effect == "restore_energy":
            success = self._execute_energy_effect(user_id, ability_data)
        elif effect == "buff_party":
            success = self._execute_party_buff_effect(username, ability_data)
        else:
            return False, f"Unknown ability effect: {effect}"

        if success:
            # Set cooldown
            cooldown_hours = ability_data.get("cooldown_hours", 24)
            cooldown_expires = datetime.now(UTC) + timedelta(hours=cooldown_hours)

            if "ability_cooldowns" not in player:
                player["ability_cooldowns"] = {}
            player["ability_cooldowns"][ability_id] = cooldown_expires.isoformat()

            self.state.update_player_data(user_id, player)

            # Make announcement
            announcement = ability_data.get("announcement", "{user} uses {ability}!")
            announcement = announcement.format(user=self.bot.title_for(username), ability=ability_data.get("name"))
            # This would be called from the main module to handle the actual announcement

            return True, announcement

        return False, "Failed to execute ability."

    def _execute_heal_all_effect(self, username: str, ability_data: Dict[str, Any]) -> bool:
        """Execute heal all injuries ability effect."""
        from .quest_status import QuestStatus
        quest_status = QuestStatus(self.bot, self.state)

        # Find all players with injuries and heal them
        all_players = self.state.get_all_players()
        healed_count = 0

        for user_id, player_data in all_players.items():
            if quest_status.has_active_injuries(user_id):
                healed_injuries = quest_status.heal_injuries(user_id, all_injuries=True)
                if healed_injuries:
                    healed_count += 1

        return healed_count > 0

    def _execute_energy_effect(self, user_id: str, ability_data: Dict[str, Any]) -> bool:
        """Execute energy restoration ability effect."""
        from .quest_energy import QuestEnergy
        quest_energy = QuestEnergy(self.bot, self.state)

        energy_amount = ability_data.get("effect_data", {}).get("energy_amount", 5)
        restored = quest_energy.restore_energy(user_id, energy_amount)

        return restored > 0

    def _execute_party_buff_effect(self, username: str, ability_data: Dict[str, Any]) -> bool:
        """Execute party buff ability effect."""
        # This would be more complex in a full implementation
        # For now, just return True as a placeholder
        return True

    def get_player_abilities(self, user_id: str) -> List[Dict[str, Any]]:
        """Get list of player's unlocked abilities with cooldown status."""
        player = self.state.get_player_data(user_id)
        unlocked_abilities = player.get("unlocked_abilities", [])

        if not unlocked_abilities:
            return []

        paths = self.load_challenge_paths()
        abilities_data = paths.get("abilities", {})
        cooldowns = player.get("ability_cooldowns", {})
        abilities_list = []

        for ability_id in unlocked_abilities:
            ability = abilities_data.get(ability_id, {})
            if not ability:
                continue

            ability_name = ability.get("name", ability_id)
            description = ability.get("description", "No description")
            command = ability.get("command", ability_id)

            # Check cooldown status
            is_ready = True
            cooldown_remaining = None

            if ability_id in cooldowns:
                cooldown_expires = datetime.fromisoformat(cooldowns[ability_id])
                if cooldown_expires > datetime.now(UTC):
                    is_ready = False
                    time_left = cooldown_expires - datetime.now(UTC)
                    hours = int(time_left.total_seconds() // 3600)
                    minutes = int((time_left.total_seconds() % 3600) // 60)
                    cooldown_remaining = f"{hours}h {minutes}m"

            abilities_list.append({
                "id": ability_id,
                "name": ability_name,
                "description": description,
                "command": command,
                "is_ready": is_ready,
                "cooldown_remaining": cooldown_remaining
            })

        return abilities_list

    def format_abilities_display(self, user_id: str) -> str:
        """Format abilities display for a player."""
        abilities = self.get_player_abilities(user_id)

        if not abilities:
            return "🎭 You haven't unlocked any abilities yet. Complete challenge paths to earn them!"

        response = "🎭 **Your Abilities:**\n"

        for ability in abilities:
            if ability["is_ready"]:
                response += f"• !quest ability {ability['command']} - {ability['description']} [READY]\n"
            else:
                response += f"• !quest ability {ability['command']} - {ability['description']} [Cooldown: {ability['cooldown_remaining']}]\n"

        return response.strip()

    def get_challenge_path_info(self, user_id: str) -> Optional[str]:
        """Get formatted info about player's current challenge path."""
        player = self.state.get_player_data(user_id)
        challenge_path_id = player.get("challenge_path")

        if not challenge_path_id:
            return None

        paths = self.load_challenge_paths()
        path_data = paths["paths"].get(challenge_path_id)
        if not path_data:
            return None

        challenge_stats = player.get("challenge_stats", {})
        completed = challenge_stats.get("completed", False)

        status = "✅ COMPLETED" if completed else "🔄 IN PROGRESS"
        return f"🎯 Challenge Path: {path_data.get('name', challenge_path_id)} [{status}]"