# Fishing Annual Reset & Championship Titles — Design

**Date:** 2026-03-01
**Status:** Approved

---

## Overview

The fishing game resets completely on April 1st each year. Before the wipe, three
champions are crowned based on the previous year's performance. Each champion earns a
global title (visible across all bot messages via `title_for()`) and a passive mechanical
bonus that lasts the entire following year. This makes the year feel meaningful while
keeping each new season fresh.

---

## Champion Categories

| Category   | Winning Metric                          | Tiebreaker      | Title            | Bonus                              |
|------------|-----------------------------------------|-----------------|------------------|------------------------------------|
| Traveler   | Highest level reached (0–9)             | Most total fish | `the Traveler`   | +20% XP per successful catch       |
| Caster     | Highest `furthest_cast` value (meters)  | Most total fish | `the Caster`     | +20% cast distance                 |
| Collector  | Most entries in `rare_catches` list     | Most total fish | `the Collector`  | +20% to rare/legendary rarity weights |

- A single player can hold multiple titles simultaneously if they win more than one category.
- Titles do not carry over year-to-year — they reset with the player data each April 1st.
- If no one has played in a category (e.g. nobody caught any rare fish), that title is not awarded.

---

## Data Model

### New state key: `fishing_champions`

```json
{
  "year": 2025,
  "traveler": "<user_id or null>",
  "caster": "<user_id or null>",
  "collector": "<user_id or null>"
}
```

- Stored in the fishing module's existing state system alongside `players`, `active_casts`, and `active_event`.
- Champion status is looked up at runtime from this key — no new fields are added to individual player records.
- The `year` field is the year the season just ended (i.e. the year of the reset that produced these champions).

### No changes to player record schema

Champion status is derived from `fishing_champions`, not stored per player. The
`_get_player()` method and existing player schema are unchanged.

---

## Reset Ceremony

### Timing

A `schedule` library job fires at **midnight UTC on April 1st** each year.

On module load (`__init__`), the next April 1st midnight UTC is computed:
- If today is before April 1st of the current year, schedule for this year's April 1st.
- If today is on or after April 1st, schedule for next year's April 1st.

### Ceremony Sequence

1. Compute winners from current `players` state (highest level → Traveler, highest
   `furthest_cast` → Caster, most `rare_catches` entries → Collector). Apply total-fish
   tiebreaker where needed.
2. Update `fishing_champions` with new winners and the outgoing year.
3. Announce to **every channel where fishing is enabled** with a multi-line message.
4. Wipe `players: {}` and `active_casts: {}`.
5. Clear `active_event`.
6. Artifacts are lost in the reset (they live inside player records).

### Sample Announcement

```
** APRIL 1ST FISHING RESET ** The sea has been cleared! This year's champions:
the Traveler: Krissy (reached The Void, level 9) — carries a +20% XP blessing into the new year
the Caster: Bob (cast 4832.7m) — carries a +20% distance blessing
the Collector: Alice (47 rare/legendary catches) — carries a +20% rare blessing
Good luck to all in the new season!
```

---

## Title Display

### Global via `title_for()` in `jeeves.py`

The fishing module exposes a new method:

```python
def get_fishing_suffix_for_user(self, user_id: str) -> str
```

Returns a string like `"the Traveler"`, `"the Traveler the Collector"`, or `""`.

In `jeeves.py`'s `title_for()`, after the existing quest suffix block, a new block calls
`fishing.get_fishing_suffix_for_user(user_id)` and appends the result — mirroring the
existing quest pattern exactly.

**Example display names:**
- `Krissy the Traveler`
- `Sir the Caster the Collector Bob`
- `Krissy` (no title if not a champion)

---

## Bonus Application

All bonuses are applied silently in existing calculation functions, with a small tag
added to the `!reel` response when the bonus actually fires.

| Bonus       | Applied in                | Method                                               |
|-------------|---------------------------|------------------------------------------------------|
| Traveler XP | `_cmd_reel`               | After `total_xp` computed, before response built     |
| Caster dist | `_get_cast_distance()`    | As a multiplier on the final distance value          |
| Collector   | `_select_rarity()`        | Alongside existing artifact rarity boost logic       |

**Reel message tags (shown when bonus fires):**
- `(Traveler's blessing: +20% XP)`

Distance and rarity bonuses are silent (no message tag — they just feel better).

---

## New Command: `!fishing champions`

Displays the current title holders and the stats they won with.

```
Current fishing champions: Traveler: Krissy (level 9, The Void) | Caster: Bob (4832.7m) | Collector: Alice (47 rare/legendary)
```

If no reset has occurred yet (first year), replies with "No champions yet — the first reset is on April 1st!"

---

## Scope of Changes

- **`modules/fishing.py`:** ~150 lines added — champion computation, reset logic, schedule
  setup/teardown (`on_load`/`on_unload`), `get_fishing_suffix_for_user()`, bonus hooks in
  `_get_cast_distance()`, `_select_rarity()`, `_cmd_reel()`, and new `!fishing champions`
  command handler.
- **`jeeves.py`:** ~8 lines added inside `title_for()` to call the fishing suffix method.
- **No schema migrations** — new state key is created fresh on first reset.
- **No new files.**
