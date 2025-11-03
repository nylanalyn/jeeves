# modules/quest/quest_utils.py
# Utility functions for the quest module

import random
import re
import operator
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple

from .constants import UTC, DUNGEON_ITEMS, DUNGEON_EQUIPPED_ITEMS, DUNGEON_PARTIAL_REWARDS, DUNGEON_SAFE_HAVENS, DUNGEON_MOMENTUM_BONUS


def format_timedelta(future_datetime: datetime) -> str:
    """Formats the time remaining until a future datetime."""
    delta = future_datetime - datetime.now(UTC)
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "recovered"

    hours, remainder = divmod(seconds, 3600)
    minutes, _ = divmod(remainder, 60)

    parts = []
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    return " ".join(parts) if parts else "less than a minute"


def to_roman(number: int) -> str:
    """Convert an integer to a Roman numeral (supports 1-3999)."""
    if not isinstance(number, int) or number <= 0:
        return str(number)
    numerals = [
        (1000, "M"), (900, "CM"), (500, "D"), (400, "CD"),
        (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
        (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")
    ]
    result = []
    remaining = min(number, 3999)
    for value, symbol in numerals:
        while remaining >= value:
            result.append(symbol)
            remaining -= value
    return "".join(result)


def get_legend_suffix_for_user(quest_module, user_id: str) -> Optional[str]:
    """Return the legend suffix for a user if they have transcended."""
    try:
        players = quest_module.get_state("players", {})
        player = players.get(user_id)
        if not isinstance(player, dict):
            return None
        transcendence = player.get("transcendence", 0)
        if transcendence <= 0:
            return None
        return "(Legend)" if transcendence == 1 else f"(Legend {to_roman(transcendence)})"
    except Exception:
        return None


def get_active_legend_bosses(quest_module) -> List[Dict[str, Any]]:
    """Return a list of legends currently eligible to appear as bosses."""
    legend_state = quest_module.get_state("legend_bosses", {}) or {}
    players = quest_module.get_state("players", {}) or {}
    active_legends: List[Dict[str, Any]] = []

    for user_id, entry in legend_state.items():
        player = players.get(user_id)
        if not isinstance(player, dict):
            continue
        transcendence = player.get("transcendence", entry.get("transcendence", 0))
        if transcendence <= 0:
            continue
        active_legends.append({
            "user_id": user_id,
            "username": player.get("name", entry.get("username", "Unknown Legend")),
            "transcendence": transcendence
        })

    return active_legends


def build_legend_boss_monster(quest_module, legend_entry: Dict[str, Any], channel: str, player_level: int) -> Tuple[Dict[str, Any], int]:
    """Build a monster dict representing a legend boss."""
    transcendence = max(1, legend_entry.get("transcendence", 1))
    level_cap = quest_module.get_config_value("level_cap", channel, default=20)
    base_level = max(level_cap + 5, player_level + 5)
    monster_level = base_level + (transcendence - 1) * 3

    legend_suffix = "(Legend)" if transcendence == 1 else f"(Legend {to_roman(transcendence)})"
    monster_name = f"{legend_entry.get('username', 'Unknown')} {legend_suffix}"

    base_xp = 250 + (transcendence - 1) * 100

    monster = {
        "name": monster_name,
        "xp_win_min": base_xp,
        "xp_win_max": base_xp + 150,
        "type": "legend_boss",
        "legend_transcendence": transcendence,
        "legend_user_id": legend_entry.get("user_id")
    }
    return monster, monster_level


def calculate_xp_for_level(quest_module, level: int) -> int:
    """Safely calculates XP required for a level using the configured formula."""
    xp_formula = quest_module.get_config_value("xp_curve_formula", default="level * 100")

    # Safe formula parser: only allow level variable and basic arithmetic
    # Supports: level * N, level + N, or combinations with parentheses
    try:
        # Replace 'level' with the actual value in a safe way
        safe_expr = xp_formula.replace('level', str(level))
        # Only allow numbers, operators, spaces, and parentheses
        if not re.match(r'^[0-9\s\+\-\*/\.\(\)]+$', safe_expr):
            quest_module.log_debug(f"Invalid XP formula: {xp_formula}, using default")
            return level * 100
        # Use safe calculation instead of eval
        result = safe_calculate(safe_expr)
        return int(result)
    except Exception as e:
        quest_module.log_debug(f"Error calculating XP formula '{xp_formula}': {e}, using default")
        return level * 100


def calculate_win_chance(player_level: float, monster_level: int, energy_modifier: float = 0.0,
                        group_modifier: float = 0.0, prestige_level: int = 0) -> float:
    """Calculate win chance for combat."""
    from .quest_progression import get_prestige_win_bonus

    level_diff = player_level - monster_level
    base_chance = 0.5 + (level_diff * 0.10)
    base_chance += energy_modifier
    base_chance += group_modifier
    base_chance += get_prestige_win_bonus(prestige_level)
    base_chance = max(0.05, min(0.95, base_chance))
    return base_chance


def check_and_clear_injury(player_data: Dict[str, Any]) -> Tuple[Dict[str, Any], Optional[str]]:
    """Checks if a player's injuries have expired and clears them if so."""
    # Migrate old single injury format to list
    if 'active_injury' in player_data:
        old_injury = player_data['active_injury']
        player_data['active_injuries'] = [old_injury]
        del player_data['active_injury']

    if 'active_injuries' in player_data and player_data['active_injuries']:
        now = datetime.now(UTC)
        expired_injuries = []
        active_injuries = []

        for injury in player_data['active_injuries']:
            try:
                expires_at = datetime.fromisoformat(injury['expires_at'])
                if now >= expires_at:
                    expired_injuries.append(injury['name'])
                else:
                    active_injuries.append(injury)
            except (ValueError, TypeError):
                # Invalid injury, skip it
                pass

        player_data['active_injuries'] = active_injuries

        if expired_injuries:
            if len(expired_injuries) == 1:
                return player_data, f"You have recovered from your {expired_injuries[0]}."
            else:
                return player_data, f"You have recovered from: {', '.join(expired_injuries)}."

    return player_data, None


def apply_injury(quest_module, user_id: str, username: str, channel: str,
                is_medic_quest: bool = False, injury_reduction: float = 0.0) -> Optional[str]:
    """Applies a random injury to a player upon defeat. Max 2 of each injury type."""
    injury_config = quest_module._get_content("injury_system", channel, default={})
    if not injury_config.get("enabled"):
        return None

    # Don't apply injuries during medic quests
    if is_medic_quest:
        return None

    injury_chance = injury_config.get("injury_chance_on_loss", 0.75)
    # Apply injury reduction from armor
    injury_chance = max(0.0, injury_chance * (1.0 - injury_reduction))
    if random.random() > injury_chance:
        return None

    possible_injuries = injury_config.get("injuries", [])
    if not possible_injuries:
        return None

    injury = random.choice(possible_injuries)

    # Import here to avoid circular dependency
    from .quest_progression import get_player

    players = quest_module.get_state("players")
    player = get_player(quest_module, user_id, username)

    # Migrate old format if needed
    if 'active_injury' in player:
        player['active_injuries'] = [player['active_injury']]
        del player['active_injury']

    # Initialize injuries list if not present
    if 'active_injuries' not in player:
        player['active_injuries'] = []

    # Check if player already has 2 of this injury type
    injury_count = sum(1 for inj in player['active_injuries'] if inj['name'] == injury['name'])
    if injury_count >= 2:
        return f"You narrowly avoid another {injury['name']}!"

    # Apply the injury
    duration = timedelta(hours=injury.get("duration_hours", 1))
    expires_at = datetime.now(UTC) + duration

    new_injury = {
        "name": injury['name'],
        "description": injury['description'],
        "expires_at": expires_at.isoformat(),
        "effects": injury.get('effects', {})
    }

    player['active_injuries'].append(new_injury)
    players[user_id] = player
    quest_module.set_state("players", players)
    quest_module.save_state()

    if injury_count == 1:
        return f"You have sustained another {injury['name']}! {injury['description']}"
    else:
        return f"You have sustained an injury: {injury['name']}! {injury['description']}"


def safe_calculate(expr: str) -> float:
    """Safely evaluates a simple mathematical expression without eval()."""
    # Remove whitespace
    expr = expr.replace(" ", "")

    # Simple recursive descent parser for basic arithmetic
    def parse_expr(s, pos):
        left, pos = parse_term(s, pos)
        while pos < len(s) and s[pos] in ('+', '-'):
            op = s[pos]
            pos += 1
            right, pos = parse_term(s, pos)
            left = operator.add(left, right) if op == '+' else operator.sub(left, right)
        return left, pos

    def parse_term(s, pos):
        left, pos = parse_factor(s, pos)
        while pos < len(s) and s[pos] in ('*', '/'):
            op = s[pos]
            pos += 1
            right, pos = parse_factor(s, pos)
            left = operator.mul(left, right) if op == '*' else operator.truediv(left, right)
        return left, pos

    def parse_factor(s, pos):
        if pos < len(s) and s[pos] == '(':
            pos += 1
            result, pos = parse_expr(s, pos)
            if pos < len(s) and s[pos] == ')':
                pos += 1
            return result, pos
        else:
            # Parse number (including decimals)
            start = pos
            while pos < len(s) and (s[pos].isdigit() or s[pos] == '.'):
                pos += 1
            return float(s[start:pos]), pos

    result, _ = parse_expr(expr, 0)
    return result


def select_dungeon_loadout(count: int = None) -> List[Dict[str, Any]]:
    """Select a random set of dungeon items."""
    if count is None:
        count = DUNGEON_EQUIPPED_ITEMS
    if not DUNGEON_ITEMS:
        return []
    count = max(1, min(count, len(DUNGEON_ITEMS)))
    return random.sample(DUNGEON_ITEMS, k=count)


def get_dungeon_state(player: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure the player has a dungeon state block."""
    state = player.setdefault("dungeon_state", {})
    state.setdefault("equipped_items", [])
    state.setdefault("last_equipped", None)
    state.setdefault("last_run", None)
    return state


def apply_dungeon_failure_penalty(quest_module, player: Dict[str, Any], user_id: str, username: str, room_reached: int = 1) -> int:
    """Apply the penalty for failing inside the dungeon and return the XP lost.

    Penalty scales with progress into the dungeon. Early rooms remove a large
    chunk of a level's progress, while deeper rooms chip away smaller portions.
    If the resulting XP loss pushes the player below zero, levels are removed
    via quest_progression.deduct_xp.
    """
    base_pool = player.get("xp_to_next_level") or calculate_xp_for_level(quest_module, max(player.get("level", 1), 1))
    penalties_cfg = quest_module.get_config_value("dungeon.failure_penalties", default={})

    early_ratio = penalties_cfg.get("early_ratio", 0.75)
    mid_ratio = penalties_cfg.get("mid_ratio", 0.50)
    late_ratio = penalties_cfg.get("late_ratio", 0.25)

    if room_reached <= 3:
        ratio = early_ratio
    elif room_reached <= 6:
        ratio = mid_ratio
    else:
        ratio = late_ratio

    xp_loss = max(1, int(round(base_pool * ratio)))

    from . import quest_progression
    quest_progression.deduct_xp(quest_module, user_id, username, xp_loss)
    return xp_loss


def calculate_dungeon_partial_reward(room_reached: int) -> Tuple[int, int]:
    """Calculate partial rewards based on how far the player got.

    Returns: (xp_reward, relic_charges)
    """
    for min_room, max_room, xp_reward, relic_charges in DUNGEON_PARTIAL_REWARDS:
        if min_room <= room_reached <= max_room:
            return (xp_reward, relic_charges)
    return (0, 0)


def grant_dungeon_quit_reward(quest_module, user_id: str, username: str, room_reached: int) -> str:
    """Grant XP rewards for safely quitting a dungeon.

    Returns a message describing what was rewarded.
    """
    from . import quest_progression

    xp_reward, relic_charges = calculate_dungeon_partial_reward(room_reached)

    if xp_reward == 0:
        return "You retreated safely after 1 room, but gained nothing."

    messages = []
    players = quest_module.get_state("players", {})
    player = players.get(user_id)

    if player and xp_reward > 0:
        xp_messages = quest_progression.grant_xp(quest_module, user_id, username, xp_reward, is_win=True)
        if xp_messages:
            messages.append(f"+{xp_reward} XP")

    quest_module.save_state()

    if messages:
        return f"You retreated safely after {room_reached} room{'s' if room_reached > 1 else ''} and gained: {', '.join(messages)}"
    return f"You retreated safely after {room_reached} room{'s' if room_reached > 1 else ''}."


def get_action_text(quest_module, user_id: str) -> str:
    """Get random action text for a user."""
    actions = quest_module.get_config_value("actions", default=[])
    if not actions:
        return "ventures forth"
    return random.choice(actions)
