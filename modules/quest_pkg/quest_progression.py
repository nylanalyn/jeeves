# modules/quest/quest_progression.py
# Progression systems: XP, leveling, prestige, transcendence, abilities, dungeons

import random
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .constants import (
    UTC,
    DUNGEON_ITEMS,
    DUNGEON_ROOMS,
    DUNGEON_ROOMS_BY_ID,
    TOTAL_DUNGEON_ROOMS,
    DUNGEON_REWARD_KEY,
    DUNGEON_REWARD_NAME,
    DUNGEON_REWARD_EFFECT_TEXT,
    DUNGEON_SAFE_HAVENS,
    DUNGEON_MOMENTUM_BONUS,
    DUNGEON_REWARD_CHARGES,
)
from . import quest_utils
from .. import achievement_hooks


def get_prestige_win_bonus(prestige: int) -> float:
    """Calculate win chance bonus from prestige level."""
    if prestige == 0:
        return 0.0
    elif prestige <= 3:
        return 0.05  # Prestige 1-3: +5%
    elif prestige <= 6:
        return 0.10  # Prestige 4-6: +10%
    elif prestige <= 9:
        return 0.15  # Prestige 7-9: +15%
    else:  # prestige == 10
        return 0.20  # Prestige 10: +20%


def get_prestige_xp_bonus(prestige: int) -> float:
    """Calculate XP multiplier from prestige level."""
    if prestige < 2:
        return 1.0  # No bonus for prestige 0-1
    elif prestige < 5:
        return 1.25  # Prestige 2-4: +25%
    elif prestige < 8:
        return 1.50  # Prestige 5-7: +50%
    elif prestige < 10:
        return 1.75  # Prestige 8-9: +75%
    else:  # prestige == 10
        return 2.0  # Prestige 10: +100% (double XP)


def get_prestige_damage_multiplier(prestige: int) -> float:
    """
    Calculate damage multiplier from prestige level for hardcore mode.
    Mirrors XP bonus structure - higher prestige means tougher enemies.
    """
    if prestige < 2:
        return 1.0  # No increase for prestige 0-1
    elif prestige < 5:
        return 1.25  # Prestige 2-4: +25% damage
    elif prestige < 8:
        return 1.50  # Prestige 5-7: +50% damage
    elif prestige < 10:
        return 1.75  # Prestige 8-9: +75% damage
    else:  # prestige == 10
        return 2.0  # Prestige 10: +100% damage (double)


def get_prestige_energy_bonus(prestige: int) -> int:
    """Calculate max energy bonus from prestige level."""
    if prestige < 3:
        return 0  # No bonus for prestige 0-2
    elif prestige < 6:
        return 1  # Prestige 3-5: +1 energy
    elif prestige < 9:
        return 2  # Prestige 6-8: +2 energy
    else:  # prestige >= 9
        return 3  # Prestige 9-10: +3 energy


def get_player_max_energy(quest_module, player_data: Dict[str, Any], channel: Optional[str] = None) -> int:
    """Return the max energy for a player, including prestige bonuses and challenge path modifiers."""
    base_max = quest_module.get_config_value("energy_system.max_energy", channel, default=10)
    prestige_level = player_data.get("prestige", 0) if isinstance(player_data, dict) else 0
    max_energy = base_max + get_prestige_energy_bonus(prestige_level)

    # Apply challenge path modifiers
    challenge_path = player_data.get("challenge_path") if isinstance(player_data, dict) else None
    if challenge_path:
        path_data = quest_module.challenge_paths.get("paths", {}).get(challenge_path, {})
        modifiers = path_data.get("modifiers", {})

        # Apply additive energy bonus first
        energy_bonus = modifiers.get("energy_max_bonus", 0)
        max_energy += energy_bonus

        # Apply multiplicative modifier (e.g., 0.5 for half energy)
        energy_multiplier = modifiers.get("energy_max_multiplier", 1.0)
        max_energy = int(max_energy * energy_multiplier)

    return max_energy


def get_player(quest_module, user_id: str, username: str) -> Dict[str, Any]:
    """Get or create a player."""
    players = quest_module.get_state("players", {})
    player = players.get(user_id)

    if not isinstance(player, dict):
        player = {"name": username, "level": 1, "xp": 0}

    max_energy = get_player_max_energy(quest_module, player)

    player.setdefault("xp_to_next_level", quest_utils.calculate_xp_for_level(quest_module, player.get("level", 1)))
    player.setdefault("last_fight", None)
    player.setdefault("last_win_date", None)
    player.setdefault("energy", max_energy)
    player.setdefault("win_streak", 0)
    player.setdefault("wins", 0)  # Total wins
    player.setdefault("losses", 0)  # Total losses
    player.setdefault("prestige", 0)  # Prestige level
    player.setdefault("transcendence", 0)  # Number of times transcended

    # Inventory system
    player.setdefault("inventory", {
        "medkits": 0,
        "energy_potions": 0,
        "lucky_charms": 0,
        "armor_shards": 0,
        "xp_scrolls": 0,
        "dungeon_relics": 0
    })
    # Ensure new inventory keys exist for legacy players
    player["inventory"].setdefault("dungeon_relics", 0)

    # Migrate old medkits format
    if "medkits" in player and isinstance(player["medkits"], int):
        player["inventory"]["medkits"] = player["medkits"]
        del player["medkits"]

    # Active effects (buffs/debuffs with expiry)
    player.setdefault("active_effects", [])

    # Unlocked abilities and cooldowns
    player.setdefault("unlocked_abilities", [])
    player.setdefault("ability_cooldowns", {})

    # Challenge path stats (for completion tracking)
    player.setdefault("challenge_stats", {
        "medkits_used_this_prestige": 0
    })

    if not isinstance(player.get("completed_challenge_paths"), list):
        player["completed_challenge_paths"] = []

    # Dungeon run metadata
    dungeon_state = player.setdefault("dungeon_state", {})
    dungeon_state.setdefault("equipped_items", [])
    dungeon_state.setdefault("last_equipped", None)
    dungeon_state.setdefault("last_run", None)
    dungeon_state.setdefault("stored_items", {})
    dungeon_state.setdefault("relic_penalty_chain", 0)  # Tracks relic decay across runs
    player["dungeon_state"] = dungeon_state

    # Hardcore mode state
    player.setdefault("hardcore_mode", False)
    player.setdefault("hardcore_hp", 0)
    player.setdefault("hardcore_max_hp", 0)
    player.setdefault("hardcore_locker", {})  # Items stored during hardcore run
    player.setdefault("hardcore_permanent_items", [])  # Item keys that persist in hardcore
    player.setdefault("hardcore_stats", {
        "completions": 0,
        "deaths": 0,
        "highest_level_reached": 0
    })

    player["name"] = username

    return player


def calculate_hardcore_max_hp(level: int) -> int:
    """Calculate max HP for hardcore mode based on level."""
    # Base HP: 100 + (level * 20)
    # Level 1: 120 HP
    # Level 20: 500 HP
    # Level 50: 1100 HP
    return 100 + (level * 20)


def enter_hardcore_mode(player: Dict[str, Any]) -> Dict[str, str]:
    """
    Enter hardcore mode: move non-permanent items to locker, set HP.
    Returns a dict of items moved to locker.
    """
    player["hardcore_mode"] = True
    player["hardcore_max_hp"] = calculate_hardcore_max_hp(player["level"])
    player["hardcore_hp"] = player["hardcore_max_hp"]

    # Reset XP to 0 when entering hardcore to avoid confusion
    # Player will start fresh from their current level (usually 20)
    player["xp"] = 0

    # Move all non-permanent items to locker
    locker = {}
    permanent_items = player.get("hardcore_permanent_items", [])

    for item_key, quantity in player["inventory"].items():
        if quantity > 0 and item_key not in permanent_items:
            locker[item_key] = quantity
            player["inventory"][item_key] = 0

    player["hardcore_locker"] = locker
    return locker


def exit_hardcore_mode(player: Dict[str, Any], completed: bool = False):
    """
    Exit hardcore mode: restore locker items, reset hardcore state.
    If completed=True, grants prestige and completion rewards.
    """
    # Restore items from locker
    locker = player.get("hardcore_locker", {})
    for item_key, quantity in locker.items():
        player["inventory"][item_key] = player["inventory"].get(item_key, 0) + quantity

    # Clear hardcore state
    player["hardcore_mode"] = False
    player["hardcore_hp"] = 0
    player["hardcore_max_hp"] = 0
    player["hardcore_locker"] = {}

    # Update stats
    if completed:
        player["hardcore_stats"]["completions"] = player["hardcore_stats"].get("completions", 0) + 1

    # Track highest level reached
    current_level = player.get("level", 1)
    if current_level > player["hardcore_stats"].get("highest_level_reached", 0):
        player["hardcore_stats"]["highest_level_reached"] = current_level


def calculate_hardcore_damage(monster_level: int, player_level: int, is_win: bool, is_boss: bool = False, prestige: int = 0) -> int:
    """
    Calculate HP damage for hardcore mode combat.
    Even wins deal damage - this is the core challenge of hardcore mode.
    Higher prestige = tougher enemies = more damage.
    """
    # Base damage calculation
    level_diff = monster_level - player_level

    if is_win:
        # Wins deal reduced damage: 10-30 HP depending on level difference
        base_damage = max(10, 20 + (level_diff * 5))
        if is_boss:
            base_damage = int(base_damage * 1.5)  # Boss fights hurt more
    else:
        # Losses deal heavy damage: 40-80 HP depending on level difference
        base_damage = max(40, 60 + (level_diff * 10))
        if is_boss:
            base_damage = int(base_damage * 2.0)  # Boss losses are devastating

    # Apply prestige damage multiplier (seasoned warriors face tougher monsters)
    prestige_mult = get_prestige_damage_multiplier(prestige)
    base_damage = int(base_damage * prestige_mult)

    # Add some randomness (+/- 20%)
    import random
    variance = int(base_damage * 0.2)
    damage = base_damage + random.randint(-variance, variance)

    return max(1, damage)  # Minimum 1 damage


def handle_hardcore_death(quest_module, player: Dict[str, Any], user_id: str, username: str) -> List[str]:
    """
    Handle permadeath in hardcore mode.
    Returns messages to display to the player.
    """
    messages = []

    # Track death
    player["hardcore_stats"]["deaths"] = player["hardcore_stats"].get("deaths", 0) + 1

    # Track highest level reached
    current_level = player.get("level", 1)
    if current_level > player["hardcore_stats"].get("highest_level_reached", 0):
        player["hardcore_stats"]["highest_level_reached"] = current_level

    # Build death announcement
    messages.append(f"\u2620\ufe0f PERMADEATH! \u2620\ufe0f")
    messages.append(f"{username} has fallen in hardcore mode at level {current_level}!")
    messages.append(f"All progress has been lost. Items return to your inventory.")

    # Exit hardcore mode (restores items, clears state)
    exit_hardcore_mode(player, completed=False)

    # No prestige reward - that's the risk!

    return messages


def complete_hardcore_mode(quest_module, player: Dict[str, Any], user_id: str, username: str) -> List[str]:
    """
    Handle successful hardcore mode completion at level 50.
    Returns messages to display to the player.
    """
    messages = []

    # Announce completion!
    messages.append(f"\u2b50 *** HARDCORE MODE COMPLETED! *** \u2b50")
    messages.append(f"{username} has conquered hardcore mode and reached level 50!")

    # Grant prestige reward
    current_prestige = player.get("prestige", 0)
    max_prestige = quest_module.get_config_value("max_prestige", default=10)

    if current_prestige < max_prestige:
        new_prestige = current_prestige + 1
        player["prestige"] = new_prestige

        # Calculate prestige bonuses
        win_bonus = get_prestige_win_bonus(new_prestige)
        xp_bonus = get_prestige_xp_bonus(new_prestige)
        energy_bonus = get_prestige_energy_bonus(new_prestige)

        bonus_parts = []
        if win_bonus > 0:
            bonus_parts.append(f"+{int(win_bonus * 100)}% win chance")
        if xp_bonus > 1.0:
            bonus_parts.append(f"{int((xp_bonus - 1.0) * 100)}% bonus XP")
        if energy_bonus > 0:
            bonus_parts.append(f"+{energy_bonus} max energy")

        bonus_text = ", ".join(bonus_parts) if bonus_parts else "preparing for future bonuses"
        messages.append(f"Prestige {new_prestige} achieved! Bonuses: {bonus_text}")
    else:
        messages.append(f"Already at max prestige ({max_prestige}), but the glory is eternal!")

    # Exit hardcore mode (restores items)
    exit_hardcore_mode(player, completed=True)

    # Reset to level 20 (standard prestige behavior)
    player["level"] = 20
    player["xp"] = 0
    player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, 20)
    player["win_streak"] = 0
    player["active_injuries"] = []
    if "active_injury" in player:
        del player["active_injury"]

    # Restore energy
    player["energy"] = get_player_max_energy(quest_module, player)

    messages.append(f"You return to level 20 with your prestige bonuses. Your items have been restored!")
    messages.append(f"Use !quest hardcore select <item> to mark one item as permanent for future hardcore runs!")
    messages.append(f"Available items: medkits, energy_potions, lucky_charms, armor_shards, xp_scrolls, dungeon_relics")

    return messages


def handle_hardcore_select_item(quest_module, connection, event, username, args):
    """Handle selecting a permanent item after hardcore completion."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)

    if not args:
        quest_module.safe_reply(connection, event, "Usage: !quest hardcore select <item>")
        quest_module.safe_reply(connection, event, "Available: medkits, energy_potions, lucky_charms, armor_shards, xp_scrolls, dungeon_relics")
        return True

    item_key = args[0].lower()

    # Valid item keys
    valid_items = ["medkits", "energy_potions", "lucky_charms", "armor_shards", "xp_scrolls", "dungeon_relics"]
    if item_key not in valid_items:
        quest_module.safe_reply(connection, event, f"Invalid item: {item_key}. Choose from: {', '.join(valid_items)}")
        return True

    # Check if player has this item in inventory
    if player["inventory"].get(item_key, 0) <= 0:
        quest_module.safe_reply(connection, event, f"You don't have any {item_key} to mark as permanent!")
        return True

    # Check if already permanent
    if item_key in player.get("hardcore_permanent_items", []):
        quest_module.safe_reply(connection, event, f"{item_key.replace('_', ' ').title()} are already permanent in hardcore mode!")
        return True

    # Add to permanent items
    if "hardcore_permanent_items" not in player:
        player["hardcore_permanent_items"] = []

    player["hardcore_permanent_items"].append(item_key)

    # Save player state
    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    quest_module.safe_reply(connection, event, f"\u2728 {item_key.replace('_', ' ').title()} are now permanently available in hardcore mode! \u2728")
    quest_module.safe_reply(connection, event, f"These items will never be locked away in future hardcore runs.")

    return True


def grant_xp(quest_module, user_id: str, username: str, amount: int, is_win: bool = False, is_crit: bool = False) -> List[str]:
    """Grant XP to a player and handle leveling."""
    player = get_player(quest_module, user_id, username)
    messages = []
    total_xp_gain = int(amount)
    today = datetime.now(UTC).date().isoformat()

    # Check if player is at level cap (different for hardcore mode)
    is_hardcore = player.get("hardcore_mode", False)
    if is_hardcore:
        level_cap = 50  # Hardcore mode cap is 50
    else:
        level_cap = quest_module.get_config_value("level_cap", default=20)

    if player.get("level", 1) >= level_cap:
        if is_hardcore:
            # Hardcore mode completion at level 50!
            completion_messages = complete_hardcore_mode(quest_module, player, user_id, username)

            # Save player state after completion
            players = quest_module.get_state("players")
            players[user_id] = player
            quest_module.set_state("players", players)
            quest_module.save_state()

            messages.extend(completion_messages)
            return messages
        else:
            messages.append(f"You are at the level cap ({level_cap}). Use !quest prestige to reset and gain permanent bonuses!")
            return messages

    # Apply prestige XP bonus
    prestige_xp_mult = get_prestige_xp_bonus(player.get("prestige", 0))
    if prestige_xp_mult > 1.0:
        total_xp_gain = int(total_xp_gain * prestige_xp_mult)

    # Critical hit bonus (2x XP)
    if is_crit:
        total_xp_gain *= 2
        messages.append("CRITICAL HIT! XP doubled!")

    # Win streak bonus (10% per streak, max 5 streaks = 50%)
    if is_win:
        current_streak = player.get("win_streak", 0)
        if current_streak > 0:
            max_streak_bonus = quest_module.get_config_value("max_streak_bonus", default=5)
            streak_bonus_mult = 1 + (min(current_streak, max_streak_bonus) * 0.10)
            old_xp = total_xp_gain
            total_xp_gain = int(total_xp_gain * streak_bonus_mult)
            messages.append(f"{current_streak}-win streak bonus! (+{total_xp_gain - old_xp} XP)")

        # Increment streak and total wins
        player["win_streak"] = current_streak + 1
        player["wins"] = player.get("wins", 0) + 1

        # Record achievement progress for quest win
        achievement_hooks.record_quest_win(quest_module.bot, username)
        # Record win streak achievement if applicable
        achievement_hooks.record_win_streak(quest_module.bot, username, player["win_streak"])

    first_win_bonus = quest_module.get_config_value("first_win_bonus_xp", default=50)

    if is_win and player.get("last_win_date") != today:
        total_xp_gain += first_win_bonus
        player["last_win_date"] = today
        messages.append(f"You receive a 'First Victory of the Day' bonus of {first_win_bonus} XP!")

    # Migrate old format
    if 'active_injury' in player:
        player['active_injuries'] = [player['active_injury']]
        del player['active_injury']

    # Apply all injury XP multipliers
    if 'active_injuries' in player:
        total_xp_mult = 1.0
        for injury in player['active_injuries']:
            xp_mult = injury.get('effects', {}).get('xp_multiplier', 1.0)
            total_xp_mult *= xp_mult

        if total_xp_mult != 1.0:
            total_xp_gain = int(total_xp_gain * total_xp_mult)
            if total_xp_mult < 1.0:
                messages.append(f"Your injuries reduce your XP gain...")

    # Apply challenge path XP multiplier
    challenge_path = player.get("challenge_path")
    if challenge_path:
        path_data = quest_module.challenge_paths.get("paths", {}).get(challenge_path, {})
        modifiers = path_data.get("modifiers", {})
        xp_multiplier = modifiers.get("xp_gain_multiplier", 1.0)
        if xp_multiplier != 1.0:
            old_xp = total_xp_gain
            total_xp_gain = int(total_xp_gain * xp_multiplier)
            if xp_multiplier < 1.0:
                messages.append(f"Challenge path penalty: XP reduced by {int((1 - xp_multiplier) * 100)}%")

    player["xp"] += total_xp_gain
    leveled_up = False

    while player["xp"] >= player["xp_to_next_level"] and player["level"] < level_cap:
        player["xp"] -= player["xp_to_next_level"]
        player["level"] += 1
        player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, player["level"])
        leveled_up = True

        # Hardcore mode: heal partial HP on level up + increase max HP
        if player.get("hardcore_mode", False):
            new_max_hp = calculate_hardcore_max_hp(player["level"])
            player["hardcore_max_hp"] = new_max_hp
            # Restore 20% of max HP on level up (not full heal)
            hp_restore = int(new_max_hp * 0.20)
            player["hardcore_hp"] = min(player["hardcore_hp"] + hp_restore, new_max_hp)
            messages.append(f"Level up! Restored {hp_restore} HP! ({player['hardcore_hp']}/{new_max_hp} HP)")

    # Cap XP at level cap
    if player["level"] >= level_cap:
        player["xp"] = 0
        player["xp_to_next_level"] = 0

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)

    if leveled_up:
        if player["level"] >= level_cap:
            messages.append(f"*** LEVEL {player['level']} ACHIEVED - MAXIMUM POWER! ***")

            # For hardcore mode, completion is handled automatically on next XP gain
            if is_hardcore:
                messages.append(f"You have conquered the hardcore challenge! Quest again to complete and claim your rewards!")
            else:
                # Check if player completed a challenge path
                challenge_path = player.get("challenge_path")
                if challenge_path:
                    completion_result = check_challenge_completion(quest_module, user_id, username, player, challenge_path)
                    if completion_result:
                        messages.extend(completion_result)
                    else:
                        messages.append(f"You have reached the peak of mortal strength. Use !quest prestige to transcend your limits and be reborn with permanent bonuses!")
                else:
                    messages.append(f"You have reached the peak of mortal strength. Use !quest prestige to transcend your limits and be reborn with permanent bonuses!")
        else:
            messages.append(f"Congratulations, you have reached Level {player['level']}!")
    return messages


def deduct_xp(quest_module, user_id: str, username: str, amount: int) -> Dict[str, Any]:
    """Deduct XP from a player (on loss), allowing level downs when XP underflows."""
    loss = max(0, int(amount))
    if loss == 0:
        return get_player(quest_module, user_id, username)

    player = get_player(quest_module, user_id, username)

    # Check if player is in hardcore mode (different level cap)
    is_hardcore = player.get("hardcore_mode", False)
    if is_hardcore:
        level_cap = 50  # Hardcore mode cap is 50
    else:
        level_cap = quest_module.get_config_value("level_cap", default=20)

    # Convert to total accumulated XP across all levels
    total_xp = player.get("xp", 0)
    for level in range(1, player.get("level", 1)):
        total_xp += quest_utils.calculate_xp_for_level(quest_module, level)

    total_xp = max(0, total_xp - loss)

    # Recalculate level and in-level XP from remaining total XP
    new_level = 1
    remaining_xp = total_xp

    for level in range(1, level_cap):
        level_cost = quest_utils.calculate_xp_for_level(quest_module, level)
        if remaining_xp >= level_cost:
            remaining_xp -= level_cost
            new_level = level + 1
        else:
            break

    player["level"] = new_level
    if new_level >= level_cap:
        player["xp"] = 0
        player["xp_to_next_level"] = 0
    else:
        player["xp"] = remaining_xp
        player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, new_level)

    # Reset win streak on loss and increment loss counter
    player["win_streak"] = 0
    player["losses"] = player.get("losses", 0) + 1

    # Record achievement progress for quest loss
    achievement_hooks.record_quest_loss(quest_module.bot, username)

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    return player


def handle_class(quest_module, connection, event, username, args):
    """Handle class selection. Players can only change class once per prestige."""
    user_id = quest_module.bot.get_user_id(username)
    chosen_class = args[0].lower() if args else ""
    player_classes = quest_module.get_state("player_classes", {})
    class_change_prestige = quest_module.get_state("class_change_prestige", {})
    classes_config = quest_module._get_content("classes", default={})

    # Get player data to check prestige level
    player = get_player(quest_module, user_id, username)
    current_prestige = player.get("prestige", 0)

    if not chosen_class:
        current_class = player_classes.get(user_id, "no class")
        available_classes = ", ".join(classes_config.keys())

        # Show class bonuses info
        if current_class != "no class":
            class_list = list(classes_config.keys())
            try:
                class_position = class_list.index(current_class)
                bonus_info = ""
                if class_position == 0:
                    bonus_info = " (+25% win chance levels 1-10, -10% levels 11-20)"
                elif class_position == 1:
                    bonus_info = " (-10% win chance levels 1-10, +25% levels 11-20)"
                elif class_position == 2:
                    bonus_info = " (50% injury reduction)"
                quest_module.safe_reply(connection, event, f"{quest_module.bot.title_for(username)}, your current class is: {current_class}{bonus_info}. Available: {available_classes}.")
            except ValueError:
                quest_module.safe_reply(connection, event, f"{quest_module.bot.title_for(username)}, your current class is: {current_class}. Available: {available_classes}.")
        else:
            quest_module.safe_reply(connection, event, f"{quest_module.bot.title_for(username)}, your current class is: {current_class}. Available: {available_classes}.")
        return True

    if chosen_class not in classes_config:
        quest_module.safe_reply(connection, event, "My apologies, that is not a recognized class.")
        return True

    # Check if player has already changed class at this prestige level
    last_change_prestige = class_change_prestige.get(user_id, -1)
    if last_change_prestige == current_prestige and user_id in player_classes:
        quest_module.safe_reply(connection, event, "You have already chosen your class for this prestige level. You can change your class again after you prestige.")
        return True

    # Allow the class change
    player_classes[user_id] = chosen_class
    class_change_prestige[user_id] = current_prestige
    quest_module.set_state("player_classes", player_classes)
    quest_module.set_state("class_change_prestige", class_change_prestige)
    quest_module.save_state()

    # Show bonus info for the chosen class
    class_list = list(classes_config.keys())
    try:
        class_position = class_list.index(chosen_class)
        bonus_info = ""
        if class_position == 0:
            bonus_info = " This class gains +25% win chance at levels 1-10, but -10% at levels 11-20."
        elif class_position == 1:
            bonus_info = " This class has -10% win chance at levels 1-10, but +25% at levels 11-20."
        elif class_position == 2:
            bonus_info = " This class has 50% reduced injury chance."
        quest_module.safe_reply(connection, event, f"Very good, {quest_module.bot.title_for(username)}. You are now a {chosen_class.capitalize()}.{bonus_info}")
    except ValueError:
        quest_module.safe_reply(connection, event, f"Very good, {quest_module.bot.title_for(username)}. You are now a {chosen_class.capitalize()}.")

    return True


def check_challenge_completion(quest_module, user_id: str, username: str, player: Dict[str, Any], challenge_path_id: str) -> Optional[List[str]]:
    """Check if player completed challenge path requirements and grant rewards."""
    path_data = quest_module.challenge_paths.get("paths", {}).get(challenge_path_id)
    if not path_data:
        return None

    completion = path_data.get("completion_conditions", {})
    if not completion:
        return None

    completed_paths = player.get("completed_challenge_paths")
    if not isinstance(completed_paths, list):
        completed_paths = []
        player["completed_challenge_paths"] = completed_paths

    # Check if completion conditions are met
    completed = True
    failure_reason = None

    if completion.get("no_medkits_used"):
        medkits_used = player.get("challenge_stats", {}).get("medkits_used_this_prestige", 0)
        if medkits_used > 0:
            completed = False
            failure_reason = f"You used {medkits_used} medkit(s) during this prestige."

    if not completed:
        messages = [
            "You reached level 20, but you did not complete the challenge requirements.",
            failure_reason,
            "You can still use !quest prestige to continue, but you won't earn the challenge rewards."
        ]
        return messages

    # Player completed the challenge! Grant rewards
    messages = [
        f"*** CHALLENGE COMPLETED: {path_data['name']}! ***",
        "You have demonstrated incredible skill and dedication!"
    ]

    if challenge_path_id not in completed_paths:
        completed_paths.append(challenge_path_id)

    rewards = path_data.get("rewards", {})

    # Unlock ability
    if "ability_unlock" in rewards:
        ability_id = rewards["ability_unlock"]
        if ability_id not in player.get("unlocked_abilities", []):
            player["unlocked_abilities"].append(ability_id)

            ability_data = quest_module.challenge_paths.get("abilities", {}).get(ability_id, {})
            ability_name = ability_data.get("name", ability_id)
            messages.append(f"NEW ABILITY UNLOCKED: {ability_name}!")
            messages.append(f"Use !quest ability {ability_data.get('command', ability_id)} to activate it.")

    # Clear challenge path since it's completed
    player["challenge_path"] = None

    # Save player state
    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    messages.append("Use !quest prestige to ascend to your next prestige level.")
    return messages


def handle_hardcore(quest_module, connection, event, username, args):
    """Handle hardcore mode commands."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)

    # Check for subcommands
    subcommand = args[0].lower() if args else "enter"

    if subcommand == "quit":
        # Exit hardcore mode early
        if not player.get("hardcore_mode", False):
            quest_module.safe_reply(connection, event, "You are not currently in hardcore mode.")
            return True

        level_reached = player.get("level", 1)
        exit_hardcore_mode(player, completed=False)

        # Save player state
        players = quest_module.get_state("players")
        players[user_id] = player
        quest_module.set_state("players", players)
        quest_module.save_state()

        quest_module.safe_reply(connection, event, f"{username} has exited hardcore mode at level {level_reached}.")
        quest_module.safe_reply(connection, event, f"Your items have been restored. No prestige was earned, but you kept your progress.")
        return True

    elif subcommand == "select":
        # Select a permanent item after hardcore completion
        return handle_hardcore_select_item(quest_module, connection, event, username, args[1:])

    elif subcommand == "enter" or not args:
        # Enter hardcore mode
        if player.get("hardcore_mode", False):
            quest_module.safe_reply(connection, event, "You are already in hardcore mode!")
            return True

        # Check if player is at level 20
        level_cap = quest_module.get_config_value("level_cap", default=20)
        if player.get("level", 1) < level_cap:
            quest_module.safe_reply(connection, event, f"You must reach level {level_cap} before you can enter hardcore mode. Current level: {player['level']}")
            return True

        # Enter hardcore mode
        locker = enter_hardcore_mode(player)

        # Save player state
        players = quest_module.get_state("players")
        players[user_id] = player
        quest_module.set_state("players", players)
        quest_module.save_state()

        # Announce entry
        quest_module.safe_reply(connection, event, f"\u2620\ufe0f *** {quest_module.bot.title_for(username)} HAS ENTERED HARDCORE MODE! *** \u2620\ufe0f")
        quest_module.safe_reply(connection, event, f"You begin at level {player['level']} with {player['hardcore_hp']}/{player['hardcore_max_hp']} HP.")
        quest_module.safe_reply(connection, event, f"Your items have been moved to storage. Reach level 50 to complete the challenge!")

        if player.get("hardcore_permanent_items"):
            perm_items = ", ".join(player["hardcore_permanent_items"])
            quest_module.safe_reply(connection, event, f"Permanent items available: {perm_items}")

        quest_module.safe_reply(connection, event, f"Death means permadeath - all progress lost! Use !quest hardcore quit to exit early.")
        return True

    else:
        quest_module.safe_reply(connection, event, "Usage: !quest hardcore [enter|quit|select <item>]")
        return True


def handle_prestige(quest_module, connection, event, username, args):
    """Handle prestige - reset to level 1 with permanent bonuses."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)

    # Prevent prestige during hardcore mode
    if player.get("hardcore_mode", False):
        quest_module.safe_reply(connection, event, "You cannot prestige while in hardcore mode! Use !quest hardcore quit to exit first.")
        return True

    # Check if player is at level cap
    level_cap = quest_module.get_config_value("level_cap", default=20)
    if player.get("level", 1) < level_cap:
        quest_module.safe_reply(connection, event, f"You must reach level {level_cap} before you can prestige. Current level: {player['level']}")
        return True

    # Check for challenge prestige
    is_challenge = args and args[0].lower() == "challenge"

    if is_challenge:
        return handle_challenge_prestige(quest_module, connection, event, username, user_id, player)

    # Normal prestige
    # Check if already at max prestige
    max_prestige = quest_module.get_config_value("max_prestige", default=10)
    current_prestige = player.get("prestige", 0)
    if current_prestige >= max_prestige:
        quest_module.safe_reply(connection, event,
                            f"You are already at maximum prestige ({max_prestige})! You are a legend! "
                            "Use !quest transcend to reset everything and ascend into legendary status.")
        return True

    # Calculate new prestige level
    new_prestige = current_prestige + 1

    # Reset player to level 1 (but keep medkits!)
    player["level"] = 1
    player["xp"] = 0
    player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, 1)
    player["prestige"] = new_prestige
    player["win_streak"] = 0
    # medkits are preserved through prestige
    player["active_injuries"] = []
    if "active_injury" in player:
        del player["active_injury"]

    # Clear challenge path on normal prestige
    player["challenge_path"] = None
    player["challenge_stats"] = {
        "medkits_used_this_prestige": 0
    }

    # Save player state
    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    # Build prestige announcement
    win_bonus = get_prestige_win_bonus(new_prestige)
    xp_bonus = get_prestige_xp_bonus(new_prestige)
    energy_bonus = get_prestige_energy_bonus(new_prestige)

    bonus_parts = []
    if win_bonus > 0:
        bonus_parts.append(f"+{int(win_bonus * 100)}% win chance")
    if xp_bonus > 1.0:
        bonus_parts.append(f"{int((xp_bonus - 1.0) * 100)}% bonus XP")
    if energy_bonus > 0:
        bonus_parts.append(f"+{energy_bonus} max energy")

    bonus_text = ", ".join(bonus_parts) if bonus_parts else "preparing for future bonuses"

    quest_module.safe_reply(connection, event, f"*** {quest_module.bot.title_for(username)} HAS ASCENDED TO PRESTIGE {new_prestige}! ***")
    quest_module.safe_reply(connection, event, f"Reborn at Level 1 with permanent bonuses: {bonus_text}")
    quest_module.safe_reply(connection, event, f"The cycle begins anew, but you are forever changed...")

    # Record achievement progress for prestige level
    achievement_hooks.record_prestige_level(quest_module.bot, username, new_prestige)

    return True


def handle_transcend(quest_module, connection, event, username):
    """Allow a max-prestige player to transcend and become a legend boss."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)

    level_cap = quest_module.get_config_value("level_cap", event.target, default=20)
    if player.get("level", 1) < level_cap:
        quest_module.safe_reply(connection, event,
                            f"You must reach level {level_cap} before you can transcend. Current level: {player['level']}.")
        return True

    max_prestige = quest_module.get_config_value("max_prestige", event.target, default=10)
    if player.get("prestige", 0) < max_prestige:
        quest_module.safe_reply(connection, event,
                            f"You must achieve Prestige {max_prestige} before you can transcend. Current prestige: {player.get('prestige', 0)}.")
        return True

    max_transcendence = quest_module.get_config_value("max_transcendence", event.target, default=None)
    current_transcendence = player.get("transcendence", 0)
    if isinstance(max_transcendence, int) and max_transcendence > 0 and current_transcendence >= max_transcendence:
        quest_module.safe_reply(connection, event,
                            f"You have already reached the maximum transcendence ({max_transcendence}). Your legend is complete.")
        return True

    new_transcendence = current_transcendence + 1

    # Preserve unlocked abilities through transcendence
    preserved_abilities = player.get("unlocked_abilities", [])

    # Reset player stats to base values
    player["transcendence"] = new_transcendence
    player["prestige"] = 1
    player["level"] = 1
    player["xp"] = 0
    player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, 1)
    player["win_streak"] = 0
    player["last_fight"] = None
    player["last_win_date"] = None
    player["active_effects"] = []
    player["active_injuries"] = []
    if "active_injury" in player:
        del player["active_injury"]
    player["challenge_path"] = None
    player["challenge_stats"] = {
        "medkits_used_this_prestige": 0
    }
    player["inventory"] = {
        "medkits": 0,
        "energy_potions": 0,
        "lucky_charms": 0,
        "armor_shards": 0,
        "xp_scrolls": 0,
        DUNGEON_REWARD_KEY: 0
    }
    if "medkits" in player:
        del player["medkits"]
    player["energy"] = get_player_max_energy(quest_module, player, event.target)
    player["dungeon_state"] = {
        "equipped_items": [],
        "last_equipped": None,
        "last_run": None
    }
    player["ability_cooldowns"] = {}  # Reset cooldowns but keep abilities
    player["unlocked_abilities"] = preserved_abilities  # Keep unlocked abilities!

    # Clear class back to default
    player_classes = quest_module.get_state("player_classes", {})
    if user_id in player_classes:
        del player_classes[user_id]
        quest_module.set_state("player_classes", player_classes)

    # Persist player changes
    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)

    legend_bosses = quest_module.get_state("legend_bosses", {})
    legend_bosses[user_id] = {
        "user_id": user_id,
        "username": player["name"],
        "transcendence": new_transcendence,
        "created_at": datetime.now(UTC).isoformat()
    }
    quest_module.set_state("legend_bosses", legend_bosses)

    quest_module.save_state()

    legend_suffix = "(Legend)" if new_transcendence == 1 else f"(Legend {quest_utils.to_roman(new_transcendence)})"

    quest_module.safe_reply(connection, event,
                        f"*** {username} transcends the mortal cycle and becomes {legend_suffix}! Their legend will haunt future mobs. ***")
    quest_module.safe_reply(connection, event,
                        "You have been reborn at Level 1, Prestige 1. Your stats have been reset to their base values.")

    # Notify about preserved abilities
    if preserved_abilities:
        abilities_data = quest_module.challenge_paths.get("abilities", {})
        ability_names = [abilities_data.get(aid, {}).get("name", aid) for aid in preserved_abilities]
        quest_module.safe_privmsg(username,
                              f"Your unlocked abilities remain with you: {', '.join(ability_names)}")

    quest_module.safe_privmsg(username,
                          "You now stalk the world as a Legend-tier boss. Future !mob encounters may summon you—good luck to the mortals!")

    return True


def handle_challenge_prestige(quest_module, connection, event, username, user_id, player):
    """Handle challenge path prestige - special alternate progression."""
    # Check if a challenge path is active
    active_path_id = quest_module.challenge_paths.get("active_path")
    if not active_path_id:
        quest_module.safe_reply(connection, event, "No challenge path is currently available. Use normal !quest prestige instead.")
        return True

    path_data = quest_module.challenge_paths["paths"].get(active_path_id)
    if not path_data:
        quest_module.safe_reply(connection, event, "Challenge path configuration error. Contact an administrator.")
        return True

    completed_paths = player.get("completed_challenge_paths")
    if isinstance(completed_paths, list) and active_path_id in completed_paths:
        path_name = path_data.get("name", active_path_id)
        quest_module.safe_reply(connection, event, f"Sorry, you have completed this path ({path_name})! Wait for the next challenge.")
        return True

    # Check requirements
    current_prestige = player.get("prestige", 0)
    min_prestige = path_data.get("requirements", {}).get("min_prestige", 0)
    max_prestige = path_data.get("requirements", {}).get("max_prestige", 10)

    if current_prestige < min_prestige:
        quest_module.safe_reply(connection, event, f"You need at least Prestige {min_prestige} to enter this challenge path.")
        return True

    if current_prestige >= max_prestige:
        quest_module.safe_reply(connection, event, f"You have exceeded the maximum prestige ({max_prestige}) for this challenge path.")
        return True

    # Reset player for challenge path
    new_prestige = current_prestige + 1
    player["level"] = 1
    player["xp"] = 0
    player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, 1)
    player["prestige"] = new_prestige
    player["win_streak"] = 0
    player["active_injuries"] = []
    player["challenge_path"] = active_path_id  # Track which path they're on

    # Reset challenge stats for new prestige
    player["challenge_stats"] = {
        "medkits_used_this_prestige": 0
    }

    if "active_injury" in player:
        del player["active_injury"]

    # Save player state
    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    # Announce challenge prestige
    quest_module.safe_reply(connection, event, f"*** {quest_module.bot.title_for(username)} HAS ENTERED THE CHALLENGE PATH: {path_data['name']}! ***")
    quest_module.safe_reply(connection, event, f"Prestige {new_prestige} - {path_data['description']}")

    # Show special rules
    if "special_rules" in path_data and path_data["special_rules"]:
        for rule in path_data["special_rules"]:
            quest_module.safe_reply(connection, event, f"  - {rule}")

    quest_module.safe_reply(connection, event, "Your journey takes a new and dangerous turn...")

    return True


def _auto_prepare_dungeon_loadout(quest_module, channel: str, user_id: str, username: str, player: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Pull cached dungeon items into the equipped loadout before a new run."""
    dungeon_state = quest_utils.get_dungeon_state(player)
    cache = quest_utils.get_dungeon_item_cache(player)

    max_equipped_default = len(DUNGEON_ITEMS)
    max_equipped = quest_module.get_config_value(
        "dungeon.max_equipped_items", channel, default=max_equipped_default
    )
    max_equipped = int(max(0, min(max_equipped, max_equipped_default)))

    loadout: List[Dict[str, Any]] = []
    if max_equipped > 0:
        for item in DUNGEON_ITEMS:
            available = cache.get(item["key"], 0)
            if available <= 0:
                continue
            quest_utils.consume_dungeon_item_from_cache(player, item["key"], 1)
            loadout.append(item)
            if len(loadout) >= max_equipped:
                break

    dungeon_state["equipped_items"] = [item["key"] for item in loadout]
    dungeon_state["last_equipped"] = datetime.now(UTC).isoformat()

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    return loadout


def _broadcast_dungeon_outcome(quest_module, connection, event, active_run: Optional[Dict[str, Any]], message: str) -> None:
    """Notify both the invoking context and, if needed, the dungeon channel about the result."""
    quest_module.safe_reply(connection, event, message)

    origin = getattr(event, "target", "") or ""
    channel = (active_run or {}).get("channel")
    if channel and channel.startswith('#') and not origin.startswith('#'):
        quest_module.safe_say(message, channel)


def cmd_dungeon_run(quest_module, connection, event, msg, username, match, skip_safe_havens=False):
    """Run the ten-room dungeon, DMing each step to the player."""
    # Import here to avoid circular dependency
    from .quest_combat import apply_active_effects_to_combat, consume_combat_effects

    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)
    dungeon_state = quest_utils.get_dungeon_state(player)
    channel = event.target
    start_time = datetime.now(UTC).isoformat()
    starting_new_run = not dungeon_state.get("active_run")

    loadout_for_run: List[Dict[str, Any]] = []
    if starting_new_run:
        loadout_for_run = _auto_prepare_dungeon_loadout(quest_module, channel, user_id, username, player)
        equipped_keys = dungeon_state.get("equipped_items", [])

        if loadout_for_run:
            item_names = ", ".join(item["name"] for item in loadout_for_run)
            quest_module.safe_reply(
                connection,
                event,
                f"{username} draws on cached gear: {item_names}."
            )
        else:
            quest_module.safe_reply(
                connection,
                event,
                f"{username} has no cached counter-items. Every room will challenge you—spend energy on !quest search to stock up."
            )

        if quest_module.get_config_value("dungeon.dm_loadout_summary", channel, default=True):
            summary_lines = ["Dungeon Loadout:"]
            if loadout_for_run:
                for item in loadout_for_run:
                    counter_rooms = [
                        DUNGEON_ROOMS_BY_ID[room_id]["name"]
                        for room_id in item.get("counters", [])
                        if room_id in DUNGEON_ROOMS_BY_ID
                    ]
                    if counter_rooms:
                        summary_lines.append(f"- {item['name']}: counters {', '.join(counter_rooms)}")
                    else:
                        summary_lines.append(f"- {item['name']}: {item['description']}")
            else:
                summary_lines.append("- No counter-items equipped. Expect every encounter to trigger.")

            cache_summary = quest_utils.describe_dungeon_cache(quest_utils.get_dungeon_item_cache(player))
            if cache_summary:
                summary_lines.append("")
                summary_lines.append(f"Cached items remaining: {', '.join(cache_summary)}")
            summary_lines.append("Loadout auto-equipped for this dungeon run; final results still land in-channel.")
            quest_module.safe_privmsg(username, "\n".join(summary_lines))
    else:
        equipped_keys = dungeon_state.get("equipped_items", [])

    # Initialize or continue run
    if starting_new_run:
        # Reset relic decay if it's been 24h since the last finished dungeon
        last_run = dungeon_state.get("last_run") or {}
        last_run_ended = last_run.get("ended")
        if last_run_ended:
            try:
                last_end_dt = datetime.fromisoformat(last_run_ended)
                # Normalize to UTC if naive datetime
                if last_end_dt.tzinfo is None:
                    last_end_dt = last_end_dt.replace(tzinfo=UTC)
                if (datetime.now(UTC) - last_end_dt) >= timedelta(hours=24):
                    dungeon_state["relic_penalty_chain"] = 0
            except (ValueError, TypeError):
                pass

        # Starting new run
        dungeon_state["active_run"] = {
            "started": start_time,
            "channel": channel,
            "current_room": 1,
            "momentum": 0,  # Consecutive victories
            "rooms_cleared": 0,
            "bypass_used": False,
            "xp_notice_sent": False,
            "relic_auto_wins": 0  # Count relic-fueled victories this run
        }
        dungeon_state["last_run"] = {
            "started": start_time,
            "channel": channel,
            "completed": False,
            "final_room": None,
            "success": None
        }
        quest_module.safe_reply(connection, event,
                            f"{username}, starting your dungeon crawl now—check your DMs for the blow-by-blow.")
        quest_module.safe_privmsg(username, f"--- Entering the Tenfold Depths ({TOTAL_DUNGEON_ROOMS} rooms) ---")

    active_run = dungeon_state["active_run"]
    # Backfill new tracking keys for older runs
    active_run.setdefault("relic_auto_wins", 0)
    start_room = active_run["current_room"]
    momentum = active_run["momentum"]

    # Run dungeon from current room
    for index in range(start_room, TOTAL_DUNGEON_ROOMS + 1):
        room = DUNGEON_ROOMS[index - 1]
        room_header = f"Room {index}/{TOTAL_DUNGEON_ROOMS}: {room['name']}"
        quest_module.safe_privmsg(username, room_header)
        quest_module.safe_privmsg(username, room["intro"])

        # Check for counter item bypass
        counter_key = next((key for key in equipped_keys if key in room.get("counter_items", [])), None)

        if counter_key and room.get("bypass_text"):
            quest_module.safe_privmsg(username, room["bypass_text"])
            active_run["rooms_cleared"] = index
            # Bypassed rooms still count for momentum
            momentum += 1
            active_run["momentum"] = momentum
            active_run["bypass_used"] = True

            # Check for safe haven after bypass
            if not skip_safe_havens and index in DUNGEON_SAFE_HAVENS:
                active_run["current_room"] = index + 1
                players = quest_module.get_state("players")
                players[user_id] = player
                quest_module.set_state("players", players)
                quest_module.save_state()
                _show_safe_haven(quest_module, username, index, momentum, player)
                return True
            continue

        # Combat encounter
        monster = room["monster"]
        monster_level = max(1, player.get("level", 1) + monster.get("level_offset", 0))

        # Get class bonuses
        class_bonuses = quest_utils.get_class_bonuses(quest_module, user_id, player.get("level", 1))

        # Calculate base win chance with prestige bonus and class bonus
        base_win_chance = quest_utils.calculate_win_chance(
            player.get("level", 1),
            monster_level,
            prestige_level=player.get("prestige", 0),
            class_bonus=class_bonuses["win_chance"]
        )
        base_win_chance += monster.get("win_chance_adjust", 0.0)

        # Add momentum bonus (dungeon-specific)
        momentum_bonus = momentum * DUNGEON_MOMENTUM_BONUS
        if momentum > 0:
            quest_module.safe_privmsg(username, f"Momentum bonus: +{momentum_bonus:.0%} win chance ({momentum} consecutive clears)")
        base_win_chance += momentum_bonus

        # Add prestige advantage bonus (experienced players get extra edge)
        player_prestige = player.get("prestige", 0)
        if player_prestige >= 3:
            prestige_bonus = 0.05
            quest_module.safe_privmsg(username, f"Veteran warrior bonus: +{prestige_bonus:.0%} win chance (Prestige {player_prestige})")
            base_win_chance += prestige_bonus

        # Apply challenge path modifiers
        challenge_path = player.get("challenge_path")
        if challenge_path:
            path_data = quest_module.challenge_paths.get("paths", {}).get(challenge_path, {})
            modifiers = path_data.get("modifiers", {})
            challenge_win_mod = modifiers.get("win_chance_modifier", 0.0)
            if challenge_win_mod != 0.0:
                base_win_chance += challenge_win_mod

        # Clamp win chance
        min_win = quest_module.get_config_value("combat.min_win_chance", channel, default=0.05)
        max_win = quest_module.get_config_value("combat.max_win_chance", channel, default=0.95)
        base_win_chance = max(min_win, min(max_win, base_win_chance))

        # Apply active effects
        base_xp = monster.get("xp_reward", 0)
        win_chance, _, effect_msgs = apply_active_effects_to_combat(player, base_win_chance, base_xp, is_win=False, quest_module=quest_module, channel=channel)
        for msg_text in effect_msgs:
            if msg_text:
                quest_module.safe_privmsg(username, msg_text)

        # Track relic-fueled auto-wins so we can scale rewards down later
        relic_auto_triggered = any(
            eff.get("type") == "dungeon_relic" and eff.get("triggered_this_fight")
            for eff in player.get("active_effects", [])
        )
        if relic_auto_triggered:
            active_run["relic_auto_wins"] = active_run.get("relic_auto_wins", 0) + 1

        # Roll combat
        win = random.random() < win_chance

        if win:
            bypass_active = active_run.get("bypass_used", False)
            if bypass_active and not active_run.get("xp_notice_sent"):
                quest_module.safe_privmsg(username, "Dungeon spirits refuse to grant XP when you rely on counter-item shortcuts.")
                active_run["xp_notice_sent"] = True

            _, xp_award, xp_effect_msgs = apply_active_effects_to_combat(player, base_win_chance, base_xp, is_win=True, quest_module=quest_module, channel=channel)
            quest_module.safe_privmsg(username, f"You defeat the {monster['name']}! (Win chance: {win_chance:.0%})")
            for msg_text in xp_effect_msgs:
                if msg_text:
                    quest_module.safe_privmsg(username, msg_text)

            player["last_fight"] = {
                "monster_name": monster["name"],
                "monster_level": monster_level,
                "win": True
            }

            if xp_award > 0 and not bypass_active:
                xp_messages = grant_xp(quest_module, user_id, username, xp_award, is_win=True)
                for xp_msg in xp_messages:
                    quest_module.safe_privmsg(username, xp_msg)

            momentum += 1
            active_run["momentum"] = momentum
            active_run["rooms_cleared"] = index
            consume_combat_effects(player, True)

            # Check for safe haven
            if not skip_safe_havens and index in DUNGEON_SAFE_HAVENS:
                active_run["current_room"] = index + 1
                players = quest_module.get_state("players")
                players[user_id] = player
                quest_module.set_state("players", players)
                quest_module.save_state()
                _show_safe_haven(quest_module, username, index, momentum, player)
                return True

        else:
            # Defeat
            quest_module.safe_privmsg(username, f"The {monster['name']} overwhelms you! (Win chance: {win_chance:.0%})")
            player["last_fight"] = {
                "monster_name": monster["name"],
                "monster_level": monster_level,
                "win": False
            }

            # Apply XP-based penalty based on progress
            previous_level = player.get("level", 1)
            xp_loss = quest_utils.apply_dungeon_failure_penalty(
                quest_module,
                player,
                user_id,
                username,
                room_reached=index
            )
            new_level = player.get("level", 1)
            consume_combat_effects(player, False)

            # Clean up dungeon state
            dungeon_state["last_run"].update({
                "completed": True,
                "final_room": index,
                "success": False,
                "ended": datetime.now(UTC).isoformat()
            })
            dungeon_state["equipped_items"] = []
            dungeon_state["active_run"] = None

            players = quest_module.get_state("players")
            players[user_id] = player
            quest_module.set_state("players", players)
            quest_module.save_state()

            # Send defeat message with penalty
            quest_module.safe_privmsg(username, f"You were defeated and lost {xp_loss} XP. No rewards were gained.")

            # Determine penalty message based on room
            if new_level < previous_level:
                penalty_msg = f"and loses {xp_loss} XP (dropping to level {new_level})"
            else:
                penalty_msg = f"and loses {xp_loss} XP"

            defeat_msg = f"{username} was defeated in room {index} ({room['name']}) {penalty_msg}."
            _broadcast_dungeon_outcome(quest_module, connection, event, active_run, defeat_msg)
            return True

    # Victory! Cleared all 10 rooms
    dungeon_state["last_run"].update({
        "completed": True,
        "final_room": TOTAL_DUNGEON_ROOMS,
        "success": True,
        "ended": datetime.now(UTC).isoformat()
    })
    dungeon_state["equipped_items"] = []
    dungeon_state["active_run"] = None

    base_relic_reward = DUNGEON_REWARD_CHARGES
    relic_auto_wins = active_run.get("relic_auto_wins", 0)
    relic_chain = dungeon_state.get("relic_penalty_chain", 0)
    relic_penalty = min(base_relic_reward, relic_auto_wins + relic_chain)
    relic_reward = max(0, base_relic_reward - relic_penalty)

    player["inventory"][DUNGEON_REWARD_KEY] = player["inventory"].get(DUNGEON_REWARD_KEY, 0) + relic_reward
    player["last_fight"] = {
        "monster_name": DUNGEON_ROOMS[-1]["monster"]["name"],
        "monster_level": player.get("level", 1) + DUNGEON_ROOMS[-1]["monster"].get("level_offset", 0),
        "win": True
    }

    if relic_penalty > 0:
        quest_module.safe_privmsg(
            username,
            f"You conquer the Heart of the Abyss! Reliance on relic power dampens the reward (-{relic_penalty})."
        )
    else:
        quest_module.safe_privmsg(username, f"You conquer the Heart of the Abyss! A {DUNGEON_REWARD_NAME} materializes in your hands.")
    quest_module.safe_privmsg(username, f"Relics earned: {relic_reward} (base {base_relic_reward}, relic auto-wins: {relic_auto_wins})")
    quest_module.safe_privmsg(username, DUNGEON_REWARD_EFFECT_TEXT)

    # Update decay chain: clean runs reset; relic runs carry forward their penalty
    if relic_auto_wins <= 0:
        dungeon_state["relic_penalty_chain"] = 0
    else:
        dungeon_state["relic_penalty_chain"] = relic_penalty  # carry forward effective debt

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    relic_suffix = "s" if relic_reward != 1 else ""
    victory_msg = f"{username} cleared all {TOTAL_DUNGEON_ROOMS} rooms and claimed {relic_reward} {DUNGEON_REWARD_NAME}{relic_suffix}! "
    if relic_penalty > 0:
        victory_msg += f"(Reduced by {relic_penalty} for relying on relic auto-wins) "
    victory_msg += DUNGEON_REWARD_EFFECT_TEXT
    _broadcast_dungeon_outcome(quest_module, connection, event, dungeon_state.get("last_run"), victory_msg)
    return True


def _show_safe_haven(quest_module, username: str, rooms_cleared: int, momentum: int, player: Dict[str, Any]):
    """Display safe haven message with options."""
    quest_module.safe_privmsg(username, "")
    quest_module.safe_privmsg(username, f"=== SAFE HAVEN (after room {rooms_cleared}/{TOTAL_DUNGEON_ROOMS}) ===")
    quest_module.safe_privmsg(username, "You've reached a sanctuary within the depths. Torches burn with soothing light.")
    quest_module.safe_privmsg(username, f"Current momentum: {momentum} consecutive clears (+{momentum * DUNGEON_MOMENTUM_BONUS:.0%} win chance)")
    quest_module.safe_privmsg(username, "")
    quest_module.safe_privmsg(username, "OPTIONS:")
    quest_module.safe_privmsg(username, "- !quest use <item> - Use consumable items (lucky charms, armor shards, etc.)")
    quest_module.safe_privmsg(username, "- !dungeon continue - Press onward to the next room")
    quest_module.safe_privmsg(username, "- !dungeon quit - Retreat safely with partial rewards")

    # Show available consumables
    consumables = []
    inventory = player.get("inventory", {})
    if inventory.get("lucky_charms", 0) > 0:
        consumables.append(f"lucky_charms x{inventory['lucky_charms']}")
    if inventory.get("armor_shards", 0) > 0:
        consumables.append(f"armor_shards x{inventory['armor_shards']}")
    if inventory.get("xp_scrolls", 0) > 0:
        consumables.append(f"xp_scrolls x{inventory['xp_scrolls']}")

    if consumables:
        quest_module.safe_privmsg(username, f"Available consumables: {', '.join(consumables)}")
    else:
        quest_module.safe_privmsg(username, "You have no consumable items.")


def cmd_dungeon_continue(quest_module, connection, event, msg, username, match):
    """Continue dungeon run from a safe haven."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)
    dungeon_state = quest_utils.get_dungeon_state(player)

    if "active_run" not in dungeon_state or not dungeon_state["active_run"]:
        quest_module.safe_reply(connection, event, "You don't have an active dungeon run. Use !quest search to stock up, then enter with !dungeon.")
        return True

    active_run = dungeon_state["active_run"]
    current_room = active_run.get("current_room", 1)

    # Check if they're actually at a safe haven
    if (current_room - 1) not in DUNGEON_SAFE_HAVENS:
        quest_module.safe_reply(connection, event, "You can only continue from a safe haven checkpoint.")
        return True

    quest_module.safe_reply(connection, event, f"{username} presses deeper into the dungeon...")
    quest_module.safe_privmsg(username, f"You steel yourself and venture into room {current_room}...")

    # Resume the dungeon run (it will pick up from current_room)
    return cmd_dungeon_run(quest_module, connection, event, msg, username, match)


def cmd_dungeon_quit(quest_module, connection, event, msg, username, match):
    """Quit dungeon run and claim XP rewards (no relics)."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)
    dungeon_state = quest_utils.get_dungeon_state(player)

    if "active_run" not in dungeon_state or not dungeon_state["active_run"]:
        quest_module.safe_reply(connection, event, "You don't have an active dungeon run to quit.")
        return True

    active_run = dungeon_state["active_run"]
    rooms_cleared = active_run.get("rooms_cleared", 0)
    current_room = active_run.get("current_room", 1)

    # Check if they're at a safe haven
    if (current_room - 1) not in DUNGEON_SAFE_HAVENS:
        quest_module.safe_reply(connection, event, "You can only quit from a safe haven checkpoint.")
        return True

    # Grant quit rewards (XP only)
    allow_xp = not active_run.get("bypass_used", False)
    reward_msg = quest_utils.grant_dungeon_quit_reward(quest_module, user_id, username, rooms_cleared, allow_xp=allow_xp)

    # Clean up dungeon state
    dungeon_state["last_run"].update({
        "completed": True,
        "final_room": rooms_cleared,
        "success": False,
        "ended": datetime.now(UTC).isoformat()
    })
    dungeon_state["equipped_items"] = []
    dungeon_state["active_run"] = None

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    quest_module.safe_privmsg(username, f"You retreat from the dungeon after clearing {rooms_cleared} rooms.")
    quest_module.safe_privmsg(username, reward_msg)
    quit_msg = f"{username} retreats from the dungeon. {reward_msg}"
    _broadcast_dungeon_outcome(quest_module, connection, event, active_run, quit_msg)

    return True
