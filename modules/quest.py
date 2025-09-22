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
    version = "2.1.1" # Version bump for bugfix
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        self.on_config_reload(config)
        super().__init__(bot)
        self.set_state("players", self.get_state("players", {}))
        self.save_state()

    def on_config_reload(self, config):
        """
        Handles reloading the module's configuration.
        The 'config' object passed here is already the specific section for this module.
        """
        self.ALLOWED_CHANNELS = config.get("allowed_channels", [])
        self.COOLDOWN = config.get("cooldown_seconds", 300)
        self.XP_CURVE_FORMULA = config.get("xp_curve_formula", "level * 100")
        self.MONSTERS = config.get("monsters", {})
        self.STORY_BEATS = config.get("story_beats", {})
        self.WORLD_LORE = config.get("world_lore", [])
        self.MONSTER_SPAWN_CHANCE = config.get("monster_spawn_chance", 80)
        self.FALLBACK_XP_GAIN = config.get("fallback_xp_gain", 10)

    def _register_commands(self):
        """Registers all the commands for the quest module."""
        self.register_command(
            r"^\s*!quest\s+profile(?:\s+(\S+))?\s*$",
            self._cmd_profile,
            name="quest profile",
            description="View your or another player's quest profile."
        )
        self.register_command(
            r"^\s*!quest\s+story\s*$",
            self._cmd_story,
            name="quest story",
            description="Learn a bit about the world or your last fight."
        )
        self.register_command(
            r"^\s*!quest\s*$",
            self._cmd_quest,
            name="quest",
            cooldown=self.COOLDOWN,
            description="Embark on a new quest."
        )

    # --- Player and State Management ---

    def _get_player(self, username: str) -> Dict[str, Any]:
        """Retrieves a player's profile, creating it if it doesn't exist."""
        players = self.get_state("players", {})
        player_key = username.lower()
        
        player = players.get(player_key, {
            "name": username,
            "level": 1,
            "xp": 0,
            "last_fight": None
        })
        
        player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
        return player

    def _save_player(self, player: Dict[str, Any]):
        """Saves a player's profile back to the state."""
        players = self.get_state("players", {})
        player_key = player["name"].lower()
        players[player_key] = player
        self.set_state("players", players)
        self.save_state()

    def _calculate_xp_for_level(self, level: int) -> int:
        """Calculates the XP needed for the next level based on the config formula."""
        try:
            return int(eval(self.XP_CURVE_FORMULA, {"__builtins__": {}}, {"level": level}))
        except Exception as e:
            self._record_error(f"Error evaluating XP curve formula: {e}")
            return level * 100

    def _grant_xp(self, username: str, amount: int) -> Optional[str]:
        """Grants XP to a player and handles leveling up."""
        player = self._get_player(username)
        player["xp"] += amount
        
        leveled_up = False
        while player["xp"] >= player["xp_to_next_level"]:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
            leveled_up = True
            
        self._save_player(player)

        if leveled_up:
            return f"Congratulations, {self.bot.title_for(username)}, you have reached Level {player['level']}!"
        return None

    def _deduct_xp(self, username: str, amount: int):
        """Deducts XP from a player, but not below zero."""
        player = self._get_player(username)
        player["xp"] = max(0, player["xp"] - amount)
        self._save_player(player)

    # --- Quest and Combat Logic ---

    def _get_monster_tier(self, level: int) -> str:
        """Determines the appropriate monster tier for a player's level."""
        if 1 <= level <= 5: return "low"
        if 6 <= level <= 15: return "mid"
        return "high"

    def _select_monster(self, player_level: int) -> Optional[Dict[str, Any]]:
        """Selects a random, level-appropriate monster from the config."""
        tier = self._get_monster_tier(player_level)
        tier_monsters = self.MONSTERS.get(tier, [])
        eligible_monsters = [m for m in tier_monsters if player_level >= m.get("min_level", 1)]
        
        if not eligible_monsters:
            return None
        return random.choice(eligible_monsters)

    # --- Command Handlers ---

    def _cmd_profile(self, connection, event, msg, username, match):
        target_user = match.group(1) or username
        player = self._get_player(target_user)
        title = self.bot.title_for(player["name"])
        
        response = (
            f"Profile for {title}: Level {player['level']} | "
            f"XP: {player['xp']}/{player['xp_to_next_level']}"
        )
        self.safe_reply(connection, event, response)
        return True

    def _cmd_story(self, connection, event, msg, username, match):
        player = self._get_player(username)
        last_fight = player.get("last_fight")
        
        lore = random.choice(self.WORLD_LORE) if self.WORLD_LORE else "The world is vast and full of stories yet to be told."
        self.safe_reply(connection, event, lore)

        if last_fight:
            outcome = "victorious against" if last_fight['won'] else "defeated by"
            history = (f"You last recall being {outcome} a Level {last_fight['monster_level']} {last_fight['monster_name']}.")
            self.safe_reply(connection, event, history)
        return True

    def _cmd_quest(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return False

        # Chance for no monster encounter
        if random.randint(1, 100) > self.MONSTER_SPAWN_CHANCE:
            xp_gain = self.FALLBACK_XP_GAIN
            self.safe_reply(connection, event, f"You search for an adventure, but the lands are quiet today. You gain {xp_gain} XP for your diligence.")
            level_up_msg = self._grant_xp(username, xp_gain)
            if level_up_msg:
                self.safe_reply(connection, event, level_up_msg)
            return True

        # Monster encounter logic
        player = self._get_player(username)
        monster = self._select_monster(player["level"])

        if not monster:
            self.safe_reply(connection, event, "You search for an adventure, but no suitable challenge can be found.")
            return True

        monster_name = monster["name"]
        monster_level = random.randint(monster["min_level"], monster["max_level"])

        opener = random.choice(self.STORY_BEATS.get("openers", ["{user} finds a {monster}."]))
        action = random.choice(self.STORY_BEATS.get("actions", ["{user} fights the {monster}."]))
        
        story = f"{opener} {action}".format(user=username, monster=monster_name)
        self.safe_reply(connection, event, story)

        time.sleep(1) # Dramatic pause

        win = player["level"] >= monster_level
        player["last_fight"] = {"monster_name": monster_name, "monster_level": monster_level, "won": win}
        self._save_player(player)

        if win:
            xp_gain = random.randint(monster["xp_win_min"], monster["xp_win_max"])
            self.safe_reply(connection, event, f"The Level {monster_level} {monster_name} is defeated! You gain {xp_gain} XP.")
            level_up_message = self._grant_xp(username, xp_gain)
            if level_up_message:
                self.safe_reply(connection, event, level_up_message)
        else:
            xp_loss = random.randint(monster["xp_loss_min"], monster["xp_loss_max"])
            self.safe_reply(connection, event, f"You were defeated by the Level {monster_level} {monster_name}! You lose {xp_loss} XP.")
            self._deduct_xp(username, xp_loss)
            
        return True

