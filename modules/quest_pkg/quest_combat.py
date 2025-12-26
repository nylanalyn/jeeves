# modules/quest/quest_combat.py
# Combat systems: mob encounters, boss fights, legend bosses, combat resolution

import random
import time
import schedule
import threading
from datetime import datetime
from typing import Dict, Any, List, Tuple

from .constants import UTC, DUNGEON_REWARD_NAME
from . import quest_utils
from . import quest_progression
from .. import achievement_hooks


def apply_active_effects_to_combat(player: Dict[str, Any], base_win_chance: float, base_xp: int, is_win: bool, quest_module=None, channel=None) -> Tuple[float, int, List[str]]:
    """
    Apply active effects to combat, return (modified_win_chance, modified_xp, messages).
    """
    messages = []
    win_chance = base_win_chance
    xp = base_xp

    # Party buffs (like Bloodlust) - check for active channel-wide buffs
    if quest_module and channel:
        party_buffs = quest_module.get_state("party_buffs", {})
        channel_buffs = party_buffs.get(channel, {})
        now = datetime.now(UTC)
        
        for buff_id, buff_data in list(channel_buffs.items()):
            # Check if buff is expired
            expires_at = datetime.fromisoformat(buff_data.get("expires_at", now.isoformat()))
            if now >= expires_at:
                # Remove expired buff
                del channel_buffs[buff_id]
                continue
            
            # Apply active buff
            if buff_data.get("type") == "win_chance_boost":
                bonus = buff_data.get("bonus", 0)
                win_chance += bonus
                ability_name = buff_data.get("ability", "Party Buff")
                bonus_pct = int(bonus * 100)
                messages.append(f"{ability_name} active! (+{bonus_pct}% win chance)")
        
        # Save cleaned buffs
        if channel_buffs != party_buffs.get(channel, {}):
            party_buffs[channel] = channel_buffs
            quest_module.set_state("party_buffs", party_buffs)

    # Mythic relic - guarantee victory for remaining solo fights
    for effect in player.get("active_effects", []):
        if effect.get("type") == "dungeon_relic" and effect.get("remaining_auto_wins", 0) > 0:
            win_chance = max(win_chance, 1.0)
            if not effect.get("triggered_this_fight"):
                effect["triggered_this_fight"] = True
                messages.append(f"The {DUNGEON_REWARD_NAME} blazes with power, guaranteeing victory!")
            break

    # Lucky charm - boost win chance
    for effect in player.get("active_effects", []):
        if effect["type"] == "lucky_charm" and effect.get("expires") == "next_fight":
            win_bonus = effect.get("win_bonus", 0) / 100.0
            win_chance += win_bonus
            messages.append(f"Your lucky charm glows! (+{effect.get('win_bonus', 0)}% win chance)")

    # XP scroll - boost XP on wins
    if is_win:
        for effect in player.get("active_effects", []):
            if effect["type"] == "xp_scroll" and effect.get("expires") == "next_win":
                xp_mult = effect.get("xp_multiplier", 1.0)
                xp = int(xp * xp_mult)
                messages.append(f"The XP scroll activates! ({xp_mult}x XP)")

    return (win_chance, xp, messages)


def consume_combat_effects(player: Dict[str, Any], is_win: bool):
    """Remove expired combat effects after a fight."""
    effects_to_remove = []

    for i, effect in enumerate(player.get("active_effects", [])):
        # Remove effects that expire on any fight
        if effect.get("expires") == "next_fight":
            effects_to_remove.append(i)
        # Remove effects that expire on win
        elif is_win and effect.get("expires") == "next_win":
            effects_to_remove.append(i)
        # Decrement fight-based effects
        elif effect["type"] == "armor_shard" and "remaining_fights" in effect:
            effect["remaining_fights"] -= 1
            if effect["remaining_fights"] <= 0:
                effects_to_remove.append(i)
        elif effect["type"] == "dungeon_relic":
            if effect.get("triggered_this_fight"):
                effect["remaining_auto_wins"] = max(0, effect.get("remaining_auto_wins", 0) - 1)
            effect.pop("triggered_this_fight", None)
            if effect.get("remaining_auto_wins", 0) <= 0 and effect.get("boss_auto_wins", 0) <= 0:
                effects_to_remove.append(i)

    # Remove in reverse order to avoid index issues
    for i in sorted(effects_to_remove, reverse=True):
        player["active_effects"].pop(i)


def get_injury_reduction(player: Dict[str, Any]) -> float:
    """Get total injury chance reduction from active effects."""
    reduction = 0.0
    for effect in player.get("active_effects", []):
        if effect["type"] == "armor_shard":
            reduction += effect.get("injury_reduction", 0.0)
    return min(reduction, 0.90)  # Cap at 90% reduction


def trigger_boss_encounter(quest_module, connection, event, username, user_id, player, energy_enabled):
    """Trigger a random boss encounter that acts like a mob fight."""
    # Check if there's already an active mob
    with quest_module.mob_lock:
        active_mob = quest_module.get_state("active_mob")
        if active_mob:
            # If there's already a mob, just do a normal quest instead
            quest_module.log_debug("Boss encounter skipped - active mob already exists")
            return False  # Fall through to normal quest logic

        # Select a boss monster
        boss_monsters = quest_module._get_content("boss_monsters", event.target, default=[])
        suitable_bosses = [b for b in boss_monsters if isinstance(b, dict) and b.get("min_level", 1) <= player["level"]]

        if not suitable_bosses:
            # No suitable boss, fall through to normal quest
            quest_module.log_debug("No suitable boss monsters found")
            return False

        boss = random.choice(suitable_bosses)
        boss_level = max(player["level"], player["level"] + 3)  # Boss is at least 3 levels higher

        # Deduct energy from initiator
        if energy_enabled and player["energy"] > 0:
            player["energy"] -= 1

        # Create the boss encounter (similar to mob)
        # Use longer timer for random boss encounters to give more time for people to join
        join_window_seconds = quest_module.get_config_value("boss_join_window_seconds", event.target, default=300)
        close_time = time.time() + join_window_seconds

        mob_data = {
            "channel": event.target,
            "monster": boss,
            "monster_level": boss_level,
            "is_rare": False,
            "is_boss": True,  # Mark this as a boss encounter
            "participants": [{"user_id": user_id, "username": username}],
            "initiator": username,
            "close_epoch": close_time
        }

        quest_module.set_state("active_mob", mob_data)

        # Save player state
        players_state = quest_module.get_state("players", {})
        players_state[user_id] = player
        quest_module.set_state("players", players_state)
        quest_module.save_state()

        # Schedule mob window close
        schedule.every(join_window_seconds).seconds.do(quest_module._close_mob_window).tag(f"{quest_module.name}-mob_close")

        # Announce the boss encounter!
        join_minutes = join_window_seconds // 60
        quest_module.safe_say(f"\u26a0\ufe0f BOSS ENCOUNTER! \u26a0\ufe0f", event.target)
        quest_module.safe_say(f"{username} has stumbled upon a [BOSS] Level {boss_level} {boss['name']}!", event.target)
        quest_module.safe_say(f"This is too powerful to face alone! Others can !quest join (or !join) within {join_minutes} minutes!", event.target)

        # Ping users who opted in for mob notifications
        mob_pings = quest_module.get_state("mob_pings", {})
        if event.target in mob_pings and mob_pings[event.target]:
            ping_names = list(mob_pings[event.target].values())
            if ping_names:
                quest_module.safe_say(f"BOSS alert: {', '.join(ping_names)}", event.target)

        return True


def cmd_mob_ping(quest_module, connection, event, msg, username, match):
    """Toggle mob ping notifications for the user."""
    if not quest_module.is_enabled(event.target):
        return False

    action = match.group(1).lower()  # "on" or "off"
    channel = event.target
    user_id = quest_module.bot.get_user_id(username)

    # Get mob ping list per channel (store as dict with user_id -> username)
    mob_pings = quest_module.get_state("mob_pings", {})
    if channel not in mob_pings:
        mob_pings[channel] = {}

    if action == "on":
        if user_id not in mob_pings[channel]:
            mob_pings[channel][user_id] = username
            quest_module.set_state("mob_pings", mob_pings)
            quest_module.save_state()
            quest_module.safe_reply(connection, event, f"{username}, you will now be notified when mob encounters start.")
        else:
            # Update username in case it changed
            mob_pings[channel][user_id] = username
            quest_module.set_state("mob_pings", mob_pings)
            quest_module.save_state()
            quest_module.safe_reply(connection, event, f"{username}, you are already receiving mob notifications.")
    else:  # off
        if user_id in mob_pings[channel]:
            del mob_pings[channel][user_id]
            quest_module.set_state("mob_pings", mob_pings)
            quest_module.save_state()
            quest_module.safe_reply(connection, event, f"{username}, you will no longer be notified of mob encounters.")
        else:
            quest_module.safe_reply(connection, event, f"{username}, you were not receiving mob notifications.")

    return True


def cmd_mob_start(quest_module, connection, event, msg, username, match):
    """Start a mob encounter that others can join."""
    if not quest_module.is_enabled(event.target):
        return False

    with quest_module.mob_lock:
        # Check global cooldown for mob encounters (per channel)
        mob_cooldown = quest_module.get_config_value("mob_cooldown_seconds", event.target, default=3600)  # 1 hour default
        if not quest_module.check_rate_limit(f"mob_spawn_{event.target}", mob_cooldown):
            quest_module.safe_reply(connection, event, "A mob encounter was recently completed. Please wait before summoning another.")
            return True

        # Store cooldown expiry timestamp for this channel (for web display)
        mob_cooldowns = quest_module.get_state("mob_cooldowns", {})
        mob_cooldowns[event.target] = time.time() + mob_cooldown
        quest_module.set_state("mob_cooldowns", mob_cooldowns)

        active_mob = quest_module.get_state("active_mob")
        if active_mob:
            quest_module.safe_reply(connection, event, "A mob encounter is already active! Use !quest join (or !join) to participate.")
            return True

        user_id = quest_module.bot.get_user_id(username)
        player = quest_progression.get_player(quest_module, user_id, username)

        # Check energy
        energy_enabled = quest_module.get_config_value("energy_system.enabled", event.target, default=True)
        if energy_enabled and player["energy"] < 1:
            quest_module.safe_reply(connection, event, f"You are too exhausted for a mob quest, {quest_module.bot.title_for(username)}.")
            return True

        # Attempt to spawn a legend boss first
        legend_candidates = quest_utils.get_active_legend_bosses(quest_module)
        legend_spawn_chance = quest_module.get_config_value("legend_boss.spawn_chance", event.target, default=0.15)
        legend_info = None
        is_legend_spawn = False
        monster = None
        is_rare = False

        if legend_candidates and random.random() < legend_spawn_chance:
            legend_info = random.choice(legend_candidates)
            monster, monster_level = quest_utils.build_legend_boss_monster(quest_module, legend_info, event.target, player['level'])
            is_legend_spawn = True
        else:
            # Select a normal mob monster
            monsters = quest_module._get_content("monsters", event.target, default=[])
            avg_level = player['level']
            possible_monsters = [m for m in monsters if isinstance(m, dict) and m['min_level'] <= avg_level + 5]

            if not possible_monsters:
                quest_module.safe_reply(connection, event, "No suitable mob encounter found.")
                return True

            monster = random.choice(possible_monsters)
            monster_level = max(player['level'], avg_level + 3)

            # Check for rare spawn
            rare_spawn_chance = quest_module.get_config_value("rare_spawn_chance", event.target, default=0.10)
            is_rare = random.random() < rare_spawn_chance

        join_window_seconds = quest_module.get_config_value("mob_join_window_seconds", event.target, default=300)
        close_time = time.time() + join_window_seconds

        mob_data = {
            "channel": event.target,
            "monster": monster,
            "monster_level": monster_level,
            "is_rare": is_rare,
            "participants": [{"user_id": user_id, "username": username}],
            "initiator": username,
            "close_epoch": close_time
        }
        if is_legend_spawn and legend_info:
            mob_data["is_boss"] = True
            mob_data["is_legend"] = True
            mob_data["legend_user_id"] = legend_info["user_id"]
            mob_data["legend_transcendence"] = legend_info.get("transcendence", 1)

        quest_module.set_state("active_mob", mob_data)
        quest_module.save_state()

        # Schedule mob window close
        schedule.every(join_window_seconds).seconds.do(quest_module._close_mob_window).tag(f"{quest_module.name}-mob_close")

        legend_prefix = "[LEGEND] " if mob_data.get("is_legend") else ""
        rare_prefix = "[RARE] " if is_rare and not mob_data.get("is_legend") else ""
        quest_module.safe_reply(connection, event, f"{username} has summoned a {legend_prefix}{rare_prefix}Level {monster_level} {monster['name']}! Others can !quest join (or !join) within {join_window_seconds} seconds!")

        if mob_data.get("is_legend"):
            quest_module.safe_say(f"A LEGENDARY boss has emerged: {monster['name']}! Rally the realm with !quest join.", event.target)
        elif is_rare:
            quest_module.safe_say(f"A rare mob encounter has appeared! Use !quest join (or !join) to participate!", event.target)

        # Ping users who opted in for mob notifications
        mob_pings = quest_module.get_state("mob_pings", {})
        if event.target in mob_pings and mob_pings[event.target]:
            ping_names = list(mob_pings[event.target].values())
            if ping_names:
                quest_module.safe_say(f"Mob alert: {', '.join(ping_names)}", event.target)

        return True


def cmd_mob_join(quest_module, connection, event, msg, username, match):
    """Join an active mob encounter."""
    if not quest_module.is_enabled(event.target):
        return False

    with quest_module.mob_lock:
        active_mob = quest_module.get_state("active_mob")
        if not active_mob:
            quest_module.safe_reply(connection, event, "No active mob encounter to join.")
            return True

        if active_mob["channel"] != event.target:
            quest_module.safe_reply(connection, event, "The mob encounter is in another channel.")
            return True

        user_id = quest_module.bot.get_user_id(username)

        # Check if already in party
        if any(p["user_id"] == user_id for p in active_mob["participants"]):
            quest_module.safe_reply(connection, event, "You are already in the party!")
            return True

        # Check energy
        player = quest_progression.get_player(quest_module, user_id, username)
        energy_enabled = quest_module.get_config_value("energy_system.enabled", event.target, default=True)
        if energy_enabled and player["energy"] < 1:
            quest_module.safe_reply(connection, event, f"You are too exhausted to join, {quest_module.bot.title_for(username)}.")
            return True

        # Add to party
        active_mob["participants"].append({"user_id": user_id, "username": username})
        quest_module.set_state("active_mob", active_mob)
        quest_module.save_state()

        party_size = len(active_mob["participants"])
        quest_module.safe_reply(connection, event, f"{username} joins the party! ({party_size} adventurers ready)")
        return True


def close_mob_window(quest_module):
    """Execute the mob encounter after the join window closes."""
    with quest_module.mob_lock:
        active_mob = quest_module.get_state("active_mob")
        if not active_mob:
            schedule.clear(quest_module.name)
            return

        channel = active_mob["channel"]
        monster = active_mob["monster"]
        monster_level = active_mob["monster_level"]
        participants = active_mob["participants"]
        party_size = len(participants)

        # Clear the active mob and scheduled task
        quest_module.set_state("active_mob", None)
        schedule.clear(quest_module.name)

        # Calculate win chance based on party size
        is_boss = active_mob.get("is_boss", False)
        is_legend = active_mob.get("is_legend", False)

        if is_boss:
            # Boss encounters are much harder!
            # 1 person = 1%, 2 = 10%, 3 = 40%, 4 = 70%, 5+ = 85%
            win_chance_map = {1: 0.01, 2: 0.10, 3: 0.40, 4: 0.70}
            win_chance = win_chance_map.get(party_size, 0.85)  # 5+ people = 85%
        else:
            # Normal mob encounters
            # 1 person = 5%, 2 = 25%, 3 = 75%, 4+ = 95%
            win_chance_map = {1: 0.05, 2: 0.25, 3: 0.75}
            win_chance = win_chance_map.get(party_size, 0.95)  # 4+ people = 95%

        # Deduct energy from all participants & detect Mythic Sigils
        energy_enabled = quest_module.get_config_value("energy_system.enabled", channel, default=True)
        players_state = quest_module.get_state("players", {})
        relic_override = None
        for p in participants:
            player = quest_progression.get_player(quest_module, p["user_id"], p["username"])
            if energy_enabled and player["energy"] > 0:
                player["energy"] -= 1
            if not relic_override:
                effect = next(
                    (
                        eff for eff in player.get("active_effects", [])
                        if eff.get("type") == "dungeon_relic" and eff.get("boss_auto_wins", 0) > 0
                    ),
                    None
                )
                if effect:
                    relic_override = {"player": player, "participant": p, "effect": effect}
            players_state[p["user_id"]] = player

        quest_module.set_state("players", players_state)

        relic_override_used = False
        if relic_override:
            win = True
            relic_override_used = True
            win_chance = 1.0
        else:
            win = random.random() < win_chance

        # Check if rare spawn
        is_rare = active_mob.get("is_rare", False)
        rare_xp_mult = quest_module.get_config_value("rare_spawn_xp_multiplier", channel, default=2.0)

        boss_prefix = "[BOSS] " if is_boss else ""
        legend_prefix = "[LEGEND] " if is_legend else ""
        rare_prefix = "[RARE] " if is_rare and not is_legend else ""
        monster_name = f"{boss_prefix}{legend_prefix}{rare_prefix}Level {monster_level} {monster['name']}"

        # Announce outcome
        party_names = ", ".join([p["username"] for p in participants])
        quest_module.safe_say(f"The party ({party_names}) engages the {monster_name}!", channel)
        time.sleep(1.5)

        if relic_override_used and relic_override:
            holder = relic_override["participant"]["username"]
            effect = relic_override["effect"]
            effect["boss_auto_wins"] = max(0, effect.get("boss_auto_wins", 0) - 1)
            remaining_sigils = effect.get("boss_auto_wins", 0)
            if effect.get("remaining_auto_wins", 0) <= 0 and remaining_sigils <= 0:
                try:
                    relic_override["player"]["active_effects"].remove(effect)
                except ValueError:
                    pass
            players_state[relic_override["participant"]["user_id"]] = relic_override["player"]
            sigil_suffix = "sigils" if remaining_sigils != 1 else "sigil"
            quest_module.safe_say(
                f"{holder}'s Mythic Sigil detonates, guaranteeing victory! ({remaining_sigils} {sigil_suffix} remaining)",
                channel
            )

        xp_level_mult = quest_module.get_config_value("xp_level_multiplier", channel, default=2)
        base_xp = random.randint(monster.get('xp_win_min', 10), monster.get('xp_win_max', 20))

        if win:
            # Victory - distribute XP
            total_xp = (base_xp + monster_level * xp_level_mult) * 1.5  # Bonus for mob

            # Apply boss multiplier (bosses give way more XP!)
            if is_boss:
                boss_xp_mult = quest_module.get_config_value("boss_xp_multiplier", channel, default=2.5)
                total_xp *= boss_xp_mult
            if is_legend:
                legend_xp_mult = quest_module.get_config_value("legend_boss.xp_multiplier", channel, default=3.0)
                total_xp *= legend_xp_mult

            # Apply rare spawn multiplier
            if is_rare:
                total_xp *= rare_xp_mult

            # Check for critical hit (shared for whole party)
            crit_chance = quest_module.get_config_value("crit_chance", channel, default=0.15)
            is_crit = random.random() < crit_chance

            if is_legend:
                quest_module.safe_say(f"Victory! (Win chance: {win_chance:.0%}) The legendary foe {monster_name} is defeated! Each adventurer gains {int(total_xp)} XP!", channel)
            else:
                quest_module.safe_say(f"Victory! (Win chance: {win_chance:.0%}) The {monster_name} falls! Each adventurer gains {int(total_xp)} XP!", channel)

            for p in participants:
                xp_msgs = quest_progression.grant_xp(quest_module, p["user_id"], p["username"], total_xp, is_win=True, is_crit=is_crit)
                for m in xp_msgs:
                    quest_module.safe_say(f"{p['username']}: {m}", channel)

                # Hardcore mode: Apply HP damage even on wins
                player = players_state.get(p["user_id"])
                if player and player.get("hardcore_mode", False):
                    damage = quest_progression.calculate_hardcore_damage(
                        monster_level=monster_level,
                        player_level=player.get("level", 1),
                        is_win=True,
                        is_boss=is_boss or is_legend,
                        prestige=player.get("prestige", 0)
                    )
                    player["hardcore_hp"] = max(0, player["hardcore_hp"] - damage)
                    quest_module.safe_say(f"{p['username']}: HP: {player['hardcore_hp']}/{player['hardcore_max_hp']} (-{damage} damage)", channel)

                    # Check for permadeath
                    if player["hardcore_hp"] <= 0:
                        death_messages = quest_progression.handle_hardcore_death(quest_module, player, p["user_id"], p["username"])
                        for msg in death_messages:
                            quest_module.safe_say(f"{p['username']}: {msg}", channel)

                    players_state[p["user_id"]] = player
        else:
            # Defeat - lose XP and potentially get injured
            xp_loss_perc = quest_module.get_config_value("xp_loss_percentage", channel, default=0.25)
            xp_loss = (base_xp + monster_level * xp_level_mult) * xp_loss_perc
            if is_legend:
                legend_loss_mult = quest_module.get_config_value("legend_boss.xp_loss_multiplier", channel, default=1.5)
                xp_loss *= legend_loss_mult
                quest_module.safe_say(f"Defeat! (Win chance: {win_chance:.0%}) The legend {monster_name} overwhelms the party! Each member loses {int(xp_loss)} XP.", channel)
            else:
                quest_module.safe_say(f"Defeat! (Win chance: {win_chance:.0%}) The party has been overwhelmed! Each member loses {int(xp_loss)} XP.", channel)

            for p in participants:
                quest_progression.deduct_xp(quest_module, p["user_id"], p["username"], xp_loss)
                # Get class bonuses for injury reduction
                player_data = players_state.get(p["user_id"], {})
                player_level = player_data.get("level", 1)
                class_bonuses = quest_utils.get_class_bonuses(quest_module, p["user_id"], player_level)
                # Get armor-based injury reduction from active effects
                armor_injury_reduction = get_injury_reduction(player_data)
                injury_msg = quest_utils.apply_injury(quest_module, p["user_id"], p["username"], channel, injury_reduction=armor_injury_reduction, class_injury_reduction=class_bonuses["injury_reduction"])
                if injury_msg:
                    quest_module.safe_say(f"{p['username']}: {injury_msg}", channel)

                # Hardcore mode: Apply HP damage (heavy on defeats!)
                player = players_state.get(p["user_id"])
                if player and player.get("hardcore_mode", False):
                    damage = quest_progression.calculate_hardcore_damage(
                        monster_level=monster_level,
                        player_level=player.get("level", 1),
                        is_win=False,
                        is_boss=is_boss or is_legend,
                        prestige=player.get("prestige", 0)
                    )
                    player["hardcore_hp"] = max(0, player["hardcore_hp"] - damage)
                    quest_module.safe_say(f"{p['username']}: HP: {player['hardcore_hp']}/{player['hardcore_max_hp']} (-{damage} damage)", channel)

                    # Check for permadeath
                    if player["hardcore_hp"] <= 0:
                        death_messages = quest_progression.handle_hardcore_death(quest_module, player, p["user_id"], p["username"])
                        for msg in death_messages:
                            quest_module.safe_say(f"{p['username']}: {msg}", channel)

                    players_state[p["user_id"]] = player

        # Save all player states
        quest_module.set_state("players", players_state)
        quest_module.save_state()

        # Record achievement progress for quest completion for all participants
        for p in participants:
            achievement_hooks.record_quest_completion(quest_module.bot, p["username"])

        quest_module.set_state("active_mob", None)
        schedule.clear(quest_module.name)

    return schedule.CancelJob
