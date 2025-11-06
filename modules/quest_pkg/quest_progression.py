# modules/quest/quest_progression.py
# Progression systems: XP, leveling, prestige, transcendence, abilities, dungeons

import random
from datetime import datetime
from typing import Dict, Any, List, Optional

from .constants import (
    UTC, DUNGEON_ROOMS, DUNGEON_ROOMS_BY_ID, TOTAL_DUNGEON_ROOMS,
    DUNGEON_REWARD_KEY, DUNGEON_REWARD_NAME, DUNGEON_REWARD_EFFECT_TEXT,
    DUNGEON_SAFE_HAVENS, DUNGEON_MOMENTUM_BONUS, DUNGEON_REWARD_CHARGES
)
from . import quest_utils


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
    """Return the max energy for a player, including prestige bonuses."""
    base_max = quest_module.get_config_value("energy_system.max_energy", channel, default=10)
    prestige_level = player_data.get("prestige", 0) if isinstance(player_data, dict) else 0
    return base_max + get_prestige_energy_bonus(prestige_level)


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
    player.setdefault("dungeon_state", {
        "equipped_items": [],
        "last_equipped": None,
        "last_run": None
    })

    player["name"] = username

    return player


def grant_xp(quest_module, user_id: str, username: str, amount: int, is_win: bool = False, is_crit: bool = False) -> List[str]:
    """Grant XP to a player and handle leveling."""
    player = get_player(quest_module, user_id, username)
    messages = []
    total_xp_gain = int(amount)
    today = datetime.now(UTC).date().isoformat()

    # Check if player is at level cap
    level_cap = quest_module.get_config_value("level_cap", default=20)
    if player.get("level", 1) >= level_cap:
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

    player["xp"] += total_xp_gain
    leveled_up = False

    while player["xp"] >= player["xp_to_next_level"] and player["level"] < level_cap:
        player["xp"] -= player["xp_to_next_level"]
        player["level"] += 1
        player["xp_to_next_level"] = quest_utils.calculate_xp_for_level(quest_module, player["level"])
        leveled_up = True

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

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    return player


def handle_class(quest_module, connection, event, username, args):
    """Handle class selection."""
    user_id = quest_module.bot.get_user_id(username)
    chosen_class = args[0].lower() if args else ""
    player_classes = quest_module.get_state("player_classes", {})
    classes_config = quest_module._get_content("classes", default={})

    if not chosen_class:
        current_class = player_classes.get(user_id, "no class")
        available_classes = ", ".join(classes_config.keys())
        quest_module.safe_reply(connection, event, f"{quest_module.bot.title_for(username)}, your current class is: {current_class}. Available: {available_classes}.")
        return True
    if chosen_class not in classes_config:
        quest_module.safe_reply(connection, event, f"My apologies, that is not a recognized class.")
        return True

    player_classes[user_id] = chosen_class
    quest_module.set_state("player_classes", player_classes)
    quest_module.save_state()
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


def handle_prestige(quest_module, connection, event, username, args):
    """Handle prestige - reset to level 1 with permanent bonuses."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)

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


def cmd_dungeon_equip(quest_module, connection, event, msg, username, match):
    """Equip a random set of dungeon items for the next run."""
    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)
    dungeon_state = quest_utils.get_dungeon_state(player)

    loadout = quest_utils.select_dungeon_loadout()
    dungeon_state["equipped_items"] = [item["key"] for item in loadout]
    dungeon_state["last_equipped"] = datetime.now(UTC).isoformat()

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    item_names = ", ".join(item["name"] for item in loadout)
    quest_module.safe_reply(
        connection,
        event,
        f"{username} draws {item_names}. Use !dungeon when you want the DM blow-by-blow; it will be spammy!"
    )

    if quest_module.get_config_value("dungeon.dm_loadout_summary", event.target, default=True):
        summary_lines = ["Dungeon Loadout:"]
        for item in loadout:
            counter_rooms = [
                DUNGEON_ROOMS_BY_ID[room_id]["name"]
                for room_id in item.get("counters", [])
                if room_id in DUNGEON_ROOMS_BY_ID
            ]
            if counter_rooms:
                summary_lines.append(f"- {item['name']}: counters {', '.join(counter_rooms)}")
            else:
                summary_lines.append(f"- {item['name']}: {item['description']}")
        summary_lines.append("Use !dungeon to begin. Final results still land in-channel.")
        quest_module.safe_privmsg(username, "\n".join(summary_lines))

    return True


def cmd_dungeon_run(quest_module, connection, event, msg, username, match):
    """Run the ten-room dungeon, DMing each step to the player."""
    # Import here to avoid circular dependency
    from .quest_combat import apply_active_effects_to_combat, consume_combat_effects

    user_id = quest_module.bot.get_user_id(username)
    player = get_player(quest_module, user_id, username)
    dungeon_state = quest_utils.get_dungeon_state(player)
    equipped_keys = dungeon_state.get("equipped_items", [])

    if not equipped_keys:
        quest_module.safe_reply(connection, event,
                            f"{quest_module.bot.title_for(username)}, you need to !equip before taking on the dungeon.")
        return True

    channel = event.target
    start_time = datetime.now(UTC).isoformat()

    # Initialize or continue run
    if "active_run" not in dungeon_state or not dungeon_state["active_run"]:
        # Starting new run
        dungeon_state["active_run"] = {
            "started": start_time,
            "channel": channel,
            "current_room": 1,
            "momentum": 0,  # Consecutive victories
            "rooms_cleared": 0
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

            # Check for safe haven after bypass
            if index in DUNGEON_SAFE_HAVENS:
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

        # Calculate base win chance with prestige bonus
        base_win_chance = quest_utils.calculate_win_chance(
            player.get("level", 1),
            monster_level,
            prestige_level=player.get("prestige", 0)
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

        # Clamp win chance
        min_win = quest_module.get_config_value("combat.min_win_chance", channel, default=0.05)
        max_win = quest_module.get_config_value("combat.max_win_chance", channel, default=0.95)
        base_win_chance = max(min_win, min(max_win, base_win_chance))

        # Apply active effects
        base_xp = monster.get("xp_reward", 0)
        win_chance, _, effect_msgs = apply_active_effects_to_combat(player, base_win_chance, base_xp, is_win=False)
        for msg_text in effect_msgs:
            if msg_text:
                quest_module.safe_privmsg(username, msg_text)

        # Roll combat
        win = random.random() < win_chance

        if win:
            _, xp_award, xp_effect_msgs = apply_active_effects_to_combat(player, base_win_chance, base_xp, is_win=True)
            quest_module.safe_privmsg(username, f"You defeat the {monster['name']}! (Win chance: {win_chance:.0%})")
            for msg_text in xp_effect_msgs:
                if msg_text:
                    quest_module.safe_privmsg(username, msg_text)

            player["last_fight"] = {
                "monster_name": monster["name"],
                "monster_level": monster_level,
                "win": True
            }

            if xp_award > 0:
                xp_messages = grant_xp(quest_module, user_id, username, xp_award, is_win=True)
                for xp_msg in xp_messages:
                    quest_module.safe_privmsg(username, xp_msg)

            momentum += 1
            active_run["momentum"] = momentum
            active_run["rooms_cleared"] = index
            consume_combat_effects(player, True)

            # Check for safe haven
            if index in DUNGEON_SAFE_HAVENS:
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

            quest_module.safe_reply(connection, event,
                            f"{username} was defeated in room {index} ({room['name']}) {penalty_msg}.")
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

    player["inventory"][DUNGEON_REWARD_KEY] = player["inventory"].get(DUNGEON_REWARD_KEY, 0) + DUNGEON_REWARD_CHARGES
    player["last_fight"] = {
        "monster_name": DUNGEON_ROOMS[-1]["monster"]["name"],
        "monster_level": player.get("level", 1) + DUNGEON_ROOMS[-1]["monster"].get("level_offset", 0),
        "win": True
    }

    quest_module.safe_privmsg(username, f"You conquer the Heart of the Abyss! A {DUNGEON_REWARD_NAME} materializes in your hands.")
    quest_module.safe_privmsg(username, DUNGEON_REWARD_EFFECT_TEXT)

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    quest_module.safe_reply(connection, event,
                        f"{username} cleared all {TOTAL_DUNGEON_ROOMS} rooms and claimed a {DUNGEON_REWARD_NAME}! {DUNGEON_REWARD_EFFECT_TEXT}")
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
        quest_module.safe_reply(connection, event, "You don't have an active dungeon run. Use !equip then !dungeon to start.")
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
    reward_msg = quest_utils.grant_dungeon_quit_reward(quest_module, user_id, username, rooms_cleared)

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
    quest_module.safe_reply(connection, event, f"{username} retreats from the dungeon. {reward_msg}")

    return True
