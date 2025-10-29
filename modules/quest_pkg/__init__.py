# modules/quest/__init__.py
# Main Quest module - coordinates all quest subsystems

import time
import schedule
import threading
from typing import Dict, Any

from ..base import SimpleCommandModule

# Import our refactored submodules
from . import constants
from . import quest_utils
from . import quest_progression
from . import quest_combat
from . import quest_display
from . import quest_core


def setup(bot):
    """Initializes the Quest module."""
    return Quest(bot)


class Quest(SimpleCommandModule):
    """A module for a persistent RPG-style questing game."""
    name = "quest"
    version = "5.0.0"  # Refactored into modular structure
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot):
        """Initializes the Quest module's state and configuration."""
        super().__init__(bot)

        self.set_state("players", self.get_state("players", {}))
        self.set_state("active_mob", self.get_state("active_mob", None))
        self.set_state("player_classes", self.get_state("player_classes", {}))
        self.set_state("legend_bosses", self.get_state("legend_bosses", {}))
        self.set_state("mob_cooldowns", self.get_state("mob_cooldowns", {}))
        self.mob_lock = threading.Lock()
        self.save_state()
        self._is_loaded = False

        # Load quest content from JSON file
        self.quest_content = quest_core.load_content(self)

        # Load challenge paths
        self.challenge_paths = quest_core.load_challenge_paths(self)

    def _get_content(self, key: str, channel: str = None, default: Any = None) -> Any:
        """Get content from JSON file, falling back to config if not found."""
        # Try to get from content file first
        if key in self.quest_content:
            return self.quest_content[key]
        # Fall back to config
        return self.get_config_value(key, channel, default=default)

    def on_load(self):
        super().on_load()
        self._is_loaded = True
        self._schedule_energy_regen()
        active_mob = self.get_state("active_mob")
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
        super().on_unload()
        schedule.clear(self.name)

    def _schedule_energy_regen(self):
        energy_enabled = self.get_config_value("energy_system.enabled", default=True)
        if not energy_enabled:
            return

        regen_minutes = self.get_config_value("energy_system.regen_minutes", default=10)
        schedule.clear(f"{self.name}-energy_regen")
        schedule.every(regen_minutes).minutes.do(self._regenerate_energy).tag(f"{self.name}-energy_regen")

    def _regenerate_energy(self):
        energy_enabled = self.get_config_value("energy_system.enabled", default=True)
        if not energy_enabled:
            return

        players, updated = self.get_state("players", {}), False

        for user_id, player_data in players.items():
            if isinstance(player_data, dict):
                max_energy = quest_progression.get_player_max_energy(self, player_data)
                regen_amount = 1

                # Migrate old format
                if 'active_injury' in player_data:
                    player_data['active_injuries'] = [player_data['active_injury']]
                    del player_data['active_injury']

                # Sum all injury effects
                if 'active_injuries' in player_data:
                    for injury in player_data['active_injuries']:
                        regen_mod = injury.get('effects', {}).get('energy_regen_modifier', 0)
                        regen_amount += regen_mod

                if regen_amount > 0 and player_data.get("energy", max_energy) < max_energy:
                    player_data["energy"] = min(max_energy, player_data.get("energy", 0) + regen_amount)
                    updated = True
        if updated:
            self.set_state("players", players)
            self.save_state()

    def _register_commands(self):
        # Register more specific patterns first
        self.register_command(r"^\s*!quest\s+reload\s*$", self._cmd_quest_reload, name="quest_reload",
                              admin_only=True, description="Reload quest content from quest_content.json")
        self.register_command(r"^\s*!quest\s+challenge\s+activate\s+(\S+)\s*$", self._cmd_challenge_activate, name="challenge_activate",
                              admin_only=True, description="Activate a challenge path by name")
        self.register_command(r"^\s*!quest\s+challenge\s+deactivate\s*$", self._cmd_challenge_deactivate, name="challenge_deactivate",
                              admin_only=True, description="Deactivate the current challenge path")
        self.register_command(r"^\s*!quest\s+challenge\s+list\s*$", self._cmd_challenge_list, name="challenge_list",
                              admin_only=True, description="List all available challenge paths")
        self.register_command(r"^\s*!quest\s+challenge\s+reload\s*$", self._cmd_challenge_reload, name="challenge_reload",
                              admin_only=True, description="Reload challenge paths from file")
        self.register_command(r"^\s*!quest\s+transcend\s*$", self._cmd_quest_transcend, name="quest_transcend",
                              description="Transcend beyond prestige to become a legend.")
        self.register_command(r"^\s*!equip\s*$", self._cmd_dungeon_equip, name="dungeon_equip",
                              description="Equip random dungeon gear that can counter threats inside !dungeon runs.")
        self.register_command(r"^\s*!dungeon\s*$", self._cmd_dungeon_run, name="dungeon_run",
                              description="Run a ten-room dungeon via private messages.")
        self.register_command(r"^\s*!quest\s+mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping")
        self.register_command(r"^\s*!quest\s+mob\s*$", self._cmd_mob_start, name="mob")
        self.register_command(r"^\s*!quest\s+join\s*$", self._cmd_mob_join, name="join")
        self.register_command(r"^\s*!quest\s+medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit",
                              description="Use a medkit to heal yourself or another player")
        self.register_command(r"^\s*!quest\s+inv(?:entory)?\s*$", self._cmd_inventory, name="inventory",
                              description="View your medkits and active injuries")
        self.register_command(r"^\s*!quest\s+ability(?:\s+(.+))?\s*$", self._cmd_ability, name="ability",
                              description="List or use unlocked abilities")
        self.register_command(r"^\s*!quest(?:\s+(.*))?$", self._cmd_quest_master, name="quest")

        # Short aliases
        self.register_command(r"^\s*!q(?:\s+(.*))?$", self._cmd_quest_master, name="quest_alias")
        self.register_command(r"^\s*!qe\s*$", self._cmd_quest_easy, name="quest_easy_alias")
        self.register_command(r"^\s*!qh\s*$", self._cmd_quest_hard, name="quest_hard_alias")
        self.register_command(r"^\s*!qp(?:\s+(.*))?\s*$", self._cmd_quest_profile_alias, name="quest_profile_alias")
        self.register_command(r"^\s*!qi\s*$", self._cmd_inventory, name="quest_inventory_alias")
        self.register_command(r"^\s*!qs(?:\s+(.*))?\s*$", self._cmd_quest_search_alias, name="quest_search_alias")
        self.register_command(r"^\s*!qm\s*$", self._cmd_quest_medic_alias, name="quest_medic_alias")
        self.register_command(r"^\s*!qu(?:\s+(.*))?\s*$", self._cmd_quest_use_alias, name="quest_use_alias")
        self.register_command(r"^\s*!qt\s*$", self._cmd_quest_leaderboard_alias, name="quest_leaderboard_alias")
        self.register_command(r"^\s*!qc(?:\s+(.*))?\s*$", self._cmd_quest_class_alias, name="quest_class_alias")

        # Legacy aliases
        self.register_command(r"^\s*!mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping_legacy")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob_legacy")
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join_legacy")
        self.register_command(r"^\s*!medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit_legacy")
        self.register_command(r"^\s*!inv(?:entory)?\s*$", self._cmd_inventory, name="inventory_legacy")

    # ===== COMMAND HANDLERS - Delegate to submodules =====

    def _cmd_quest_master(self, connection, event, msg, username, match):
        """Master quest command handler."""
        if not self.is_enabled(event.target):
            return False

        args_str = (match.group(1) or "").strip()
        args = args_str.split()

        difficulty_mods = self.get_config_value("difficulty", default={})
        if not args_str or args[0].lower() in difficulty_mods:
            return quest_core.handle_solo_quest(self, connection, event, username, args[0] if args else "normal")

        subcommand = args[0].lower()
        if subcommand == "search":
            return quest_core.handle_search(self, connection, event, username, args[1:])
        elif subcommand == "medic":
            return quest_core.handle_medic_quest(self, connection, event, username)
        elif subcommand == "profile":
            return quest_display.handle_profile(self, connection, event, username, args[1:])
        elif subcommand == "story":
            return quest_display.handle_story(self, connection, event, username)
        elif subcommand == "class":
            return quest_progression.handle_class(self, connection, event, username, args[1:])
        elif subcommand in ("top", "leaderboard"):
            return quest_display.handle_leaderboard(self, connection, event)
        elif subcommand == "prestige":
            return quest_progression.handle_prestige(self, connection, event, username, args[1:])
        elif subcommand == "use":
            return quest_core.handle_use_item(self, connection, event, username, args[1:])
        else:
            self.safe_reply(connection, event, f"Unknown quest command. Use '!quest', or '!quest <search|use|medic|profile|story|class|top|prestige>'.")
            return True

    def _cmd_quest_easy(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return quest_core.handle_solo_quest(self, connection, event, username, "easy")

    def _cmd_quest_hard(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return quest_core.handle_solo_quest(self, connection, event, username, "hard")

    def _cmd_quest_transcend(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return quest_progression.handle_transcend(self, connection, event, username)

    def _cmd_quest_profile_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return quest_display.handle_profile(self, connection, event, username, args)

    def _cmd_quest_search_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return quest_core.handle_search(self, connection, event, username, args)

    def _cmd_quest_medic_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return quest_core.handle_medic_quest(self, connection, event, username)

    def _cmd_quest_use_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return quest_core.handle_use_item(self, connection, event, username, args)

    def _cmd_quest_leaderboard_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        return quest_display.handle_leaderboard(self, connection, event)

    def _cmd_quest_class_alias(self, connection, event, msg, username, match):
        if not self.is_enabled(event.target):
            return False
        args_str = (match.group(1) or "").strip() if match and match.lastindex else ""
        args = args_str.split() if args_str else []
        return quest_progression.handle_class(self, connection, event, username, args)

    def _cmd_dungeon_equip(self, connection, event, msg, username, match):
        return quest_progression.cmd_dungeon_equip(self, connection, event, msg, username, match)

    def _cmd_dungeon_run(self, connection, event, msg, username, match):
        return quest_progression.cmd_dungeon_run(self, connection, event, msg, username, match)

    def _cmd_mob_ping(self, connection, event, msg, username, match):
        return quest_combat.cmd_mob_ping(self, connection, event, msg, username, match)

    def _cmd_mob_start(self, connection, event, msg, username, match):
        return quest_combat.cmd_mob_start(self, connection, event, msg, username, match)

    def _cmd_mob_join(self, connection, event, msg, username, match):
        return quest_combat.cmd_mob_join(self, connection, event, msg, username, match)

    def _close_mob_window(self):
        return quest_combat.close_mob_window(self)

    def _cmd_medkit(self, connection, event, msg, username, match):
        # Placeholder - full implementation needed
        self.safe_reply(connection, event, "Medkit functionality being refactored.")
        return True

    def _cmd_inventory(self, connection, event, msg, username, match):
        return quest_display.cmd_inventory(self, connection, event, msg, username, match)

    def _cmd_ability(self, connection, event, msg, username, match):
        return quest_display.cmd_ability(self, connection, event, msg, username, match)

    def _cmd_quest_reload(self, connection, event, msg, username, match):
        """Reload quest content from JSON file."""
        if not self.is_enabled(event.target):
            return False
        self.quest_content = quest_core.load_content(self)
        self.safe_reply(connection, event, "Quest content reloaded from quest_content.json")
        return True

    def _cmd_challenge_activate(self, connection, event, msg, username, match):
        """Activate a challenge path."""
        if not self.is_enabled(event.target):
            return False
        path_id = match.group(1)
        if path_id not in self.challenge_paths.get("paths", {}):
            self.safe_reply(connection, event, f"Challenge path '{path_id}' not found.")
            return True
        self.challenge_paths["active_path"] = path_id
        quest_core.save_challenge_paths(self)
        path_name = self.challenge_paths["paths"][path_id].get("name", path_id)
        self.safe_reply(connection, event, f"Challenge path '{path_name}' activated!")
        return True

    def _cmd_challenge_deactivate(self, connection, event, msg, username, match):
        """Deactivate the current challenge path."""
        if not self.is_enabled(event.target):
            return False
        self.challenge_paths["active_path"] = None
        quest_core.save_challenge_paths(self)
        self.safe_reply(connection, event, "Challenge path deactivated.")
        return True

    def _cmd_challenge_list(self, connection, event, msg, username, match):
        """List all challenge paths."""
        if not self.is_enabled(event.target):
            return False
        paths = self.challenge_paths.get("paths", {})
        if not paths:
            self.safe_reply(connection, event, "No challenge paths defined.")
            return True
        active_path = self.challenge_paths.get("active_path")
        self.safe_reply(connection, event, "Available challenge paths:")
        for path_id, path_data in paths.items():
            active_marker = " [ACTIVE]" if path_id == active_path else ""
            self.safe_reply(connection, event, f"  {path_id}: {path_data.get('name', path_id)}{active_marker}")
        return True

    def _cmd_challenge_reload(self, connection, event, msg, username, match):
        """Reload challenge paths from file."""
        if not self.is_enabled(event.target):
            return False
        self.challenge_paths = quest_core.load_challenge_paths(self)
        self.safe_reply(connection, event, "Challenge paths reloaded from challenge_paths.json")
        return True
