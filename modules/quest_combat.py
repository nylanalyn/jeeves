# modules/quest_combat.py
# Combat mechanics, encounters, and group content for quest module
import random
import time
import schedule
import threading
from typing import Dict, Any, List, Tuple, Optional

from .quest_state import QuestStateManager


class QuestCombat:
    """Combat system for solo quests, mob encounters, and boss fights."""

    def __init__(self, bot, state_manager: QuestStateManager):
        self.bot = bot
        self.state = state_manager
        self.config = state_manager.get_quest_config()
        self.mob_lock = threading.Lock()

    def calculate_win_chance(self, player_level: int, monster_level: int,
                           energy_modifier: float = 0.0, group_modifier: float = 0.0,
                           prestige_level: int = 0) -> float:
        """Calculate win chance for combat encounters."""
        combat_config = self.config.get("combat", {})
        base_win = combat_config.get("base_win_chance", 0.50)
        level_mod = combat_config.get("win_chance_level_modifier", 0.10)
        min_win = combat_config.get("min_win_chance", 0.05)
        max_win = combat_config.get("max_win_chance", 0.95)

        level_diff = player_level - monster_level
        prestige_bonus = prestige_level * 0.05  # 5% per prestige level

        chance = base_win + (level_diff * level_mod) + energy_modifier + group_modifier + prestige_bonus
        return max(min_win, min(max_win, chance))

    def get_random_monster(self, player_level: int, is_boss: bool = False) -> Optional[Dict[str, Any]]:
        """Get a random monster appropriate for the player's level."""
        if is_boss:
            # Try to get a Legacy Boss first (25% chance)
            if random.random() < 0.25:
                from .quest_legacy import QuestLegacy
                legacy = QuestLegacy(self.bot, self.state)
                legacy_boss = legacy.get_random_legacy_boss(player_level)
                if legacy_boss:
                    return legacy_boss

            # Fall back to regular boss monsters
            monsters = self.config.get("boss_monsters", [])
        else:
            monsters = self.config.get("monsters", [])

        suitable_monsters = []
        for monster in monsters:
            if monster["min_level"] <= player_level <= monster["max_level"]:
                suitable_monsters.append(monster)

        if not suitable_monsters:
            # Fallback to any monster
            suitable_monsters = monsters

        return random.choice(suitable_monsters) if suitable_monsters else None

    def trigger_boss_encounter(self, user_id: str, username: str, channel: str) -> bool:
        """Trigger a random boss encounter that acts like a mob fight."""
        player = self.state.get_player_data(user_id)
        player_level = player["level"]

        # Check boss encounter conditions
        boss_config = self.config.get("boss_encounter", {})
        min_level = boss_config.get("boss_encounter_min_level", 17)
        max_level = boss_config.get("boss_encounter_max_level", 20)
        encounter_chance = boss_config.get("boss_encounter_chance", 0.10)

        if not (min_level <= player_level <= max_level):
            return False

        if random.random() > encounter_chance:
            return False

        # Check if there's already an active mob
        with self.mob_lock:
            active_mob = self.state.get_active_mob()
            if active_mob:
                self.bot.log_debug("Boss encounter skipped - active mob already exists")
                return False

            # Create the boss encounter
            boss = self.get_random_monster(player_level, is_boss=True)
            if not boss:
                return False

            join_window_seconds = self.config.get("boss_join_window_seconds", 300)  # 5 minutes for bosses

            mob_data = {
                "channel": channel,
                "monster": boss,
                "monster_level": player_level + 5,  # Bosses are tougher
                "participants": [{"user_id": user_id, "username": username}],
                "start_time": time.time(),
                "join_window_seconds": join_window_seconds,
                "close_epoch": time.time() + join_window_seconds,
                "is_boss": True,
                "xp_multiplier": self.config.get("boss_xp_multiplier", 2.5)
            }

            self.state.update_active_mob(mob_data)

            # Schedule mob window close
            schedule.every(join_window_seconds).seconds.do(self._close_mob_window).tag("quest-mob_close")

            # Announce boss encounter
            if boss.get("is_legacy"):
                # Special announcement for Legacy Bosses
                traits_str = ", ".join(boss.get("traits", [])[:2])  # Show first 2 traits
                xp_reward = boss.get("xp_reward", 0)
                self.bot.safe_say(f"🌟 **LEGACY BOSS ENCOUNTER!** {boss['name']} appears! ({traits_str})\n"
                                 f"This transcendent warrior challenges you! Use !quest join to fight! [{xp_reward} XP reward]", channel)
            else:
                self.bot.safe_say(f"⚠️ **BOSS ENCOUNTER!** A wild {boss['name']} appears! Use !quest join to fight it together!", channel)

            # Ping users who opted in for mob notifications
            self._ping_mob_users(channel)

            return True

    def start_mob_encounter(self, username: str, user_id: str, channel: str) -> Tuple[bool, str]:
        """Start a mob encounter that others can join."""
        with self.mob_lock:
            # Check global cooldown for mob encounters
            mob_cooldown = self.config.get("mob_cooldown_seconds", 3600)  # 1 hour default
            if not self.bot.check_rate_limit(f"mob_spawn_{channel}", mob_cooldown):
                return False, "A mob encounter was recently completed. Please wait before summoning another."

            active_mob = self.state.get_active_mob()
            if active_mob:
                return False, "A mob encounter is already active! Use !quest join to participate."

            # Check player energy
            from .quest_energy import QuestEnergy
            energy = QuestEnergy(self.bot, self.state)
            if not energy.consume_energy(user_id, 2):  # Mob encounters cost 2 energy
                return False, f"You don't have enough energy for a mob quest, {self.bot.title_for(username)}."

            # Select a mob monster
            player = self.state.get_player_data(user_id)
            mob = self.get_random_monster(player["level"])
            if not mob:
                return False, "No suitable mob encounter found."

            join_window_seconds = self.config.get("mob_join_window_seconds", 60)

            # Determine if it's a rare encounter
            is_rare = random.random() < self.config.get("rare_spawn_chance", 0.10)

            mob_data = {
                "channel": channel,
                "monster": mob,
                "monster_level": player["level"] + 2,  # Mobs are slightly tougher
                "participants": [{"user_id": user_id, "username": username}],
                "start_time": time.time(),
                "join_window_seconds": join_window_seconds,
                "close_epoch": time.time() + join_window_seconds,
                "is_boss": False,
                "is_rare": is_rare,
                "xp_multiplier": self.config.get("rare_spawn_xp_multiplier", 2.0) if is_rare else 1.0
            }

            self.state.update_active_mob(mob_data)

            # Schedule mob window close
            schedule.every(join_window_seconds).seconds.do(self._close_mob_window).tag("quest-mob_close")

            # Announce mob encounter
            if is_rare:
                self.bot.safe_say(f"✨ **RARE MOB ENCOUNTER!** A rare {mob['name']} appears! Use !quest join to participate!", channel)
            else:
                self.bot.safe_say(f"⚔️ **MOB ENCOUNTER!** A {mob['name']} appears! Use !quest join to participate!", channel)

            # Ping users who opted in for mob notifications
            self._ping_mob_users(channel)

            return True, f"Mob encounter started! Others have {join_window_seconds} seconds to join."

    def join_mob_encounter(self, username: str, user_id: str, channel: str) -> Tuple[bool, str]:
        """Join an active mob encounter."""
        with self.mob_lock:
            active_mob = self.state.get_active_mob()
            if not active_mob:
                return False, "No active mob encounter to join."

            if active_mob["channel"] != channel:
                return False, "The mob encounter is in another channel."

            # Check if already joined
            if any(p["user_id"] == user_id for p in active_mob["participants"]):
                return False, "You have already joined this mob encounter!"

            # Check energy
            from .quest_energy import QuestEnergy
            energy = QuestEnergy(self.bot, self.state)
            if not energy.consume_energy(user_id, 1):  # Joining costs 1 energy
                return False, f"You don't have enough energy to join the mob encounter, {self.bot.title_for(username)}."

            # Add participant
            active_mob["participants"].append({"user_id": user_id, "username": username})
            self.state.update_active_mob(active_mob)

            party_size = len(active_mob["participants"])
            return True, f"{username} joined the mob encounter! Party size: {party_size}"

    def _close_mob_window(self):
        """Execute the mob encounter after the join window closes."""
        with self.mob_lock:
            active_mob = self.state.get_active_mob()
            if not active_mob:
                return

            channel = active_mob["channel"]
            monster = active_mob["monster"]
            monster_level = active_mob["monster_level"]
            participants = active_mob["participants"]

            # Clear the active mob and scheduled task
            self.state.update_active_mob(None)
            schedule.clear("quest-mob_close")

            if len(participants) == 0:
                self.bot.safe_say("No one joined the mob encounter. The monster wanders off...", channel)
                return

            # Execute mob encounter
            is_boss = active_mob.get("is_boss", False)
            self._execute_mob_encounter(participants, monster, monster_level, channel, is_boss, active_mob)

    def _execute_mob_encounter(self, participants: List[Dict], monster: Dict,
                              monster_level: int, channel: str, is_boss: bool = False,
                              mob_data: Dict = None):
        """Execute a mob encounter with all participants."""
        from .quest_core import QuestCore
        from .quest_items import QuestItems
        from .quest_status import QuestStatus
        from .quest_energy import QuestEnergy

        quest_core = QuestCore(self.bot, self.state)
        quest_items = QuestItems(self.bot, self.state)
        quest_status = QuestStatus(self.bot, self.state)
        quest_energy = QuestEnergy(self.bot, self.state)

        # Calculate party stats
        avg_level = sum(self.state.get_player_data(p["user_id"])["level"] for p in participants) / len(participants)

        # Calculate group combat modifiers
        group_config = self.config.get("group_content", {})
        win_modifiers = group_config.get("win_chance_modifiers", [])
        group_modifier = 0.0

        for modifier in win_modifiers:
            if len(participants) >= modifier["players"]:
                group_modifier = modifier["modifier"]
                break

        # Calculate overall win chance
        if monster.get("is_legacy"):
            # Use predefined win chance for Legacy Bosses
            win_chance = monster.get("win_chance", 0.4)  # Default 40% for Legacy Bosses
        else:
            win_chance = self.calculate_win_chance(int(avg_level), monster_level, group_modifier=group_modifier)
        is_win = random.random() < win_chance

        # Calculate XP rewards
        if monster.get("is_legacy"):
            # Use predefined XP reward for Legacy Bosses
            base_xp = monster.get("xp_reward", random.randint(1000, 2000))
            xp_mult = 1.0  # Legacy Bosses have built-in scaling
        else:
            base_xp = random.randint(monster["xp_win_min"], monster["xp_win_max"])
            xp_mult = mob_data.get("xp_multiplier", 1.0) if mob_data else 1.0

        # Apply XP scaling for large groups
        xp_scaling = group_config.get("xp_scaling", [])
        for scaling in xp_scaling:
            if len(participants) >= scaling["players"]:
                xp_mult *= scaling["multiplier"]
                break

        total_xp = int(base_xp * xp_mult)
        xp_per_player = total_xp // len(participants)

        # Process results
        results = []
        for participant in participants:
            user_id = participant["user_id"]
            username = participant["username"]
            player = self.state.get_player_data(user_id)

            if is_win:
                # Victory
                new_level, leveled_up = quest_core.grant_xp(user_id, xp_per_player)
                player["wins"] += 1

                # Process items (medkit drops for mobs)
                if not is_boss and random.random() < 0.25:  # 25% chance for medkit drop
                    quest_items.add_item(user_id, "medkit")
                    item_msg = " Found a medkit!"
                else:
                    item_msg = ""

                # Process active effects
                self._process_combat_effects(player, is_win=True)

                result = {
                    "username": username,
                    "result": "victory",
                    "xp": xp_per_player,
                    "leveled_up": leveled_up,
                    "new_level": new_level,
                    "message": f"{username} defeated the {monster['name']}! +{xp_per_player} XP{item_msg}"
                }

            else:
                # Defeat
                player["losses"] += 1
                xp_loss_percentage = self.config.get("xp_loss_percentage", 0.25)
                xp_for_current_level = quest_core.calculate_xp_for_level(player["level"])
                max_xp_loss = int((player["xp"] - xp_for_current_level) * xp_loss_percentage)
                actual_xp_loss = quest_core.deduct_xp(user_id, max_xp_loss)

                # Apply injury with reduction
                injury_reduction = quest_status.get_injury_reduction(user_id)
                injury_msg = quest_status.apply_injury(user_id, username, channel, injury_reduction=injury_reduction)

                # Process active effects
                self._process_combat_effects(player, is_win=False)

                result = {
                    "username": username,
                    "result": "defeat",
                    "xp_loss": actual_xp_loss,
                    "injury": injury_msg,
                    "message": f"{username} was defeated by the {monster['name']}!"
                }

            results.append(result)
            self.state.update_player_data(user_id, player)

        # Record Legacy Boss defeat if applicable
        if is_win and monster.get("is_legacy"):
            from .quest_legacy import QuestLegacy
            legacy = QuestLegacy(self.bot, self.state)
            # Pick a random participant as the "main victor" for recording purposes
            main_victor = random.choice(participants)
            legacy.record_legacy_boss_defeat(monster, main_victor["username"], main_victor["user_id"])

        # Announce results
        if monster.get("is_legacy"):
            encounter_type = "LEGACY BOSS"
        elif is_boss:
            encounter_type = "BOSS"
        else:
            encounter_type = "RARE MOB" if mob_data and mob_data.get("is_rare") else "MOB"

        outcome = "VICTORY!" if is_win else "DEFEAT!"

        self.bot.safe_say(f"🎯 {encounter_type} ENCOUNTER - {outcome}", channel)

        if monster.get("is_legacy"):
            # Special message for Legacy Bosses
            if is_win:
                self.bot.safe_say(f"🌟 The party has defeated the transcendent warrior {monster['name']}! Their legend grows stronger!", channel)
            else:
                self.bot.safe_say(f"💀 The party was defeated by {monster['name']}! The Legacy Boss proves too powerful!", channel)
        else:
            self.bot.safe_say(f"⚔️ The party fought a {monster['name']} (Level {monster_level})", channel)
        self.bot.safe_say(f"👥 Party size: {len(participants)} | Win chance: {win_chance*100:.0f}%", channel)

        for result in results:
            self.bot.safe_say(f"• {result['message']}", channel)

            if result.get("injury"):
                self.bot.safe_say(f"  {result['injury']}", channel)

    def _process_combat_effects(self, player: Dict, is_win: bool):
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

    def _ping_mob_users(self, channel: str):
        """Ping users who opted in for mob notifications."""
        # Get mob ping list
        all_state = self.bot.state_manager.get_module_state("quest", {})
        mob_pings = all_state.get("mob_pings", {})

        if channel in mob_pings and mob_pings[channel]:
            ping_names = list(mob_pings[channel].values())
            if ping_names:
                ping_str = ", ".join(ping_names)
                self.bot.safe_say(f"🔔 Mob ping: {ping_str}", channel)

    def toggle_mob_ping(self, user_id: str, username: str, channel: str, action: str) -> str:
        """Toggle mob ping notifications for the user."""
        action = action.lower()
        if action not in ["on", "off"]:
            return "Usage: !quest mob ping <on|off>"

        # Get mob ping list per channel
        all_state = self.bot.state_manager.get_module_state("quest", {})
        mob_pings = all_state.get("mob_pings", {})
        if channel not in mob_pings:
            mob_pings[channel] = {}

        if action == "on":
            if user_id not in mob_pings[channel]:
                mob_pings[channel][user_id] = username
                all_state["mob_pings"] = mob_pings
                self.bot.state_manager.update_module_state("quest", all_state)
                return f"{username}, you will now be notified when mob encounters start."
            else:
                return f"{username}, you are already receiving mob notifications."
        else:  # action == "off"
            if user_id in mob_pings[channel]:
                del mob_pings[channel][user_id]
                all_state["mob_pings"] = mob_pings
                self.bot.state_manager.update_module_state("quest", all_state)
                return f"{username}, you will no longer be notified of mob encounters."
            else:
                return f"{username}, you were not receiving mob notifications."

    def get_active_mob_info(self) -> Optional[Dict[str, Any]]:
        """Get information about the currently active mob encounter."""
        return self.state.get_active_mob()

    def calculate_combat_difficulty_modifiers(self, difficulty: str) -> Dict[str, float]:
        """Get combat modifiers based on difficulty setting."""
        difficulty_config = self.config.get("difficulty", {})

        if difficulty in difficulty_config:
            config = difficulty_config[difficulty]
            return {
                "level_modifier": config.get("level_mod", 0),
                "xp_multiplier": config.get("xp_mult", 1.0)
            }

        # Default modifiers
        defaults = {
            "easy": {"level_modifier": -2, "xp_multiplier": 0.7},
            "normal": {"level_modifier": 1, "xp_multiplier": 1.0},
            "hard": {"level_modifier": 3, "xp_multiplier": 1.5}
        }

        return defaults.get(difficulty, defaults["normal"])