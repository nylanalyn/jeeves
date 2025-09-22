# modules/quest.py
# A persistent RPG-style questing game for the channel.
import random
import time
import re
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

from .base import SimpleCommandModule, admin_required

UTC = timezone.utc

def setup(bot, config):
    """Initializes the Quest module."""
    return Quest(bot, config)

class Quest(SimpleCommandModule):
    """A module for a persistent RPG-style questing game."""
    name = "quest"
    version = "2.0.1"
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        # --- Pre-super() setup ---
        # Load config first to ensure attributes like COOLDOWN are available for command registration.
        self.on_config_reload(config)

        # --- super() call ---
        # This will call _register_commands, so all needed attributes must be set above.
        super().__init__(bot)

        # --- Post-super() setup ---
        # Now it's safe to initialize state and other properties.
        self.set_state("players", self.get_state("players", {}))
        self.save_state()
        self.is_loaded = True

    def on_config_reload(self, config):
        """Handles reloading the module's configuration."""
        quest_config = config.get(self.name, {})
        self.ALLOWED_CHANNELS = quest_config.get("allowed_channels", [])
        self.COOLDOWN = quest_config.get("cooldown_seconds", 300)
        self.XP_CURVE_FORMULA = quest_config.get("xp_curve_formula", "level * 100")
        self.MONSTERS = quest_config.get("monsters", {})
        self.STORY_BEATS = quest_config.get("story_beats", {})

    def _register_commands(self):
        """Registers all the commands for the quest module."""
        self.register_command(
            r"^\s*!quest\s+profile(?:\s+(\S+))?\s*$",
            self._cmd_profile,
            name="quest profile",
            description="View your or another player's quest profile."
        )
        self.register_command(
            r"^\s*!quest\s*$",
            self._cmd_quest,
            name="quest",
            cooldown=self.COOLDOWN,
            description="Embark on a new quest."
        )
        self.register_command(
            r"^\s*!quest\s+admin\s+addxp\s+(\S+)\s+(\d+)\s*$",
            self._cmd_admin_add_xp,
            name="quest admin addxp",
            admin_only=True,
            description="[Admin] Give a player XP."
        )

    def _get_player(self, username: str) -> Dict[str, Any]:
        """Retrieves a player's profile from the state, creating it if it doesn't exist."""
        players = self.get_state("players", {})
        player_key = username.lower()
        
        if player_key not in players:
            players[player_key] = {
                "name": username, "level": 1, "xp": 0,
                "xp_to_next_level": self._calculate_xp_for_level(1)
            }
        
        if "xp_to_next_level" not in players[player_key]:
            level = players[player_key].get("level", 1)
            players[player_key]["xp_to_next_level"] = self._calculate_xp_for_level(level)

        return players[player_key]

    def _calculate_xp_for_level(self, level: int) -> int:
        """Calculates the XP needed to advance to the next level."""
        try:
            return int(eval(self.XP_CURVE_FORMULA, {"__builtins__": {}}, {"level": level}))
        except Exception as e:
            self._record_error(f"Error evaluating XP curve formula: {e}")
            return level * 100

    def _grant_xp(self, username: str, amount: int) -> tuple[Optional[str], Optional[str]]:
        """Grants or removes XP and handles leveling up. Returns level-up and final messages."""
        player = self._get_player(username)
        player_key = username.lower()
        
        player["xp"] += amount
        level_up_message = None

        if player["xp"] >= player["xp_to_next_level"]:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
            level_up_message = f"Congratulations, you have reached Level {player['level']}!"
        
        if player["xp"] < 0:
            player["xp"] = 0

        players = self.get_state("players")
        players[player_key] = player
        self.set_state("players", players)
        self.save_state()

        final_message = f"You now have {player['xp']}/{player['xp_to_next_level']} XP."
        return level_up_message, final_message

    def _select_monster(self, player_level: int) -> Optional[Dict[str, Any]]:
        """Selects an appropriate monster based on player level."""
        if not self.MONSTERS: return None
        
        # Determine appropriate tier
        if player_level <= 5: tier = 'low'
        elif player_level <= 15: tier = 'mid'
        else: tier = 'high'
        
        tier_monsters = self.MONSTERS.get(tier, [])
        if not tier_monsters:
            # Fallback to lower tiers if the current one is empty
            if tier == 'high': tier_monsters = self.MONSTERS.get('mid', [])
            if not tier_monsters: tier_monsters = self.MONSTERS.get('low', [])
            if not tier_monsters: return None
        
        return random.choice(tier_monsters)

    def _generate_quest_story(self, player_name: str, monster: Dict[str, Any]) -> str:
        """Generates a random quest narrative."""
        if not self.STORY_BEATS:
            return f"{player_name} encounters a {monster['name']}."

        opener = random.choice(self.STORY_BEATS.get('openers', ["You encounter a {monster}."]))
        action = random.choice(self.STORY_BEATS.get('actions', ["You attack the {monster}."]))
        
        return (opener + " " + action).format(user=player_name, monster=monster['name'])

    def _cmd_profile(self, connection, event, msg, username, match):
        """Handles the !quest profile command."""
        target_user = match.group(1) or username
        player = self._get_player(target_user)
        
        response = (
            f"Profile for {self.bot.title_for(player['name'])}: "
            f"Level {player['level']} | "
            f"XP: {player['xp']}/{player['xp_to_next_level']}"
        )
        self.safe_reply(connection, event, response)
        return True

    def _cmd_quest(self, connection, event, msg, username, match):
        """Handles the !quest command, initiating a quest and combat."""
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return False

        player = self._get_player(username)
        monster = self._select_monster(player['level'])

        if not monster:
            self.safe_reply(connection, event, "You search for an adventure, but the lands are quiet today. You gain 10 XP for your diligence.")
            _, final_xp_msg = self._grant_xp(username, 10)
            self.safe_reply(connection, event, final_xp_msg)
            return True

        story = self._generate_quest_story(username, monster)
        self.safe_reply(connection, event, story)
        time.sleep(1) # Dramatic pause

        # Combat Logic
        monster_level = random.randint(monster['min_level'], monster['max_level'])
        
        if player['level'] >= monster_level:
            # Win
            xp_gain = random.randint(monster['xp_win_min'], monster['xp_win_max'])
            result_msg = f"The {monster['name']} (Level {monster_level}) is defeated! You gain {xp_gain} XP."
            self.safe_reply(connection, event, result_msg)
            level_up_msg, final_xp_msg = self._grant_xp(username, xp_gain)
        else:
            # Loss
            xp_loss = random.randint(monster['xp_loss_min'], monster['xp_loss_max'])
            result_msg = f"You were defeated by the {monster['name']} (Level {monster_level})! You lose {xp_loss} XP."
            self.safe_reply(connection, event, result_msg)
            level_up_msg, final_xp_msg = self._grant_xp(username, -xp_loss)
            
        if level_up_msg:
            self.safe_reply(connection, event, level_up_msg)
        self.safe_reply(connection, event, final_xp_msg)
        return True
        
    @admin_required
    def _cmd_admin_add_xp(self, connection, event, msg, username, match):
        """Admin command to grant XP to a player."""
        target_user, amount_str = match.groups()
        amount = int(amount_str)
        
        level_up_msg, final_xp_msg = self._grant_xp(target_user, amount)
        self.safe_reply(connection, event, f"Granted {amount} XP to {target_user}. {final_xp_msg}")
        if level_up_msg:
            self.safe_reply(connection, event, f"{target_user} leveled up! {level_up_msg}")
        return True

