# Fishing Artifacts Design

## Overview

Add rare artifact finds to the fishing game. When reeling in, instead of junk, players occasionally discover an artifact that modifies their future cast messages with absurd flavor text and grants a small mechanical bonus. Players hold one artifact at a time; finding a new one replaces the old.

## Data Model

Artifacts stored in player record as `player["artifact"]` (None when empty):

```python
{
    "name": "Rod of Indifference",
    "cast_text": "You cast your line apathetically",
    "float_text": "and floats with profound disinterest",
    "bonus_type": "distance",  # one of: distance, rarity, junk_shield, xp
    "bonus_value": 0.10,
}
```

## Artifact Pool (10 artifacts)

| Name | Cast Text | Float Text | Bonus Type | Bonus Value |
|------|-----------|------------|------------|-------------|
| Rod of Indifference | "You cast your line apathetically" | "and floats with profound disinterest" | distance | +10% |
| Bobber of Passion | "You cast your line with burning intensity" | "and floats seductively" | rarity | +5% |
| Line of Questionable Intent | "You cast your line suspiciously" | "and floats with unclear motives" | junk_shield | -25% |
| Rod of Excessive Enthusiasm | "You cast your line with WAY too much energy" | "and floats aggressively" | distance | +15% |
| Bobber of Existential Dread | "You cast your line into the uncaring void" | "and floats, contemplating its existence" | xp | +10% |
| Line of Mild Disappointment | "You cast your line with a heavy sigh" | "and floats, barely trying" | rarity | +10% |
| Rod of Unearned Confidence | "You cast your line like you own the place" | "and floats with smug satisfaction" | xp | +10% |
| Bobber of Chaotic Energy | "You cast your line in a wild frenzy" | "and floats unpredictably" | distance | +20% |
| Line of Ancient Wisdom | "You cast your line thoughtfully" | "and floats with quiet dignity" | rarity | +15% |
| Rod of Procrastination | "You eventually get around to casting your line" | "and floats, putting things off" | junk_shield | -30% |

## Discovery Mechanic

- During the existing junk check in `_cmd_reel` (~10% base chance), 15% of junk rolls become artifact finds instead.
- Effective artifact find rate: ~1.5% per successful reel.
- Finding an artifact replaces the current one (if any).

## Cast Message Integration

**With artifact:** Message assembled from parts:
1. Artifact `cast_text` (e.g. "You cast your line apathetically")
2. Distance with bonus applied (e.g. "it sails 35.2m into the Pond")
3. Artifact `float_text` (e.g. "and floats with profound disinterest...")

**Without artifact:** Unchanged - random pick from existing `CAST_MESSAGES`.

## Artifact Discovery Message

> "Duke reels in... wait, something else is tangled in the line! You found the **Rod of Indifference**! Your casts will never be the same. (Replaced: Bobber of Passion)"

The "(Replaced: ...)" only shows if they had a previous artifact.

## Bonus Application Points

- `distance`: applied in `_get_cast_distance`, multiplies final distance
- `rarity`: applied in `_select_rarity`, boosts rare/legendary weights (same mechanism as water boost)
- `junk_shield`: reduces junk chance in `_cmd_reel`
- `xp`: applied to `xp_gain` calculation in `_cmd_reel`

## Commands

**`!discard`** - Removes current artifact.
- With artifact: "You toss the Rod of Indifference into the water. All bonuses lost. Your casts return to normal."
- Without artifact: "You don't have an artifact to discard."

No other new commands. Artifact info visible only through cast messages.
