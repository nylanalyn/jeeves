# Feature Planning & Ideas

This document captures feature ideas and design discussions for future implementation.

## Quest Module: Hardcore Mode

**Status:** Design Complete - Awaiting Player Feedback (2025-11-05)

### Quick Summary

Hardcore mode is a high-risk, high-reward alternative to normal prestige. When you hit level 20, instead of prestiging immediately, you can choose hardcore mode to push to level 50 with these challenges:

**The Challenge:**
- Reach level 50 instead of 20 (5x longer journey)
- All items except (h) permanent items locked away
- New health system: lose HP each fight, die at 0 HP = permadeath
- 80% item drop rates
- No random boss encounters (but can join !mob voluntarily)
- No abilities
- Can't do challenge paths simultaneously

**The Rewards:**
- Pick ONE item to make permanently "hardcore" (h) - never locks again
- Get your prestige bonuses (that you delayed from level 20)
- All locked items returned
- Death stats, completion stats, bragging rights

**The Gamble:**
- Success at 50: Get everything + permanent item + prestige
- Permadeath (0 HP): Lose everything, reset to level 1, NO prestige bonuses
- Can abandon anytime with `!quest hardcore quit` (items returned, no penalty)

### Concept
A challenging prestige variant that requires players to reach level 50 (instead of 20) with restricted inventory and permadeath mechanics, but offers unique permanent item rewards.

### Mechanics

**Activation:**
- Available at level 20 as ALTERNATIVE to normal prestige
- Two choices when hitting level 20:
  - `!quest prestige` - Normal prestige (safe, get prestige bonuses immediately)
  - `!quest hardcore` - Enter hardcore mode (risky, delay prestige for bigger rewards)
- **Cannot do both** - it's one or the other each cycle

**Restrictions:**
- All current items moved to a "locker" (unavailable during hardcore run)
- All abilities disabled/removed
- Must reach level 50 instead of normal level 20 cap
- Health system active (see below)

**Health System (Hardcore Only):**
- Players have health pool in addition to energy
- Normal fights: Lose random small amount of health (even on wins)
- Defeats: Lose large chunk of health
- **Health Restoration:**
  - Medkits: Small heal (10-20 HP?)
  - Level up: FULL heal (strategic timing becomes important!)
- **Permadeath:** Health reaches 0 = hardcore run FAILED
  - Kicked from hardcore mode
  - Reset to level 1 on a NORMAL (non-hardcore) prestige run
  - Lose all progress toward level 50
  - Permanent items from previous completions NOT available (must complete another hardcore run first)
- **Stats Tracking:**
  - Track total hardcore deaths
  - Track successful completions
  - Display on profile/leaderboard

**Rewards Upon Reaching Level 50:**
- NOW you can prestige (you delayed it from level 20)
- Get normal prestige bonuses that you skipped at level 20
- All items returned from locker
- Pick ONE item from entire inventory (locker + current run items) to make "hardcore permanent"
  - Marked with (h) indicator in inventory displays
- Reset to level 1
- Can choose hardcore OR normal prestige again next time you hit level 20

**The Gamble:**
- Normal prestige at 20: Safe, immediate bonuses, restart quickly
- Hardcore at 20: Risky, delay prestige, but if you reach 50 you get:
  - The prestige bonuses you delayed
  - All your items back
  - One (h) permanent item selection
  - Bragging rights
- Permadeath in hardcore: Lose everything, reset to level 1 with NO prestige bonuses

**Hardcore Permanent Items:**
- Available in BOTH normal mode AND hardcore mode
- Never get locked when entering hardcore
- Build up collection over multiple completions
- Each completion = one more permanent item
- Strategic choice: which item helps most in future hardcore runs?

**Item Locking Behavior:**
- Entering hardcore: ALL items except (h) permanent items go to locker
- Each new hardcore run: start with only (h) items + items you find during run
- Green: items from current run | Red with *0*: locked items | (h): hardcore permanent

### Decided Design

1. **Item Locker Display:**
   - Locked items shown in `!qp` and `!qi` commands
   - Locked items: RED color + wrapped in `*0*` for non-color clients
   - Items earned during current hardcore run: GREEN color
   - Example: `*0* Sword of Power *0*` (locked) vs `Health Potion` (usable)

2. **Item Selection at Completion:**
   - Present numbered list of all items
   - Player types number to select permanent item
   - Command flow: bot shows list → player replies with number → confirmed

3. **Abandonment:**
   - Players CAN quit mid-run
   - Command: `!quest hardcore quit` or similar
   - Items restored from locker immediately
   - No penalty (besides losing progression toward level 50)

4. **System Architecture:**
   - **NOT** a challenge path - separate system
   - Always available as an alternative progression mode
   - Runs parallel to normal quest system
   - Think of it as "hardcore prestige" vs "normal prestige"

### Design Questions Still Open

1. **Health Pool System (Leaning toward scaling):**

   **Chosen approach: Scaling HP (10 + 5 per level)**
   - Start: 10 HP at level 1
   - Growth: +5 HP per level (Level 10 = 60 HP, Level 20 = 110 HP, Level 50 = 260 HP)
   - Level-up heals to full, so max HP increases feel rewarding

   **Damage Scaling Options:**

   A. **Monster level-based damage** (simpler)
   - Early monsters (level 1-10): 2-5 HP damage on win, 15-25 HP on loss
   - Mid monsters (level 11-30): 5-10 HP damage on win, 30-50 HP on loss
   - Late monsters (level 31-50): 8-15 HP damage on win, 50-80 HP on loss
   - Pros: Intuitive, ties into existing monster difficulty
   - Cons: Need to tune numbers for each tier

   B. **Percentage-based damage** (more complex)
   - Normal fight: 5-15% of max HP
   - Defeat: 30-50% of max HP
   - Pros: Auto-scales perfectly, stays consistently tense
   - Cons: More moving parts, harder to predict/balance

   **Still to decide:**
   - Which damage scaling approach?
   - Should health show in `!qp` display? (Yes, probably)
   - Medkit heal amount? (20 HP fixed? 25% of max HP?)

2. **Difficulty Scaling:**
   - Should enemies be harder in hardcore mode beyond just health loss?
   - Different XP requirements for levels 21-50?
   - Special hardcore-only bosses or encounters?

3. **Rewards Balance:**
   - Should there be restrictions on which items can be kept permanently?
   - Limit on how many permanent items total (or unlimited growth)?
   - Any other rewards besides item selection? (titles, badges, bragging rights?)

4. **Progression:**
   - Linear XP curve from 20-50, or exponential?
   - Should medkits work the same way as normal mode?
   - Any special mechanics for levels 21-50?

5. **Permadeath Impact:**
   - Should there be a "death count" stat tracked?
   - Any cooldown before re-entering hardcore after permadeath?
   - Show death history on profile?

### Potential Issues & Edge Cases to Address

1. **Boss Fights:**
   - Do bosses use same damage tiers or special scaling?
   - Should there be hardcore-only bosses?
   - Boss defeat damage might need to be higher?

2. **Party/Multiplayer Mechanics:**
   - **Random boss encounters:** REMOVED for hardcore players (no forced participation)
   - **!mob battles:** Hardcore players CAN join voluntarily
   - Boss defeat = high HP damage (60-80 HP or 50-70%?)
   - Player choice = player responsibility
   - If hardcore player dies mid-boss: they're out, fight continues for others

3. **Energy vs Health:** ✅ DECIDED
   - Energy system still exists and works exactly as normal mode
   - Energy gates fight cooldowns
   - Health is separate system ONLY for hardcore permadeath tracking
   - Both systems run in parallel: spend energy to fight, lose health each fight

4. **Item Earning During Run:** ✅ DECIDED
   - Players CAN find/earn items during hardcore (they show as green)
   - **80% of normal drop rates** for all items including medkits
   - Not too punishing - difficulty comes from HP system, not item scarcity
   - Adds slight challenge without making items a pain point

5. **Starting Hardcore:** ✅ DECIDED
   - Only available at level 20 as alternative to `!quest prestige`
   - It's a choice: prestige now OR try hardcore
   - Available at any prestige count (veteran players with 10 prestiges can still try)
   - Choosing hardcore delays your prestige until you reach level 50 (or die trying)

6. **Permanent Items Scope:** ✅ DECIDED
   - (h) permanent items work in BOTH normal and hardcore mode
   - They're always available, never get locked
   - Gives advantage in both modes but earned through hardcore completion

7. **Item Selection Pool:** ✅ DECIDED
   - Choose from ENTIRE inventory (locker + current run items)
   - Presented as numbered list at level 50
   - Strategic: rare boss drops from locker? Or powerful item from current run?

8. **Death Announcement:**
   - **CHANNEL-WIDE** announcement with flair
   - Include: name, level reached, maybe stats
   - Examples:
     - "💀⚰️ RIP Player - Died at level 23 after 47 wins. Another soul lost to the hardcore grind. ⚰️💀"
     - "☠️ HARDCORE DEATH ☠️ Player has fallen at level 23! (47W/12L)"
   - Make it dramatic - part of the fun!

9. **Abandon vs Death:**
   - Abandon (`!quest hardcore quit`): Get items back, can retry, no penalty
   - Death (0 HP): Lose everything, reset to level 1 normal, harsh penalty
   - This is intentional - gives escape hatch if life gets busy

10. **Medkit Availability:** ✅ DECIDED
    - Medkits drop randomly from fights (higher chance on defeat, lower on win)
    - Same mechanics as normal mode
    - Affected by 80% drop rate in hardcore
    - Heals small amount (10-20 HP)
    - Strategic: save for emergencies or use proactively?

11. **Win Rates:** ✅ DECIDED
    - Fight win percentages SAME as normal mode
    - Hardcore difficulty comes from HP system, not harder fights
    - Keeps combat feeling fair while adding permadeath stakes

12. **Challenge Path Interaction:**
    - Hardcore explicitly NOT a challenge path
    - Should be mutually exclusive (can't do both at once)
    - Entering hardcore disables challenge paths
    - Keeps complexity manageable

13. **Partial Completion:**
    - **ALL OR NOTHING** - Must reach level 50 for any reward
    - No prestige option at level 20
    - Can abandon and get items back, but no permanent item selection
    - Hardcore is meant to be a complete challenge

14. **XP Curve 20-50:**

    **DECIDED: Keep same formula (level * 100)**

    **Current formula:** `level * 100` XP to reach next level

    **Total XP comparison:**
    - Level 1 → 20: 21,000 total XP (100+200+...+2000)
    - Level 1 → 50: 127,500 total XP (100+200+...+5000)
    - **Level 20 → 50 alone: 106,500 XP** (about 5x the 1-20 journey)

    **Time estimates:**
    - Casual players: 1-20 takes days/weeks → 20-50 would take weeks/months
    - Power players: 1-20 takes ~2 days → 20-50 takes ~10 days
    - This is designed for power players who've "beaten" normal mode
    - Gives them a proper endgame challenge with permadeath stakes

### Implementation Notes

- State structure needs:
  - `hardcore_mode: bool` - Currently in hardcore
  - `hardcore_hp: int` - Current health
  - `hardcore_max_hp: int` - Max health (10 + 5*level)
  - `hardcore_locker: []` - Stored items during run
  - `hardcore_permanent_items: []` - Items kept from previous completions
  - `hardcore_completions: int` - Times completed
  - `hardcore_deaths: int` - Times died
  - `hardcore_best_level: int` - Furthest level reached before death

- Related existing systems:
  - Challenge paths (in challenge_paths.json) - need to ensure mutual exclusion
  - Abilities system - disable during hardcore
  - Prestige system - hardcore bypasses normal prestige at 20
  - Item/inventory system - locker mechanic, permanent items
  - Boss fights - damage scaling
  - Party/mob system - health damage in multiplayer

### Related Files
- `modules/quest.py` - Main quest module
- `config/challenge_paths.json` - May need hardcore exclusion flag

---

## For Player Feedback

When presenting this to players, key questions to ask:

1. **Is the reward worth the risk?** Does one permanent (h) item feel valuable enough for the 10-day grind + permadeath risk?

2. **Is the health system too punishing or too forgiving?**
   - Starting: 10 HP at level 1
   - Growth: +5 HP per level (260 HP at level 50)
   - Damage tiers need playtesting

3. **Should there be additional rewards?** Titles, badges, cosmetic unlocks, leaderboards?

4. **Is 80% item drop rate too low or too generous?**

5. **Should there be hardcore-only content?** Special bosses, unique items, exclusive storylines?

6. **Channel announcement style** - How dramatic should death/completion announcements be?

### Values That May Need Tuning

These numbers are educated guesses and will likely need adjustment:

- **HP damage ranges:** 2-5 / 5-10 / 8-15 for wins, 15-25 / 30-50 / 50-80 for losses
- **Boss defeat damage:** 60-80 HP or percentage-based
- **Medkit heal amount:** 10-20 HP
- **Drop rate:** 80% of normal
- **XP curve:** level * 100 (might need flattening if too grindy)

### Future Expansions (Not in Initial Version)

- Hardcore-only items or bosses
- Difficulty tiers (hardcore+, nightmare mode)
- Seasonal hardcore ladders/leaderboards
- Special achievements for deathless runs, speed runs, etc.
- Co-op hardcore mode with shared HP pool
- Legacy system (permanent items pass down to alts?)
