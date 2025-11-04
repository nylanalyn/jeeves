# modules/quest/__init__.py
# Main Quest module - coordinates all quest subsystems

import re
import time
import secrets
import schedule
import threading
from typing import Dict, Any, Tuple

from ..base import SimpleCommandModule

# Import our refactored submodules
from . import constants
from . import quest_utils
from . import quest_progression
from . import quest_combat
from . import quest_display
from . import quest_core
from . import quest_boss_hunt

WEB_LINK_TOKEN_TTL = 600  # seconds (10 minutes)


def setup(bot):
    """Initializes the Quest module."""
    return Quest(bot)


class Quest(SimpleCommandModule):
    """A module for a persistent RPG-style questing game."""
    name = "quest"
    version = "5.1.0"  # Added web link token support
    description = "An RPG-style questing game where users can fight monsters and level up."

    def __init__(self, bot):
        """Initializes the Quest module's state and configuration."""
        super().__init__(bot)

        self.set_state("players", self.get_state("players", {}))
        self.set_state("active_mob", self.get_state("active_mob", None))
        self.set_state("player_classes", self.get_state("player_classes", {}))
        self.set_state("legend_bosses", self.get_state("legend_bosses", {}))
        self.set_state("mob_cooldowns", self.get_state("mob_cooldowns", {}))
        self.set_state("web_link_tokens", self.get_state("web_link_tokens", {}))
        self.mob_lock = threading.Lock()
        self.save_state()
        self._is_loaded = False

        # Load quest content from JSON file
        self.quest_content = quest_core.load_content(self)

        # Load challenge paths
        self.challenge_paths = quest_core.load_challenge_paths(self)

    def _refresh_state_cache(self) -> None:
        """Refresh cached state if external changes were detected."""
        with self._state_lock:
            if self._state_dirty:
                return
            latest = self.bot.get_module_state(self.name) or {}
            if not isinstance(latest, dict):
                latest = {}
            self._state_cache = latest.copy()

    def get_state(self, key: str = None, default: Any = None) -> Any:
        self._refresh_state_cache()
        return super().get_state(key, default)

    def set_state(self, key: str, value: Any) -> None:
        self._refresh_state_cache()
        super().set_state(key, value)

    def update_state(self, updates: Dict[str, Any]) -> None:
        self._refresh_state_cache()
        super().update_state(updates)

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
        self._cleanup_expired_tokens()
        self._schedule_energy_regen()
        self._schedule_token_cleanup()

        # Initialize boss hunt system
        quest_boss_hunt.initialize_boss_hunt_state(self)

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

                # Clear expired injuries during energy regen so recovery happens even if the player is idle
                previous_injury_count = 0
                if 'active_injuries' in player_data and isinstance(player_data['active_injuries'], list):
                    previous_injury_count = len(player_data['active_injuries'])
                elif 'active_injury' in player_data:
                    previous_injury_count = 1

                player_data, recovery_msg = quest_utils.check_and_clear_injury(player_data)
                players[user_id] = player_data
                current_injuries = player_data.get('active_injuries', [])
                if recovery_msg or (previous_injury_count and len(current_injuries) < previous_injury_count):
                    updated = True

                # Sum all injury effects
                if current_injuries:
                    for injury in current_injuries:
                        regen_mod = injury.get('effects', {}).get('energy_regen_modifier', 0)
                        regen_amount += regen_mod

                if regen_amount > 0 and player_data.get("energy", max_energy) < max_energy:
                    player_data["energy"] = min(max_energy, player_data.get("energy", 0) + regen_amount)
                    updated = True
        if updated:
            self.set_state("players", players)
            self.save_state()

    def _dispatch_commands(self, connection, event, msg: str, username: str) -> bool:
        """Override to allow dungeon and item-use commands in DMs."""
        # Check if this is a DM (event.target is bot's nickname, not a channel)
        is_dm = not event.target.startswith('#')

        # Allow dungeon commands and !quest use / !qu in DMs regardless of channel settings
        if is_dm:
            dm_allowed_patterns = [
                r"^\s*[!,]dungeon",  # All dungeon commands
                r"^\s*[!,]quest\s+use\b",  # !quest use
                r"^\s*[!,]qu\s+",  # !qu alias
            ]
            for pattern in dm_allowed_patterns:
                if re.match(pattern, msg, re.IGNORECASE):
                    # Process this command even though module isn't "enabled" for DMs
                    # Temporarily skip the is_enabled check by calling parent's parent method
                    for cmd_id, cmd_info in self._commands.items():
                        match = cmd_info["pattern"].match(msg)
                        if match:
                            self.log_debug(f"DM Command '{cmd_info['name']}' matched by user {username}")
                            if cmd_info["admin_only"] and not self.bot.is_admin(event.source):
                                self.log_debug(f"Denying admin command '{cmd_info['name']}' for non-admin {username}")
                                continue
                            cooldown_val = self.get_config_value("cooldown_seconds", event.target, cmd_info["cooldown"])
                            if not self.check_user_cooldown(username, cmd_id, cooldown_val):
                                self.log_debug(f"Command '{cmd_info['name']}' on cooldown for user {username}")
                                continue
                            try:
                                if cmd_info["handler"](connection, event, msg, username, match):
                                    self.log_debug(f"DM Command '{cmd_info['name']}' handled successfully.")
                                    return True
                            except Exception as e:
                                import traceback
                                self.log_debug(f"Error in command {cmd_id}: {e}\n{traceback.format_exc()}")
                    return False

        # For channel messages, use normal dispatch with is_enabled check
        return super()._dispatch_commands(connection, event, msg, username)

    def on_privmsg(self, connection, event):
        """Dispatch supported quest commands received via private messages."""
        msg = event.arguments[0] if event.arguments else ""
        if not msg:
            return False
        username = getattr(event.source, "nick", str(event.source))
        return self._dispatch_commands(connection, event, msg, username)

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

        # Admin commands for abilities
        self.register_command(r"^\s*!quest\s+admin\s+ability\s+grant\s+(\S+)\s+(\S+)\s*$", self._cmd_admin_ability_grant, name="admin_ability_grant",
                              admin_only=True, description="Grant an ability to a player")
        self.register_command(r"^\s*!quest\s+admin\s+ability\s+revoke\s+(\S+)\s+(\S+)\s*$", self._cmd_admin_ability_revoke, name="admin_ability_revoke",
                              admin_only=True, description="Revoke an ability from a player")
        self.register_command(r"^\s*!quest\s+admin\s+ability\s+list\s+(\S+)\s*$", self._cmd_admin_ability_list, name="admin_ability_list",
                              admin_only=True, description="List a player's unlocked abilities")

        # Admin commands for challenge paths
        self.register_command(r"^\s*!quest\s+admin\s+path\s+set\s+(\S+)\s+(\S+)\s*$", self._cmd_admin_path_set, name="admin_path_set",
                              admin_only=True, description="Set a player's active challenge path")
        self.register_command(r"^\s*!quest\s+admin\s+path\s+clear\s+(\S+)\s*$", self._cmd_admin_path_clear, name="admin_path_clear",
                              admin_only=True, description="Clear a player's challenge path")

        # Admin commands for injuries
        self.register_command(r"^\s*!quest\s+admin\s+injury\s+add\s+(\S+)(?:\s+(.+))?\s*$", self._cmd_admin_injury_add, name="admin_injury_add",
                              admin_only=True, description="Add an injury to a player (random if not specified)")
        self.register_command(r"^\s*!quest\s+admin\s+injury\s+clear\s+(\S+)\s*$", self._cmd_admin_injury_clear, name="admin_injury_clear",
                              admin_only=True, description="Clear all injuries from a player")
        self.register_command(r"^\s*!quest\s+admin\s+injury\s+list\s+(\S+)\s*$", self._cmd_admin_injury_list, name="admin_injury_list",
                              admin_only=True, description="List a player's active injuries")

        # Boss hunt commands
        self.register_command(r"^\s*!quest\s+boss(?:\s+status)?\s*$", self._cmd_boss_status, name="boss_status",
                              description="Show current boss hunt status")
        self.register_command(r"^\s*!quest\s+admin\s+boss\s+spawn\s*$", self._cmd_boss_spawn, name="admin_boss_spawn",
                              admin_only=True, description="Spawn a new boss")
        self.register_command(r"^\s*!quest\s+admin\s+boss\s+damage\s+(\d+)\s*$", self._cmd_boss_damage, name="admin_boss_damage",
                              admin_only=True, description="Deal damage to the current boss")
        self.register_command(r"^\s*!quest\s+admin\s+boss\s+buff\s+(on|off|status)\s*$", self._cmd_boss_buff, name="admin_boss_buff",
                              admin_only=True, description="Toggle or check boss hunt buff")

        self.register_command(r"^\s*!quest\s+transcend\s*$", self._cmd_quest_transcend, name="quest_transcend",
                              description="Transcend beyond prestige to become a legend.")
        self.register_command(r"^\s*!equip\s*$", self._cmd_dungeon_equip, name="dungeon_equip",
                              description="Equip random dungeon gear that can counter threats inside !dungeon runs.")
        self.register_command(r"^\s*!dungeon\s*$", self._cmd_dungeon_run, name="dungeon_run",
                              description="Run a ten-room dungeon via private messages.")
        self.register_command(r"^\s*!dungeon\s+continue\s*$", self._cmd_dungeon_continue, name="dungeon_continue",
                              description="Continue your dungeon run from a safe haven.")
        self.register_command(r"^\s*!dungeon\s+quit\s*$", self._cmd_dungeon_quit, name="dungeon_quit",
                              description="Abandon your dungeon run and claim partial rewards.")
        self.register_command(r"^\s*!quest\s+mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping")
        self.register_command(r"^\s*!quest\s+mob\s*$", self._cmd_mob_start, name="mob")
        self.register_command(r"^\s*!quest\s+join\s*$", self._cmd_mob_join, name="join")
        self.register_command(r"^\s*!quest\s+medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit",
                              description="Use a medkit to heal yourself or another player")
        self.register_command(r"^\s*!quest\s+inv(?:entory)?\s*$", self._cmd_inventory, name="inventory",
                              description="View your medkits and active injuries")
        self.register_command(r"^\s*!quest\s+ability(?:\s+(.+))?\s*$", self._cmd_ability, name="ability",
                              description="List or use unlocked abilities")
        self.register_command(r"^\s*!quest\s+weblink\s*$", self._cmd_weblink, name="quest_weblink",
                              description="Generate a short-lived code to link your account to the quest website")
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
        self.register_command(r"^\s*!weblink\s*$", self._cmd_weblink, name="weblink_alias",
                              description="Generate a short-lived code to link your account to the quest website")

        # Legacy aliases
        self.register_command(r"^\s*!mob\s+ping\s+(on|off)\s*$", self._cmd_mob_ping, name="mob_ping_legacy")
        self.register_command(r"^\s*!mob\s*$", self._cmd_mob_start, name="mob_legacy")
        self.register_command(r"^\s*!join\s*$", self._cmd_mob_join, name="join_legacy")
        self.register_command(r"^\s*!medkit(?:\s+(.+))?\s*$", self._cmd_medkit, name="medkit_legacy")
        self.register_command(r"^\s*!inv(?:entory)?\s*$", self._cmd_inventory, name="inventory_legacy")

    def _issue_weblink_token(self, username: str) -> Tuple[str, float]:
        """Return an active web link token for the given user or create a new one."""
        now = time.time()
        tokens = dict(self.get_state("web_link_tokens", {}))

        # Prune expired tokens
        stale_tokens = [token for token, info in tokens.items()
                        if not isinstance(info, dict) or info.get("expires_at", 0) <= now]
        for token in stale_tokens:
            tokens.pop(token, None)

        user_id = self.bot.get_user_id(username)
        for token, info in tokens.items():
            if info.get("user_id") == user_id:
                return token, info.get("expires_at", now)

        # Issue a fresh token
        token = None
        while not token or token in tokens:
            token = secrets.token_urlsafe(6)
        expires_at = now + WEB_LINK_TOKEN_TTL
        tokens[token] = {
            "user_id": user_id,
            "username": username,
            "issued_at": now,
            "expires_at": expires_at,
        }
        self.set_state("web_link_tokens", tokens)
        self.save_state()
        return token, expires_at

    def _cleanup_expired_tokens(self) -> None:
        """Remove expired weblink tokens from state."""
        now = time.time()
        tokens = dict(self.get_state("web_link_tokens", {}))

        # Count tokens before cleanup
        initial_count = len(tokens)

        # Remove expired tokens
        expired_tokens = [token for token, info in tokens.items()
                         if not isinstance(info, dict) or info.get("expires_at", 0) <= now]
        for token in expired_tokens:
            tokens.pop(token, None)

        # Only save if we actually removed something
        if len(tokens) != initial_count:
            self.set_state("web_link_tokens", tokens)
            self.save_state()
            removed_count = initial_count - len(tokens)
            self.log_debug(f"Cleaned up {removed_count} expired weblink token(s)")

    def _schedule_token_cleanup(self) -> None:
        """Schedule periodic cleanup of expired weblink tokens."""
        # Run cleanup every hour
        schedule.every(1).hours.do(self._cleanup_expired_tokens).tag(f"{self.name}-token_cleanup")

    def _cmd_weblink(self, connection, event, msg, username, match):
        """Provide a short-lived token to link an IRC account with the quest website."""
        target = getattr(event, "target", "")
        if target.startswith('#') and not self.is_enabled(target):
            return False

        token, expires_at = self._issue_weblink_token(username)
        remaining_seconds = max(5, int(expires_at - time.time()))
        remaining_minutes = max(1, remaining_seconds // 60)

        details = (
            f"Your Jeeves quest website link code is: {token}\n"
            f"It expires in about {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''}."
        )

        if not self.safe_privmsg(username, details):
            # Fall back to replying in the same context if DMs fail
            self.safe_reply(
                connection,
                event,
                f"{self.bot.title_for(username)}, I couldn't DM you. "
                f"Your link code is {token} (valid for {remaining_minutes} minute{'s' if remaining_minutes != 1 else ''})."
            )
            return True

        if target.startswith('#'):
            self.safe_reply(connection, event, f"{self.bot.title_for(username)}, I've sent your link code via private message.")
        else:
            self.safe_reply(connection, event, "I've sent your link code via private message. Check our DM for the code.")
        return True

    # ===== COMMAND HANDLERS - Delegate to submodules =====

    def _cmd_quest_master(self, connection, event, msg, username, match):
        """Master quest command handler."""
        args_str = (match.group(1) or "").strip()
        args = args_str.split()

        # Allow "!quest use" in DMs for dungeon item usage, but require channel for everything else
        subcommand = args[0].lower() if args else ""
        if subcommand == "use":
            return quest_core.handle_use_item(self, connection, event, username, args[1:])

        # All other quest commands require the module to be enabled in the channel
        if not self.is_enabled(event.target):
            return False

        difficulty_mods = self.get_config_value("difficulty", default={})
        if not args_str or args[0].lower() in difficulty_mods:
            return quest_core.handle_solo_quest(self, connection, event, username, args[0] if args else "normal")

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
        # Allow !qu in DMs for dungeon item usage (no channel restriction)
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

    def _cmd_dungeon_continue(self, connection, event, msg, username, match):
        return quest_progression.cmd_dungeon_continue(self, connection, event, msg, username, match)

    def _cmd_dungeon_quit(self, connection, event, msg, username, match):
        return quest_progression.cmd_dungeon_quit(self, connection, event, msg, username, match)

    def _cmd_mob_ping(self, connection, event, msg, username, match):
        return quest_combat.cmd_mob_ping(self, connection, event, msg, username, match)

    def _cmd_mob_start(self, connection, event, msg, username, match):
        return quest_combat.cmd_mob_start(self, connection, event, msg, username, match)

    def _cmd_mob_join(self, connection, event, msg, username, match):
        return quest_combat.cmd_mob_join(self, connection, event, msg, username, match)

    def _close_mob_window(self):
        return quest_combat.close_mob_window(self)

    def _cmd_medkit(self, connection, event, msg, username, match):
        """Use a medkit to heal yourself or another player."""
        if not self.is_enabled(event.target):
            return False
        target_arg = (match.group(1) or "").strip() if match else ""
        return quest_core.handle_medkit(self, connection, event, username, target_arg)

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

    # ===== ADMIN COMMANDS FOR ABILITIES =====

    def _cmd_admin_ability_grant(self, connection, event, msg, username, match):
        """Grant an ability to a player."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)
        ability_id = match.group(2)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Check if ability exists
        abilities = self.challenge_paths.get("abilities", {})
        if ability_id not in abilities:
            self.safe_reply(connection, event, f"Ability '{ability_id}' not found. Available: {', '.join(abilities.keys())}")
            return True

        # Get or create player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]
        player.setdefault("unlocked_abilities", [])

        # Grant ability
        if ability_id in player["unlocked_abilities"]:
            self.safe_reply(connection, event, f"{target_nick} already has the {ability_id} ability.")
            return True

        player["unlocked_abilities"].append(ability_id)
        self.set_state("players", players)
        self.save_state()

        ability_name = abilities[ability_id].get("name", ability_id)
        self.safe_reply(connection, event, f"Granted {ability_name} ability to {target_nick}!")
        return True

    def _cmd_admin_ability_revoke(self, connection, event, msg, username, match):
        """Revoke an ability from a player."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)
        ability_id = match.group(2)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]
        unlocked = player.get("unlocked_abilities", [])

        # Revoke ability
        if ability_id not in unlocked:
            self.safe_reply(connection, event, f"{target_nick} doesn't have the {ability_id} ability.")
            return True

        unlocked.remove(ability_id)
        player["unlocked_abilities"] = unlocked
        self.set_state("players", players)
        self.save_state()

        abilities = self.challenge_paths.get("abilities", {})
        ability_name = abilities.get(ability_id, {}).get("name", ability_id)
        self.safe_reply(connection, event, f"Revoked {ability_name} ability from {target_nick}.")
        return True

    def _cmd_admin_ability_list(self, connection, event, msg, username, match):
        """List a player's unlocked abilities."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]
        unlocked = player.get("unlocked_abilities", [])

        if not unlocked:
            self.safe_reply(connection, event, f"{target_nick} has no unlocked abilities.")
            return True

        abilities = self.challenge_paths.get("abilities", {})
        ability_names = [abilities.get(aid, {}).get("name", aid) for aid in unlocked]
        self.safe_reply(connection, event, f"{target_nick}'s abilities: {', '.join(ability_names)}")
        return True

    # ===== ADMIN COMMANDS FOR CHALLENGE PATHS =====

    def _cmd_admin_path_set(self, connection, event, msg, username, match):
        """Set a player's active challenge path."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)
        path_id = match.group(2)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Check if path exists
        paths = self.challenge_paths.get("paths", {})
        if path_id not in paths:
            self.safe_reply(connection, event, f"Challenge path '{path_id}' not found. Available: {', '.join(paths.keys())}")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]
        old_path = player.get("challenge_path")
        player["challenge_path"] = path_id

        # Reset challenge stats
        player["challenge_stats"] = {
            "medkits_used_this_prestige": 0
        }

        self.set_state("players", players)
        self.save_state()

        path_name = paths[path_id].get("name", path_id)
        if old_path:
            old_name = paths.get(old_path, {}).get("name", old_path)
            self.safe_reply(connection, event, f"Changed {target_nick}'s challenge path from {old_name} to {path_name}!")
        else:
            self.safe_reply(connection, event, f"Set {target_nick}'s challenge path to {path_name}!")
        return True

    def _cmd_admin_path_clear(self, connection, event, msg, username, match):
        """Clear a player's challenge path."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]
        old_path = player.get("challenge_path")

        if not old_path:
            self.safe_reply(connection, event, f"{target_nick} is not on a challenge path.")
            return True

        player["challenge_path"] = None
        player["challenge_stats"] = {
            "medkits_used_this_prestige": 0
        }

        self.set_state("players", players)
        self.save_state()

        paths = self.challenge_paths.get("paths", {})
        old_name = paths.get(old_path, {}).get("name", old_path)
        self.safe_reply(connection, event, f"Cleared {target_nick}'s challenge path ({old_name}).")
        return True

    # ===== ADMIN COMMANDS FOR INJURIES =====

    def _cmd_admin_injury_add(self, connection, event, msg, username, match):
        """Add an injury to a player."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)
        injury_name = match.group(2).strip() if match.group(2) else None

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        # Get available injuries
        injury_config = self._get_content("injury_system", event.target, default={})
        possible_injuries = injury_config.get("injuries", [])

        if not possible_injuries:
            self.safe_reply(connection, event, "No injuries are configured in the system.")
            return True

        # Select injury
        if injury_name:
            # Find matching injury by name (case-insensitive)
            injury = None
            for inj in possible_injuries:
                if inj.get('name', '').lower() == injury_name.lower():
                    injury = inj
                    break

            if not injury:
                available = ', '.join([inj.get('name', 'Unknown') for inj in possible_injuries])
                self.safe_reply(connection, event, f"Injury '{injury_name}' not found. Available: {available}")
                return True
        else:
            # Random injury
            import random
            injury = random.choice(possible_injuries)

        # Apply the injury manually
        player = players[target_user_id]

        # Migrate old format if needed
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        if 'active_injuries' not in player:
            player['active_injuries'] = []

        # Check if player already has 2 of this injury type
        injury_count = sum(1 for inj in player['active_injuries'] if inj['name'] == injury['name'])
        if injury_count >= 2:
            self.safe_reply(connection, event, f"{target_nick} already has 2 {injury['name']} injuries (max limit).")
            return True

        # Add the injury
        from datetime import datetime, timedelta
        duration = timedelta(hours=injury.get("duration_hours", 1))
        expires_at = datetime.now(constants.UTC) + duration

        new_injury = {
            "name": injury['name'],
            "description": injury['description'],
            "expires_at": expires_at.isoformat(),
            "effects": injury.get('effects', {})
        }

        player['active_injuries'].append(new_injury)
        self.set_state("players", players)
        self.save_state()

        self.safe_reply(connection, event, f"Added {injury['name']} to {target_nick}! (Duration: {injury.get('duration_hours', 1)}h)")
        return True

    def _cmd_admin_injury_clear(self, connection, event, msg, username, match):
        """Clear all injuries from a player."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]

        # Migrate old format if needed
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        injuries = player.get('active_injuries', [])

        if not injuries:
            self.safe_reply(connection, event, f"{target_nick} has no active injuries.")
            return True

        injury_count = len(injuries)
        injury_names = [inj['name'] for inj in injuries]

        # Clear all injuries
        player['active_injuries'] = []
        self.set_state("players", players)
        self.save_state()

        if injury_count == 1:
            self.safe_reply(connection, event, f"Cleared {injury_names[0]} from {target_nick}.")
        else:
            self.safe_reply(connection, event, f"Cleared {injury_count} injuries from {target_nick}: {', '.join(injury_names)}")
        return True

    def _cmd_admin_injury_list(self, connection, event, msg, username, match):
        """List a player's active injuries."""
        if not self.is_enabled(event.target):
            return False

        target_nick = match.group(1)

        # Get target user ID
        target_user_id = self.bot.get_user_id(target_nick)
        if not target_user_id:
            self.safe_reply(connection, event, f"Player '{target_nick}' not found.")
            return True

        # Get player
        players = self.get_state("players", {})
        if target_user_id not in players:
            self.safe_reply(connection, event, f"Player '{target_nick}' has not started playing yet.")
            return True

        player = players[target_user_id]

        # Migrate old format if needed
        if 'active_injury' in player:
            player['active_injuries'] = [player['active_injury']]
            del player['active_injury']

        injuries = player.get('active_injuries', [])

        if not injuries:
            self.safe_reply(connection, event, f"{target_nick} has no active injuries.")
            return True

        # Format injury list with expiration times
        from datetime import datetime
        injury_details = []
        for injury in injuries:
            expires_str = injury.get('expires_at', '')
            if expires_str:
                try:
                    expires_at = datetime.fromisoformat(expires_str)
                    time_left = quest_utils.format_timedelta(expires_at)
                    injury_details.append(f"{injury['name']} (expires in {time_left})")
                except:
                    injury_details.append(injury['name'])
            else:
                injury_details.append(injury['name'])

        self.safe_reply(connection, event, f"{target_nick}'s injuries: {', '.join(injury_details)}")
        return True

    # ===== BOSS HUNT COMMANDS =====

    def _cmd_boss_status(self, connection, event, msg, username, match):
        """Show current boss hunt status."""
        return quest_boss_hunt.cmd_boss_status(self, connection, event, msg, username, match)

    def _cmd_boss_spawn(self, connection, event, msg, username, match):
        """Admin command to spawn a new boss."""
        return quest_boss_hunt.cmd_boss_spawn(self, connection, event, msg, username, match)

    def _cmd_boss_damage(self, connection, event, msg, username, match):
        """Admin command to damage the boss."""
        return quest_boss_hunt.cmd_boss_damage(self, connection, event, msg, username, match)

    def _cmd_boss_buff(self, connection, event, msg, username, match):
        """Admin command to toggle boss buff."""
        return quest_boss_hunt.cmd_boss_buff(self, connection, event, msg, username, match)
