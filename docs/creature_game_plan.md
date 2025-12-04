# Creature Battle Game - Technical Architecture Plan

## Game Name Suggestion
**"ABSURDIA"** or **"The Menagerie of Questionable Existence"**

---

## 1. DATABASE SCHEMA

### Table: players
```sql
CREATE TABLE players (
    user_id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    coins INTEGER DEFAULT 1000,  -- Starting currency
    total_arena_wins INTEGER DEFAULT 0,
    total_arena_losses INTEGER DEFAULT 0,
    current_win_streak INTEGER DEFAULT 0,
    best_win_streak INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_daily_reset TIMESTAMP  -- For daily training limits
);
```

### Table: creatures
```sql
CREATE TABLE creatures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,  -- "sentient potato", "angry doorknob", etc.
    nickname TEXT,  -- Optional player-given nickname
    rarity TEXT NOT NULL,  -- Common, Uncommon, Rare, Legendary, Feral
    creature_type TEXT NOT NULL,  -- Sturdy Nonsense, Sharp Weird, Flimsy Chaos

    -- UNIQUE constraint: one creature per type per owner
    UNIQUE(owner_id, name),

    -- Base stats (set on capture, based on rarity)
    base_hp INTEGER NOT NULL,
    base_attack INTEGER NOT NULL,
    base_defense INTEGER NOT NULL,
    base_speed INTEGER NOT NULL,

    -- Training bonuses (accumulated through training)
    bonus_hp INTEGER DEFAULT 0,
    bonus_attack INTEGER DEFAULT 0,
    bonus_defense INTEGER DEFAULT 0,
    bonus_speed INTEGER DEFAULT 0,

    -- Care tracking
    happiness INTEGER DEFAULT 50,  -- 0-100 scale
    last_fed TIMESTAMP,
    last_played TIMESTAMP,
    last_petted TIMESTAMP,

    -- Combat stats
    total_wins INTEGER DEFAULT 0,
    total_losses INTEGER DEFAULT 0,

    -- Metadata
    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    submitted_to_arena BOOLEAN DEFAULT 0,  -- Currently in arena queue

    FOREIGN KEY (owner_id) REFERENCES players(user_id),

);

-- Index for faster lookup when checking if player has creature type
CREATE INDEX idx_owner_name ON creatures(owner_id, name);
```

### Table: pending_catches
```sql
-- Temporary storage for catches awaiting player decision
CREATE TABLE pending_catches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    creature_name TEXT NOT NULL,

    -- New creature stats (rolled from trap)
    new_rarity TEXT NOT NULL,
    new_hp INTEGER NOT NULL,
    new_attack INTEGER NOT NULL,
    new_defense INTEGER NOT NULL,
    new_speed INTEGER NOT NULL,
    new_creature_type TEXT NOT NULL,

    -- Which trap caught it (for refund calculation)
    trap_quality TEXT NOT NULL,

    -- Timeout
    caught_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,  -- 30 seconds after caught_at

    FOREIGN KEY (owner_id) REFERENCES players(user_id)
);
```

### Table: active_traps
```sql
CREATE TABLE active_traps (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    trap_quality TEXT NOT NULL,  -- Basic, Standard, Premium, Deluxe
    set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ready_at TIMESTAMP NOT NULL,  -- When creature can be collected
    collected BOOLEAN DEFAULT 0,

    FOREIGN KEY (owner_id) REFERENCES players(user_id)
);
```

### Table: arena_matches
```sql
CREATE TABLE arena_matches (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER NOT NULL,  -- Groups matches by hour
    creature1_id INTEGER NOT NULL,
    creature2_id INTEGER NOT NULL,
    winner_id INTEGER,  -- NULL for draws

    -- Combat details for flavor text
    creature1_hp_remaining INTEGER,
    creature2_hp_remaining INTEGER,
    total_rounds INTEGER,
    type_advantage TEXT,  -- Which creature had advantage

    fought_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (creature1_id) REFERENCES creatures(id),
    FOREIGN KEY (creature2_id) REFERENCES creatures(id),
    FOREIGN KEY (winner_id) REFERENCES creatures(id)
);
```

### Table: training_sessions
```sql
CREATE TABLE training_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    creature_id INTEGER NOT NULL,
    stat_trained TEXT NOT NULL,  -- hp, attack, defense, speed
    improvement INTEGER NOT NULL,
    trained_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (creature_id) REFERENCES creatures(id)
);
```

### Table: creature_templates
```sql
-- Pre-defined creature types with flavor text
CREATE TABLE creature_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    rarity TEXT NOT NULL,
    creature_type TEXT NOT NULL,

    -- Stat ranges for this creature (base stats rolled within range)
    hp_min INTEGER,
    hp_max INTEGER,
    attack_min INTEGER,
    attack_max INTEGER,
    defense_min INTEGER,
    defense_max INTEGER,
    speed_min INTEGER,
    speed_max INTEGER,

    -- Flavor text for care commands
    feed_text TEXT,  -- "You acknowledge Tuesday's existence. It seems satisfied."
    play_text TEXT,
    pet_text TEXT,

    -- Catch flavor
    catch_text TEXT  -- "A sentient potato rolls into your trap, looking mildly inconvenienced."
);
```

### Table: inventory
```sql
CREATE TABLE inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id TEXT NOT NULL,
    item_type TEXT NOT NULL,  -- trap, food, toy, training_item
    item_name TEXT NOT NULL,  -- basic_trap, strength_weights, etc.
    quantity INTEGER DEFAULT 1,

    FOREIGN KEY (owner_id) REFERENCES players(user_id)
);
```

---

## 2. COMMAND STRUCTURE

### Core Commands

**!catch / !trap [quality]**
- Usage: `!catch basic` or `!trap premium` or just `!catch` (hand-catching)
- Sets a trap if player has one in inventory
- **LIMIT: Players may only have ONE active trap at a time**
- Trap qualities and times:
  - Basic (50 coins): 3 hours, Common/Uncommon only
  - Standard (150 coins): 2 hours, Common/Uncommon/Rare
  - Premium (400 coins): 1.5 hours, all rarities (higher legendary chance)
  - Deluxe (1000 coins): 1 hour, all rarities (best legendary chance)
- Response: "You set a [quality] trap. Check back in [time] with !check"

**!catch (no trap / hand-catching)**
- Usage: `!catch` when player has no traps or can't afford one
- No cooldown, can spam attempt
- Very low success rate: 5% chance
- On failure: "You try to grab [creature name] but it squirms free" (randomized failures)
- On success: "You grab [creature name] with your bare hands. It squirms angrily but surrenders to your attentions eventually."
- Hand-caught creatures ("Feral" rarity tier):
  - HP: 40-60 (weaker than Common)
  - Attack: 10-15
  - Defense: 8-12
  - Speed: 8-12
  - Only Common-tier creatures can be hand-caught
  - Prevents players from being completely stuck with no resources
  - Can still be trained/cared for to improve stats
- **Subject to same "one per type" rule** - triggers comparison if duplicate

**!keep / !swap**
- Used during catch comparison when you already have this creature type
- `!keep` - Keep newly caught creature, release old one (50% trap refund)
- `!swap` - Same as !keep (alias for clarity)
- Default after 30s timeout: keep current creature, new one is released with refund

**!check**
- Shows status of active trap(s)
- If not ready: displays time remaining
- **If ready: Creature is AUTOMATICALLY caught and added to stable when timer completes**
- Rolls creature from appropriate pool based on trap quality
- **If player already has this creature type:**
  - Shows comparison: "You caught [New Creature]! You already have one."
  - Displays both stat blocks side-by-side
  - Prompts: "Keep new (!keep) or release (!release)?"
  - Waits for player choice (30 second timeout, defaults to keep current)
  - Released creature refunds 50% of trap cost
- **If new creature type:**
  - Adds to inventory directly
  - Shows catch flavor text
  - Response includes creature stats and type

**!creatures / !menagerie**
- Lists all owned creatures with basic info
- Format: "[ID] Nickname (Name) - Type - W:X L:Y - Currently: [in arena / available]"
- **Limited to one creature per type, so max creatures = total unique creature types**
- No pagination needed (probably 20-40 creatures max)
- Shows total collection count: "You have 12 of 50 possible creatures"

**!stats [creature_id]**
- Detailed view of specific creature
- Shows: Name, Type, Rarity, All stats (base + bonus), Happiness, W/L record, Care cooldown status

**!nickname [creature_id] [name]**
- Set custom nickname for creature
- Max 30 characters

**!feed [creature_id]**
- Cooldown: 4 hours per creature
- Costs: 10 coins
- Effects: +5 happiness, +1-3 random stat, earn 5-10 coins (net -5 to 0)
- Purpose: Prevent decay, small passive income, show care
- **Cannot be used on creatures currently submitted to arena**

**!play [creature_id]**
- Cooldown: 2 hours per creature
- Costs: 5 coins
- Effects: +3 happiness, small boost to attack or speed, earn 3-7 coins
- Purpose: Targeted stat growth, frequent interaction
- **Cannot be used on creatures currently submitted to arena**

**!pet [creature_id]**
- Cooldown: 1 hour per creature
- Free
- Effects: +2 happiness, earn 2-4 coins
- Purpose: Quick passive income, maintain happiness
- **Cannot be used on creatures currently submitted to arena**

**!train [creature_id] [stat]**
- Stats: hp, attack, defense, speed
- Requires training item in inventory
- Daily limit: 3 training sessions per creature
- Costs vary by training item quality:
  - Basic Training Item (50 coins): +2 to stat
  - Advanced Training Item (150 coins): +5 to stat
  - Elite Training Item (500 coins): +10 to stat
- Response: Shows new total for stat

**!submit [creature_id]**
- Enters creature in next hourly arena
- Can only submit one creature at a time
- Can withdraw before arena starts with !withdraw
- **WARNING: Creatures in arena cannot be cared for and lose stats over time!**
  - Happiness decays at 2x normal rate (-1 per 3 hours instead of per 6 hours)
  - Each hour in arena without care: -1 happiness
  - Prolonged arena camping causes significant stat degradation
  - Strategic choice: keep strong creature in arena vs. maintain stats through care

**!withdraw**
- Removes your creature from arena queue if not yet started
- Resets creature to normal care schedule
- No penalty for withdrawing

**!arena**
- Shows current arena status:
  - Time until next tournament
  - Number of creatures entered
  - Your submitted creature (if any)

**!arenahistory / !battles [creature_id]**
- Shows recent matches for a specific creature
- Includes opponent, result, rewards earned

**!leaderboard / !top**
- Shows top 10 players by:
  - Total arena wins
  - Current win streak
  - Total coins earned
- Shows top 10 creatures by wins

**!shop**
- Lists purchasable items:
  - Traps (basic to deluxe)
  - Training items (basic to elite)
  - Food items
  - Toys
- Shows player's current coins

**!buy [item_name] [quantity]**
- Purchase items from shop
- Deducts coins, adds to inventory

**!inventory / !items**
- Shows player's current items and quantities

**!release [creature_id]**
- Permanently remove creature from inventory
- Confirmation required (or used during !check comparison)
- Refunds based on context:
  - Manual release: Small coin refund based on rarity (Common: 25, Uncommon: 75, Rare: 200, Legendary: 500)
  - Release during catch comparison: 50% of trap cost refunded
  - Cannot release creature currently in arena queue

---

## 3. COMBAT CALCULATION LOGIC

### Type Advantages (Rock-Paper-Scissors)
- **Sturdy Nonsense** > **Sharp Weird** > **Flimsy Chaos** > **Sturdy Nonsense**
- Advantage modifier: exactly **1.3x damage** (not to stats, to damage dealt)

### Combat Formula

```
Effective HP = Base HP + Bonus HP + (Happiness/10)
Effective Attack = Base Attack + Bonus Attack + (Happiness/20)
Effective Defense = Base Defense + Bonus Defense + (Happiness/20)
Effective Speed = Base Speed + Bonus Speed

Turn order: Creature with highest Speed attacks first (ties broken randomly)

Damage per turn:
  Damage = (Attacker_ATK / Defender_DEF) * type_multiplier * random(0.95, 1.05)
  where:
    - type_multiplier = 1.3 if attacker has type advantage, else 1.0
    - random(0.95, 1.05) provides ±5% variance
    - final damage is rounded

Battle continues turn-by-turn until one creature reaches 0 HP

Example:
Creature A: 100 HP, 30 ATK, 20 DEF, 25 SPD (Sharp Weird)
Creature B: 110 HP, 28 ATK, 25 DEF, 22 SPD (Flimsy Chaos)

Type advantage: A has advantage (Sharp Weird > Flimsy Chaos)
A strikes first (higher speed)

A's damage to B: (30 / 25) * 1.3 * random(0.95-1.05) = ~1.56 * 1.3 = ~2.0 damage per hit
B's damage to A: (28 / 20) * 1.0 * random(0.95-1.05) = ~1.4 damage per hit

Combat continues turn-by-turn until winner determined
```

### Combat Balance Targets
- Average match: 5-10 rounds
- Type advantage should matter but not guarantee victory
- Stat differences of 20%+ should usually determine winner
- RNG can swing close matches (±5% stat difference)

---

## 4. CREATURE STAT GENERATION

### Base Stats by Rarity

**Feral (Hand-caught only):**
- HP: 40-60
- Attack: 10-15
- Defense: 8-12
- Speed: 8-12
- Hand-catch success rate: 5%
- Only Common creatures available for hand-catching
- Purpose: Safety net for broke/stuck players

**Common:**
- HP: 60-90
- Attack: 15-25
- Defense: 10-20
- Speed: 10-20
- Trap chance: 70% (basic), 50% (standard+)
- Hand-catch chance: 5% (results in Feral stats)

**Uncommon:**
- HP: 80-120
- Attack: 20-35
- Defense: 15-30
- Speed: 15-30
- Trap chance: 28% (basic), 35% (standard), 40% (premium+)

**Rare:**
- HP: 110-160
- Attack: 30-50
- Defense: 25-45
- Speed: 25-45
- Trap chance: 0% (basic), 14% (standard), 25% (premium), 30% (deluxe)

**Legendary:**
- HP: 150-220
- Attack: 45-70
- Defense: 40-60
- Speed: 40-60
- Trap chance: 2% (basic), 1% (standard), 5% (premium), 10% (deluxe)

### Stat Growth Through Care
- Happiness affects effective stats in combat (see formula above)
- Decay rates:
  - Normal: -1 happiness per 6 hours if not cared for (minimum 0)
  - **In Arena Queue: -1 happiness per 3 hours (2x faster decay)**
  - **Arena hourly penalty: -1 happiness per hour while submitted**
  - Creatures in arena CANNOT be fed, played with, or petted
- **NEW: Stat Decay System**
  - If creature receives NO care for 24+ hours, stats begin to decay
  - Decay rate: 2% per day (of base stats)
  - Minimum floor: 70% of base stats (cannot decay below this)
  - Decay affects base stats, not bonus stats from training
  - Any care action (feed/play/pet) resets the decay timer
  - Strategic consideration: Check in daily to maintain stats
- Training provides permanent stat bonuses (no decay)
- Strategic consideration: Long-term arena camping weakens creatures significantly

---

## 5. ECONOMY BALANCE

### Income Sources
| Activity | Coins Earned | Frequency | Daily Cap |
|----------|--------------|-----------|-----------|
| Pet creature | 2-4 | Every 1 hour | 10 care actions/day total |
| Play with creature | 3-7 (net -2 to +2) | Every 2 hours | 10 care actions/day total |
| Feed creature | 5-10 (net -5 to 0) | Every 4 hours | 10 care actions/day total |
| Arena win | 150-300 (based on streak) | Variable | None |
| Arena loss | 20-40 | Variable | None |

**NEW: Daily Care Cap**
- Players can earn coins from care actions (feed/play/pet) a maximum of **10 times per day total**
- Cap applies across all creatures (not per-creature)
- After 10 care actions, you can still care for creatures (happiness/stats still apply) but earn 0 coins
- Cap resets at midnight UTC
- Prevents infinite coin grinding while still allowing full care

### Expenses
| Item | Cost | Purpose |
|------|------|---------|
| Basic trap | 50 | Catching creatures |
| Standard trap | 150 | Better creatures |
| Premium trap | 400 | Rare/Legendary access |
| Deluxe trap | 1000 | Best legendary chance |
| Basic training item | 50 | +2 stat |
| Advanced training item | 150 | +5 stat |
| Elite training item | 500 | +10 stat |
| Food item | 10 | Care/feeding |
| Toy item | 5 | Playing |

### Daily Income Potential (with care cap)
- Casual player (3 creatures, basic care, 10 actions): ~30-60 coins/day from care
- Active player (10 care actions + arena): ~100-200 coins/day
- Competitive player (10 care actions + optimized arena): ~250-500 coins/day
- Care cap prevents grinding: max ~60 coins/day from care alone (10 actions × avg 6 coins)

### Sample Week: Casual Player Progression

**Starting state:** 1000 coins, no creatures

**Day 1 (Monday):**
- Buy 2 basic traps (100 coins total)
- Set first trap (3h wait)
- Hand-catch attempt while waiting: fail
- Collect trap: Common creature (sentient potato, HP:65 ATK:18 DEF:12 SPD:15)
- Set second trap
- Pet creature every hour: 3 actions = +9 coins
- End of day: 909 coins, 1 creature, trap pending

**Day 2 (Tuesday):**
- Collect trap: Uncommon creature (argumentative cloud, HP:95 ATK:28 DEF:22 SPD:20)
- Buy 1 standard trap (150 coins)
- Set standard trap
- Care actions (10 total across both creatures):
  - 3× pet potato = +9 coins
  - 2× play potato = +4 coins (net, after cost)
  - 2× feed potato = 0 coins (net, after cost)
  - 3× pet cloud = +9 coins
  - Daily care cap reached (10 actions)
- End of day: 772 coins, 2 creatures, trap pending

**Day 3 (Wednesday):**
- Collect standard trap: Rare creature (philosophical cheese wheel, HP:135 ATK:42 DEF:35 SPD:30)
- Save coins (no trap purchase)
- 10 care actions = ~22 coins earned (mix of all three types)
- End of day: 794 coins, 3 creatures

**Day 4 (Thursday):**
- Buy premium trap (400 coins)
- Set premium trap
- 10 care actions = ~22 coins earned
- End of day: 416 coins, 3 creatures, trap pending

**Day 5 (Friday):**
- Collect premium trap: Legendary creature (existentially troubled doorknob, HP:185 ATK:58 DEF:52 SPD:48)
- BUT it's a duplicate type! Already have one
- Compare stats, keep new one (better stats)
- Refund: 200 coins (50% of premium trap)
- 10 care actions on 3 best creatures = ~22 coins
- End of day: 638 coins, 3 creatures (1 upgraded)

**Day 6 (Saturday):**
- Submit best creature to arena (doorknob)
- Arena result: WIN! Earned 150 coins
- Buy basic trap (50 coins), set it
- 10 care actions on remaining 2 = ~22 coins
- End of day: 760 coins, 3 creatures, trap pending

**Day 7 (Sunday):**
- Collect trap: Common duplicate (sentient potato again)
- Keep old one (has bonus stats from care), get 25 coin refund
- 10 care actions = ~22 coins
- Submit philosophical cheese to arena: LOSS (30 coins)
- Week total: 837 coins, 3 creatures with growing stats

**Weekly summary:** Started with 1000, ended with 837 + much stronger creatures with bonus stats. Sustainable income from mix of care (capped) and arena battles. Ready to save for better traps or training items.

---

## 6. ARENA AUTOMATION SYSTEM

### Hourly Arena Flow

```
At :00 of each hour:
1. Check arena_submissions table for entered creatures
2. Apply pre-battle decay to all submitted creatures:
   - Reduce happiness by 1 for each hour in queue
   - Minimum happiness: 0
3. If odd number, one gets bye (random selection, auto-win but still gets decay)
4. Pair creatures randomly
5. For each pairing:
   a. Load creature stats from database (including decay)
   b. Run combat simulation
   c. Record results in arena_matches table
   d. Update creature W/L records
   e. Update player win streaks
   f. Calculate and award coins
   g. Reset creature's submitted_to_arena flag
6. Post results to IRC channel:
   - Match-by-match summaries
   - Notable moments (crits, upsets, streaks)
   - Mention if creatures are suffering from neglect
   - Updated leaderboard top 3
7. Clear arena queue for next hour
```

### Results Announcement Format

```
=== ARENA TOURNAMENT #1234 - 14:00 UTC ===
8 creatures entered, 4 matches fought!

Match 1: "Disappointed Brick" (styx) vs "Existential Toaster" (rumi)
→ Winner: Existential Toaster (Sharp Weird advantage!)
   Toaster dealt 156 damage over 7 rounds. Brick fought valiantly!

Match 2: "God's Typo" (Essay) vs "Angry Doorknob" (TheSinner)
→ Winner: God's Typo (Critical hit in round 3!)
   A legendary performance! Typo maintains 5-win streak!

[...more matches...]

💰 Payouts:
- Essay (Win, 5-streak): 300 coins
- rumi (Win): 150 coins
- styx (Loss): 25 coins
- TheSinner (Loss): 25 coins

🏆 Current Top Streaks:
1. Essay's "God's Typo" - 5 wins
2. rumi's "Existential Toaster" - 2 wins
```

### Implementation Approach
- Use Python `schedule` library (already in Jeeves)
- Register hourly task: `schedule.every().hour.at(":00").do(run_arena_tournament)`
- Task runs in background thread
- All database operations wrapped in transactions
- Error handling: if combat fails, log error and skip that match

---

## 7. CODE STRUCTURE

### Module Organization

```
modules/
├── absurdia.py              # Main module (command handlers, setup)
├── absurdia_combat.py       # Combat simulation logic
├── absurdia_creatures.py    # Creature generation, stats, care
├── absurdia_arena.py        # Arena automation and matchmaking
└── absurdia_db.py           # Database initialization and queries
```

### absurdia.py (Main Module)
```python
class Absurdia(SimpleCommandModule):
    name = "absurdia"
    version = "1.0.0"
    description = "Creature catching and battling game"

    def __init__(self, bot):
        super().__init__(bot)
        self.db = AbsurdiaDatabase(bot.ROOT / "config" / "absurdia.db")
        self.combat = CombatEngine()
        self.creature_gen = CreatureGenerator(self.db)
        self.arena = ArenaManager(self.db, self.combat, bot)

        # Schedule hourly arena
        schedule.every().hour.at(":00").do(self._run_arena)

    def _register_commands(self):
        # Register all commands here
        self.register_command(r"^\s*!catch\s+(\w+)\s*$", self._cmd_catch, ...)
        self.register_command(r"^\s*!feed\s+(\d+)\s*$", self._cmd_feed, ...)
        # etc.
```

### absurdia_db.py (Database Layer)
```python
class AbsurdiaDatabase:
    def __init__(self, db_path):
        self.db_path = db_path
        self.conn = None
        self._initialize_db()

    def _initialize_db(self):
        # Create tables if not exist
        # Load creature templates from JSON file

    def get_player(self, user_id):
        # Fetch player data, create if doesn't exist

    def get_creature(self, creature_id):
        # Fetch creature with all stats

    def update_creature_stats(self, creature_id, **kwargs):
        # Update creature stats atomically

    def create_trap(self, owner_id, quality, ready_time):
        # Insert new trap

    def get_ready_traps(self, owner_id):
        # Get traps ready to collect

    def create_creature(self, owner_id, template_id):
        # Roll stats and create new creature
        # Check if player already has this creature type
        # If duplicate, create pending_catch entry instead

    def get_pending_catch(self, owner_id):
        # Get active pending catch for player
        # Clean up expired entries

    def resolve_pending_catch(self, owner_id, keep_new):
        # If keep_new: replace old creature with new one, refund 50% trap cost
        # If keep_old: delete pending catch, refund 50% trap cost
        # Return refund amount

    def submit_to_arena(self, creature_id):
        # Mark creature as submitted

    def get_arena_queue(self):
        # Get all submitted creatures for next tournament

    def record_match(self, creature1_id, creature2_id, winner_id, details):
        # Store match results

    def get_collection_progress(self, owner_id):
        # Return (owned_count, total_possible_count)

    # ... more helper methods
```

### absurdia_combat.py (Combat Engine)
```python
class CombatEngine:
    TYPE_ADVANTAGES = {
        "Sturdy Nonsense": "Sharp Weird",
        "Sharp Weird": "Flimsy Chaos",
        "Flimsy Chaos": "Sturdy Nonsense"
    }

    def simulate_battle(self, creature1_data, creature2_data):
        # Returns: (winner_id, combat_log, stats)

        # 1. Calculate effective stats
        # 2. Determine type advantage
        # 3. Simulate turn-by-turn combat
        # 4. Return results with flavor text

    def calculate_damage(self, attacker_stats, defender_stats, has_advantage):
        # Returns damage dealt this turn

    def generate_combat_log(self, rounds):
        # Returns IRC-friendly summary
```

### absurdia_creatures.py (Creature Logic)
```python
class CreatureGenerator:
    def __init__(self, db):
        self.db = db
        self.templates = self._load_templates()

    def generate_creature(self, trap_quality):
        # 1. Roll rarity based on trap quality
        # 2. Select random template of that rarity
        # 3. Roll stats within template's ranges
        # 4. Return creature data dict

    def get_catch_flavor(self, template):
        # Return catch announcement text

class CreatureCare:
    FEED_COOLDOWN = 4 * 3600  # 4 hours in seconds
    PLAY_COOLDOWN = 2 * 3600
    PET_COOLDOWN = 1 * 3600

    def can_care_for(self, creature_data):
        # Check if creature is in arena (blocked if submitted)
        if creature_data['submitted_to_arena']:
            return False, "Cannot care for creatures in the arena queue"
        return True, None

    def can_feed(self, creature_data):
        # Check cooldown + arena status

    def feed_creature(self, creature_id):
        # Update stats, happiness, timestamp
        # Return coins earned

    # Similar for play, pet

    def apply_decay(self, creature_data, is_in_arena=False):
        # Calculate happiness decay based on time
        # Use different decay rates for arena vs normal
        if is_in_arena:
            decay_rate = 3 * 3600  # 3 hours
        else:
            decay_rate = 6 * 3600  # 6 hours

    def hand_catch_attempt(self):
        # 5% success rate
        # Return (success, creature_data or None, flavor_text)
        success = random.random() < 0.05
        if success:
            # Generate Feral-tier creature
            template = self._get_random_common_template()
            creature_data = self._generate_feral_stats(template)
            return True, creature_data, template['hand_catch_success']
        else:
            # Random failure message
            template = self._get_random_common_template()
            fail_msg = random.choice(template['hand_catch_fail'])
            return False, None, fail_msg
```

### absurdia_arena.py (Arena Management)
```python
class ArenaManager:
    def __init__(self, db, combat_engine, bot):
        self.db = db
        self.combat = combat_engine
        self.bot = bot
        self.tournament_counter = self._get_last_tournament_id()

    def run_tournament(self):
        # Main arena execution
        # 1. Get queue
        # 2. Apply hourly decay to all creatures in queue (-1 happiness each)
        # 3. Create pairings
        # 4. Simulate all matches (using current happiness-affected stats)
        # 5. Award prizes
        # 6. Clear submitted_to_arena flags
        # 7. Announce results (note neglected creatures)

    def create_pairings(self, creature_list):
        # Random pairing, handle odd number

    def calculate_rewards(self, winner_creature, loser_creature):
        # Base reward + streak bonus

    def announce_results(self, matches, channel):
        # Format and send IRC messages
        # Include warnings for low-happiness creatures
        # "Angry Doorknob looks exhausted from arena neglect!" (happiness < 20)
```

---

## 8. CONFIGURATION

### config.yaml addition
```yaml
absurdia:
    allowed_channels:
      - "#quest-dev"  # or wherever you want it

    arena_channel: "#quest-dev"  # Where to announce results

    starting_coins: 1000

    trap_prices:
        basic: 50
        standard: 150
        premium: 400
        deluxe: 1000

    trap_timers:  # In seconds
        basic: 10800    # 3 hours
        standard: 7200  # 2 hours
        premium: 5400   # 1.5 hours
        deluxe: 3600    # 1 hour

    training_limit_per_day: 3

    arena_rewards:
        win_base: 150
        win_streak_bonus: 30  # Per streak level
        loss_base: 25

    care_cooldowns:  # In seconds
        feed: 14400   # 4 hours
        play: 7200    # 2 hours
        pet: 3600     # 1 hour

    care_costs:
        feed: 10
        play: 5
        pet: 0

    daily_care_cap: 10  # Maximum care actions that earn coins per day

    stat_decay:
        enabled: true
        grace_period_hours: 24  # No decay for first 24 hours without care
        decay_per_day: 0.02  # 2% per day
        minimum_percent: 0.70  # Cannot decay below 70% of base stats

    happiness_decay:
        normal_hours: 6  # -1 happiness every 6 hours normally
        arena_hours: 3   # -1 happiness every 3 hours in arena queue
        arena_hourly: 1  # -1 happiness per arena cycle while submitted

    hand_catch:
        enabled: true
        success_rate: 0.05  # 5% chance
        cooldown: 0  # No cooldown (can spam attempts)
        stat_penalty: 0.6  # Hand-caught creatures have 60% of common stats

    duplicate_handling:
        comparison_timeout_seconds: 30
        trap_refund_percent: 0.5  # 50% of trap cost back on duplicate
        manual_release_refunds:
            Feral: 10
            Common: 25
            Uncommon: 75
            Rare: 200
            Legendary: 500
```

---

## 9. CREATURE TEMPLATES JSON

Store in `config/absurdia_creatures.json`:

```json
{
  "creatures": [
    {
      "name": "sentient potato",
      "rarity": "Common",
      "type": "Sturdy Nonsense",
      "hp": [60, 80],
      "attack": [15, 20],
      "defense": [12, 18],
      "speed": [10, 15],
      "feed_text": "You offer the potato some soil. It accepts with dignified silence.",
      "play_text": "You roll the potato across the floor. It seems... content?",
      "pet_text": "You pat the potato gently. It does not object.",
      "catch_text": "A sentient potato rolls into your trap, looking mildly inconvenienced.",
      "hand_catch_success": "You grab the sentient potato with your bare hands. It squirms angrily but surrenders to your attentions eventually.",
      "hand_catch_fail": ["You try to grab the potato but it rolls away", "The potato evades your grasp with surprising dignity", "Your fingers close on empty air. The potato is elsewhere."]
    },
    {
      "name": "the concept of Tuesday",
      "rarity": "Rare",
      "type": "Flimsy Chaos",
      "hp": [110, 140],
      "attack": [35, 45],
      "defense": [28, 38],
      "speed": [30, 40],
      "feed_text": "You acknowledge Tuesday's existence. It seems satisfied.",
      "play_text": "You contemplate Tuesday with enthusiasm. It vibrates slightly.",
      "pet_text": "You validate Tuesday. It glows faintly.",
      "catch_text": "Tuesday manifests in your trap. It's definitely a Tuesday.",
      "hand_catch_success": "N/A - Rare creatures cannot be hand-caught",
      "hand_catch_fail": []
    },
    {
      "name": "God's least favorite typo",
      "rarity": "Legendary",
      "type": "Sharp Weird",
      "hp": [180, 220],
      "attack": [55, 70],
      "defense": [45, 60],
      "speed": [50, 60],
      "feed_text": "You offer divine correction fluid. The typo rejects it defiantly.",
      "play_text": "You proofread near the typo. It pulses with cosmic irritation.",
      "pet_text": "You acknowledge the typo's right to exist. It radiates smugness.",
      "catch_text": "Reality hiccups. The typo materializes, smirking at autocorrect itself.",
      "hand_catch_success": "N/A - Legendary creatures cannot be hand-caught",
      "hand_catch_fail": []
    }
  ]
}
```

---

## 10. IMPLEMENTATION PHASES

### Phase 1: Core Infrastructure (Week 1)
- Set up database schema
- Create absurdia_db.py with basic CRUD operations
- Load creature templates from JSON
- Implement player registration (auto on first command)
- Test database operations

### Phase 2: Creature Catching (Week 1-2)
- Implement trap system (!catch, !check)
- Creature generation with stat rolling
- One-per-type duplicate detection
- Comparison UI and pending catch system
- !keep/!swap commands with timeout
- Trap refund on duplicate release
- Basic inventory management
- Test full catch cycle including duplicates

### Phase 3: Creature Management (Week 2)
- !creatures, !stats, !nickname commands
- Display formatting for creature info
- Basic economy (coin tracking)

### Phase 4: Care System (Week 2-3)
- !feed, !play, !pet with cooldowns
- Happiness tracking and decay
- Care flavor text from templates
- Coin rewards from care

### Phase 5: Combat Engine (Week 3)
- Build combat simulation in absurdia_combat.py
- Type advantage calculation
- Turn-based damage calculation
- Combat log generation
- Test with mock battles

### Phase 6: Arena System (Week 3-4)
- Arena queue management (!submit, !withdraw, !arena)
- Matchmaking algorithm
- Arena automation with schedule
- Results announcement formatting
- Reward distribution

### Phase 7: Training & Economy (Week 4)
- !shop, !buy, !inventory
- Training items and stat boosts
- Daily training limits
- Complete economy loop

### Phase 8: Leaderboards & History (Week 4-5)
- !leaderboard with multiple categories
- !arenahistory for individual creatures
- Win streak tracking
- Stats dashboard

### Phase 9: Polish & Balance (Week 5)
- Tune combat formulas
- Adjust economy based on testing
- Add more creature templates
- Flavor text variations
- Bug fixes

---

## 11. TESTING CHECKLIST

- [ ] Creature stat generation produces balanced values
- [ ] Type advantages work correctly in combat
- [ ] Combat typically resolves in 5-10 rounds
- [ ] Cooldowns prevent spam
- [ ] Daily limits reset properly
- [ ] Economy is sustainable (can't go infinite)
- [ ] Arena handles odd/even numbers of submissions
- [ ] Database transactions prevent race conditions
- [ ] Creature happiness decays appropriately
- [ ] Training limits work across module reloads
- [ ] Leaderboards update correctly
- [ ] Commands work only in configured channels
- [ ] Hand-catching has appropriate low success rate
- [ ] Hand-caught creatures are weaker than trapped ones
- [ ] Arena creatures cannot be cared for while submitted
- [ ] Arena happiness decay applies correctly
- [ ] Players can always recover from zero coins/traps via hand-catching
- [ ] Only one creature per type per player enforced
- [ ] Duplicate catches trigger comparison UI
- [ ] Trap refunds work correctly (50% on duplicate, rarity-based on manual release)
- [ ] Pending catches expire after 30 seconds with correct default
- [ ] !creatures list never floods channel (limited by unique types)
- [ ] Daily care cap enforces 10 actions/day limit
- [ ] Care cap resets at midnight UTC
- [ ] Stat decay applies after 24 hours without care
- [ ] Stat decay cannot reduce stats below 70% of base
- [ ] Care actions still work after hitting cap (no coins but still happiness/stats)

---

## 12. STRATEGIC IMPLICATIONS OF NEW MECHANICS

### One Creature Per Type Limit

**Purpose:** Prevents inventory bloat and channel flooding while making each catch meaningful.

**Mechanics:**
- Each player can only have ONE of each creature type (e.g., one "sentient potato")
- When catching a duplicate, game shows comparison and forces choice
- Keeps inventory manageable (max ~20-50 creatures depending on template count)
- Makes !creatures list readable in IRC

**Comparison Flow:**
```
You caught a sentient potato! You already have one.

CURRENT (ID: 12):
├─ HP: 75, Attack: 22, Defense: 18, Speed: 14
├─ Happiness: 85
├─ Wins: 5, Losses: 2
└─ Type: Sturdy Nonsense

NEW CATCH:
├─ HP: 82, Attack: 19, Defense: 16, Speed: 15
├─ Happiness: 50 (new catch)
├─ Wins: 0, Losses: 0
└─ Type: Sturdy Nonsense

Keep new (!keep) or keep current (!swap defaults to current in 30s)?
```

**Strategic Implications:**
- Each catch is a stat-rolling opportunity to improve your collection
- Better stats vs. established win record tradeoff
- Encourages catching to find better stat rolls
- Trap refund (50%) softens the cost of duplicate catches
- Promotes "completing the collection" rather than hoarding

**Economy Impact:**
- Duplicate catches refund 50% of trap cost
- Prevents infinite creature farming
- Manual releases give smaller refunds (rarity-based)
- Example: Premium trap (400 coins) catches duplicate → 200 coins back
- Net cost to "reroll" a creature: 200 coins (fair price for stat gambling)

### Hand-Catching Safety Net
**Purpose:** Prevents dead-end game states where players have zero coins and no traps.

**Mechanics:**
- 5% success rate on !catch with no arguments
- Only yields Common creatures with Feral stats (60% of normal Common stats)
- No cooldown, so desperate players can spam attempts
- Provides weak creatures that can still earn passive income through care
- Creates path back to sustainability: hand-catch → care for coins → buy trap → catch better creatures

**Economic Impact:**
- Expected attempts to catch: ~20 tries (5% rate)
- Free action, so no resource cost
- Feral creature can generate 8-14 coins/day via basic care
- After ~7-10 days of care, can afford Basic trap
- Prevents rage-quits from being broke

**Flavor Examples:**
- Fail: "You lunge at a disappointed cloud but it dissipates smugly"
- Fail: "The angry doorknob sees you coming and locks itself"
- Fail: "You almost grab the sentient potato. Almost."
- Success: "You grab a moderately concerned brick with your bare hands. It squirms angrily but surrenders to your attentions eventually."

### Arena Decay Strategy

**Purpose:** Prevents "set and forget" meta where players submit strongest creature and ignore care system.

**Mechanics:**
- Creatures in arena queue lose happiness 2x faster than normal
- Additional -1 happiness per tournament cycle (hourly)
- Creatures in arena CANNOT be fed/played with/petted
- Lower happiness = lower effective combat stats
- Strategic tension: compete now vs. prepare for later

**Strategic Layers:**

1. **Active Arena Participation (Withdraw/Resubmit)**
   - Submit before tournament → withdraw after → care for creature → resubmit next hour
   - Maintains happiness but requires constant attention
   - Best for active players

2. **Rotation Strategy**
   - Maintain 3+ creatures
   - Submit different one each hour while caring for others
   - Spreads decay across stable
   - Best for moderate players

3. **Dedicated Fighter (Sacrifice Strategy)**
   - Submit strongest creature permanently
   - Accept stat degradation over time
   - Eventually creature becomes weak from neglect
   - Must train replacement while champion decays
   - High-risk but less micromanagement

4. **Care-Focused (Passive Income)**
   - Never submit to arena
   - Focus entirely on caring for multiple creatures
   - Steady coin income, no combat rewards
   - Lower ceiling but minimal stress

**Happiness Impact on Combat:**
```
Effective HP = Base HP + Bonus HP + (Happiness/10)
Effective Attack = Base Attack + Bonus Attack + (Happiness/20)

Example Legendary at Happiness 100 (well-cared):
- Base HP: 200, Attack: 60, Defense: 50
- Effective HP: 210, Attack: 65, Defense: 50

Same creature at Happiness 20 (neglected in arena):
- Effective HP: 202, Attack: 61, Defense: 50
- Lost: 8 HP, 4 Attack

After 20 hours in arena (Happiness 0):
- Effective HP: 200, Attack: 60, Defense: 50
- Lost: 10 HP, 5 Attack (roughly 5% combat power)
```

**Balance Targets:**
- 1-2 tournaments: minimal impact (~5% stat loss)
- 5+ tournaments: significant impact (~10-15% stat loss)
- 20+ tournaments: severe impact (back to base stats)
- Forces choice: win streak maintenance vs. creature health

---

## 13. POTENTIAL EXPANSIONS (Future)

- Breeding system (combine two creatures)
- Seasonal events with limited creatures
- Creature abilities (special moves in combat)
- Trading between players
- Team battles (2v2 arena mode)
- Achievement system
- Creature evolution at certain win thresholds
- Boss battles (co-op against super creature)
- Cosmetic items for creatures
- Creature quests (PvE content)

---

This plan should give you everything needed to build Absurdia step-by-step. The modular structure keeps it separate from your Quest system, and the economy is designed to reward both casual collectors and competitive battlers. Let me know if you want me to adjust any mechanics or start implementing specific phases!
