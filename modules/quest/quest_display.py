# modules/quest/quest_display.py
# Display and UI functions: profile, leaderboard, inventory, story

import random
from datetime import datetime
from typing import Dict, Any

from .constants import UTC, DUNGEON_REWARD_NAME, DUNGEON_REWARD_KEY
from . import quest_utils
from . import quest_progression


def handle_profile(quest_module, connection, event, username, args):
    """Display player profile with stats, inventory, and active effects."""
    target_user_nick = args[0] if args else username
    user_id = quest_module.bot.get_user_id(target_user_nick)
    player = quest_progression.get_player(quest_module, user_id, target_user_nick)

    player, recovery_msg = quest_utils.check_and_clear_injury(player)
    if recovery_msg:
        quest_module.safe_reply(connection, event, recovery_msg)
        players_state = quest_module.get_state("players")
        players_state[user_id] = player
        quest_module.set_state("players", players_state)
        quest_module.save_state()

    title = quest_module.bot.title_for(player["name"])
    player_class = quest_module.get_state("player_classes", {}).get(user_id, "None")
    prestige_level = player.get("prestige", 0)
    challenge_path = player.get("challenge_path")
    max_energy = quest_progression.get_player_max_energy(quest_module, player, event.target)
    transcendence_level = player.get("transcendence", 0)

    legend_suffix = ""
    if transcendence_level > 0:
        legend_suffix = " (Legend)" if transcendence_level == 1 else f" (Legend {quest_utils.to_roman(transcendence_level)})"

    # Build profile header with prestige and challenge path
    if prestige_level > 0:
        prestige_text = f"Prestige {prestige_level}"
        if challenge_path:
            path_data = quest_module.challenge_paths.get("paths", {}).get(challenge_path, {})
            path_name = path_data.get("name", challenge_path)
            prestige_text = f"{prestige_text} [{path_name}]"
        profile_parts = [f"Profile for {title}{legend_suffix}: Level {player['level']} ({prestige_text})"]
    else:
        profile_parts = [f"Profile for {title}{legend_suffix}: Level {player['level']}"]

    # Add XP (unless at level cap)
    level_cap = quest_module.get_config_value("level_cap", event.target, default=20)
    if player['level'] < level_cap:
        profile_parts.append(f"XP: {player['xp']}/{player['xp_to_next_level']}")
    else:
        profile_parts.append(f"XP: MAX (use !quest prestige to ascend)")

    profile_parts.append(f"Class: {player_class.capitalize()}")

    if quest_module.get_config_value("energy_system.enabled", event.target, default=True):
        profile_parts.append(f"Energy: {player['energy']}/{max_energy}")

    # Show medkit count
    medkit_count = player.get("medkits", 0)
    if medkit_count > 0:
        profile_parts.append(f"Medkits: {medkit_count}")
    relic_count = player.get("inventory", {}).get(DUNGEON_REWARD_KEY, 0)
    if relic_count > 0:
        profile_parts.append(f"{DUNGEON_REWARD_NAME}s: {relic_count}")
    if transcendence_level > 0:
        profile_parts.append(f"Transcendence: {'Legend' if transcendence_level == 1 else quest_utils.to_roman(transcendence_level)}")

    # Migrate old format
    if 'active_injury' in player:
        player['active_injuries'] = [player['active_injury']]
        del player['active_injury']

    if 'active_injuries' in player and player['active_injuries']:
        injury_strs = []
        for injury in player['active_injuries']:
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                time_left = quest_utils.format_timedelta(expires_at)
                injury_strs.append(f"{injury['name']} ({time_left})")
            except (ValueError, TypeError):
                injury_strs.append(injury['name'])

        if injury_strs:
            profile_parts.append(f"Status: Injured ({', '.join(injury_strs)})")

    quest_module.safe_reply(connection, event, " | ".join(profile_parts))

    # Show full inventory
    inventory = player.get("inventory", {})

    # Build inventory display
    items = []
    if inventory.get("medkits", 0) > 0:
        items.append(f"Medkits: {inventory['medkits']}")
    if inventory.get("energy_potions", 0) > 0:
        items.append(f"Energy Potions: {inventory['energy_potions']}")
    if inventory.get("lucky_charms", 0) > 0:
        items.append(f"Lucky Charms: {inventory['lucky_charms']}")
    if inventory.get("armor_shards", 0) > 0:
        items.append(f"Armor Shards: {inventory['armor_shards']}")
    if inventory.get("xp_scrolls", 0) > 0:
        items.append(f"XP Scrolls: {inventory['xp_scrolls']}")
    if inventory.get(DUNGEON_REWARD_KEY, 0) > 0:
        items.append(f"{DUNGEON_REWARD_NAME}s: {inventory[DUNGEON_REWARD_KEY]}")

    if not items:
        items_msg = "No items (try !quest search)"
    else:
        items_msg = ", ".join(items)

    # Active effects
    effects = []
    for effect in player.get("active_effects", []):
        if effect["type"] == "lucky_charm":
            effects.append(f"Lucky Charm (+{effect.get('win_bonus', 0)}% win)")
        elif effect["type"] == "armor_shard":
            effects.append(f"Armor ({effect.get('remaining_fights', 0)} fights)")
        elif effect["type"] == "xp_scroll":
            effects.append("XP Scroll (next win)")
        elif effect["type"] == "dungeon_relic":
            charges = effect.get("remaining_auto_wins", 0)
            suffix = "win" if charges == 1 else "wins"
            effects.append(f"{DUNGEON_REWARD_NAME} ({charges} guaranteed {suffix})")

    # Active injuries
    injuries = []
    if 'active_injuries' in player and player['active_injuries']:
        for injury in player['active_injuries']:
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                time_left = quest_utils.format_timedelta(expires_at)
                injuries.append(f"{injury['name']} ({time_left})")
            except (ValueError, TypeError):
                injuries.append(injury['name'])

    # Output inventory and status
    quest_module.safe_reply(connection, event, f"Inventory: {items_msg}")
    if effects:
        quest_module.safe_reply(connection, event, f"Active Effects: {', '.join(effects)}")
    if injuries:
        quest_module.safe_reply(connection, event, f"Injuries: {', '.join(injuries)}")
    elif not effects:
        quest_module.safe_reply(connection, event, "Status: Healthy")

    return True


def handle_story(quest_module, connection, event, username):
    """Display world lore and player's last fight."""
    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)
    world_lore = quest_module._get_content("world_lore", default=[])
    lore = random.choice(world_lore) if world_lore else "The world is vast."

    history = ""
    if (last_fight := player.get("last_fight")):
        outcome = "victorious against" if last_fight['win'] else "defeated by"
        history = f" You last remember being {outcome} a Level {last_fight['monster_level']} {last_fight['monster_name']}."

    quest_module.safe_reply(connection, event, f"{lore}{history}")
    return True


def handle_leaderboard(quest_module, connection, event):
    """Display top 10 players by prestige, level, and XP."""
    players = quest_module.get_state("players", {})

    if not players:
        quest_module.safe_reply(connection, event, "No players have embarked on quests yet.")
        return True

    # Sort by prestige (desc), then level (desc), then XP (desc)
    sorted_players = sorted(
        [(uid, p) for uid, p in players.items() if isinstance(p, dict)],
        key=lambda x: (x[1].get("prestige", 0), x[1].get("level", 1), x[1].get("xp", 0)),
        reverse=True
    )[:10]

    quest_module.safe_reply(connection, event, "Quest Leaderboard - Top 10 Adventurers:")
    for idx, (uid, player) in enumerate(sorted_players, 1):
        name = player.get("name", "Unknown")
        level = player.get("level", 1)
        xp = player.get("xp", 0)
        prestige = player.get("prestige", 0)
        transcendence = player.get("transcendence", 0)
        streak = player.get("win_streak", 0)

        # Build player line
        legend_suffix = ""
        if transcendence > 0:
            legend_suffix = " (Legend)" if transcendence == 1 else f" (Legend {quest_utils.to_roman(transcendence)})"

        if prestige > 0:
            prestige_str = f" [P{prestige}]"
        else:
            prestige_str = ""

        if streak > 0:
            streak_str = f" {streak}-win streak"
        else:
            streak_str = ""

        quest_module.safe_reply(connection, event, f"{idx}. {name}{legend_suffix}{prestige_str} - Lvl {level} ({xp} XP){streak_str}")

    return True


def cmd_inventory(quest_module, connection, event, msg, username, match):
    """Show player's inventory items and active effects."""
    if not quest_module.is_enabled(event.target):
        return False

    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)

    title = quest_module.bot.title_for(username)
    inventory = player.get("inventory", {})

    # Build inventory display
    items = []
    if inventory.get("medkits", 0) > 0:
        items.append(f"Medkits: {inventory['medkits']}")
    if inventory.get("energy_potions", 0) > 0:
        items.append(f"Energy Potions: {inventory['energy_potions']}")
    if inventory.get("lucky_charms", 0) > 0:
        items.append(f"Lucky Charms: {inventory['lucky_charms']}")
    if inventory.get("armor_shards", 0) > 0:
        items.append(f"Armor Shards: {inventory['armor_shards']}")
    if inventory.get("xp_scrolls", 0) > 0:
        items.append(f"XP Scrolls: {inventory['xp_scrolls']}")
    if inventory.get(DUNGEON_REWARD_KEY, 0) > 0:
        items.append(f"{DUNGEON_REWARD_NAME}s: {inventory[DUNGEON_REWARD_KEY]}")

    if not items:
        items_msg = "No items (try !quest search)"
    else:
        items_msg = ", ".join(items)

    # Active effects
    effects = []
    for effect in player.get("active_effects", []):
        if effect["type"] == "lucky_charm":
            effects.append(f"Lucky Charm (+{effect.get('win_bonus', 0)}% win)")
        elif effect["type"] == "armor_shard":
            effects.append(f"Armor ({effect.get('remaining_fights', 0)} fights)")
        elif effect["type"] == "xp_scroll":
            effects.append("XP Scroll (next win)")
        elif effect["type"] == "dungeon_relic":
            charges = effect.get("remaining_auto_wins", 0)
            suffix = "win" if charges == 1 else "wins"
            effects.append(f"{DUNGEON_REWARD_NAME} ({charges} guaranteed {suffix})")

    # Build final message
    quest_module.safe_reply(connection, event, f"{title}'s Inventory: {items_msg}")
    if effects:
        quest_module.safe_reply(connection, event, f"Active Effects: {', '.join(effects)}")

    return True


def cmd_ability(quest_module, connection, event, msg, username, match):
    """List or use unlocked abilities."""
    if not quest_module.is_enabled(event.target):
        return False

    user_id = quest_module.bot.get_user_id(username)
    player = quest_progression.get_player(quest_module, user_id, username)

    args_str = (match.group(1) or "").strip() if match and match.lastindex else ""

    # If no args, list abilities
    if not args_str:
        return list_abilities(quest_module, connection, event, username, player)

    # Otherwise, try to use an ability - import here to avoid circular dependency
    from .quest_core import use_ability
    ability_name = args_str.lower()
    return use_ability(quest_module, connection, event, username, user_id, player, ability_name)


def list_abilities(quest_module, connection, event, username, player):
    """List all unlocked abilities for a player."""
    unlocked = player.get("unlocked_abilities", [])

    if not unlocked:
        quest_module.safe_reply(connection, event, f"{username}, you haven't unlocked any abilities yet. Complete challenge paths to earn them!")
        return True

    quest_module.safe_reply(connection, event, f"{username}'s Unlocked Abilities:")

    abilities_data = quest_module.challenge_paths.get("abilities", {})
    for ability_id in unlocked:
        ability = abilities_data.get(ability_id, {})
        ability_name = ability.get("name", ability_id)
        description = ability.get("description", "No description")
        command = ability.get("command", ability_id)

        # Check cooldown
        cooldowns = player.get("ability_cooldowns", {})
        if ability_id in cooldowns:
            cooldown_expires = datetime.fromisoformat(cooldowns[ability_id])
            now = datetime.now(UTC)
            if now < cooldown_expires:
                time_left = quest_utils.format_timedelta(cooldown_expires)
                quest_module.safe_reply(connection, event, f"  !quest ability {command} - {description} [Cooldown: {time_left}]")
                continue

        quest_module.safe_reply(connection, event, f"  !quest ability {command} - {description} [READY]")

    return True
