# modules/quest_pkg/quest_boss_hunt.py
# Collaborative boss hunt system - track down the mafia boss through clues

import random
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from .constants import UTC


def initialize_boss_hunt_state(quest_module) -> Dict[str, Any]:
    """Initialize the boss hunt state if it doesn't exist."""
    boss_hunt = quest_module.get_state("boss_hunt", {})

    # Initialize stats if missing
    if "stats" not in boss_hunt:
        boss_hunt["stats"] = {
            "total_bosses_defeated": 0,
            "total_clues_found": 0
        }

    # Initialize buff if missing
    if "buff" not in boss_hunt:
        boss_hunt["buff"] = {
            "active": False,
            "expires_at": None,
            "xp_multiplier": 1.0,
            "level_reduction": 0
        }

    # Check if we need to spawn a boss or clear expired buff
    boss_hunt = _check_boss_state(quest_module, boss_hunt)

    quest_module.set_state("boss_hunt", boss_hunt)
    return boss_hunt


def _check_boss_state(quest_module, boss_hunt: Dict[str, Any]) -> Dict[str, Any]:
    """Check and update boss state (clear expired buff, spawn new boss)."""
    channel = None  # We'll use default config since this is global

    # Check if buff has expired
    buff = boss_hunt.get("buff", {})
    if buff.get("active") and buff.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(buff["expires_at"])
            now = datetime.now(UTC)
            if now >= expires_at:
                # Buff expired, deactivate it
                boss_hunt["buff"]["active"] = False
                quest_module.log_debug("Boss hunt buff expired")
        except (ValueError, TypeError):
            pass

    # Check if we need to spawn a new boss
    current_boss = boss_hunt.get("current_boss")
    if not current_boss or current_boss.get("current_hp", 0) <= 0:
        # Spawn a new boss
        boss_hunt["current_boss"] = _spawn_new_boss(quest_module, channel)
        quest_module.log_debug(f"New boss spawned: {boss_hunt['current_boss']['name']}")

    return boss_hunt


def _spawn_new_boss(quest_module, channel) -> Dict[str, Any]:
    """Spawn a new boss for the hunt."""
    # Get boss configuration
    bosses = quest_module.get_config_value("boss_hunt.bosses", channel, default=[
        {"name": "Don Corleone", "description": "The head of the local crime family", "max_hp": 500},
        {"name": "Big Tony", "description": "The mob's enforcer", "max_hp": 600},
        {"name": "Lucky Luciano", "description": "The casino owner", "max_hp": 550}
    ])

    # Get default HP if bosses list is empty
    default_hp = quest_module.get_config_value("boss_hunt.boss_spawn_hp", channel, default=500)

    if not bosses:
        bosses = [{"name": "Crime Boss", "description": "A mysterious criminal mastermind", "max_hp": default_hp}]

    boss_config = random.choice(bosses)
    max_hp = boss_config.get("max_hp", default_hp)

    return {
        "name": boss_config.get("name", "Crime Boss"),
        "description": boss_config.get("description", "A dangerous criminal"),
        "max_hp": max_hp,
        "current_hp": max_hp,
        "clues_collected": 0,
        "spawned_at": datetime.now(UTC).isoformat()
    }


def is_buff_active(quest_module) -> Tuple[bool, Optional[Dict[str, Any]]]:
    """Check if the boss hunt buff is currently active.

    Returns:
        Tuple of (is_active, buff_data)
    """
    boss_hunt = quest_module.get_state("boss_hunt", {})
    buff = boss_hunt.get("buff", {})

    if not buff.get("active"):
        return False, None

    # Check if expired
    if buff.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(buff["expires_at"])
            now = datetime.now(UTC)
            if now >= expires_at:
                return False, None
        except (ValueError, TypeError):
            return False, None

    return True, buff


def apply_boss_hunt_buff_to_combat(quest_module, player_level: int, base_xp: int, channel) -> Tuple[int, int, Optional[str]]:
    """Apply boss hunt buff to combat if active.

    Returns:
        Tuple of (modified_monster_level, modified_xp, buff_message)
    """
    is_active, buff = is_buff_active(quest_module)

    if not is_active:
        return player_level, base_xp, None

    # Reduce monster level
    level_reduction = buff.get("level_reduction", 0)
    modified_level = max(1, player_level - level_reduction)

    # Increase XP
    xp_multiplier = buff.get("xp_multiplier", 1.0)
    modified_xp = int(base_xp * xp_multiplier)

    # Build message
    message = f"🎉 The heat's off! (Enemies -{level_reduction} levels, XP x{xp_multiplier})"

    return modified_level, modified_xp, message


def try_drop_clue(quest_module, connection, event, username: str, channel: str) -> bool:
    """Try to drop a clue after a successful fight.

    Returns:
        True if a clue was dropped, False otherwise
    """
    # Check if boss hunt is enabled
    if not quest_module.get_config_value("boss_hunt.enabled", channel, default=True):
        return False

    # Initialize boss hunt state
    boss_hunt = initialize_boss_hunt_state(quest_module)
    current_boss = boss_hunt.get("current_boss")

    if not current_boss or current_boss.get("current_hp", 0) <= 0:
        # No active boss
        return False

    # Check if clue drops
    clue_drop_chance = quest_module.get_config_value("boss_hunt.clue_drop_chance", channel, default=0.15)
    if random.random() >= clue_drop_chance:
        return False

    # Clue dropped!
    damage_per_clue = quest_module.get_config_value("boss_hunt.boss_damage_per_clue", channel, default=10)

    # Deal damage to boss
    current_boss["current_hp"] = max(0, current_boss["current_hp"] - damage_per_clue)
    current_boss["clues_collected"] = current_boss.get("clues_collected", 0) + 1

    # Update stats
    boss_hunt["stats"]["total_clues_found"] = boss_hunt["stats"].get("total_clues_found", 0) + 1

    # Check if boss defeated
    boss_defeated = current_boss["current_hp"] <= 0

    # Save state
    quest_module.set_state("boss_hunt", boss_hunt)
    quest_module.save_state()

    # Build response message
    hp_bar = _build_hp_bar(current_boss["current_hp"], current_boss["max_hp"])

    if boss_defeated:
        _handle_boss_defeat(quest_module, connection, event, username, current_boss, channel)
    else:
        clue_messages = [
            "finds a crucial piece of evidence",
            "discovers a witness statement",
            "uncovers a financial record",
            "locates a surveillance photo",
            "intercepts a phone conversation",
            "finds a damning document",
            "discovers a hidden ledger"
        ]
        clue_msg = random.choice(clue_messages)

        quest_module.safe_say(
            f"🔍 {username} {clue_msg}! The trail to {current_boss['name']} grows clearer... "
            f"({current_boss['current_hp']}/{current_boss['max_hp']} HP) {hp_bar}",
            channel
        )

    return True


def _build_hp_bar(current_hp: int, max_hp: int, bar_length: int = 20) -> str:
    """Build a visual HP bar."""
    if max_hp <= 0:
        return "[░░░░░░░░░░░░░░░░░░░░]"

    filled_length = int(bar_length * current_hp / max_hp)
    empty_length = bar_length - filled_length

    bar = "█" * filled_length + "░" * empty_length
    return f"[{bar}]"


def _handle_boss_defeat(quest_module, connection, event, username: str, boss: Dict[str, Any], channel: str):
    """Handle boss defeat - activate buff and announce."""
    boss_hunt = quest_module.get_state("boss_hunt", {})

    # Update defeat stats
    boss_hunt["stats"]["total_bosses_defeated"] = boss_hunt["stats"].get("total_bosses_defeated", 0) + 1

    # Activate buff
    buff_duration_days = quest_module.get_config_value("boss_hunt.buff_duration_days", channel, default=7)
    xp_multiplier = quest_module.get_config_value("boss_hunt.buff_xp_multiplier", channel, default=1.5)
    level_reduction = quest_module.get_config_value("boss_hunt.buff_level_reduction", channel, default=2)

    expires_at = datetime.now(UTC) + timedelta(days=buff_duration_days)

    boss_hunt["buff"] = {
        "active": True,
        "expires_at": expires_at.isoformat(),
        "xp_multiplier": xp_multiplier,
        "level_reduction": level_reduction
    }

    # Mark boss as defeated (will auto-spawn new one next time)
    boss["current_hp"] = 0

    # Save state
    quest_module.set_state("boss_hunt", boss_hunt)
    quest_module.save_state()

    # Announce!
    quest_module.safe_say(
        f"🎊 BOSS DEFEATED! 🎊",
        channel
    )
    quest_module.safe_say(
        f"{username} found the final clue! {boss['name']} has been brought to justice after {boss['clues_collected']} clues!",
        channel
    )
    quest_module.safe_say(
        f"🎉 The heat's off for the next {buff_duration_days} days! "
        f"Enemies are easier (Level -{level_reduction}) and XP is increased (x{xp_multiplier})!",
        channel
    )


def get_boss_status(quest_module, channel) -> Optional[str]:
    """Get current boss hunt status as a formatted string.

    Returns:
        Status string or None if boss hunt is disabled
    """
    if not quest_module.get_config_value("boss_hunt.enabled", channel, default=True):
        return None

    boss_hunt = initialize_boss_hunt_state(quest_module)
    current_boss = boss_hunt.get("current_boss")

    if not current_boss:
        return "No active boss hunt."

    hp_bar = _build_hp_bar(current_boss["current_hp"], current_boss["max_hp"])
    hp_pct = int((current_boss["current_hp"] / current_boss["max_hp"]) * 100)

    status = (
        f"🔍 Current Target: {current_boss['name']} - {current_boss['description']}\n"
        f"   Progress: {current_boss['current_hp']}/{current_boss['max_hp']} HP ({hp_pct}%) {hp_bar}\n"
        f"   Clues collected: {current_boss.get('clues_collected', 0)}"
    )

    # Add buff status if active
    is_active, buff = is_buff_active(quest_module)
    if is_active and buff.get("expires_at"):
        try:
            expires_at = datetime.fromisoformat(buff["expires_at"])
            now = datetime.now(UTC)
            time_left = expires_at - now
            days = time_left.days
            hours = time_left.seconds // 3600

            status += f"\n   🎉 BUFF ACTIVE: Easier fights & bonus XP for {days}d {hours}h!"
        except (ValueError, TypeError):
            pass

    return status


def cmd_boss_status(quest_module, connection, event, msg, username, match):
    """Show current boss hunt status."""
    if not quest_module.is_enabled(event.target):
        return False

    status = get_boss_status(quest_module, event.target)
    if status:
        quest_module.safe_reply(connection, event, status)
    else:
        quest_module.safe_reply(connection, event, "Boss hunt is not currently enabled.")

    return True


def cmd_boss_spawn(quest_module, connection, event, msg, username, match):
    """Admin command to spawn a new boss (or reset current one)."""
    if not quest_module.is_enabled(event.target):
        return False

    boss_hunt = quest_module.get_state("boss_hunt", {})
    if "stats" not in boss_hunt:
        boss_hunt["stats"] = {"total_bosses_defeated": 0, "total_clues_found": 0}

    # Spawn new boss
    boss_hunt["current_boss"] = _spawn_new_boss(quest_module, event.target)
    quest_module.set_state("boss_hunt", boss_hunt)
    quest_module.save_state()

    boss = boss_hunt["current_boss"]
    quest_module.safe_say(
        f"🚨 NEW TARGET: {boss['name']} - {boss['description']} "
        f"({boss['max_hp']} HP). Find clues through combat to bring them down!",
        event.target
    )

    return True


def cmd_boss_damage(quest_module, connection, event, msg, username, match):
    """Admin command to deal direct damage to boss."""
    if not quest_module.is_enabled(event.target):
        return False

    try:
        damage = int(match.group(1))
        if damage < 1:
            quest_module.safe_reply(connection, event, "Damage must be at least 1.")
            return True
    except (ValueError, IndexError):
        quest_module.safe_reply(connection, event, "Usage: !admin boss damage <amount>")
        return True

    boss_hunt = initialize_boss_hunt_state(quest_module)
    current_boss = boss_hunt.get("current_boss")

    if not current_boss or current_boss.get("current_hp", 0) <= 0:
        quest_module.safe_reply(connection, event, "No active boss to damage.")
        return True

    # Deal damage
    old_hp = current_boss["current_hp"]
    current_boss["current_hp"] = max(0, current_boss["current_hp"] - damage)
    boss_defeated = current_boss["current_hp"] <= 0

    quest_module.set_state("boss_hunt", boss_hunt)
    quest_module.save_state()

    hp_bar = _build_hp_bar(current_boss["current_hp"], current_boss["max_hp"])

    if boss_defeated:
        quest_module.safe_reply(connection, event, f"Dealt {damage} damage to {current_boss['name']}!")
        _handle_boss_defeat(quest_module, connection, event, username, current_boss, event.target)
    else:
        quest_module.safe_reply(
            connection,
            event,
            f"Dealt {damage} damage to {current_boss['name']}! ({current_boss['current_hp']}/{current_boss['max_hp']} HP) {hp_bar}"
        )

    return True


def cmd_boss_buff(quest_module, connection, event, msg, username, match):
    """Admin command to toggle or check boss hunt buff."""
    if not quest_module.is_enabled(event.target):
        return False

    action = match.group(1).lower() if match.lastindex >= 1 else "status"

    boss_hunt = initialize_boss_hunt_state(quest_module)
    buff = boss_hunt.get("buff", {})

    if action == "on":
        # Activate buff
        buff_duration_days = quest_module.get_config_value("boss_hunt.buff_duration_days", event.target, default=7)
        xp_multiplier = quest_module.get_config_value("boss_hunt.buff_xp_multiplier", event.target, default=1.5)
        level_reduction = quest_module.get_config_value("boss_hunt.buff_level_reduction", event.target, default=2)

        expires_at = datetime.now(UTC) + timedelta(days=buff_duration_days)

        boss_hunt["buff"] = {
            "active": True,
            "expires_at": expires_at.isoformat(),
            "xp_multiplier": xp_multiplier,
            "level_reduction": level_reduction
        }

        quest_module.set_state("boss_hunt", boss_hunt)
        quest_module.save_state()

        quest_module.safe_reply(
            connection,
            event,
            f"Boss hunt buff activated for {buff_duration_days} days! (Level -{level_reduction}, XP x{xp_multiplier})"
        )
    elif action == "off":
        # Deactivate buff
        boss_hunt["buff"]["active"] = False
        quest_module.set_state("boss_hunt", boss_hunt)
        quest_module.save_state()

        quest_module.safe_reply(connection, event, "Boss hunt buff deactivated.")
    else:
        # Show status
        is_active, buff_data = is_buff_active(quest_module)
        if is_active and buff_data and buff_data.get("expires_at"):
            try:
                expires_at = datetime.fromisoformat(buff_data["expires_at"])
                now = datetime.now(UTC)
                time_left = expires_at - now
                days = time_left.days
                hours = time_left.seconds // 3600

                quest_module.safe_reply(
                    connection,
                    event,
                    f"Boss hunt buff is ACTIVE: Level -{buff_data.get('level_reduction', 0)}, "
                    f"XP x{buff_data.get('xp_multiplier', 1.0)} for {days}d {hours}h"
                )
            except (ValueError, TypeError):
                quest_module.safe_reply(connection, event, "Boss hunt buff is active but expiration is invalid.")
        else:
            quest_module.safe_reply(connection, event, "Boss hunt buff is not active.")

    return True
