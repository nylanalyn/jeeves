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
from . import quest_boss_hunt


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

    # Check if the big bad boss has returned and notify user
    quest_boss_hunt.check_and_notify_boss_return(quest_module, connection, event, username, event.target)

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

    # Apply boss hunt buff to reduce monster level if active
    boss_hunt_level_mod, _, boss_buff_msg = quest_boss_hunt.apply_boss_hunt_buff_to_combat(
        quest_module, target_monster_level, 0, event.target
    )
    target_monster_level = boss_hunt_level_mod

    possible_monsters = [m for m in monsters if isinstance(m, dict) and m['min_level'] <= target_monster_level <= m['max_level']]
    if not possible_monsters:
        quest_module.safe_reply(connection, event, "The lands are eerily quiet... no suitable monsters could be found.")
        if energy_enabled:
            player["energy"] += 1
        return True

    monster = random.choice(possible_monsters)
    monster_level = max(1, random.randint(min(player_level - 1, target_monster_level), max(player_level - 1, target_monster_level)))

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

    # Apply boss hunt buff to XP if active
    _, buffed_xp, _ = quest_boss_hunt.apply_boss_hunt_buff_to_combat(
        quest_module, 0, total_xp, event.target
    )
    total_xp = buffed_xp

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
        # Show buff message if active (before victory message)
        if boss_buff_msg:
            quest_module.safe_reply(connection, event, boss_buff_msg)

        quest_module.safe_reply(connection, event, f"Victory! (Win chance: {win_chance_modified:.0%}) The {monster_name_with_level} is defeated! You gain {int(total_xp)} XP.")
        # Show XP scroll message if it activated
        for msg in xp_effect_msgs:
            if "scroll" in msg.lower():
                quest_module.safe_reply(connection, event, msg)
        for m in quest_progression.grant_xp(quest_module, user_id, username, total_xp, is_win=True, is_crit=is_crit):
            quest_module.safe_reply(connection, event, m)

        # Try to drop an item from combat
        item_drop_msg = try_drop_item_from_combat(quest_module, player, event, is_win=True, is_crit=is_crit)
        if item_drop_msg:
            quest_module.safe_reply(connection, event, item_drop_msg)

        # Try to drop a clue for boss hunt
        quest_boss_hunt.try_drop_clue(quest_module, connection, event, username, event.target)

        # Try to show haunting message on win
        quest_boss_hunt.try_show_haunting_message(quest_module, connection, event, username, event.target, "win")
    else:
        xp_loss_perc = quest_module.get_config_value("xp_loss_percentage", event.target, default=0.25)
        xp_loss = total_xp * xp_loss_perc
        quest_module.safe_reply(connection, event, f"Defeat! (Win chance: {win_chance_modified:.0%}) You have been bested! You lose {int(xp_loss)} XP.")
        quest_progression.deduct_xp(quest_module, user_id, username, xp_loss)

        # Try to drop a medkit on loss
        item_drop_msg = try_drop_item_from_combat(quest_module, player, event, is_win=False, is_crit=False)
        if item_drop_msg:
            quest_module.safe_reply(connection, event, item_drop_msg)

        # Apply injury with armor reduction
        injury_reduction = quest_combat.get_injury_reduction(player)
        injury_msg = quest_utils.apply_injury(quest_module, user_id, username, event.target, injury_reduction=injury_reduction)
        if injury_msg:
            quest_module.safe_reply(connection, event, injury_msg)
            # Try to show haunting message on injury
            quest_boss_hunt.try_show_haunting_message(quest_module, connection, event, username, event.target, "injury")

    # Consume active effects after combat
    quest_combat.consume_combat_effects(player, is_win=win)

    players = quest_module.get_state("players")
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()
    return True


def try_drop_item_from_combat(quest_module, player: Dict[str, Any], event, is_win: bool, is_crit: bool) -> Optional[str]:
    """
    Try to drop items from combat. Can drop multiple items!

    Args:
        quest_module: The quest module instance
        player: Player data dict
        event: IRC event
        is_win: True if player won the fight
        is_crit: True if it was a critical hit

    Returns:
        Item drop message or None if no drops
    """
    dropped_items = []

    if is_win:
        # Win drops: medkit, lucky charm, armor shard, XP scroll, energy potion
        # Try for each item type independently - can get multiple!
        base_drop_chance = quest_module.get_config_value("combat_drops.win_drop_chance", event.target, default=0.35)
        crit_bonus = quest_module.get_config_value("combat_drops.crit_drop_bonus", event.target, default=0.20)
        drop_chance = base_drop_chance + (crit_bonus if is_crit else 0.0)

        # Each item type has its own roll
        item_chances = {
            "medkit": quest_module.get_config_value("combat_drops.medkit_chance", event.target, default=0.25),
            "energy_potion": quest_module.get_config_value("combat_drops.energy_potion_chance", event.target, default=0.30),
            "lucky_charm": quest_module.get_config_value("combat_drops.lucky_charm_chance", event.target, default=0.20),
            "armor_shard": quest_module.get_config_value("combat_drops.armor_shard_chance", event.target, default=0.20),
            "xp_scroll": quest_module.get_config_value("combat_drops.xp_scroll_chance", event.target, default=0.20)
        }

        # Try for each item type
        for item_type, item_chance in item_chances.items():
            if random.random() < (drop_chance * item_chance):
                if item_type == "medkit":
                    player["inventory"]["medkits"] = player["inventory"].get("medkits", 0) + 1
                    dropped_items.append("⚕️ MEDKIT")
                elif item_type == "energy_potion":
                    player["inventory"]["energy_potions"] = player["inventory"].get("energy_potions", 0) + 1
                    dropped_items.append("💎 ENERGY POTION")
                elif item_type == "lucky_charm":
                    player["inventory"]["lucky_charms"] = player["inventory"].get("lucky_charms", 0) + 1
                    dropped_items.append("🍀 LUCKY CHARM")
                elif item_type == "armor_shard":
                    player["inventory"]["armor_shards"] = player["inventory"].get("armor_shards", 0) + 1
                    dropped_items.append("🛡️ ARMOR SHARD")
                elif item_type == "xp_scroll":
                    player["inventory"]["xp_scrolls"] = player["inventory"].get("xp_scrolls", 0) + 1
                    dropped_items.append("📜 XP SCROLL")

    else:
        # Loss drops: medkits and energy potions
        medkit_chance = quest_module.get_config_value("combat_drops.loss_medkit_chance", event.target, default=0.30)
        potion_chance = quest_module.get_config_value("combat_drops.loss_potion_chance", event.target, default=0.20)

        if random.random() < medkit_chance:
            player["inventory"]["medkits"] = player["inventory"].get("medkits", 0) + 1
            dropped_items.append("⚕️ MEDKIT")

        if random.random() < potion_chance:
            player["inventory"]["energy_potions"] = player["inventory"].get("energy_potions", 0) + 1
            dropped_items.append("💎 ENERGY POTION")

    # Build message
    if not dropped_items:
        return None

    if len(dropped_items) == 1:
        return f"You found {dropped_items[0]}!"
    else:
        return f"You found multiple items: {', '.join(dropped_items)}!"


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
    # Search has been retired in favor of combat drops
    quest_module.safe_reply(connection, event, "Search has been retired! Items now drop from combat. Win fights for supplies, lose fights for medkits. Critical hits increase drop chances!")
    return True

def handle_search_old(quest_module, connection, event, username, args):
    """OLD: Handle search command - search for items using energy."""
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
    """Handle using items from inventory."""
    if not args:
        quest_module.safe_reply(connection, event, "Usage: !quest use <item> - Available items: medkit, energy_potion, lucky_charm, armor_shard, xp_scroll, dungeon_relic")
        return True

    item_name = args[0].lower()
    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)
    inventory = player.get("inventory", {})

    # Map user-friendly names to inventory keys
    item_map = {
        "medkit": "medkits",
        "energy_potion": "energy_potions",
        "potion": "energy_potions",
        "lucky_charm": "lucky_charms",
        "charm": "lucky_charms",
        "armor_shard": "armor_shards",
        "armor": "armor_shards",
        "xp_scroll": "xp_scrolls",
        "scroll": "xp_scrolls",
        "dungeon_relic": DUNGEON_REWARD_KEY,
        "relic": DUNGEON_REWARD_KEY
    }

    if item_name not in item_map:
        quest_module.safe_reply(connection, event, f"Unknown item: {item_name}. Available: medkit, energy_potion, lucky_charm, armor_shard, xp_scroll, dungeon_relic")
        return True

    inventory_key = item_map[item_name]
    if inventory.get(inventory_key, 0) < 1:
        quest_module.safe_reply(connection, event, f"You don't have any {item_name.replace('_', ' ')}s!")
        return True

    # Ensure active effects list exists for legacy players
    player.setdefault("active_effects", [])

    if inventory_key == "medkits":
        # Medkit heals the oldest injury first
        if "active_injury" in player:
            player["active_injuries"] = [player["active_injury"]]
            del player["active_injury"]

        injuries = player.get("active_injuries", [])
        if not injuries:
            quest_module.safe_reply(connection, event, "You are not injured! Save your medkit for when you need it.")
            return True

        player["inventory"]["medkits"] -= 1
        injury_healed = injuries.pop(0)
        quest_module.safe_reply(
            connection,
            event,
            f"You use a medkit to heal your {injury_healed['name']}. You feel much better! ({player['inventory']['medkits']} medkits remaining)"
        )

    elif inventory_key == "energy_potions":
        max_energy = quest_progression.get_player_max_energy(quest_module, player, event.target)
        if player.get("energy", 0) >= max_energy:
            quest_module.safe_reply(connection, event, "Your energy is already full! Save the potion for later.")
            return True

        energy_restore = random.randint(2, 4)
        player["inventory"]["energy_potions"] -= 1
        old_energy = player.get("energy", 0)
        player["energy"] = min(max_energy, old_energy + energy_restore)
        actual_restore = player["energy"] - old_energy
        quest_module.safe_reply(
            connection,
            event,
            f"You drink the energy potion and feel refreshed! +{actual_restore} energy ({player['energy']}/{max_energy}). ({player['inventory']['energy_potions']} potions remaining)"
        )

    elif inventory_key == "lucky_charms":
        # Lucky charm boosts next fight win chance
        if any(effect.get("type") == "lucky_charm" for effect in player["active_effects"]):
            quest_module.safe_reply(connection, event, "You already have a lucky charm active! The effects don't stack.")
            return True

        player["inventory"]["lucky_charms"] -= 1
        win_bonus = random.randint(10, 20)
        player["active_effects"].append({
            "type": "lucky_charm",
            "win_bonus": win_bonus,
            "expires": "next_fight"
        })
        quest_module.safe_reply(
            connection,
            event,
            f"You activate the lucky charm! Your next fight will have +{win_bonus}% win chance. ({player['inventory']['lucky_charms']} charms remaining)"
        )

    elif inventory_key == "armor_shards":
        # Armor shard reduces injury chance for the next three fights
        if any(effect.get("type") == "armor_shard" for effect in player["active_effects"]):
            quest_module.safe_reply(connection, event, "You already have armor protection active! The effects don't stack.")
            return True

        player["inventory"]["armor_shards"] -= 1
        player["active_effects"].append({
            "type": "armor_shard",
            "injury_reduction": 0.30,
            "remaining_fights": 3
        })
        quest_module.safe_reply(
            connection,
            event,
            f"You equip the armor shard! Injury chance reduced by 30% for the next 3 fights. ({player['inventory']['armor_shards']} shards remaining)"
        )

    elif inventory_key == "xp_scrolls":
        # XP scroll boosts XP on next victory
        if any(effect.get("type") == "xp_scroll" for effect in player["active_effects"]):
            quest_module.safe_reply(connection, event, "You already have an XP scroll active! The effects don't stack.")
            return True

        player["inventory"]["xp_scrolls"] -= 1
        player["active_effects"].append({
            "type": "xp_scroll",
            "xp_multiplier": 1.5,
            "expires": "next_win"
        })
        quest_module.safe_reply(
            connection,
            event,
            f"You read the XP scroll! Your next victory will grant 1.5x XP. ({player['inventory']['xp_scrolls']} scrolls remaining)"
        )

    elif inventory_key == DUNGEON_REWARD_KEY:
        # Mythic relic guarantees upcoming victories
        player["inventory"][DUNGEON_REWARD_KEY] -= 1
        existing = next((eff for eff in player["active_effects"] if eff.get("type") == "dungeon_relic"), None)
        if existing:
            existing["remaining_auto_wins"] = existing.get("remaining_auto_wins", 0) + DUNGEON_REWARD_CHARGES
            existing.pop("triggered_this_fight", None)
            total_charges = existing["remaining_auto_wins"]
            quest_module.safe_reply(
                connection,
                event,
                f"The {DUNGEON_REWARD_NAME} flares brighter! You now have {total_charges} guaranteed solo quest victories banked."
            )
        else:
            player["active_effects"].append({
                "type": "dungeon_relic",
                "remaining_auto_wins": DUNGEON_REWARD_CHARGES
            })
            quest_module.safe_reply(
                connection,
                event,
                f"The {DUNGEON_REWARD_NAME} hums with power. Your next {DUNGEON_REWARD_CHARGES} solo quests (including !dungeon rooms) are automatic victories."
            )

    # Persist player changes
    players_state = quest_module.get_state("players", {})
    players_state[user_id] = player
    quest_module.set_state("players", players_state)
    quest_module.save_state()
    return True


def handle_medic_quest(quest_module, connection, event, username):
    """Handle medic quest - heal injuries (simplified for now)."""
    # This is a placeholder - the full implementation is in the original quest.py
    # We'll need to keep this in the main __init__.py file due to its complexity
    quest_module.safe_reply(connection, event, "Medic quest functionality is being refactored. Please use the main quest module.")
    return True


def use_ability(quest_module, connection, event, username, user_id, player, ability_name):
    """Use an unlocked ability."""
    # Check if player has this ability unlocked
    unlocked = player.get("unlocked_abilities", [])
    abilities_data = quest_module.challenge_paths.get("abilities", {})

    # Find the ability by command name
    ability_id = None
    ability_data = None
    for aid, adata in abilities_data.items():
        if adata.get("command", "").lower() == ability_name:
            ability_id = aid
            ability_data = adata
            break

    if not ability_id or ability_id not in unlocked:
        quest_module.safe_reply(connection, event, f"You don't have the '{ability_name}' ability unlocked.")
        return True

    # Check cooldown
    cooldowns = player.get("ability_cooldowns", {})
    if ability_id in cooldowns:
        cooldown_expires = datetime.fromisoformat(cooldowns[ability_id])
        now = datetime.now(UTC)
        if now < cooldown_expires:
            time_left = quest_utils.format_timedelta(cooldown_expires)
            quest_module.safe_reply(connection, event, f"That ability is on cooldown for {time_left}.")
            return True

    # Execute the ability
    effect = ability_data.get("effect")
    success = _execute_ability_effect(quest_module, connection, event, username, user_id, effect, ability_data)

    if success:
        # Set cooldown
        cooldown_hours = ability_data.get("cooldown_hours", 24)
        cooldown_expires = datetime.now(UTC) + timedelta(hours=cooldown_hours)
        player["ability_cooldowns"][ability_id] = cooldown_expires.isoformat()

        # Save player state
        players = quest_module.get_state("players")
        players[user_id] = player
        quest_module.set_state("players", players)
        quest_module.save_state()

        # Announce to channel
        announcement = ability_data.get("announcement", "{user} uses {ability}!")
        announcement = announcement.format(user=quest_module.bot.title_for(username), ability=ability_data.get("name"))
        quest_module.safe_say(announcement, event.target)

    return True


def _execute_ability_effect(quest_module, connection, event, username, user_id, effect, ability_data):
    """Execute the actual effect of an ability."""
    if effect == "heal_all_injuries":
        # Heal all injuries for all players in channel
        players = quest_module.get_state("players", {})
        healed_count = 0

        for pid, pdata in players.items():
            if isinstance(pdata, dict):
                if pdata.get("active_injuries") and len(pdata.get("active_injuries", [])) > 0:
                    pdata["active_injuries"] = []
                    healed_count += 1
                    players[pid] = pdata

        quest_module.set_state("players", players)
        quest_module.save_state()

        if healed_count > 0:
            quest_module.safe_say(f"{healed_count} player(s) have been healed!", event.target)
        return True

    elif effect == "restore_party_energy":
        # Restore energy to all players
        players = quest_module.get_state("players", {})
        energy_amount = ability_data.get("effect_data", {}).get("energy_amount", 5)
        restored_count = 0

        for pid, pdata in players.items():
            if isinstance(pdata, dict):
                max_energy = quest_progression.get_player_max_energy(quest_module, pdata, event.target)
                old_energy = pdata.get("energy", 0)
                pdata["energy"] = min(max_energy, old_energy + energy_amount)
                if pdata["energy"] > old_energy:
                    restored_count += 1
                players[pid] = pdata

        quest_module.set_state("players", players)
        quest_module.save_state()

        if restored_count > 0:
            quest_module.safe_say(f"{restored_count} player(s) restored energy!", event.target)
        return True

    elif effect == "party_buff_win_chance":
        # Add a timed buff to all players
        # This would require more complex buff tracking - placeholder for now
        quest_module.safe_say("Party buff applied! (Full implementation pending)", event.target)
        return True

    # Unknown effect
    quest_module.safe_reply(connection, event, f"Unknown ability effect: {effect}")
    return False


def handle_medkit(quest_module, connection, event, username, target_arg):
    """Handle medkit usage - heal yourself or another player."""
    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)

    # Check if player has medkits
    medkit_count = player.get("inventory", {}).get("medkits", 0)
    if medkit_count < 1:
        quest_module.safe_reply(connection, event, f"You don't have any medkits, {quest_module.bot.title_for(username)}. Try !quest search to find one!")
        return True

    # Determine target
    if not target_arg:
        # Self-heal
        return _medkit_self_heal(quest_module, connection, event, username, user_id, player)
    else:
        # Heal another player
        return _medkit_heal_other(quest_module, connection, event, username, user_id, player, target_arg)


def _medkit_self_heal(quest_module, connection, event, username, user_id, player):
    """Use medkit on self."""
    # Migrate old format
    if 'active_injury' in player:
        player['active_injuries'] = [player['active_injury']]
        del player['active_injury']

    if 'active_injuries' not in player or not player['active_injuries']:
        quest_module.safe_reply(connection, event, f"You're not injured, {quest_module.bot.title_for(username)}!")
        return True

    injury_names = [inj['name'] for inj in player['active_injuries']]
    injury_count = len(injury_names)

    # Remove all injuries
    player['active_injuries'] = []

    # Deduct medkit
    player["inventory"]["medkits"] -= 1

    # Track medkit usage for challenge paths
    if "challenge_stats" not in player:
        player["challenge_stats"] = {}
    player["challenge_stats"]["medkits_used_this_prestige"] = player["challenge_stats"].get("medkits_used_this_prestige", 0) + 1

    # Grant partial XP
    base_xp = quest_module.get_config_value("base_xp_reward", event.target, default=50)
    self_heal_multiplier = quest_module.get_config_value("medic_quests.self_heal_xp_multiplier", event.target, default=0.75)
    xp_reward = int(base_xp * self_heal_multiplier)

    xp_messages = []
    for msg in quest_progression.grant_xp(quest_module, user_id, username, xp_reward, is_win=False, is_crit=False):
        xp_messages.append(msg)

    # Save state
    players_state = quest_module.get_state("players", {})
    players_state[user_id] = player
    quest_module.set_state("players", players_state)
    quest_module.save_state()

    if injury_count == 1:
        response = f"{quest_module.bot.title_for(username)} uses a medkit and recovers from {injury_names[0]}! (+{xp_reward} XP)"
    else:
        response = f"{quest_module.bot.title_for(username)} uses a medkit and recovers from all injuries ({', '.join(injury_names)})! (+{xp_reward} XP)"

    if xp_messages:
        response += " " + " ".join(xp_messages)

    quest_module.safe_reply(connection, event, response)
    return True


def _medkit_heal_other(quest_module, connection, event, username, user_id, player, target_nick):
    """Use medkit on another player."""
    target_id = quest_module.bot.get_user_id(target_nick)
    target_player = quest_progression.get_player(quest_module, target_id, target_nick)

    # Check if target is on a no-medkit challenge path
    target_challenge_path = target_player.get("challenge_path")
    if target_challenge_path:
        path_data = quest_module.challenge_paths.get("paths", {}).get(target_challenge_path, {})
        completion = path_data.get("completion_conditions", {})
        if completion.get("no_medkits_used"):
            path_name = path_data.get("name", target_challenge_path)
            quest_module.safe_reply(connection, event, f"{target_nick} is on the {path_name} challenge and cannot be healed with medkits!")
            return True

    # Migrate old format
    if 'active_injury' in target_player:
        target_player['active_injuries'] = [target_player['active_injury']]
        del target_player['active_injury']

    # Check if target is injured
    if 'active_injuries' not in target_player or not target_player['active_injuries']:
        quest_module.safe_reply(connection, event, f"{target_nick} is not injured!")
        return True

    injury_names = [inj['name'] for inj in target_player['active_injuries']]
    injury_count = len(injury_names)

    # Remove all target's injuries
    target_player['active_injuries'] = []

    # Deduct medkit from healer
    player["inventory"]["medkits"] -= 1

    # Track medkit usage for challenge paths
    if "challenge_stats" not in player:
        player["challenge_stats"] = {}
    player["challenge_stats"]["medkits_used_this_prestige"] = player["challenge_stats"].get("medkits_used_this_prestige", 0) + 1

    # Grant MASSIVE XP to healer
    base_xp = quest_module.get_config_value("base_xp_reward", event.target, default=50)
    altruistic_multiplier = quest_module.get_config_value("medic_quests.altruistic_heal_xp_multiplier", event.target, default=3.0)
    xp_reward = int(base_xp * altruistic_multiplier)

    xp_messages = []
    for msg in quest_progression.grant_xp(quest_module, user_id, username, xp_reward, is_win=True, is_crit=False):
        xp_messages.append(msg)

    # Save both players
    players_state = quest_module.get_state("players", {})
    players_state[user_id] = player
    players_state[target_id] = target_player
    quest_module.set_state("players", players_state)
    quest_module.save_state()

    if injury_count == 1:
        response = f"{quest_module.bot.title_for(username)} uses a medkit to heal {target_nick}'s {injury_names[0]}! Such selflessness is rewarded with +{xp_reward} XP!"
    else:
        response = f"{quest_module.bot.title_for(username)} uses a medkit to heal all of {target_nick}'s injuries ({', '.join(injury_names)})! Such selflessness is rewarded with +{xp_reward} XP!"

    if xp_messages:
        response += " " + " ".join(xp_messages)

    quest_module.safe_reply(connection, event, response)
    return True
