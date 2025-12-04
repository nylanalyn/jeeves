# Quest Module Architecture Guide for LLMs

**Purpose**: This guide provides a comprehensive overview of the Quest module's architecture for AI coding assistants. Read this alongside the main LLM_ARCHITECTURE_GUIDE.md when working on quest-related features.

---

## Table of Contents
1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [Core Systems](#core-systems)
4. [Data Files](#data-files)
5. [Player State & Progression](#player-state--progression)
6. [Combat & Encounters](#combat--encounters)
7. [Items & Inventory](#items--inventory)
8. [Themes & Content](#themes--content)
9. [Common Patterns](#common-patterns)
10. [Common Pitfalls](#common-pitfalls)
11. [Quick Reference](#quick-reference)

---

## Overview

The Quest module is Jeeves' largest and most complex module - a full-fledged RPG system with:
- **Solo quests** with difficulty modes (easy, normal, hard)
- **Mob encounters** where multiple players fight together
- **Boss hunt** - collaborative clue-finding system
- **Prestige system** with 10 levels and challenge paths
- **Transcendence** for players beyond max prestige
- **Hardcore mode** with permadeath
- **Dungeon runs** - 10-room gauntlet with item management
- **Energy system** with regeneration and penalties
- **Injury system** with timed debuffs
- **Class system** with level-based bonuses
- **Inventory & items** (medkits, energy potions, lucky charms, armor, XP scrolls, dungeon relics)
- **Abilities** unlocked via challenge path completion
- **Themeable content** (noir, holiday shopping, cyberpunk, etc.)

The module is a **package** (`modules/quest_pkg/`) split into specialized submodules for maintainability.

---

## File Structure

```
modules/
  quest.py                 # Thin wrapper that imports from quest_pkg
  quest_pkg/
    __init__.py           # Main Quest class and command registration
    constants.py          # Constants: dungeon items, rooms, UTC timezone
    quest_core.py         # Core: solo quests, search, item usage, medic quests, abilities
    quest_utils.py        # Utilities: XP calculations, injury handling, class bonuses
    quest_combat.py       # Combat: mob encounters, boss fights, combat effects
    quest_progression.py  # Progression: XP, leveling, prestige, transcendence, dungeons, hardcore
    quest_display.py      # Display: profile, leaderboard, inventory, story
    quest_boss_hunt.py    # Boss hunt: clue system, buff management, haunting mechanics

quest_content.json        # Themed content (monsters, story, classes, injuries, boss hunt)
challenge_paths.json      # Challenge paths and unlockable abilities
```

### Module Responsibilities

- **`__init__.py`**: Main `Quest` class, inherits from `SimpleCommandModule`, registers all commands, delegates to submodules
- **`constants.py`**: Dungeon items, dungeon rooms, reward constants, UTC timezone
- **`quest_core.py`**: Solo quest logic, search system, item usage, medic quests, medkit handling, ability usage, content loading
- **`quest_utils.py`**: XP formulas, win chance calculation, injury application/clearing, class bonus calculation, legend boss building, timedelta formatting
- **`quest_combat.py`**: Mob encounters, boss encounters, combat effect application (lucky charms, armor, relics), injury reduction
- **`quest_progression.py`**: Player creation, XP grants, leveling, prestige, transcendence, hardcore mode, dungeon runs
- **`quest_display.py`**: Profile display, leaderboard, inventory display, story/lore display
- **`quest_boss_hunt.py`**: Collaborative boss hunt, clue drops, buff management, haunting mechanics (Big Tony/Krampus returns)

---

## Core Systems

### 1. Energy System

Players have energy that regenerates over time and is consumed by quests.

**Key Config**:
```yaml
energy_system:
  enabled: true
  max_energy: 10          # Base max energy
  regen_minutes: 10       # Regen 1 energy every 10 minutes
  penalties:              # Low energy penalties
    - threshold: 3
      xp_multiplier: 0.75
      win_chance_modifier: -0.05
```

**Prestige Bonuses**: Prestige 3+ grants +1 to +3 max energy (see `get_prestige_energy_bonus()`)

**Challenge Path Modifiers**:
- `energy_max_bonus`: Add flat energy (e.g., +5 for hard mode)
- `energy_max_multiplier`: Multiply energy (e.g., 0.5 for ascetic path = half energy)

**Energy Regeneration**: Scheduled task runs every N minutes (see `_regenerate_energy()` in `__init__.py`)
- Clears expired injuries during regen
- Applies injury effects to regen rate (`energy_regen_modifier`)

### 2. Injury System

Players can sustain injuries on quest losses, which apply debuffs for a duration.

**Structure** (`quest_content.json` under each theme):
```json
"injury_system": {
  "enabled": true,
  "injury_chance_on_loss": 0.5,
  "injuries": [
    {
      "name": "Pistol Whipped",
      "description": "Someone got the drop on you - your head is ringing like church bells.",
      "duration_hours": 2,
      "effects": {
        "xp_multiplier": 0.5,
        "energy_regen_modifier": -1
      }
    }
  ]
}
```

**Player State**: `player["active_injuries"]` is a list of active injury dicts with `expires_at` timestamps

**Migration**: Old single `active_injury` format is auto-migrated to `active_injuries` list

**Max Limit**: Players can have max 2 of each injury type (see `apply_injury()`)

**Armor Shards**: Reduce injury chance (see `get_injury_reduction()`)

**Class Bonuses**: Third class (index 2) gets 50% injury reduction

### 3. Class System

Players choose a class that provides level-based bonuses.

**Class Position Bonuses** (see `get_class_bonuses()`):
- **Position 0 (first class)**: +25% win at levels 1-10, -10% win at levels 11-20 (early game advantage)
- **Position 1 (second class)**: -10% win at levels 1-10, +25% win at levels 11-20 (late game advantage)
- **Position 2 (third class)**: 50% injury reduction at all levels (tank/support)

**Class Content** (`quest_content.json`):
```json
"classes": {
  "detective": {
    "description": "A hardboiled private eye...",
    "actions": [
      "{user} pulls out their trusty revolver and aims steady at the {monster}.",
      ...
    ]
  }
}
```

**Class Change**: Players can change class at each prestige (tracked in `player_classes` and `class_change_prestige` state)

### 4. Prestige System

Players at level 20 can prestige to reset level and gain permanent bonuses.

**Max Prestige**: 10 (configurable via `max_prestige`)

**Bonuses** (see `quest_progression.py`):
- **Win Chance**: P1-3: +5%, P4-6: +10%, P7-9: +15%, P10: +20%
- **XP Multiplier**: P2-4: 1.25x, P5-7: 1.5x, P8-9: 1.75x, P10: 2.0x
- **Max Energy**: P3-5: +1, P6-8: +2, P9-10: +3

**Challenge Paths**: Special prestige modes (hard mode, ironman, ascetic) with modifiers and completion conditions

**Challenge Path Completion**: Tracked in `player["completed_challenge_paths"]`, rewards abilities

### 5. Challenge Paths

Defined in `challenge_paths.json`, activated by admins, chosen during prestige.

**Structure**:
```json
"paths": {
  "hard_mode": {
    "name": "Hard Mode",
    "description": "Lower XP gain, lower win chance, bonus to energy if you make it!",
    "enabled": true,
    "requirements": {
      "min_prestige": 0,
      "max_prestige": 10
    },
    "modifiers": {
      "xp_gain_multiplier": 0.5,
      "win_chance_modifier": -0.1,
      "energy_max_bonus": 5
    },
    "completion_conditions": {
      "reach_level_20": true,
      "custom_stat": {
        "stat_name": "medkits_used",
        "comparison": "less_than",
        "value": 1
      }
    },
    "rewards": {
      "prestige_xp_bonus": 0.25,
      "title_suffix": " the Challenger",
      "ability_unlock": "bloodlust"
    }
  }
}
```

**Active Path**: `challenge_paths["active_path"]` - set by admin, shown to players during prestige

**Player Path**: `player["challenge_path"]` - the path the player is currently on

**Challenge Stats**: `player["challenge_stats"]` tracks stats for completion (e.g., `medkits_used_this_prestige`)

### 6. Abilities

Unlocked by completing challenge paths, have cooldowns, channel-wide effects.

**Structure** (`challenge_paths.json`):
```json
"abilities": {
  "doctor": {
    "name": "Doctor",
    "description": "Heal all injuries for all players in the channel",
    "command": "doctor",
    "cooldown_hours": 168,
    "effect": "heal_all_injuries",
    "announcement": "{user} channels healing energy! All injuries in the channel have been healed!"
  }
}
```

**Player State**:
- `player["unlocked_abilities"]`: List of ability IDs
- `player["ability_cooldowns"]`: Dict of `{ability_id: expires_at_timestamp}`

**Usage**: `!quest ability` lists abilities, `!quest ability <name>` uses one

### 7. Transcendence

Players at max prestige (10) can transcend to become Legends.

**Transcendence Level**: `player["transcendence"]` - increments each time

**Legend Suffix**: "(Legend)" or "(Legend II)", "(Legend III)" etc. (Roman numerals)

**Legend Bosses**: Transcended players can appear as mob/boss encounters for others (see `get_active_legend_bosses()`)

**Legend Boss Level**: `base_level + (transcendence - 1) * 3` (scales with transcendence)

**Legend State**: Stored in `legend_bosses` state with `{user_id: {username, transcendence}}`

### 8. Hardcore Mode

Permadeath mode: players have HP, all combat deals damage, death = reset.

**Activation**: `!quest hardcore` at level 20, enters hardcore mode

**HP Calculation**: `100 + (level * 20)` - Level 20: 500 HP, Level 50: 1100 HP

**Level Cap**: 50 (vs normal 20)

**Damage**:
- **Win**: 10-30 HP base (bosses: 1.5x)
- **Loss**: 40-80 HP base (bosses: 2.0x)
- Scaled by prestige multiplier (same as XP mult)

**Item Locker**: Non-permanent items moved to `hardcore_locker`, returned on completion/death

**Permanent Items**: Players who complete hardcore can select one item type to keep in future runs (see `handle_hardcore_select_item()`)

**Completion**: Reach level 50 = prestige reward + items restored

**Death**: HP = 0 = no prestige, items restored, reset to level 20

**Stats**: `player["hardcore_stats"]` tracks `{completions, deaths, highest_level_reached}`

### 9. Dungeon System

10-room gauntlet with item management, momentum bonuses, safe havens.

**Dungeon Items** (see `constants.py`):
- 7 item types, each counters 2 specific room types
- Players equip up to 4 items before entering
- Items stored in "dungeon cache" via `!quest search`

**Rooms**: 10 rooms ordered easiest to hardest, each has:
- Monster with level offset and win chance adjust
- Counter items that allow instant bypass
- Flavor text for entering and bypassing

**Safe Havens**: Rooms 3, 6, 9 - players can `!dungeon quit` and claim partial XP rewards

**Momentum**: Each consecutive win = +2% win chance for next fight (resets on loss or bypass)

**Nonstop Mode**: `!dungeon nonstop` skips safe havens, runs all 10 rooms at once

**Rewards**:
- **Completion (room 10)**: Mythic Relics (5 charges = 5 guaranteed solo wins)
- **Sigil Formation**: 4 relics → 1 boss sigil (auto-win next mob/boss)
- **Partial (quit early)**: XP only, no relics

**Relic Penalty**: Failed dungeon runs increase relic decay (anti-farming mechanic)

**State**: `player["dungeon_state"]` tracks `{equipped_items, stored_items, last_run, relic_penalty_chain}`

### 10. Boss Hunt System

Collaborative boss-hunting system where players collect clues to damage a boss.

**Boss Lifecycle**:
1. Boss spawns with max HP (500-600)
2. Players drop clues randomly on solo quest wins (15% chance)
3. Each clue deals damage (default 10 HP)
4. Boss defeated → channel-wide buff (24h: -2 monster levels, 1.5x XP)
5. **Haunting period** (Big Tony/Krampus only): 7 days, random injury/win messages
6. After haunting: New boss spawns

**Big Bad Boss**: Second boss in `boss_hunt.bosses` list (Big Tony, Krampus, etc.)
- Has special haunting mechanics
- Returns after 7-day haunting period with return announcement

**State** (`boss_hunt`):
- `current_boss`: `{name, max_hp, current_hp, clues_collected, spawned_at}`
- `buff`: `{active, expires_at, xp_multiplier, level_reduction}`
- `haunting`: `{active, boss_name, started_at, ends_at, users_notified}`
- `stats`: `{total_bosses_defeated, total_clues_found}`

**Config** (`quest_content.json` or `config.yaml`):
```json
"boss_hunt": {
  "bosses": [
    {"name": "Don Corleone", "description": "...", "max_hp": 500},
    {"name": "Big Tony", "description": "...", "max_hp": 600}
  ],
  "clue_messages": ["finds a crucial piece of evidence", ...],
  "haunting_messages": {
    "injury": ["💀 A gift from an old friend.", ...],
    "win": ["💀 Enjoy it whilst it lasts.", ...]
  },
  "return_message": "💀 {username}: TONY RETURNS!",
  "defeat_announcement": "🎊 BOSS DEFEATED! 🎊"
}
```

---

## Data Files

### quest_content.json

Themed content file with support for multiple themes.

**Structure**:
```json
{
  "default_theme": "noir_november",
  "themes": {
    "noir_november": {
      "theme": {
        "name": "noir_november",
        "background": "#070708",
        ...
      },
      "world_lore": ["The city hums with secrets...", ...],
      "story_beats": {
        "openers": ["{user} pushes open the agency door..."],
        "actions": ["{user} adjusts their fedora..."]
      },
      "monsters": [
        {
          "name": "Two-Bit Hoodlum",
          "min_level": 1,
          "max_level": 3,
          "xp_win_min": 15,
          "xp_win_max": 30
        }
      ],
      "boss_monsters": [...],
      "classes": {...},
      "injury_system": {...},
      "boss_hunt": {...}
    }
  }
}
```

**Theme Selection**: Via `quest.theme` config, or falls back to `default_theme`

**Content Access**: Use `quest_module._get_content(key, channel, default)` to retrieve themed content

**Theme Metadata**: Stored in `quest_module.active_theme_key`, `quest_module.available_theme_keys`, `quest_module._theme_catalog`

### challenge_paths.json

Challenge paths and abilities configuration.

**Top-Level Keys**:
- `paths`: Dict of path definitions
- `abilities`: Dict of ability definitions
- `active_path`: Currently active path ID (admin-controlled)

**Modifiers**:
- `xp_gain_multiplier`: Multiply all XP gains
- `win_chance_modifier`: Add to win chance
- `energy_max_bonus`: Add to max energy
- `energy_max_multiplier`: Multiply max energy

**Completion Conditions**:
- `reach_level_20`: Must hit level 20
- `no_medkits_used`: Custom stat check
- `custom_stat`: General stat comparison (`{stat_name, comparison, value}`)

---

## Player State & Progression

### Player Data Structure

Created/loaded via `quest_progression.get_player(quest_module, user_id, username)`.

**Core Fields**:
```python
{
  "name": "username",
  "level": 1,
  "xp": 0,
  "xp_to_next_level": 100,
  "energy": 10,
  "prestige": 0,
  "transcendence": 0,
  "wins": 0,
  "losses": 0,
  "win_streak": 0,
  "last_fight": {"monster_name": "...", "monster_level": 5, "win": True},
  "last_win_date": "2024-01-15",

  # Inventory
  "inventory": {
    "medkits": 0,
    "energy_potions": 0,
    "lucky_charms": 0,
    "armor_shards": 0,
    "xp_scrolls": 0,
    "dungeon_relics": 0
  },

  # Active effects
  "active_effects": [
    {
      "type": "lucky_charm",
      "win_bonus": 10,
      "expires": "next_fight"
    }
  ],

  # Injuries
  "active_injuries": [
    {
      "name": "Knife Wound",
      "description": "...",
      "expires_at": "2024-01-15T10:30:00+00:00",
      "effects": {"energy_regen_modifier": -1}
    }
  ],

  # Challenge paths
  "challenge_path": "hard_mode",
  "completed_challenge_paths": ["ironman_challenge"],
  "challenge_stats": {
    "medkits_used_this_prestige": 0
  },

  # Abilities
  "unlocked_abilities": ["doctor", "bloodlust"],
  "ability_cooldowns": {
    "doctor": 1736956800.0  # Unix timestamp
  },

  # Dungeon
  "dungeon_state": {
    "equipped_items": ["ember_lantern", "tempest_charm"],
    "stored_items": {"ember_lantern": 2, "spiral_shell": 1},
    "last_run": "2024-01-15T10:30:00+00:00",
    "relic_penalty_chain": 0
  },

  # Hardcore
  "hardcore_mode": False,
  "hardcore_hp": 0,
  "hardcore_max_hp": 0,
  "hardcore_locker": {},
  "hardcore_permanent_items": ["medkits"],
  "hardcore_stats": {
    "completions": 0,
    "deaths": 0,
    "highest_level_reached": 0
  }
}
```

### XP & Leveling

**XP Formula**: `quest_utils.calculate_xp_for_level(quest_module, level)`
- Default: `level * 100` (level 5 = 500 XP to next level)
- Configurable via `xp_curve_formula` (e.g., `level * level * 10`)

**Granting XP**: `quest_progression.grant_xp(quest_module, user_id, username, xp_amount, is_win=False, is_crit=False)`
- Applies challenge path XP multipliers
- Applies prestige XP bonuses
- Handles level-ups (returns list of messages)
- Stops at level cap (20, or 50 for hardcore)

**Deducting XP**: `quest_progression.deduct_xp(quest_module, user_id, username, xp_amount)`
- Can cause level-downs
- Prevents going below level 1

**Crit Hits**: 15% chance on wins (configurable via `crit_chance`), currently cosmetic

### Prestige Flow

1. Player reaches level 20
2. Player uses `!quest prestige` or `!quest prestige challenge`
3. If challenge path active, can choose that path
4. Resets to level 1 (or 20 if configured), clears XP, increments prestige
5. Clears injuries, restores energy
6. Resets challenge stats
7. Grants prestige bonuses

**Code**: `quest_progression.handle_prestige()` (not shown in excerpts, but follows this pattern)

### Transcendence Flow

1. Player at max prestige (10) and level 20
2. Player uses `!quest transcend`
3. Increments transcendence level
4. Resets to level 1
5. Becomes eligible as legend boss encounter

**Code**: `quest_progression.handle_transcend()` (delegates to submodule)

---

## Combat & Encounters

### Win Chance Calculation

**Formula** (see `quest_utils.calculate_win_chance()`):
```python
base_chance = 0.5 + (level_diff * 0.10)
base_chance += energy_modifier  # From low energy penalties
base_chance += group_modifier   # From mob encounters
base_chance += get_prestige_win_bonus(prestige_level)
base_chance += class_bonus      # From class system
base_chance = max(0.05, min(0.95, base_chance))  # Clamp to 5%-95%
```

**Level Diff**: `player_level - monster_level` (each level = +10% win chance)

**Energy Modifier**: Negative modifier when energy is low (see energy penalties config)

**Challenge Path Modifier**: `win_chance_modifier` from challenge path

### Solo Quest Flow

1. **Cooldown check** (default 5 minutes)
2. **Energy check** (requires 1 energy if system enabled)
3. **Injury recovery check** (auto-clear expired injuries)
4. **Boss hunt notification** (if Big Tony returned)
5. **Monster spawn** (80% chance, else 10 XP)
6. **Boss encounter chance** (10% at levels 17-20, unless hardcore)
7. **Deduct energy** (1 energy)
8. **Select monster** (based on level + difficulty mod)
9. **Apply boss hunt buff** (reduce monster level if active)
10. **Check for rare spawn** (10% chance, 2x XP)
11. **Calculate win chance** (energy penalties, class bonuses, challenge modifiers)
12. **Apply active effects** (lucky charm, dungeon relic)
13. **Roll combat** (RNG vs win chance)
14. **Grant XP or deduct XP** (win = full XP, loss = 25% XP lost)
15. **Apply injury** (loss only, 50% chance with reductions)
16. **Item drops** (medkits, lucky charms, armor shards, XP scrolls, energy potions)
17. **Boss hunt clue drop** (15% chance on win)
18. **Hardcore damage** (if hardcore mode, check for death)

**Code**: `quest_core.handle_solo_quest()`

### Mob Encounters

**Flow**:
1. Player uses `!quest mob` (or `!mob`)
2. **Global cooldown check** (1 hour default per channel)
3. **Energy check** (1 energy required)
4. **Legend boss chance** (15% to spawn legend instead of normal mob)
5. **Create mob window** (60 seconds default for players to join)
6. **Announce mob** (ping opted-in users)
7. Players join with `!quest join` (or `!join`)
8. **Window closes** → combat resolves
9. **Calculate group average level**
10. **Group bonus** (+5% win per additional player after first)
11. **XP split** (divided evenly, prestige bonuses apply per player)
12. **Rare spawn multiplier** (2x XP if rare)

**State**: `active_mob` holds `{channel, monster, monster_level, is_rare, participants, initiator, close_epoch}`

**Mob Lock**: Uses `quest_module.mob_lock` (threading.Lock) to prevent race conditions

**Code**: `quest_combat.cmd_mob_start()`, `quest_combat.cmd_mob_join()`, `quest_combat.close_mob_window()`

### Boss Encounters

**Random Boss Encounters**:
- 10% chance at levels 17-20 during solo quests
- NOT triggered in hardcore mode (opt-in only via `!mob`)
- Uses longer join window (5 minutes vs 60 seconds)

**Boss Differences**:
- Marked with `is_boss: True` in mob data
- +3 levels higher than player
- Typically from `boss_monsters` list in content

---

## Items & Inventory

### Item Types

**Medkits**: `!quest medkit` or `!medkit` - clears all injuries
- Can target another player: `!quest medkit username`
- Hardcore mode: can also heal 50% max HP even if uninjured; blocked for targets on challenge paths that forbid medkits
- Increments `challenge_stats.medkits_used_this_prestige`

**Energy Potions**: `!quest use energy_potion` - restores 3 energy (default)
- Cannot exceed max energy

**Lucky Charms**: `!quest use lucky_charm` - +10% win chance next fight
- Stored as active effect with `expires: "next_fight"`

**Armor Shards**: `!quest use armor_shard` - reduces injury chance for 3 fights
- Stores `remaining_fights` counter
- Provides 25% injury reduction (stacks additively)

**XP Scrolls**: `!quest use xp_scroll` - 2x XP on next win
- Stored as active effect with `expires: "next_win"`

**Dungeon Relics**: `!quest use dungeon_relic <count> [solo|boss]` - guaranteed wins
- 5 solo charges per relic
- 4 relics → 1 boss sigil (auto-win mob/boss)
- Default mode: auto-convert to sigils in groups of 4, rest to solo
- `solo` mode: bank only solo victories
- `boss` mode: forge sigils only

### Dungeon Search System

- `!quest search [n]` spends energy (default 1 each) to bank counter-items for dungeons; up to 20 searches per command.
- Searches auto-clear expired injuries and migrate old formats; if any active injuries remain the search is blocked and state is saved.
- Outcomes: find counter-item (added to dungeon cache), spring trap (lose XP per `injury_xp_min/max` and -1 energy), or nothing (flavor).
- Overall find chance pulled from `search_system.dungeon_item_chance` or legacy drop knobs via `_get_dungeon_item_find_chance`.

### Item Drops

**Win Drops** (35% base chance, +20% on crit):
- Medkit: 25% of drop chance
- Energy Potion: 30% of drop chance
- Lucky Charm: 20% of drop chance
- Armor Shard: 20% of drop chance
- XP Scroll: 20% of drop chance
- **Can drop multiple items per fight!**

**Loss Drops** (10% chance):
- Medkit only

**Dungeon Cache Drops** (Search system):
- Players use `!quest search` to find dungeon items
- Items stored in `dungeon_state.stored_items`
- Used during `!dungeon` runs

**Code**: `quest_core.try_drop_item_from_combat()`

---

## Themes & Content

### Theme System

**Theme Selection**:
1. Check `quest.theme` config
2. Fall back to `default_theme` from `quest_content.json`
3. Validate theme exists, fall back to first available

**Loading**: `quest_core.load_content(quest_module)` called in `__init__`

**Accessing Content**: `quest_module._get_content(key, channel, default)`
- Supports dotted paths: `"boss_hunt.bosses"`
- Falls back to config if not in content JSON

### Creating a New Theme

1. **Add theme to `quest_content.json`**:
```json
"themes": {
  "my_theme": {
    "theme": {
      "name": "my_theme",
      "background": "#...",
      "foreground": "#...",
      "accent": "#...",
      ...
    },
    "world_lore": [...],
    "story_beats": {
      "openers": [...],
      "actions": [...]
    },
    "monsters": [...],
    "boss_monsters": [...],
    "classes": {...},
    "injury_system": {...},
    "boss_hunt": {...}
  }
}
```

2. **Set theme in config**:
```yaml
quest:
  theme: my_theme
```

3. **Reload content**: `!quest reload` (admin command)

### Web UI Theme Support

The quest web dashboard (`web/quest_web.py`) reads theme metadata from `quest_content.json`:
- Background/foreground colors
- Prestige tier icons and colors
- Website title and subtitle
- Footer text

---

## Common Patterns

### Pattern 1: Reading Player Data

```python
# Always get player via quest_progression
from . import quest_progression

user_id = quest_module.bot.get_user_id(username)
player = quest_progression.get_player(quest_module, user_id, username)

# Check and clear injuries
player, recovery_msg = quest_utils.check_and_clear_injury(player)
if recovery_msg:
    quest_module.safe_reply(connection, event, recovery_msg)

# Modify player
player["xp"] += 100

# Save player
players = quest_module.get_state("players", {})
players[user_id] = player
quest_module.set_state("players", players)
quest_module.save_state()
```

### Pattern 2: Granting XP

```python
from . import quest_progression

# Grant XP and get level-up messages
messages = quest_progression.grant_xp(
    quest_module,
    user_id,
    username,
    xp_amount,
    is_win=True,  # For win streak tracking
    is_crit=False  # For crit notifications
)

# Send messages to user
for msg in messages:
    quest_module.safe_reply(connection, event, msg)
```

### Pattern 3: Applying Challenge Path Modifiers

```python
# Get player's active challenge path
challenge_path = player.get("challenge_path")
if challenge_path:
    path_data = quest_module.challenge_paths.get("paths", {}).get(challenge_path, {})
    modifiers = path_data.get("modifiers", {})

    # Apply XP multiplier
    xp_mult = modifiers.get("xp_gain_multiplier", 1.0)
    total_xp = base_xp * xp_mult

    # Apply win chance modifier
    win_mod = modifiers.get("win_chance_modifier", 0.0)
    win_chance += win_mod
```

### Pattern 4: Handling Active Effects

```python
from . import quest_combat

# Apply effects to combat (before determining outcome)
win_chance_modified, xp_modified, effect_msgs = quest_combat.apply_active_effects_to_combat(
    player, base_win_chance, base_xp, is_win=False
)

# Show pre-combat messages
for msg in effect_msgs:
    if "lucky charm" in msg.lower():
        quest_module.safe_reply(connection, event, msg)

# Determine outcome
win = random.random() < win_chance_modified

# Re-apply effects for XP scroll (only activates on win)
_, total_xp, xp_effect_msgs = quest_combat.apply_active_effects_to_combat(
    player, base_win_chance, base_xp, is_win=win
)

# Show post-combat messages
for msg in xp_effect_msgs:
    if "scroll" in msg.lower():
        quest_module.safe_reply(connection, event, msg)

# Consume effects after combat
quest_combat.consume_combat_effects(player, is_win=win)
```

### Pattern 5: Getting Content

```python
# Get themed monsters list
monsters = quest_module._get_content("monsters", event.target, default=[])

# Get boss hunt config
bosses = quest_module._get_content("boss_hunt.bosses", event.target, default=[])

# Get injury config with overrides
injury_config = quest_module.get_injury_config(event.target)
```

### Pattern 6: Checking Boss Hunt Buff

```python
from . import quest_boss_hunt

# Check if buff is active
is_active, buff = quest_boss_hunt.is_buff_active(quest_module)

if is_active:
    # Apply buff to combat
    modified_level, modified_xp, buff_msg = quest_boss_hunt.apply_boss_hunt_buff_to_combat(
        quest_module, monster_level, base_xp, event.target
    )

    # Show buff message
    if buff_msg:
        quest_module.safe_reply(connection, event, buff_msg)
```

---

## Common Pitfalls

### ❌ Pitfall 1: Not Using get_player()

```python
# WRONG - doesn't initialize defaults
players = quest_module.get_state("players", {})
player = players.get(user_id, {})

# CORRECT
from . import quest_progression
player = quest_progression.get_player(quest_module, user_id, username)
```

### ❌ Pitfall 2: Forgetting to Check/Clear Injuries

```python
# WRONG - doesn't auto-clear expired injuries
player = quest_progression.get_player(quest_module, user_id, username)
# Proceed with player...

# CORRECT
player = quest_progression.get_player(quest_module, user_id, username)
player, recovery_msg = quest_utils.check_and_clear_injury(player)
if recovery_msg:
    quest_module.safe_reply(connection, event, recovery_msg)
```

### ❌ Pitfall 3: Hardcoding Max Energy

```python
# WRONG - ignores prestige bonuses and challenge modifiers
max_energy = 10

# CORRECT
from . import quest_progression
max_energy = quest_progression.get_player_max_energy(quest_module, player, event.target)
```

### ❌ Pitfall 4: Not Handling Old Injury Format

```python
# WRONG - assumes active_injuries list exists
for injury in player["active_injuries"]:
    ...

# CORRECT - migrate old format
if 'active_injury' in player:
    player['active_injuries'] = [player['active_injury']]
    del player['active_injury']

if 'active_injuries' in player and player['active_injuries']:
    for injury in player['active_injuries']:
        ...
```

### ❌ Pitfall 5: Using eval() for XP Formula

```python
# WRONG - security risk!
xp = eval(xp_formula.replace('level', str(level)))

# CORRECT - use safe calculation
from . import quest_utils
xp = quest_utils.calculate_xp_for_level(quest_module, level)
```

### ❌ Pitfall 6: Forgetting Mob Lock

```python
# WRONG - race conditions possible
active_mob = quest_module.get_state("active_mob")
if active_mob:
    ...

# CORRECT
with quest_module.mob_lock:
    active_mob = quest_module.get_state("active_mob")
    if active_mob:
        ...
    quest_module.set_state("active_mob", new_mob_data)
    quest_module.save_state()
```

### ❌ Pitfall 7: Not Saving Player After Modification

```python
# WRONG - changes lost!
player["xp"] += 100

# CORRECT
player["xp"] += 100
players = quest_module.get_state("players", {})
players[user_id] = player
quest_module.set_state("players", players)
quest_module.save_state()
```

### ❌ Pitfall 8: Timezone-Naive Datetimes

```python
# WRONG
from datetime import datetime
now = datetime.now()

# CORRECT
from .constants import UTC
from datetime import datetime
now = datetime.now(UTC)
```

---

## Quick Reference

### State Keys

```python
# In games.json under modules.quest
"players"               # Main player data: {user_id: player_dict}
"active_mob"            # Current mob encounter
"player_classes"        # {user_id: class_name}
"class_change_prestige" # {user_id: prestige_when_last_changed}
"legend_bosses"         # {user_id: {username, transcendence}}
"mob_cooldowns"         # {channel: cooldown_expires_timestamp}
"mob_pings"             # {channel: {user_id: username}}
"boss_hunt"             # Boss hunt state
"web_link_tokens"       # {token: {user_id, username, issued_at, expires_at}}
```

### Important Functions

```python
# Progression
quest_progression.get_player(quest_module, user_id, username)
quest_progression.grant_xp(quest_module, user_id, username, xp, is_win, is_crit)
quest_progression.deduct_xp(quest_module, user_id, username, xp)
quest_progression.get_player_max_energy(quest_module, player, channel)
quest_progression.get_prestige_win_bonus(prestige)
quest_progression.get_prestige_xp_bonus(prestige)

# Utils
quest_utils.calculate_xp_for_level(quest_module, level)
quest_utils.calculate_win_chance(player_level, monster_level, energy_mod, group_mod, prestige, class_bonus)
quest_utils.check_and_clear_injury(player_data)
quest_utils.apply_injury(quest_module, user_id, username, channel, is_medic_quest, injury_reduction, class_injury_reduction)
quest_utils.get_class_bonuses(quest_module, user_id, player_level)
quest_utils.format_timedelta(future_datetime)
quest_utils.to_roman(number)

# Combat
quest_combat.apply_active_effects_to_combat(player, base_win_chance, base_xp, is_win)
quest_combat.consume_combat_effects(player, is_win)
quest_combat.get_injury_reduction(player)

# Boss Hunt
quest_boss_hunt.initialize_boss_hunt_state(quest_module)
quest_boss_hunt.is_buff_active(quest_module)
quest_boss_hunt.apply_boss_hunt_buff_to_combat(quest_module, player_level, base_xp, channel)
quest_boss_hunt.try_drop_clue(quest_module, connection, event, username, channel)

# Core
quest_core.load_content(quest_module)
quest_core.load_challenge_paths(quest_module)
quest_core.save_challenge_paths(quest_module)
```

### Command Patterns

```python
# Main commands
!quest [easy|normal|hard]  # Solo quest
!quest search              # Find dungeon items
!quest use <item>          # Use consumable item
!quest medic               # Medic quest (no injury risk)
!quest profile [username]  # View profile
!quest story               # World lore
!quest class [class_name]  # View/change class
!quest top                 # Leaderboard
!quest prestige [challenge]# Prestige
!quest transcend           # Transcend (max prestige only)
!quest hardcore            # Enter hardcore mode
!quest ability [name]      # List/use abilities
!quest weblink             # Get web dashboard link

# Mob commands
!quest mob                 # Start mob encounter
!quest join                # Join active mob
!quest mob ping on|off     # Toggle mob notifications

# Boss hunt commands
!quest boss                # Show boss status

# Dungeon commands
!dungeon                   # Start dungeon run
!dungeon nonstop           # Run dungeon without safe havens
!dungeon continue          # Continue from safe haven
!dungeon quit              # Quit dungeon early

# Short aliases
!q, !qe, !qh              # Quest easy/hard
!qp [username]            # Profile
!qi                       # Inventory
!qs                       # Search
!qm                       # Medkit
!qu <item>                # Use item
!qt                       # Leaderboard (top)
!qc [class]               # Class
!mob, !join               # Mob shortcuts
!medkit, !inv             # Legacy shortcuts

# Notes
- `!quest`/`!qu use` and all `!dungeon` commands are allowed via DM even if the module is disabled in the channel (command dispatch special-case).
- `!quest medic` is currently a stub that just replies it is being refactored; rely on medkits instead.
```

### Admin Commands

```python
# Quest content
!quest reload                                # Reload quest_content.json

# Challenge paths
!quest challenge activate <path>             # Activate challenge path
!quest challenge deactivate                  # Deactivate challenge path
!quest challenge list                        # List all paths
!quest challenge reload                      # Reload challenge_paths.json

# Player management
!quest admin ability grant <user> <ability>  # Grant ability
!quest admin ability revoke <user> <ability> # Revoke ability
!quest admin ability list <user>             # List player abilities
!quest admin path set <user> <path>          # Set player's challenge path
!quest admin path clear <user>               # Clear player's challenge path
!quest admin injury add <user> [injury]      # Add injury (random if not specified)
!quest admin injury clear <user>             # Clear all injuries
!quest admin injury list <user>              # List player injuries

# Boss hunt
!quest admin boss spawn                      # Spawn new boss
!quest admin boss damage <amount>            # Deal damage to boss
!quest admin boss buff on|off|status         # Toggle boss buff
```

---

## Development Tips

### Testing Quest Features

1. **Start as new player**: Delete your user from `config/games.json` → `modules.quest.players`
2. **Fast leveling**: Grant yourself XP via admin or edit state file
3. **Test prestige**: Set level to 20, use `!quest prestige`
4. **Test injuries**: Lose fights or use `!quest admin injury add`
5. **Test challenge paths**: Activate path with `!quest challenge activate`, prestige with `!quest prestige challenge`
6. **Test boss hunt**: Use `!quest admin boss spawn` and `!quest admin boss damage`
7. **Test web dashboard**: Run `python3 web/quest_web.py --host 127.0.0.1 --port 8080`

### Debugging

1. **Check debug.log**: `tail -f debug.log`
2. **Inspect state**: `cat config/games.json | jq '.modules.quest'`
3. **Check player**: `cat config/games.json | jq '.modules.quest.players["<user_id>"]'`
4. **Validate content**: Open `quest_content.json` in JSON validator
5. **Check theme**: Look for `[quest] Active theme: <theme_name>` in logs

### Adding New Features

**New Item Type**:
1. Add to `player["inventory"]` defaults in `quest_progression.get_player()`
2. Add drop logic to `quest_core.try_drop_item_from_combat()`
3. Add usage handler in `quest_core.handle_use_item()`
4. Add display to `quest_display.cmd_inventory()` and `handle_profile()`

**New Challenge Path**:
1. Add to `challenge_paths.json` → `paths`
2. Test activation: `!quest challenge activate <path_id>`
3. Test prestige: `!quest prestige challenge`
4. Verify modifiers apply in `quest_core.handle_solo_quest()`

**New Ability**:
1. Add to `challenge_paths.json` → `abilities`
2. Add effect handler in `quest_display.cmd_ability()` (not shown in excerpts)
3. Link to challenge path reward

**New Theme**:
1. Add to `quest_content.json` → `themes`
2. Set `quest.theme` config
3. Reload with `!quest reload`
4. Test web UI theme display

---

## Related Files

- **Web Dashboard**: `web/quest_web.py` - Flask app for quest visualization
- **Config Validator**: `config_validator.py` - Validates quest config
- **Main Architecture**: `docs/LLM_ARCHITECTURE_GUIDE.md` - General bot architecture

---

**When in doubt, grep for examples in `modules/quest_pkg/`!**
