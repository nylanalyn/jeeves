# modules/quest/quest_core.py
# Core quest mechanics: solo quests, search system, item usage, medic quests, abilities

import random
import time
import json
import os
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

from .constants import (
    UTC, DUNGEON_REWARD_KEY, DUNGEON_REWARD_NAME, DUNGEON_REWARD_CHARGES
)
from . import quest_utils
from . import quest_progression
from . import quest_combat


def load_content(quest_module) -> Dict[str, Any]:
    """Load quest content from JSON file."""
    content_file = "quest_content.json"
    try:
        with open(content_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        quest_module.log_debug(f"Quest content file not found: {content_file}")
        return {}
    except json.JSONDecodeError as e:
        quest_module.log_debug(f"Error parsing quest content: {e}")
        return {}


def load_challenge_paths(quest_module) -> Dict[str, Any]:
    """Load challenge paths configuration."""
    paths_file = "challenge_paths.json"
    try:
        with open(paths_file, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"paths": {}, "abilities": {}, "active_path": None}
    except json.JSONDecodeError as e:
        quest_module.log_debug(f"Error parsing challenge paths: {e}")
        return {"paths": {}, "abilities": {}, "active_path": None}


def save_challenge_paths(quest_module):
    """Save challenge paths configuration."""
    paths_file = "challenge_paths.json"
    try:
        with open(paths_file, "w") as f:
            json.dump(quest_module.challenge_paths, f, indent=2)
    except Exception as e:
        quest_module.log_debug(f"Error saving challenge paths: {e}")


def get_content(quest_module, key: str, channel: str = None, default: Any = None) -> Any:
    """Get content from loaded quest content."""
    return quest_module.quest_content.get(key, default)


def handle_solo_quest(quest_module, connection, event, username, difficulty):
    """Handle solo quest encounters."""
    cooldown = quest_module.get_config_value("cooldown_seconds", event.target, default=300)
    if not quest_module.check_user_cooldown(username, "quest_solo", cooldown):
        quest_module.safe_reply(connection, event, f"You are still recovering, {quest_module.bot.title_for(username)}.")
        return True

    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)

    player, recovery_msg = quest_utils.check_and_clear_injury(player)
    if recovery_msg:
        quest_module.safe_reply(connection, event, recovery_msg)

    energy_enabled = quest_module.get_config_value("energy_system.enabled", event.target, default=True)
    if energy_enabled and player["energy"] < 1:
        quest_module.safe_reply(connection, event, f"You are too exhausted for a quest, {quest_module.bot.title_for(username)}. You must rest.")
        return True

    difficulty_mods = quest_module.get_config_value("difficulty", event.target, default={})
    diff_mod = difficulty_mods.get(difficulty, {"level_mod": 1, "xp_mult": 1.0})
    player_level = player['level']

    monster_spawn_chance = quest_module.get_config_value("monster_spawn_chance", event.target, default=0.8)
    monsters = quest_module._get_content("monsters", event.target, default=[])
    story_beats = quest_module._get_content("story_beats", event.target, default={})

    if random.random() > monster_spawn_chance:
        quest_module.safe_reply(connection, event, "The lands are quiet. You gain 10 XP for your diligence.")
        for m in quest_progression.grant_xp(quest_module, user_id, username, 10):
            quest_module.safe_reply(connection, event, m)
        return True

    # Check for boss encounter (levels 17-20, 10% chance)
    boss_encounter_chance = quest_module.get_config_value("boss_encounter_chance", event.target, default=0.10)
    boss_min_level = quest_module.get_config_value("boss_encounter_min_level", event.target, default=17)
    boss_max_level = quest_module.get_config_value("boss_encounter_max_level", event.target, default=20)

    if boss_min_level <= player_level <= boss_max_level and random.random() < boss_encounter_chance:
        return quest_combat.trigger_boss_encounter(quest_module, connection, event, username, user_id, player, energy_enabled)

    if energy_enabled:
        player["energy"] -= 1

    target_monster_level = player_level + diff_mod["level_mod"]
    possible_monsters = [m for m in monsters if isinstance(m, dict) and m['min_level'] <= target_monster_level <= m['max_level']]
    if not possible_monsters:
        quest_module.safe_reply(connection, event, "The lands are eerily quiet... no suitable monsters could be found.")
        if energy_enabled:
            player["energy"] += 1
        return True

    monster = random.choice(possible_monsters)
    monster_level = max(1, random.randint(min(player_level - 1, player_level + diff_mod["level_mod"]), max(player_level - 1, player_level + diff_mod["level_mod"])))

    # Check for rare spawn
    rare_spawn_chance = quest_module.get_config_value("rare_spawn_chance", event.target, default=0.10)
    is_rare = random.random() < rare_spawn_chance
    rare_xp_mult = quest_module.get_config_value("rare_spawn_xp_multiplier", event.target, default=2.0)

    monster_prefix = "[RARE] " if is_rare else ""
    monster_name_with_level = f"{monster_prefix}Level {monster_level} {monster['name']}"
    action_text = quest_utils.get_action_text(quest_module, user_id)

    story = f"{random.choice(story_beats.get('openers',[]))} {action_text}".format(user=username, monster=monster_name_with_level)
    quest_module.safe_reply(connection, event, story)

    if is_rare:
        quest_module.safe_say(f"A rare {monster['name']} has appeared! {username} engages in combat!", event.target)
    time.sleep(1.5)

    energy_xp_mult, energy_win_chance_mod = 1.0, 0.0
    applied_penalty_msgs = []
    if energy_enabled:
        energy_penalties = quest_module.get_config_value("energy_system.penalties", event.target, default=[])
        # Check all penalties and apply the most severe (lowest threshold) that matches
        for penalty in sorted(energy_penalties, key=lambda x: x['threshold'], reverse=True):
            if player["energy"] <= penalty["threshold"]:
                energy_xp_mult = penalty.get("xp_multiplier", 1.0)
                energy_win_chance_mod = penalty.get("win_chance_modifier", 0.0)
                # Don't break - let lower thresholds override

        # Generate message after finding final penalty values
        if energy_xp_mult < 1.0:
            applied_penalty_msgs.append("you will gain less experience")
        if energy_win_chance_mod < 0.0:
            applied_penalty_msgs.append("you are less effective in battle")

        if applied_penalty_msgs:
            quest_module.safe_reply(connection, event, f"You feel fatigued... ({' and '.join(applied_penalty_msgs)}).")

    base_win_chance = quest_utils.calculate_win_chance(player_level, monster_level, energy_win_chance_mod, prestige_level=player.get("prestige", 0))

    # Calculate base XP
    xp_level_mult = quest_module.get_config_value("xp_level_multiplier", event.target, default=2)
    base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))
    total_xp = (base_xp + player_level * xp_level_mult) * diff_mod["xp_mult"] * energy_xp_mult

    # Apply rare spawn multiplier
    if is_rare:
        total_xp *= rare_xp_mult

    # Apply active effects (lucky charm, xp scroll) - pass placeholder for is_win
    win_chance_modified, xp_modified, effect_msgs = quest_combat.apply_active_effects_to_combat(player, base_win_chance, total_xp, is_win=False)

    # Show effect messages before combat
    for msg in effect_msgs:
        if "lucky charm" in msg.lower():  # Only show lucky charm pre-combat
            quest_module.safe_reply(connection, event, msg)

    # Determine combat result
    win = random.random() < win_chance_modified
    player['last_fight'] = {"monster_name": monster['name'], "monster_level": monster_level, "win": win}

    # Re-apply effects now that we know the outcome (for XP scroll)
    _, total_xp, xp_effect_msgs = quest_combat.apply_active_effects_to_combat(player, base_win_chance, total_xp, is_win=win)

    # Check for critical hit
    crit_chance = quest_module.get_config_value("crit_chance", event.target, default=0.15)
    is_crit = win and random.random() < crit_chance

    if win:
        quest_module.safe_reply(connection, event, f"Victory! (Win chance: {win_chance_modified:.0%}) The {monster_name_with_level} is defeated! You gain {int(total_xp)} XP.")
        # Show XP scroll message if it activated
        for msg in xp_effect_msgs:
            if "scroll" in msg.lower():
                quest_module.safe_reply(connection, event, msg)
        for m in quest_progression.grant_xp(quest_module, user_id, username, total_xp, is_win=True, is_crit=is_crit):
            quest_module.safe_reply(connection, event, m)
    else:
        xp_loss_perc = quest_module.get_config_value("xp_loss_percentage", event.target, default=0.25)
        xp_loss = total_xp * xp_loss_perc
        quest_module.safe_reply(connection, event, f"Defeat! (Win chance: {win_chance_modified:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
        quest_progression.deduct_xp(quest_module, user_id, username, xp_loss)

        # Apply injury with armor reduction
        injury_reduction = quest_combat.get_injury_reduction(player)
        injury_msg = quest_utils.apply_injury(quest_module, user_id, username, event.target, injury_reduction=injury_reduction)
        if injury_msg:
            quest_module.safe_reply(connection, event, injury_msg)

    # Consume active effects after combat
    quest_combat.consume_combat_effects(player, is_win=win)

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()
    return True


def perform_single_search(quest_module, player: Dict[str, Any], event) -> Dict[str, Any]:
    """
    Perform a single search and return the result.
    Returns: {"type": str, "item": str, "message": str, "xp_change": int}
    """
    roll = random.random()
    result = {"type": "nothing", "item": None, "message": "", "xp_change": 0}

    # Get search probabilities from config
    medkit_chance = quest_module.get_config_value("search_system.medkit_chance", event.target, default=0.25)
    energy_potion_chance = quest_module.get_config_value("search_system.energy_potion_chance", event.target, default=0.15)
    lucky_charm_chance = quest_module.get_config_value("search_system.lucky_charm_chance", event.target, default=0.15)
    armor_shard_chance = quest_module.get_config_value("search_system.armor_shard_chance", event.target, default=0.10)
    xp_scroll_chance = quest_module.get_config_value("search_system.xp_scroll_chance", event.target, default=0.10)
    injury_chance = quest_module.get_config_value("search_system.injury_chance", event.target, default=0.05)

    cumulative = 0.0

    # Medkit
    cumulative += medkit_chance
    if roll < cumulative:
        player["inventory"]["medkits"] += 1
        result = {"type": "item", "item": "medkit", "message": "a MEDKIT", "xp_change": 0}
        return result

    # Energy Potion
    cumulative += energy_potion_chance
    if roll < cumulative:
        player["inventory"]["energy_potions"] += 1
        result = {"type": "item", "item": "energy_potion", "message": "an ENERGY POTION", "xp_change": 0}
        return result

    # Lucky Charm
    cumulative += lucky_charm_chance
    if roll < cumulative:
        player["inventory"]["lucky_charms"] += 1
        result = {"type": "item", "item": "lucky_charm", "message": "a LUCKY CHARM", "xp_change": 0}
        return result

    # Armor Shard
    cumulative += armor_shard_chance
    if roll < cumulative:
        player["inventory"]["armor_shards"] += 1
        result = {"type": "item", "item": "armor_shard", "message": "an ARMOR SHARD", "xp_change": 0}
        return result

    # XP Scroll
    cumulative += xp_scroll_chance
    if roll < cumulative:
        player["inventory"]["xp_scrolls"] += 1
        result = {"type": "item", "item": "xp_scroll", "message": "an XP SCROLL", "xp_change": 0}
        return result

    # Minor Injury
    cumulative += injury_chance
    if roll < cumulative:
        # Lose 1 energy and small XP
        player["energy"] = max(0, player["energy"] - 1)
        xp_loss = random.randint(5, 15)
        result = {"type": "injury", "item": None, "message": "INJURED! Lost 1 energy", "xp_change": -xp_loss}
        return result

    # Nothing found
    result = {"type": "nothing", "item": None, "message": "nothing", "xp_change": 0}
    return result


def handle_search(quest_module, connection, event, username, args):
    """Handle search command - search for items using energy."""
    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)

    # Check if search is enabled
    if not quest_module.get_config_value("search_system.enabled", event.target, default=True):
        quest_module.safe_reply(connection, event, "Searching is not available at this time.")
        return True

    # Parse number of searches
    num_searches = 1
    if args:
        try:
            num_searches = int(args[0])
            if num_searches < 1:
                quest_module.safe_reply(connection, event, "You must search at least once!")
                return True
            if num_searches > 20:
                quest_module.safe_reply(connection, event, "You can search at most 20 times at once!")
                return True
        except ValueError:
            quest_module.safe_reply(connection, event, "Please provide a valid number of searches (e.g., !quest search 5)")
            return True

    # Check energy
    energy_cost_per_search = quest_module.get_config_value("search_system.energy_cost", event.target, default=1)
    total_energy_cost = energy_cost_per_search * num_searches

    if player["energy"] < total_energy_cost:
        quest_module.safe_reply(connection, event, f"You need {total_energy_cost} energy to search {num_searches} time(s). You have {player['energy']}.")
        return True

    # Check and clear expired injury
    player, recovery_msg = quest_utils.check_and_clear_injury(player)
    if recovery_msg:
        quest_module.safe_reply(connection, event, recovery_msg)

    # Migrate old injury format
    if 'active_injury' in player:
        player['active_injuries'] = [player['active_injury']]
        del player['active_injury']

    # Check if player is injured
    if 'active_injuries' in player and player['active_injuries']:
        injury_names = [inj['name'] for inj in player['active_injuries']]
        if len(injury_names) == 1:
            quest_module.safe_reply(connection, event, f"You are still recovering from your {injury_names[0]}. Rest or use a medkit to heal.")
        else:
            quest_module.safe_reply(connection, event, f"You are still recovering from: {', '.join(injury_names)}. Rest or use a medkit to heal.")
        players_state = quest_module.get_state("players", {})
        players_state[user_id] = player
        quest_module.set_state("players", players_state)
        quest_module.save_state()
        return True

    # Deduct energy upfront
    player["energy"] -= total_energy_cost

    # Perform searches
    results = []
    total_xp_change = 0
    for _ in range(num_searches):
        search_result = perform_single_search(quest_module, player, event)
        results.append(search_result)
        total_xp_change += search_result["xp_change"]

    # Apply XP change if any
    if total_xp_change < 0:
        quest_progression.deduct_xp(quest_module, user_id, username, abs(total_xp_change))

    # Save player state
    players_state = quest_module.get_state("players", {})
    players_state[user_id] = player
    quest_module.set_state("players", players_state)
    quest_module.save_state()

    # Build result message
    if num_searches == 1:
        result = results[0]
        msg = f"You search the area and find {result['message']}!"
        if result["xp_change"] < 0:
            msg += f" (Lost {abs(result['xp_change'])} XP)"
        quest_module.safe_reply(connection, event, msg)
    else:
        # Summarize multiple searches
        item_counts = {
            "medkit": 0,
            "energy_potion": 0,
            "lucky_charm": 0,
            "armor_shard": 0,
            "xp_scroll": 0,
            "nothing": 0,
            "injury": 0
        }

        for result in results:
            if result["type"] == "item":
                item_counts[result["item"]] += 1
            elif result["type"] == "nothing":
                item_counts["nothing"] += 1
            elif result["type"] == "injury":
                item_counts["injury"] += 1

        # Build summary
        found_items = []
        if item_counts["medkit"] > 0:
            found_items.append(f"{item_counts['medkit']} medkit(s)")
        if item_counts["energy_potion"] > 0:
            found_items.append(f"{item_counts['energy_potion']} energy potion(s)")
        if item_counts["lucky_charm"] > 0:
            found_items.append(f"{item_counts['lucky_charm']} lucky charm(s)")
        if item_counts["armor_shard"] > 0:
            found_items.append(f"{item_counts['armor_shard']} armor shard(s)")
        if item_counts["xp_scroll"] > 0:
            found_items.append(f"{item_counts['xp_scroll']} XP scroll(s)")

        msg = f"After {num_searches} searches, you found: "
        if found_items:
            msg += ", ".join(found_items)
        else:
            msg += "nothing of value"

        if item_counts["nothing"] > 0:
            msg += f" ({item_counts['nothing']} empty search(es))"
        if item_counts["injury"] > 0:
            msg += f" (Injured {item_counts['injury']} time(s), lost {abs(total_xp_change)} XP)"

        quest_module.safe_reply(connection, event, msg)

    return True


def handle_use_item(quest_module, connection, event, username, args):
    """Handle using items from inventory (simplified for now - full implementation in main module)."""
    if not args:
        quest_module.safe_reply(connection, event, "Usage: !quest use <item> - Available items: medkit, energy_potion, lucky_charm, armor_shard, xp_scroll, dungeon_relic")
        return True

    # This is a placeholder - the full implementation is in the original quest.py
    # We'll need to keep this in the main __init__.py file due to its complexity
    quest_module.safe_reply(connection, event, "Item usage functionality is being refactored. Please use the main quest module.")
    return True


def handle_medic_quest(quest_module, connection, event, username):
    """Handle medic quest - heal injuries (simplified for now)."""
    # This is a placeholder - the full implementation is in the original quest.py
    # We'll need to keep this in the main __init__.py file due to its complexity
    quest_module.safe_reply(connection, event, "Medic quest functionality is being refactored. Please use the main quest module.")
    return True


def use_ability(quest_module, connection, event, username, user_id, player, ability_name):
    """Use an unlocked ability (simplified for now)."""
    # This is a placeholder - the full implementation is in the original quest.py
    # We'll need to keep this in the main __init__.py file due to its complexity
    quest_module.safe_reply(connection, event, "Ability system is being refactored. Please use the main quest module.")
    return True
