# Roadmap & Feature Concepts

## Quest Hardcore Mode (Design Draft)
**Status:** Design complete, awaiting player validation.

### Concept
Hardcore mode offers a high-risk alternative to prestige. At level 20 players may enter hardcore instead of prestiging, push to level 50 under harsher rules, and earn a permanent item slot if they survive. Death resets progress with no prestige reward.

### Core Mechanics
- **Entry Point:** Triggered at level 20 via `!quest hardcore`; mutually exclusive with `!quest prestige`.
- **Inventory Lockers:** All items except previously designated hardcore-permanent gear move into storage until the run ends.
- **Health System:** Players track HP in addition to energy. Fights consume HP even on wins, and hitting 0 HP causes permadeath. Level-ups heal to full.
- **Rewards:** Successful runs grant delayed prestige bonuses, restore inventory, and allow the player to mark one item as permanently available in future hardcore attempts.
- **Abort Option:** `!quest hardcore quit` exits early with no penalty beyond lost progress.

### Balancing Notes
- Normalize injury chances and drop rates around an 80% baseline to keep challenge focused on HP attrition.
- Boss encounters should inflict heavier HP swings while remaining opt-in (`!mob` only).
- Track completion/death stats for leaderboard flair and optional profile badges.

### Open Questions
- Finalize damage scaling model (tiered numeric vs. percentage of max HP).
- Determine medkit healing values and whether additional hardcore-only consumables are needed.
- Decide if item permanence should be capped or left uncapped for long-term collectors.

### Implementation To-Do
1. Extend quest state to store hardcore runs, locker contents, and permanent item flags.
2. Add HP tracking to combat resolution, including victory and defeat branches.
3. Build command flows for entering, monitoring, quitting, and finishing hardcore runs.
4. Update web UI and in-game messaging to visualize HP, lockers, and permanent items.
5. Write regression and unit tests around HP math, storage migrations, and command parsing.
