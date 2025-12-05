# Absurdia Module Architecture Guide for LLMs

**Purpose**: This guide provides a comprehensive overview of the Absurdia module's architecture for AI coding assistants. Read this alongside the main LLM_ARCHITECTURE_GUIDE.md when working on Absurdia-related features.

---

## Table of Contents
1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [Database Schema](#database-schema)
4. [Core Systems](#core-systems)
5. [Catching System](#catching-system)
6. [Care System](#care-system)
7. [Arena System](#arena-system)
8. [Combat Engine](#combat-engine)
9. [Economy & Shop](#economy--shop)
10. [Exploration System](#exploration-system)
11. [Common Patterns](#common-patterns)
12. [Common Pitfalls](#common-pitfalls)
13. [Quick Reference](#quick-reference)

---

## Overview

Absurdia is a creature collecting and battling game featuring absurdist, bizarre creatures. Players:
- **Catch creatures** using traps or hand-catching
- **Care for creatures** to boost stats and earn coins (feed, play, pet)
- **Battle in hourly arena tournaments** for coin rewards
- **Explore** for random trap rewards
- **Manage duplicates** by comparing stats and choosing which to keep

Unlike Quest (which uses JSON state), Absurdia uses a **SQLite database** for persistence.

**Key Features**:
- **Rarity tiers**: Common, Uncommon, Rare, Legendary, Feral (hand-caught)
- **Type advantages**: Rock-paper-scissors combat (Sturdy Nonsense > Sharp Weird > Flimsy Chaos)
- **Trap tiers**: Basic, Standard, Premium, Deluxe (higher tier = better rarities)
- **Daily care cap**: Coin rewards limited to 10 care actions per day (resets midnight UTC)
- **Duplicate system**: One of each species per player, must choose to keep/swap
- **Happiness system**: Decays over time, boosts arena stats
- **Auto-collect**: Traps auto-collect 24h after ready time

---

## File Structure

```text
modules/
  absurdia.py                      # Thin wrapper
  absurdia_pkg/
    __init__.py                    # Package init
    absurdia_main.py               # Main Absurdia class, command handlers
    absurdia_db.py                 # Database layer (SQLite)
    absurdia_creatures.py          # Creature generation and care logic
    absurdia_combat.py             # Combat engine (turn-based battles)
    absurdia_exploration.py        # Exploration flavor text and rewards

config/
  absurdia.db                      # SQLite database (created on first run)
  absurdia_creatures.json          # Creature templates (species, stats, flavor text)
```

### Module Responsibilities

- **`absurdia_main.py`**: Main `Absurdia` class, inherits from `SimpleCommandModule`, registers commands, delegates to subsystems
- **`absurdia_db.py`**: `AbsurdiaDatabase` class - all database operations (players, creatures, traps, arena, inventory)
- **`absurdia_creatures.py`**: `CreatureGenerator` (stat rolling, rarity selection) and `CreatureCare` (care cooldowns, rewards, happiness decay)
- **`absurdia_combat.py`**: `CombatEngine` - turn-based battle simulation, type advantages, damage calculation
- **`absurdia_exploration.py`**: `ExplorationManager` - flavor text and trap drop rolls

---

## Database Schema

Absurdia uses **SQLite** (`config/absurdia.db`) with the following tables:

### players

```sql
CREATE TABLE players (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    coins INTEGER DEFAULT 1000,
    total_arena_wins INTEGER DEFAULT 0,
    total_arena_losses INTEGER DEFAULT 0,
    current_win_streak INTEGER DEFAULT 0,
    best_win_streak INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_daily_reset TIMESTAMP,
    daily_care_count INTEGER DEFAULT 0,
    last_explored TIMESTAMP
)
```

**Starting coins**: 300 (set in `get_player()`)

### creatures

```sql
CREATE TABLE creatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,              -- Species name
    nickname TEXT,                    -- Player-set nickname
    rarity TEXT NOT NULL,             -- Common/Uncommon/Rare/Legendary/Feral
    creature_type TEXT NOT NULL,      -- Sturdy Nonsense/Sharp Weird/Flimsy Chaos

    base_hp INTEGER NOT NULL,
    base_attack INTEGER NOT NULL,
    base_defense INTEGER NOT NULL,
    base_speed INTEGER NOT NULL,

    bonus_hp INTEGER DEFAULT 0,       -- Stat bonuses from care
    bonus_attack INTEGER DEFAULT 0,
    bonus_defense INTEGER DEFAULT 0,
    bonus_speed INTEGER DEFAULT 0,

    happiness INTEGER DEFAULT 50,     -- 0-100, affects arena stats
    last_fed TIMESTAMP,
    last_played TIMESTAMP,
    last_petted TIMESTAMP,

    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,

    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_to_arena BOOLEAN DEFAULT 0,

    FOREIGN KEY (owner_id) REFERENCES players(user_id),
    UNIQUE(owner_id, name)            -- One of each species per player
)
```

**Key constraint**: `UNIQUE(owner_id, name)` enforces one-per-species rule

### pending_catches

Holds catches that need duplicate resolution.

```sql
CREATE TABLE pending_catches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    creature_name TEXT NOT NULL,

    new_rarity TEXT NOT NULL,
    new_hp INTEGER NOT NULL,
    new_attack INTEGER NOT NULL,
    new_defense INTEGER NOT NULL,
    new_speed INTEGER NOT NULL,
    new_creature_type TEXT NOT NULL,

    trap_quality TEXT NOT NULL,       -- For refund calculation

    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,    -- 30 second timeout

    FOREIGN KEY (owner_id) REFERENCES players(user_id)
)
```

**Expiry**: Pending catches expire after 30 seconds (configurable via `duplicate_handling.comparison_timeout_seconds`)

### active_traps

Tracks set traps and their ready times.

```sql
CREATE TABLE active_traps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    trap_quality TEXT NOT NULL,       -- basic/standard/premium/deluxe
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMP NOT NULL,
    collected BOOLEAN DEFAULT 0,
    auto_announced BOOLEAN DEFAULT 0, -- For auto-collect notifications

    FOREIGN KEY (owner_id) REFERENCES players(user_id)
)
```

**One trap per player**: Enforced in `_cmd_catch()` handler

**Auto-collect**: Scheduled task runs every 15 minutes, collects traps ready for 24+ hours

### arena_matches

Historical record of arena battles.

```sql
CREATE TABLE arena_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,
    creature1_id INTEGER NOT NULL,
    creature2_id INTEGER NOT NULL,
    winner_id INTEGER,

    creature1_hp_remaining INTEGER,
    creature2_hp_remaining INTEGER,
    total_rounds INTEGER,
    type_advantage TEXT,              -- e.g., "creature1" if creature1 had type advantage

    fought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (creature1_id) REFERENCES creatures(id),
    FOREIGN KEY (creature2_id) REFERENCES creatures(id),
    FOREIGN KEY (winner_id) REFERENCES creatures(id)
)
```

### inventory

Player items (traps).

```sql
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    item_type TEXT NOT NULL,          -- 'trap'
    item_name TEXT NOT NULL,          -- 'basic', 'standard', etc.
    quantity INTEGER DEFAULT 1,

    FOREIGN KEY (owner_id) REFERENCES players(user_id),
    UNIQUE(owner_id, item_type, item_name)
)
```

### training_sessions

Historical record of stat training (not currently used in UI, but tracked).

```sql
CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creature_id INTEGER NOT NULL,
    stat_trained TEXT NOT NULL,
    improvement INTEGER NOT NULL,
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (creature_id) REFERENCES creatures(id)
)
```

---

## Core Systems

### 1. Creature Templates

Defined in `config/absurdia_creatures.json`.

**Structure**:
```json
{
  "creatures": [
    {
      "name": "sentient potato",
      "rarity": "Common",
      "type": "Sturdy Nonsense",
      "hp": [60, 80],           // Min-max stat ranges
      "attack": [15, 20],
      "defense": [12, 18],
      "speed": [10, 15],
      "feed_text": "...",       // Flavor text
      "play_text": "...",
      "pet_text": "...",
      "catch_text": "...",
      "hand_catch_success": "...",
      "hand_catch_fail": ["...", "..."]
    }
  ]
}
```

**Stats**: Actual stats are **rolled randomly** within the ranges when creature is generated

**Templates loading**: Loaded in `AbsurdiaDatabase.__init__()` → `_load_templates()`

### 2. Rarity System

**Rarity Tiers**: Common, Uncommon, Rare, Legendary, Feral

**Trap Quality Rarity Weights** (see `CreatureGenerator.RARITY_WEIGHTS`):

```python
'basic': {
    'Common': 0.70,
    'Uncommon': 0.28,
    'Rare': 0.02,
    'Legendary': 0.00
},
'standard': {
    'Common': 0.50,
    'Uncommon': 0.35,
    'Rare': 0.14,
    'Legendary': 0.01
},
'premium': {
    'Common': 0.30,
    'Uncommon': 0.40,
    'Rare': 0.25,
    'Legendary': 0.05
},
'deluxe': {
    'Common': 0.20,
    'Uncommon': 0.40,
    'Rare': 0.30,
    'Legendary': 0.10
}
```

**Feral**: Special rarity for hand-caught creatures (always Common species, 60% stat penalty)

### 3. Type Advantages

Rock-paper-scissors combat:

```python
TYPE_ADVANTAGES = {
    'Sturdy Nonsense': 'Sharp Weird',   # Sturdy beats Sharp
    'Sharp Weird': 'Flimsy Chaos',      # Sharp beats Flimsy
    'Flimsy Chaos': 'Sturdy Nonsense'   # Flimsy beats Sturdy
}
```

**Type multiplier**: 1.3x damage when attacker has advantage

### 4. Happiness System

**Range**: 0-100

**Starting happiness**: 50 (new catches)

**Decay**:
- **Normal**: 1 happiness per 6 hours (configurable via `happiness_decay.normal_hours`)
- **In arena**: 1 happiness per 3 hours (configurable via `happiness_decay.arena_hours`)

**Decay calculation**: Based on time since last care action (feed/play/pet) or caught_at

**Happiness gains**:
- Feed: +5
- Play: +3
- Pet: +2

**Arena bonuses** (see `CombatEngine.calculate_effective_stats()`):
- Effective HP = Base HP + Bonus HP + (Happiness / 10)
- Effective Attack = Base Attack + Bonus Attack + (Happiness / 20)
- Effective Defense = Base Defense + Bonus Defense + (Happiness / 20)
- Speed is NOT affected by happiness

**Maintenance**: At 100 happiness, +10 HP and +5 ATK/DEF in arena

---

## Catching System

### Hand-Catching

**Command**: `!catch` (no trap specified)

**Success rate**: 5% (configurable via `hand_catch.success_rate`)

**Stat penalty**: 60% (configurable via `hand_catch.stat_penalty`)

**Rarity**: Always "Feral" (only Common species can be hand-caught)

**Cost**: Free

**Use case**: Emergency catching when out of traps/coins

### Trap-Catching

**Command**: `!catch <trap_type>`

**Process**:
1. Player buys trap from shop (`!buy basic`)
2. Player sets trap (`!catch basic`)
3. Trap has timer (3h-24h depending on quality)
4. Player checks trap when ready (`!check`)
5. Creature is generated with rarity based on trap quality

**Trap Tiers** (config defaults):

| Trap | Price | Timer | Rarities |
|------|-------|-------|----------|
| Basic | 50 coins | 3h | Common/Uncommon only |
| Standard | 100 coins | 6h | Common/Uncommon/Rare |
| Premium | 200 coins | 12h | All rarities |
| Deluxe | 400 coins | 24h | All rarities (best legendary odds) |

**Config keys**:
- `trap_prices`: `{basic: 50, standard: 100, premium: 200, deluxe: 400}`
- `trap_timers`: `{basic: 10800, standard: 21600, premium: 43200, deluxe: 86400}` (seconds)

**Auto-collect**: Traps ready for 24+ hours auto-collect via scheduled task (`_check_auto_collect_traps()`)

**Notifications**: Auto-collected traps announce in channel if player has been active recently

**Auto-collect duplicates**: Auto-collected duplicates create pending catches with a long timeout (7 days) instead of 30 seconds and are marked as auto-announced for later resolution.

### Duplicate Handling

**One-per-species rule**: Players can only own one of each creature species

**Duplicate flow**:
1. Player catches duplicate (via hand-catch or trap)
2. System creates `pending_catch` record (expires in 30 seconds)
3. Shows comparison UI with current vs new stats
4. Player uses `!keep` or `!swap` to choose new creature
5. If timeout expires, old creature is kept by default

**Comparison UI**: Shows base stats, happiness, W/L record, type

**Refund**: When keeping new creature, player gets partial refund (50% of trap cost, configurable via `duplicate_handling.trap_refund_percent`)

**Blocking**: Players with pending catches are blocked from other commands (`_check_and_show_pending_catch()`)

---

## Care System

Care actions boost creature stats, grant happiness, and earn coins (with daily cap).

### Care Actions

**Feed** (`!feed <id>`):
- **Cost**: 10 coins (configurable via `care_costs.feed`)
- **Cooldown**: 4 hours (configurable via `care_cooldowns.feed`)
- **Earnings**: Random 5-10 coins (net -5 to 0 after cost)
- **Happiness**: +5
- **Stat boost**: +1 to +3 to random stat (HP/ATK/DEF/SPD)

**Play** (`!play <id>`):
- **Cost**: 5 coins (configurable via `care_costs.play`)
- **Cooldown**: 2 hours (configurable via `care_cooldowns.play`)
- **Earnings**: Random 3-7 coins (net -2 to +2 after cost)
- **Happiness**: +3
- **Stat boost**: +1 to +2 to ATK or SPD only

**Pet** (`!pet <id>`):
- **Cost**: FREE
- **Cooldown**: 1 hour (configurable via `care_cooldowns.pet`)
- **Earnings**: Random 2-4 coins
- **Happiness**: +2
- **Stat boost**: None

### Daily Care Cap

**Purpose**: Prevent infinite coin farming via care spam

**Config key**: `daily_care_cap` (default: 10)

**Reset**: Midnight UTC

**Behavior**:
- Tracks care actions per player per day (`daily_care_count`)
- First 10 actions per day grant coin rewards
- After cap, care actions only cost coins (no earnings)
- Happiness and stat boosts still apply

**Display**: Shows "(daily care cap reached: 0 coins earned)" when capped

### Care Restrictions

**Cannot care for**:
- Creatures in arena queue (must `!withdraw` first)

**Cooldowns**: Per-creature, per-action type

**Cooldown display**: Shows remaining time in hours/minutes

---

## Training System

Permanent stat boosts via training items.

**Items & Sources**:
- Shop items: `hp`, `power`, `shield`, `speed` (prices from `training_prices`); also drop from `!explore` (5% total, 1.25% each).
- Inventory stored in DB under item_type `training`.

**Command**: `!train <id> <hp|power|shield|speed>`
- Costs one matching training item; errors if you don’t own it.
- Grants +5 to the corresponding bonus stat, capped at +50 per stat.
- Records a row in `training_sessions` (audit trail).

**Display**: Shop shows training items; `!stats` and arena queue include bonuses in totals.

**Notes**:
- Training works while the creature is not owned by someone else and ignores care cooldowns.
- Inventory mutations and stat updates are wrapped in DB lock to avoid races.

---

## Arena System

Hourly tournaments where creatures battle for coins.

### Arena Flow

1. Players submit creatures to queue (`!submit <id>`)
2. **One creature per player** in queue at a time
3. **At top of every hour**, scheduled task runs (`_run_hourly_arena()`)
4. Creatures are paired randomly (if odd number, one sits out)
5. Battles are simulated via `CombatEngine.simulate_battle()`
6. Winners/losers earn coins and W/L records update
7. Creatures are withdrawn from queue automatically

### Arena Rewards

**Win**: +150 coins (default, configurable via `arena.win_reward`)

**Loss**: +30 coins (default, configurable via `arena.loss_reward`)

**Bye**: If odd number of entrants, one creature gets a bye win and earns `arena_rewards.bye` coins (default 50).

### Submission Rules

**One submission per player**: Cannot submit while another creature is in queue

**No care while submitted**: Must withdraw before feeding/playing/petting

**Happiness decay**: Creatures in arena decay happiness faster (3h vs 6h)

### Arena Commands

- `!submit <id>` - Submit creature to queue
- `!withdraw` - Withdraw creature from queue
- `!arena` - View current arena queue

### Tournament Scheduling

**Frequency**: Every hour at :00 (configurable via `schedule.every().hour.at(":00")`)

**Tag**: `absurdia-arena_close` (for schedule cancellation)

**Tournament ID**: Incremented counter stored in state (`last_tournament_id`)

---

## Combat Engine

Turn-based battle simulation.

### Battle Mechanics

**Turn order**: Higher speed creature attacks first (random if tied)

**Damage formula**:
```python
BASE_MULTIPLIER = 8
base_damage = (attacker_ATK / defender_DEF) * BASE_MULTIPLIER * type_multiplier
final_damage = base_damage * random(0.95, 1.05)  # 5% variance
final_damage = max(1, round(final_damage))       # Minimum 1 damage
```

**Type multiplier**: 1.3 if attacker has type advantage, else 1.0

**Rounds**: Alternating attacks until one creature reaches 0 HP (max 100 rounds safety limit)

### Effective Stats

Stats used in combat include happiness bonuses:

```python
effective_hp = base_hp + bonus_hp + (happiness // 10)
effective_attack = base_attack + bonus_attack + (happiness // 20)
effective_defense = base_defense + bonus_defense + (happiness // 20)
effective_speed = base_speed + bonus_speed
```

**Happiness impact**: 100 happiness = +10 HP, +5 ATK, +5 DEF (speed unaffected)

### Battle Results

**Returns**:
```python
{
    'winner': creature_dict,
    'loser': creature_dict,
    'rounds': int,
    'battle_log': List[str],        # Full combat log
    'final_hp': {
        creature1_id: hp_remaining,
        creature2_id: hp_remaining
    }
}
```

**Battle log**: Full turn-by-turn record including type advantages, damage, HP remaining

**Summary**: Short format for IRC display (winner, loser, rounds, final HP)

---

## Economy & Shop

### Starting Coins

New players start with **300 coins** (set in `AbsurdiaDatabase.get_player()`)

### Shop Items

**Traps** (default prices):
- Basic: 50 coins
- Standard: 100 coins
- Premium: 200 coins
- Deluxe: 400 coins

**Training items** (default prices via `training_prices`):
- `hp` (HP Tonic), `power` (Power Crystal), `shield` (Shield Fragment), `speed` (Speed Charm) — +5 to the corresponding bonus stat, max +50

**Commands**:
- `!shop` - View available items and prices
- `!buy <trap_type> [quantity]` - Purchase traps
- `!buy <training_item> [quantity]` - Purchase training items
- `!train <id> <hp|power|shield|speed>` - Consume training item to boost stats
- `!inventory` - View owned items

### Coin Sources

1. **Care rewards**: Feed (net -5 to 0), Play (net -2 to +2), Pet (+2 to +4)
2. **Arena wins**: +150 coins
3. **Arena losses**: +30 coins
4. **Duplicate refunds**: 50% of trap cost when swapping
5. **Exploration**: Rare trap or training item drops (no coins but free items)

### Coin Sinks

1. **Trap purchases**: 50-400 coins
2. **Training item purchases**: Prices from `training_prices` (e.g., 200 each by default)
3. **Care costs**: Feed (10 coins), Play (5 coins), Pet (free)

### Daily Care Cap Impact

**First 10 care actions per day**: Full coin rewards

**After cap**: Only pay costs, no earnings (prevents infinite farming)

---

## Exploration System

**Command**: `!explore`

**Cooldown**: 4 hours (configurable via exploration cooldown check in handler)

**Purpose**: Find free traps via absurdist flavor text

### Flavor Text

40 absurdist exploration messages (see `ExplorationManager.FLAVOR_TEXTS`):
- "You wander into a forest of upside-down trees. You find nothing but vertigo."
- "You stare into the abyss. It blinks."
- "You find a rock that looks suspiciously like your mother-in-law."
- ...etc.

**Random selection**: One flavor text shown per exploration

### Rewards

**Drop rates** (see `ExplorationManager.roll_exploration_reward()`):
- Traps (10.5% total):
  - Premium trap: 0.5%
  - Standard trap: 2.0%
  - Basic trap: 8.0%
- Training items (5% total, 1.25% each for hp/power/shield/speed)
- Nothing: 84.5%

**Display**: Shows flavor text, then "Wait! You found a <item>!" if rewarded

---

## Common Patterns

### Pattern 1: Getting Player Data

```python
# Always use get_player() - creates if doesn't exist
user_id = self.bot.get_user_id(username)
player = self.db.get_player(user_id, username)

# Access player data
coins = player['coins']
```

### Pattern 2: Getting Creature Data

```python
# Get single creature by ID
creature = self.db.get_creature(creature_id)

# Verify ownership
if creature['owner_id'] != user_id:
    self.safe_reply(connection, event, "That's not your creature!")
    return True

# Get all player's creatures
creatures = self.db.get_player_creatures(user_id)
```

### Pattern 3: Updating Coins

```python
# Add coins
new_balance = self.db.update_player_coins(user_id, 50)  # +50

# Subtract coins
new_balance = self.db.update_player_coins(user_id, -50)  # -50

# Check balance first
player = self.db.get_player(user_id, username)
if player['coins'] < cost:
    self.safe_reply(connection, event, "Not enough coins!")
    return True
```

### Pattern 4: Checking Daily Care Cap

```python
config = self.bot.config.get('absurdia', {})
daily_care_cap = config.get('daily_care_cap', 10)

# Check and reset if needed (new day)
current_care_count = self.db.check_and_reset_daily_care(user_id)

# Calculate rewards
net_coins, happiness_gain, stat_gain = self.care.calculate_care_reward('feed')

# Apply cap
if current_care_count >= daily_care_cap:
    coins_earned = -cost  # Only pay cost, no earnings
    cap_message = " (daily care cap reached: 0 coins earned)"
else:
    coins_earned = net_coins
    cap_message = ""

# Increment count if under cap
if current_care_count < daily_care_cap:
    self.db.increment_daily_care(user_id)
```

### Pattern 5: Checking Care Cooldown

```python
# Check if can care (not in arena)
can_care, error_msg = self.care.can_care_for(creature)
if not can_care:
    self.safe_reply(connection, event, error_msg)
    return True

# Check cooldown
can_feed, cooldown_msg = self.care.check_care_cooldown(creature, 'feed')
if not can_feed:
    self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cooldown_msg}")
    return True
```

### Pattern 6: Handling Pending Catches

```python
# Check for pending catch before allowing other commands
if self._check_and_show_pending_catch(connection, event, username, user_id):
    return True  # Blocked, pending catch shown

# Continue with command...
```

### Pattern 7: Generating Creatures

```python
# From trap
creature_name, rarity, creature_type, hp, attack, defense, speed, template = \
    self.generator.generate_creature(trap_quality)

# Hand-catch attempt
result = self.generator.hand_catch_attempt(success_rate, stat_penalty)
if not result:
    # Failed
    self.safe_reply(connection, event, "You failed to catch it!")
    return True

creature_name, rarity, creature_type, hp, attack, defense, speed, template = result
```

### Pattern 8: Simulating Combat

```python
# Get creatures
creature1 = self.db.get_creature(creature1_id)
creature2 = self.db.get_creature(creature2_id)

# Simulate battle
battle_result = self.combat.simulate_battle(creature1, creature2)

# Get winner/loser
winner = battle_result['winner']
loser = battle_result['loser']

# Format for display
summary = self.combat.format_battle_summary(battle_result, include_full_log=False)
self.safe_reply(connection, event, summary)
```

---

## Common Pitfalls

### ❌ Pitfall 1: Not Using get_player()

```python
# WRONG - doesn't create player if missing
players = self.db.get_state("players", {})
player = players.get(user_id)

# CORRECT
player = self.db.get_player(user_id, username)
```

### ❌ Pitfall 2: Forgetting to Check Pending Catches

```python
# WRONG - allows commands while pending catch exists
def _cmd_creatures(self, ...):
    creatures = self.db.get_player_creatures(user_id)
    # ... show creatures

# CORRECT
def _cmd_creatures(self, ...):
    if self._check_and_show_pending_catch(connection, event, username, user_id):
        return True  # Blocked
    creatures = self.db.get_player_creatures(user_id)
    # ... show creatures
```

### ❌ Pitfall 3: Not Applying Daily Care Cap

```python
# WRONG - gives infinite coins
net_coins = self.care.calculate_care_reward('feed')
self.db.update_player_coins(user_id, net_coins)

# CORRECT
current_care_count = self.db.check_and_reset_daily_care(user_id)
net_coins = self.care.calculate_care_reward('feed')

if current_care_count >= daily_care_cap:
    coins_earned = -cost  # Only cost, no earnings
else:
    coins_earned = net_coins
    self.db.increment_daily_care(user_id)

self.db.update_player_coins(user_id, coins_earned)
```

### ❌ Pitfall 4: Not Checking Creature Ownership

```python
# WRONG - allows feeding other players' creatures
creature = self.db.get_creature(creature_id)
# ... feed creature

# CORRECT
creature = self.db.get_creature(creature_id)
if creature['owner_id'] != user_id:
    self.safe_reply(connection, event, "That's not your creature!")
    return True
```

### ❌ Pitfall 5: Not Checking Arena Submission

```python
# WRONG - allows care while in arena
def _cmd_feed(self, ...):
    creature = self.db.get_creature(creature_id)
    # ... feed creature

# CORRECT
def _cmd_feed(self, ...):
    creature = self.db.get_creature(creature_id)
    can_care, error_msg = self.care.can_care_for(creature)
    if not can_care:
        self.safe_reply(connection, event, error_msg)
        return True
```

### ❌ Pitfall 6: Hardcoding Config Values

```python
# WRONG - inflexible
trap_price = 50

# CORRECT
config = self.bot.config.get('absurdia', {})
trap_prices = config.get('trap_prices', {})
trap_price = trap_prices.get('basic', 50)
```

### ❌ Pitfall 7: Forgetting Database Lock

```python
# WRONG - potential race conditions
conn = self.db._get_connection()
cursor = conn.cursor()
cursor.execute('UPDATE ...')
conn.commit()

# CORRECT - use existing methods that handle locking
self.db.update_player_coins(user_id, amount)

# Or if writing new DB method
with self._lock:
    conn = self._get_connection()
    cursor = conn.cursor()
    cursor.execute('UPDATE ...')
    conn.commit()
    conn.close()
```

### ❌ Pitfall 8: Not Handling Happiness Decay

```python
# WRONG - uses raw happiness from DB
happiness = creature['happiness']

# CORRECT - calculate with decay applied
current_happiness = self.care.apply_happiness_decay(creature, is_in_arena=False)
# Note: apply_happiness_decay() does NOT modify database
```

---

## Quick Reference

### Database Methods

```python
# Players
self.db.get_player(user_id, username)
self.db.update_player_coins(user_id, amount)
self.db.get_player_coins(user_id)
self.db.check_and_reset_daily_care(user_id)
self.db.increment_daily_care(user_id)
self.db.update_player_exploration(user_id)

# Creatures
self.db.get_creature(creature_id)
self.db.get_player_creatures(user_id)
self.db.get_all_creatures()
self.db.has_creature_type(user_id, creature_name)
self.db.create_creature(user_id, name, rarity, type, hp, atk, def, spd)
self.db.update_creature_happiness(creature_id, happiness)
self.db.update_creature_care_timestamp(creature_id, care_type)
self.db.set_creature_nickname(creature_id, nickname)
self.db.submit_creature_to_arena(creature_id, True/False)
self.db.get_collection_progress(user_id)  # Returns (owned, total)

# Pending catches
self.db.get_pending_catch(user_id)
self.db.create_pending_catch(user_id, name, rarity, type, hp, atk, def, spd, trap, timeout)
self.db.resolve_pending_catch(user_id, keep_new=True/False, trap_refund_percent)
self.db.clear_expired_pending_catches()

# Traps
self.db.get_active_traps(user_id)
self.db.create_trap(user_id, trap_quality, ready_time)
self.db.mark_trap_collected(trap_id)
self.db.get_traps_ready_for_auto_collect(hours)

# Inventory
self.db.get_inventory(user_id)
self.db.get_item_count(user_id, item_type, item_name)
self.db.add_item(user_id, item_type, item_name, quantity)
self.db.remove_item(user_id, item_type, item_name, quantity)

# Arena
self.db.record_arena_match(tournament_id, battle_result)
self.db.update_creature_win_loss(creature_id, is_win)
self.db.update_player_arena_stats(user_id, is_win)
```

### Generator Methods

```python
# Creature generation
self.generator.generate_creature(trap_quality)  # Returns tuple
self.generator.hand_catch_attempt(success_rate, stat_penalty)  # Returns tuple or None
self.generator.roll_rarity(trap_quality)
self.generator.roll_stats(template)
self.generator.get_catch_flavor(template, is_hand_catch, success)
self.generator.get_care_flavor(template, care_type)
```

### Care Methods

```python
# Care checks
self.care.can_care_for(creature)  # Returns (bool, error_msg)
self.care.check_care_cooldown(creature, care_type)  # Returns (bool, error_msg)
self.care.calculate_care_reward(care_type)  # Returns (coins, happiness, stat)
self.care.apply_happiness_decay(creature, is_in_arena)  # Returns current happiness
```

### Combat Methods

```python
# Combat
self.combat.calculate_effective_stats(creature)
self.combat.get_type_multiplier(attacker_type, defender_type)
self.combat.calculate_damage(attacker_stats, defender_stats, type_mult)
self.combat.simulate_battle(creature1, creature2)
self.combat.format_battle_summary(battle_result, include_full_log)
```

### Exploration Methods

```python
# Exploration
self.exploration.get_exploration_flavor()
self.exploration.roll_exploration_reward()  # Returns trap_type or None
```

### Command Patterns

```python
# Info commands
!absurdia help
!guide [start|next|reset|1|2|3|4]
!creatures (or !menagerie)
!stats <id>
!nickname <id> <name>
!coins

# Shop commands
!shop
!buy <trap_type> [quantity]
!inventory

# Catching commands
!explore
!catch                  # Hand-catch
!catch <trap_type>      # Set trap
!check                  # Check trap status
!keep (or !swap)        # Keep new creature during duplicate

# Care commands
!feed <id>
!play <id>
!pet <id>

# Arena commands
!submit <id>
!withdraw
!arena
```

### Config Keys

```yaml
absurdia:
  trap_prices:
    basic: 50
    standard: 100
    premium: 200
    deluxe: 400

  trap_timers:          # Seconds
    basic: 10800        # 3 hours
    standard: 21600     # 6 hours
    premium: 43200      # 12 hours
    deluxe: 86400       # 24 hours

  hand_catch:
    enabled: true
    success_rate: 0.05  # 5%
    stat_penalty: 0.6   # 60% of normal stats

  duplicate_handling:
    comparison_timeout_seconds: 30
    trap_refund_percent: 0.5

  care_costs:
    feed: 10
    play: 5
    pet: 0

  care_cooldowns:       # Seconds
    feed: 14400         # 4 hours
    play: 7200          # 2 hours
    pet: 3600           # 1 hour

  happiness_decay:
    normal_hours: 6
    arena_hours: 3

  daily_care_cap: 10
  auto_collect_hours: 24

  arena:
    win_reward: 150
    loss_reward: 30
```

---

## Development Tips

### Testing Absurdia Features

1. **Start fresh**: Delete `config/absurdia.db` to reset database
2. **Check DB schema**: Use `sqlite3 config/absurdia.db .schema` to inspect tables
3. **Inspect data**: Use `sqlite3 config/absurdia.db "SELECT * FROM players"`
4. **Test hand-catching**: Requires many attempts due to 5% success rate
5. **Test traps**: Set `trap_timers.basic: 10` for 10-second traps during testing
6. **Test care cap**: Set `daily_care_cap: 1` to quickly hit limit
7. **Test arena**: Manually trigger `_run_hourly_arena()` via schedule
8. **Check templates**: Ensure `config/absurdia_creatures.json` has valid JSON

### Debugging

1. **Database errors**: Check `debug.log` for SQLite errors
2. **Template loading**: Look for "[absurdia] Loaded X creature templates" in logs
3. **Pending catches**: Query `pending_catches` table to see stuck entries
4. **Arena queue**: Check `creatures.submitted_to_arena` column
5. **Care cooldowns**: Check `creatures.last_fed/last_played/last_petted` timestamps
6. **Daily reset**: Check `players.last_daily_reset` and `daily_care_count`

### Adding New Creatures

1. Add creature to `config/absurdia_creatures.json`
2. Set `name`, `rarity`, `type`, stat ranges, flavor text
3. Reload module or restart bot (templates loaded on init)
4. Test catching via appropriate trap tier
5. Verify flavor text displays correctly

### Adding New Care Actions

1. Add config entries: `care_costs.<action>`, `care_cooldowns.<action>`
2. Add database column: `creatures.last_<action>`
3. Add generator flavor: `template.<action>_text`
4. Update `CreatureCare.check_care_cooldown()` field_map
5. Update `CreatureCare.calculate_care_reward()` for action
6. Add command handler in `absurdia_main.py`

### Adding New Trap Tiers

1. Add to `trap_prices` and `trap_timers` config
2. Add rarity weights to `CreatureGenerator.RARITY_WEIGHTS`
3. Update shop display in `_cmd_shop()`
4. Test purchasing and setting trap

---

## Related Files

- **Main Architecture**: `docs/LLM_ARCHITECTURE_GUIDE.md` - General bot architecture
- **Quest Module**: `docs/LLM_QUEST_GUIDE.md` - Sister game module (JSON-based)

---

**When in doubt, check the database schema or grep for examples in `modules/absurdia_pkg/`!**
