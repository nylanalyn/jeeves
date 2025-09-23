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
    version = "2.2.1" # Initialization fix
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot, config):
        """Initializes the Quest module's state and configuration."""
        # --- Pre-super() setup ---
        # This is where we define attributes needed by _register_commands.
        # The config must be loaded FIRST.
        self._is_loaded = False
        self.on_config_reload(config)

        # --- super() call ---
        # Now that COOLDOWN is set, the parent can safely register commands.
        super().__init__(bot)

        # --- Post-super() setup ---
        # Initialize state for player profiles
        self.set_state("players", self.get_state("players", {}))
        self.save_state()

    def on_config_reload(self, config):
        """Handles reloading the module's configuration."""
        quest_config = config.get(self.name, config)
        self.ALLOWED_CHANNELS = quest_config.get("allowed_channels", [])
        self.COOLDOWN = quest_config.get("cooldown_seconds", 300)
        self.XP_CURVE_FORMULA = quest_config.get("xp_curve_formula", "level * 100")
        self.MONSTER_SPAWN_CHANCE = quest_config.get("monster_spawn_chance", 0.8)
        self.MONSTERS = quest_config.get("monsters", {})
        self.STORY_BEATS = quest_config.get("story_beats", {})
        self.WORLD_LORE = quest_config.get("world_lore", [])

    def on_load(self):
        super().on_load()
        self._is_loaded = True

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
            description="Learn a bit about the world or your recent history."
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

    def _get_player(self, user_id: str, username: str) -> Dict[str, Any]:
        """
        Retrieves a player's profile from the state, creating it if it doesn't exist.
        """
        players = self.get_state("players", {})
        
        if user_id not in players:
            players[user_id] = {
                "name": username,
                "level": 1,
                "xp": 0,
                "xp_to_next_level": self._calculate_xp_for_level(1),
                "last_fight": None
            }
        
        if "xp_to_next_level" not in players[user_id]:
            level = players[user_id].get("level", 1)
            players[user_id]["xp_to_next_level"] = self._calculate_xp_for_level(level)
        
        players[user_id]["name"] = username
        return players[user_id]

    def _calculate_xp_for_level(self, level: int) -> int:
        """Calculates the XP needed to advance to the next level."""
        try:
            return int(eval(self.XP_CURVE_FORMULA, {"__builtins__": {}}, {"level": level}))
        except Exception as e:
            self._record_error(f"Error evaluating XP curve formula: {e}")
            return level * 100

    def _grant_xp(self, user_id: str, username: str, amount: int) -> Optional[str]:
        """Grants XP to a player and handles leveling up."""
        player = self._get_player(user_id, username)
        player["xp"] += amount
        
        leveled_up = False
        while player["xp"] >= player["xp_to_next_level"]:
            player["xp"] -= player["xp_to_next_level"]
            player["level"] += 1
            player["xp_to_next_level"] = self._calculate_xp_for_level(player["level"])
            leveled_up = True
            
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

        if leveled_up:
            return f"Congratulations, you have reached Level {player['level']}!"
        return None
        
    def _deduct_xp(self, user_id: str, username: str, amount: int):
        """Deducts XP from a player, but not below zero."""
        player = self._get_player(user_id, username)
        player["xp"] = max(0, player["xp"] - amount)
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()

    def _get_monster_tier(self, level: int) -> str:
        if 1 <= level <= 5: return "low"
        if 6 <= level <= 15: return "mid"
        return "high"

    def _cmd_profile(self, connection, event, msg, username, match):
        target_user_nick = match.group(1) or username
        user_id = self.bot.get_user_id(target_user_nick)
        player = self._get_player(user_id, target_user_nick)
        
        title = self.bot.title_for(player["name"])
        
        response = (
            f"Profile for {title}: "
            f"Level {player['level']} | "
            f"XP: {player['xp']}/{player['xp_to_next_level']}"
        )
        
        self.safe_reply(connection, event, response)
        return True

    def _cmd_story(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)

        lore = random.choice(self.WORLD_LORE) if self.WORLD_LORE else "The world is vast and full of stories yet to be told."
        
        history = ""
        last_fight = player.get("last_fight")
        if last_fight:
            outcome = "victorious against" if last_fight['win'] else "defeated by"
            history = f" You last remember being {outcome} a Level {last_fight['monster_level']} {last_fight['monster_name']}."

        self.safe_reply(connection, event, f"{lore}{history}")
        return True

    def _cmd_quest(self, connection, event, msg, username, match):
        if self.ALLOWED_CHANNELS and event.target not in self.ALLOWED_CHANNELS:
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id, username)
        player_level = player['level']

        if random.random() > self.MONSTER_SPAWN_CHANCE:
            xp_gain = 10
            self.safe_reply(connection, event, f"You search for adventure, but the lands are quiet today. You gain {xp_gain} XP for your diligence.")
            level_up_msg = self._grant_xp(user_id, username, xp_gain)
            if level_up_msg:
                self.safe_reply(connection, event, level_up_msg)
            return True

        tier = self._get_monster_tier(player_level)
        available_monsters = self.MONSTERS.get(tier, [])
        if not available_monsters:
            self.safe_reply(connection, event, "The lands are eerily quiet today... no monsters could be found.")
            return True
        
        monster = random.choice(available_monsters)
        monster_level = random.randint(monster['min_level'], monster['max_level'])
        
        opener = random.choice(self.STORY_BEATS.get("openers", ["A {monster} appears!"]))
        action = random.choice(self.STORY_BEATS.get("actions", ["{user} attacks the {monster}!"]))
        
        story = f"{opener} {action}".format(user=username, monster=monster['name'])
        self.safe_reply(connection, event, story)

        time.sleep(1.5)

        win = player_level >= monster_level
        last_fight_data = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}
        player['last_fight'] = last_fight_data
        
        if win:
            xp_gain = random.randint(monster['xp_win_min'], monster['xp_win_max'])
            self.safe_reply(connection, event, f"The Level {monster_level} {monster['name']} is defeated! You gain {xp_gain} XP.")
            level_up_msg = self._grant_xp(user_id, username, xp_gain)
            if level_up_msg:
                self.safe_reply(connection, event, level_up_msg)
        else:
            xp_loss = random.randint(monster['xp_loss_min'], monster['xp_loss_max'])
            self.safe_reply(connection, event, f"You have been defeated by the Level {monster_level} {monster['name']}! You lose {xp_loss} XP.")
            self._deduct_xp(user_id, username, xp_loss)
            
        players = self.get_state("players")
        players[user_id] = player
        self.set_state("players", players)
        self.save_state()
        return True
        
    @admin_required
    def _cmd_admin_add_xp(self, connection, event, msg, username, match):
        target_user, amount_str = match.groups()
        user_id = self.bot.get_user_id(target_user)
        amount = int(amount_str)
        
        self.safe_reply(connection, event, f"Granted {amount} XP to {target_user}.")
        
        level_up_message = self._grant_xp(user_id, target_user, amount)
        if level_up_message:
            self.safe_reply(connection, event, f"{target_user} leveled up! {level_up_message}")
            
        return True

