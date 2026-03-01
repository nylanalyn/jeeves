# Fishing Annual Reset & Championship Titles — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an April 1st annual fishing reset that crowns three champions (Traveler, Caster, Collector) with global titles and passive bonuses for the following year.

**Architecture:** All new logic lives in `modules/fishing.py` (champion computation, reset ceremony, scheduler, bonus application, suffix method) plus a small hook in `jeeves.py`'s `title_for()` following the same pattern already used by the quest module. State is stored under a new `fishing_champions` key in the fishing module's existing state system.

**Tech Stack:** Python 3, `schedule` library (already used by roadtrip module), `unittest` for tests, existing `SimpleCommandModule` state API.

---

## Context You Must Know Before Starting

### Relevant files
- **`modules/fishing.py`** — all new code except the `title_for` hook
- **`jeeves.py:715-748`** — `title_for()` method where fishing suffix will be added
- **`tests/test_title_for.py`** — extend with fishing suffix tests
- **`modules/base.py:213-231`** — `get_state`/`set_state`/`save_state` (state API used by all modules)
- **`modules/roadtrip.py:165-189`** — reference for `schedule` + `on_load`/`on_unload` pattern

### How state works
Modules store state via `self.get_state(key, default)` / `self.set_state(key, value)` / `self.save_state()`. State lives in `_state_cache` (a dict). In tests, create a fishing stub by setting `_state_cache` directly — no file I/O needed.

### How `title_for` works
`jeeves.py:715-748` — builds a display name by stacking:
1. Courtesy title (Sir, Madam, custom)
2. Quest legend suffix (e.g. `(Legend III)`)
3. *(new)* Fishing champion suffix

Pattern for quest (lines 738-745):
```python
quest_module = self.pm.plugins.get("quest")
if quest_module and hasattr(quest_module, "get_legend_suffix_for_user"):
    suffix = quest_module.get_legend_suffix_for_user(user_id)
    if suffix and not base_title.endswith(suffix):
        base_title = f"{base_title} {suffix}"
```
The fishing hook follows this exactly, calling `get_fishing_suffix_for_user(user_id)`.

### Champion categories
| Category | Metric | Title string | Bonus |
|---|---|---|---|
| Traveler | Highest `level` (0–9) | `"the Traveler"` | +20% XP per reel |
| Caster | Highest `furthest_cast` | `"the Caster"` | +20% cast distance |
| Collector | `len(rare_catches)` | `"the Collector"` | +20% rare/legendary rarity weights |

Tiebreaker: most `total_fish`. If nobody qualifies for a category (empty metric), that champion is null.

### Champion state schema
```json
{
  "fishing_champions": {
    "year": 2025,
    "traveler": "user-id-string-or-null",
    "caster": "user-id-string-or-null",
    "collector": "user-id-string-or-null"
  }
}
```

### How to create a Fishing test stub
```python
import threading
from modules.fishing import Fishing

def _make_fishing_stub(state=None):
    f = Fishing.__new__(Fishing)
    f._state_cache = state or {}
    f._state_lock = threading.RLock()
    f._state_dirty = False
    return f
```

### Running tests
```bash
cd /jeeves
python -m pytest tests/ -v
```

---

## Task 1: Champion Computation Logic

**Files:**
- Create: `tests/test_fishing_champions.py`
- Modify: `modules/fishing.py` (add static method to `Fishing` class, after `_get_player`)

**Step 1: Write the failing tests**

Create `tests/test_fishing_champions.py`:

```python
import threading
import unittest
import types
import sys


def _install_stubs():
    for mod_name in ["irc", "irc.bot", "irc.connection"]:
        if mod_name not in sys.modules:
            sys.modules[mod_name] = types.ModuleType(mod_name)
    if "irc.bot" in sys.modules:
        sys.modules["irc.bot"].SingleServerIRCBot = object
    if "irc.connection" in sys.modules:
        sys.modules["irc.connection"].Factory = lambda *a, **kw: None
    if "schedule" not in sys.modules:
        sched = types.ModuleType("schedule")
        sched.every = lambda *a, **kw: sched
        sched.seconds = sched
        sched.do = lambda *a, **kw: None
        sched.get_jobs = lambda: []
        sched.cancel_job = lambda j: None
        sched.CancelJob = object()
        sys.modules["schedule"] = sched
    # Stub out achievement_hooks
    if "modules.achievement_hooks" not in sys.modules:
        ah = types.ModuleType("modules.achievement_hooks")
        ah.record_achievement = lambda *a, **kw: None
        ah.record_fishing_level = lambda *a, **kw: None
        sys.modules["modules.achievement_hooks"] = ah


_install_stubs()

from modules.fishing import Fishing  # noqa: E402


def _make_fishing(state=None):
    f = Fishing.__new__(Fishing)
    f._state_cache = state.copy() if state else {}
    f._state_lock = threading.RLock()
    f._state_dirty = False
    return f


def _player(level=0, furthest_cast=0.0, rare_catches=None, total_fish=0):
    return {
        "level": level,
        "furthest_cast": furthest_cast,
        "rare_catches": rare_catches or [],
        "total_fish": total_fish,
    }


class TestComputeAnnualChampions(unittest.TestCase):
    def test_returns_null_champions_when_no_players(self):
        result = Fishing._compute_annual_champions({})
        self.assertIsNone(result["traveler"])
        self.assertIsNone(result["caster"])
        self.assertIsNone(result["collector"])

    def test_traveler_is_highest_level(self):
        players = {
            "alice": _player(level=9),
            "bob": _player(level=5),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "alice")

    def test_caster_is_highest_furthest_cast(self):
        players = {
            "alice": _player(furthest_cast=100.0),
            "bob": _player(furthest_cast=4999.9),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["caster"], "bob")

    def test_collector_is_most_rare_catches(self):
        players = {
            "alice": _player(rare_catches=[{"name": "Fish"}] * 3),
            "bob": _player(rare_catches=[{"name": "Fish"}] * 10),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["collector"], "bob")

    def test_traveler_tiebreak_by_total_fish(self):
        players = {
            "alice": _player(level=9, total_fish=50),
            "bob": _player(level=9, total_fish=100),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "bob")

    def test_caster_tiebreak_by_total_fish(self):
        players = {
            "alice": _player(furthest_cast=500.0, total_fish=10),
            "bob": _player(furthest_cast=500.0, total_fish=99),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["caster"], "bob")

    def test_collector_tiebreak_by_total_fish(self):
        players = {
            "alice": _player(rare_catches=[{}] * 5, total_fish=5),
            "bob": _player(rare_catches=[{}] * 5, total_fish=20),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["collector"], "bob")

    def test_collector_ignores_players_with_no_rare_catches(self):
        players = {
            "alice": _player(rare_catches=[]),
            "bob": _player(rare_catches=[]),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertIsNone(result["collector"])

    def test_all_three_can_be_same_player(self):
        players = {
            "alice": _player(level=9, furthest_cast=9999.0, rare_catches=[{}] * 20, total_fish=100),
        }
        result = Fishing._compute_annual_champions(players)
        self.assertEqual(result["traveler"], "alice")
        self.assertEqual(result["caster"], "alice")
        self.assertEqual(result["collector"], "alice")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run tests to verify they fail**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py -v
```
Expected: FAIL with `AttributeError: type object 'Fishing' has no attribute '_compute_annual_champions'`

**Step 3: Implement `_compute_annual_champions` in `modules/fishing.py`**

Add this static method to the `Fishing` class, after the `_save_player` method (around line 568):

```python
@staticmethod
def _compute_annual_champions(players: Dict[str, Any]) -> Dict[str, Any]:
    """Compute the three annual champions from player data. Pure function."""
    def best(key_fn, filter_fn=None):
        candidates = [(uid, p) for uid, p in players.items() if filter_fn is None or filter_fn(p)]
        if not candidates:
            return None
        return max(candidates, key=lambda x: (key_fn(x[1]), x[1].get("total_fish", 0)))[0]

    return {
        "traveler": best(lambda p: p.get("level", 0), lambda p: p.get("level", 0) > 0),
        "caster": best(lambda p: p.get("furthest_cast", 0.0), lambda p: p.get("furthest_cast", 0.0) > 0),
        "collector": best(lambda p: len(p.get("rare_catches", [])), lambda p: len(p.get("rare_catches", [])) > 0),
    }
```

**Step 4: Run tests to verify they pass**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py -v
```
Expected: All 9 tests PASS

**Step 5: Commit**

```bash
cd /jeeves && git add tests/test_fishing_champions.py modules/fishing.py
git commit -m "feat(fishing): add _compute_annual_champions static method"
```

---

## Task 2: Champion Bonus Helper & Fishing Suffix Method

**Files:**
- Modify: `tests/test_fishing_champions.py` (add new test class at the bottom)
- Modify: `modules/fishing.py` (add two methods to `Fishing` class)

**Step 1: Write the failing tests**

Append to `tests/test_fishing_champions.py`:

```python
class TestGetChampionBonuses(unittest.TestCase):
    def test_no_champions_returns_zero_bonuses(self):
        f = _make_fishing({"fishing_champions": {}})
        bonuses = f._get_champion_bonuses("alice")
        self.assertEqual(bonuses["xp"], 0.0)
        self.assertEqual(bonuses["distance"], 0.0)
        self.assertEqual(bonuses["rarity"], 0.0)

    def test_traveler_gets_xp_bonus(self):
        f = _make_fishing({"fishing_champions": {"traveler": "alice"}})
        bonuses = f._get_champion_bonuses("alice")
        self.assertEqual(bonuses["xp"], 0.20)
        self.assertEqual(bonuses["distance"], 0.0)

    def test_caster_gets_distance_bonus(self):
        f = _make_fishing({"fishing_champions": {"caster": "bob"}})
        bonuses = f._get_champion_bonuses("bob")
        self.assertEqual(bonuses["distance"], 0.20)

    def test_collector_gets_rarity_bonus(self):
        f = _make_fishing({"fishing_champions": {"collector": "carol"}})
        bonuses = f._get_champion_bonuses("carol")
        self.assertEqual(bonuses["rarity"], 0.20)

    def test_player_can_hold_multiple_titles(self):
        f = _make_fishing({"fishing_champions": {
            "traveler": "alice", "caster": "alice", "collector": "alice"
        }})
        bonuses = f._get_champion_bonuses("alice")
        self.assertEqual(bonuses["xp"], 0.20)
        self.assertEqual(bonuses["distance"], 0.20)
        self.assertEqual(bonuses["rarity"], 0.20)

    def test_non_champion_gets_zero_bonuses(self):
        f = _make_fishing({"fishing_champions": {"traveler": "alice"}})
        bonuses = f._get_champion_bonuses("bob")
        self.assertEqual(bonuses["xp"], 0.0)


class TestGetFishingSuffix(unittest.TestCase):
    def test_no_champions_returns_empty(self):
        f = _make_fishing({"fishing_champions": {}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "")

    def test_traveler_returns_suffix(self):
        f = _make_fishing({"fishing_champions": {"traveler": "alice"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "the Traveler")

    def test_caster_returns_suffix(self):
        f = _make_fishing({"fishing_champions": {"caster": "alice"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "the Caster")

    def test_collector_returns_suffix(self):
        f = _make_fishing({"fishing_champions": {"collector": "alice"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "the Collector")

    def test_multiple_titles_join_in_order(self):
        f = _make_fishing({"fishing_champions": {
            "traveler": "alice", "caster": "alice", "collector": "alice"
        }})
        result = f.get_fishing_suffix_for_user("alice")
        self.assertEqual(result, "the Traveler the Caster the Collector")

    def test_non_champion_returns_empty(self):
        f = _make_fishing({"fishing_champions": {"traveler": "bob"}})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "")

    def test_no_fishing_champions_state_returns_empty(self):
        f = _make_fishing({})
        self.assertEqual(f.get_fishing_suffix_for_user("alice"), "")
```

**Step 2: Run tests to verify they fail**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py::TestGetChampionBonuses tests/test_fishing_champions.py::TestGetFishingSuffix -v
```
Expected: FAIL with AttributeError

**Step 3: Implement both methods in `modules/fishing.py`**

Add after `_compute_annual_champions`:

```python
def _get_champion_bonuses(self, user_id: str) -> Dict[str, float]:
    """Return active champion bonuses for a user. All values 0.0 if not a champion."""
    champions = self.get_state("fishing_champions", {})
    return {
        "xp": 0.20 if champions.get("traveler") == user_id else 0.0,
        "distance": 0.20 if champions.get("caster") == user_id else 0.0,
        "rarity": 0.20 if champions.get("collector") == user_id else 0.0,
    }

def get_fishing_suffix_for_user(self, user_id: str) -> str:
    """Return champion title suffix for display in title_for(). Empty string if none."""
    champions = self.get_state("fishing_champions", {})
    parts = []
    if champions.get("traveler") == user_id:
        parts.append("the Traveler")
    if champions.get("caster") == user_id:
        parts.append("the Caster")
    if champions.get("collector") == user_id:
        parts.append("the Collector")
    return " ".join(parts)
```

**Step 4: Run tests to verify they pass**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py -v
```
Expected: All tests PASS

**Step 5: Commit**

```bash
cd /jeeves && git add tests/test_fishing_champions.py modules/fishing.py
git commit -m "feat(fishing): add champion bonus helper and fishing suffix method"
```

---

## Task 3: Hook Fishing Suffix Into `title_for()`

**Files:**
- Modify: `tests/test_title_for.py` (add `_FishingStub` and new test class)
- Modify: `jeeves.py:738-748` (add fishing suffix block after quest suffix block)

**Step 1: Write the failing tests**

In `tests/test_title_for.py`, add after the `_QuestStub` class (around line 57):

```python
class _FishingStub:
    def __init__(self, suffix):
        self._suffix = suffix

    def get_fishing_suffix_for_user(self, user_id):
        return self._suffix
```

Update `_make_bot` to accept `fishing_suffix`:

```python
def _make_bot(*, courtesy_profile=None, quest_suffix=None, fishing_suffix=None):
    bot = Jeeves.__new__(Jeeves)
    plugins = {}
    if courtesy_profile is not None:
        plugins["courtesy"] = _CourtesyStub(courtesy_profile)
    if quest_suffix is not None:
        plugins["quest"] = _QuestStub(quest_suffix)
    if fishing_suffix is not None:
        plugins["fishing"] = _FishingStub(fishing_suffix)
    bot.pm = _PluginManagerStub(plugins)
    def _get_user_id(nick):
        return f"user-id-for:{nick}"
    bot.get_user_id = _get_user_id
    return bot
```

Add new test class at the bottom of `tests/test_title_for.py`:

```python
class TestTitleForFishingSuffix(unittest.TestCase):
    def test_fishing_suffix_appended_to_nick(self):
        bot = _make_bot(fishing_suffix="the Traveler")
        self.assertEqual(bot.title_for("Alice"), "Alice the Traveler")

    def test_fishing_suffix_appended_after_quest_suffix(self):
        bot = _make_bot(quest_suffix="(Legend)", fishing_suffix="the Collector")
        self.assertEqual(bot.title_for("Alice"), "Alice (Legend) the Collector")

    def test_fishing_suffix_appended_after_courtesy_and_quest(self):
        bot = _make_bot(
            courtesy_profile={"title": "archmage"},
            quest_suffix="(Legend)",
            fishing_suffix="the Traveler the Caster",
        )
        self.assertEqual(bot.title_for("Alice"), "Archmage (Legend) the Traveler the Caster")

    def test_empty_fishing_suffix_not_appended(self):
        bot = _make_bot(fishing_suffix="")
        self.assertEqual(bot.title_for("Alice"), "Alice")

    def test_no_fishing_module_no_change(self):
        bot = _make_bot()
        self.assertEqual(bot.title_for("Alice"), "Alice")
```

**Step 2: Run tests to verify they fail**

```bash
cd /jeeves && python -m pytest tests/test_title_for.py::TestTitleForFishingSuffix -v
```
Expected: FAIL (fishing suffix not yet applied)

**Step 3: Add fishing suffix block to `jeeves.py`**

In `jeeves.py`, find the quest suffix block (lines 738–745):
```python
        try:
            quest_module = self.pm.plugins.get("quest")
            if quest_module and hasattr(quest_module, "get_legend_suffix_for_user"):
                user_id = self.get_user_id(nick)
                suffix = quest_module.get_legend_suffix_for_user(user_id)
                if suffix and not base_title.endswith(suffix):
                    base_title = f"{base_title} {suffix}"
        except Exception as e:
            self.log_debug(f"[core] Error getting legend suffix for {nick}: {e}")
```

Add immediately after that block, before `return base_title`:

```python
        try:
            fishing_module = self.pm.plugins.get("fishing")
            if fishing_module and hasattr(fishing_module, "get_fishing_suffix_for_user"):
                user_id = self.get_user_id(nick)
                suffix = fishing_module.get_fishing_suffix_for_user(user_id)
                if suffix and not base_title.endswith(suffix):
                    base_title = f"{base_title} {suffix}"
        except Exception as e:
            self.log_debug(f"[core] Error getting fishing suffix for {nick}: {e}")
```

**Step 4: Run all title tests**

```bash
cd /jeeves && python -m pytest tests/test_title_for.py -v
```
Expected: All 10 tests PASS

**Step 5: Commit**

```bash
cd /jeeves && git add tests/test_title_for.py jeeves.py
git commit -m "feat: add fishing champion suffix to title_for()"
```

---

## Task 4: Apply Caster Distance Bonus in `_get_cast_distance()`

**Files:**
- Modify: `tests/test_fishing_champions.py` (add `TestCasterBonus` class)
- Modify: `modules/fishing.py` — `_get_cast_distance()` signature and `_cmd_cast` call site

**Step 1: Write the failing tests**

Append to `tests/test_fishing_champions.py`:

```python
class TestCasterBonus(unittest.TestCase):
    def test_no_champion_bonus_no_change(self):
        from modules.fishing import LOCATIONS
        puddle = LOCATIONS[0]  # max_distance=5
        # Without bonus, distance is in [1.5, 3.5] (0.3–0.7 * 5 for level 0)
        # With 0.0 bonus it should not exceed 5.0
        distance = Fishing._get_cast_distance(0, puddle, 0.0, 0.0)
        self.assertLessEqual(distance, 5.0)

    def test_caster_bonus_increases_distance(self):
        from modules.fishing import LOCATIONS
        void = LOCATIONS[9]  # max_distance=5000
        without = Fishing._get_cast_distance(9, void, 0.0, 0.0)
        with_bonus = Fishing._get_cast_distance(9, void, 0.0, 0.20)
        self.assertGreater(with_bonus, without)

    def test_caster_bonus_is_multiplicative(self):
        from modules.fishing import LOCATIONS, Fishing
        import random
        random.seed(42)
        void = LOCATIONS[9]
        random.seed(42)
        base = Fishing._get_cast_distance(9, void, 0.0, 0.0)
        random.seed(42)
        with_bonus = Fishing._get_cast_distance(9, void, 0.0, 0.20)
        self.assertAlmostEqual(with_bonus, base * 1.20, places=1)
```

**Step 2: Run tests to verify they fail**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py::TestCasterBonus -v
```
Expected: FAIL — `_get_cast_distance` doesn't accept a 4th argument yet

**Step 3: Update `_get_cast_distance` signature in `modules/fishing.py`**

Current signature (around line 622):
```python
def _get_cast_distance(self, level: int, location: Dict[str, Any], artifact_bonus: float = 0.0) -> float:
```

Change to:
```python
def _get_cast_distance(self, level: int, location: Dict[str, Any], artifact_bonus: float = 0.0, champion_bonus: float = 0.0) -> float:
```

At the end of the method, the current line:
```python
    distance *= (1.0 + artifact_bonus)
    return round(distance, 1)
```

Change to:
```python
    distance *= (1.0 + artifact_bonus)
    distance *= (1.0 + champion_bonus)
    return round(distance, 1)
```

**Step 4: Update the call site in `_cmd_cast`**

Find (around line 829):
```python
        distance = self._get_cast_distance(player["level"], location, artifact_distance_bonus)
```

Change to:
```python
        champion_bonuses = self._get_champion_bonuses(user_id)
        distance = self._get_cast_distance(player["level"], location, artifact_distance_bonus, champion_bonuses["distance"])
```

**Step 5: Run tests**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py -v
```
Expected: All tests PASS

**Step 6: Commit**

```bash
cd /jeeves && git add tests/test_fishing_champions.py modules/fishing.py
git commit -m "feat(fishing): apply Caster distance bonus in _get_cast_distance"
```

---

## Task 5: Apply Collector Rarity Bonus in `_select_rarity()`

**Files:**
- Modify: `tests/test_fishing_champions.py` (add `TestCollectorBonus`)
- Modify: `modules/fishing.py` — `_select_rarity()` signature and `_cmd_reel` call site

**Step 1: Write the failing tests**

Append to `tests/test_fishing_champions.py`:

```python
class TestCollectorBonus(unittest.TestCase):
    def test_select_rarity_accepts_champion_rarity_boost(self):
        f = _make_fishing({})
        # Should not raise with 5th argument
        result = f._select_rarity(20.0, None, 0.0, 0.20)
        self.assertIn(result, ["common", "uncommon", "rare", "legendary"])

    def test_collector_boost_shifts_weights_toward_rare(self):
        """With max wait and collector boost, rare/legendary should dominate."""
        import random
        f = _make_fishing({})
        random.seed(0)
        results_with = [f._select_rarity(20.0, None, 0.0, 0.20) for _ in range(200)]
        random.seed(0)
        results_without = [f._select_rarity(20.0, None, 0.0, 0.0) for _ in range(200)]
        rare_with = sum(1 for r in results_with if r in ("rare", "legendary"))
        rare_without = sum(1 for r in results_without if r in ("rare", "legendary"))
        self.assertGreater(rare_with, rare_without)
```

**Step 2: Run tests to verify they fail**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py::TestCollectorBonus -v
```
Expected: FAIL

**Step 3: Update `_select_rarity()` signature**

Current (around line 633):
```python
def _select_rarity(self, wait_hours: float, event: Optional[Dict[str, Any]] = None, artifact_rarity_boost: float = 0.0) -> str:
```

Change to:
```python
def _select_rarity(self, wait_hours: float, event: Optional[Dict[str, Any]] = None, artifact_rarity_boost: float = 0.0, champion_rarity_boost: float = 0.0) -> str:
```

At the end of the artifact rarity boost block (after line 664), find:
```python
        # Weighted random selection
```

Before that line, add:
```python
        # Apply champion rarity boost (same logic as artifact boost)
        if champion_rarity_boost > 0:
            common_reduction = weights["common"] * champion_rarity_boost
            weights["common"] = max(1, int(weights["common"] - common_reduction))
            weights["rare"] = int(weights["rare"] + common_reduction * 0.6)
            weights["legendary"] = int(weights["legendary"] + common_reduction * 0.4)
```

**Step 4: Update the call site in `_cmd_reel`**

In `_cmd_reel`, find the `_select_rarity` call (around line 1007):
```python
        rarity = self._select_rarity(effective_wait, active_event, artifact_rarity_boost)
```

Change to:
```python
        champion_bonuses = self._get_champion_bonuses(user_id)
        rarity = self._select_rarity(effective_wait, active_event, artifact_rarity_boost, champion_bonuses["rarity"])
```

**Step 5: Run tests**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py -v
```
Expected: All tests PASS

**Step 6: Commit**

```bash
cd /jeeves && git add tests/test_fishing_champions.py modules/fishing.py
git commit -m "feat(fishing): apply Collector rarity bonus in _select_rarity"
```

---

## Task 6: Apply Traveler XP Bonus in `_cmd_reel()`

**Files:**
- Modify: `modules/fishing.py` — `_cmd_reel()` XP calculation section

> No new tests for this task — the XP calculation is deeply embedded in `_cmd_reel`. The champion bonus helper is already tested. This step wires it in.

**Step 1: Locate the XP section in `_cmd_reel`**

Find around line 1090–1130 where `total_xp` is assembled:

```python
        total_xp = xp_gain + extra_xp
        player["xp"] += total_xp
        self._save_player(user_id, player)
```

**Step 2: Add Traveler XP bonus before `player["xp"] += total_xp`**

Replace:
```python
        total_xp = xp_gain + extra_xp
        player["xp"] += total_xp
```

With:
```python
        total_xp = xp_gain + extra_xp

        # Traveler champion XP bonus
        if not hasattr(self, '_champion_bonuses_cached'):
            pass  # bonuses already fetched earlier in this method
        champion_bonuses = self._get_champion_bonuses(user_id)
        if champion_bonuses["xp"] > 0:
            total_xp = int(total_xp * (1.0 + champion_bonuses["xp"]))
            bonus_messages.append(f"Traveler's blessing: +20% XP.")

        player["xp"] += total_xp
```

> **Note:** The `champion_bonuses` variable should be declared once near the top of the "Successful catch!" section (around line 1002). If `_get_champion_bonuses` is already being called earlier in `_cmd_reel` for the rarity boost (Task 5), reuse that variable instead of calling it again. Look for the `champion_bonuses = self._get_champion_bonuses(user_id)` line added in Task 5 and just use it here — no second call needed.

Actually, after Task 5, `champion_bonuses` is already defined in `_cmd_reel`. So just insert:

```python
        if champion_bonuses["xp"] > 0:
            total_xp = int(total_xp * (1.0 + champion_bonuses["xp"]))
            bonus_messages.append("Traveler's blessing: +20% XP.")
```

immediately before `player["xp"] += total_xp`.

**Step 3: Run all tests**

```bash
cd /jeeves && python -m pytest tests/ -v
```
Expected: All tests PASS

**Step 4: Commit**

```bash
cd /jeeves && git add modules/fishing.py
git commit -m "feat(fishing): apply Traveler XP bonus in _cmd_reel"
```

---

## Task 7: Add `!fishing champions` Command

**Files:**
- Modify: `modules/fishing.py` — new command handler + registration

**Step 1: Add the command registration in `_register_commands()`**

Find the `!fishing top` registration block and add after it:

```python
        self.register_command(
            r'^\s*!fish(?:ing)?\s+champions?\s*$',
            self._cmd_fishing_champions,
            name="fishing champions",
            description="Show current fishing champions and their winning stats"
        )
```

**Step 2: Add the handler method**

Add `_cmd_fishing_champions` after `_cmd_fishing_top`:

```python
def _cmd_fishing_champions(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
    if not self.is_enabled(event.target):
        return False

    champions = self.get_state("fishing_champions", {})
    if not champions or not any(champions.get(k) for k in ("traveler", "caster", "collector")):
        self.safe_reply(
            connection, event,
            "No champions yet — the first reset is on April 1st!"
        )
        return True

    year = champions.get("year", "?")
    players = self.get_state("players", {})
    user_map = self.bot.get_module_state("users").get("user_map", {})

    parts = [f"Fishing Champions ({year}):"]

    traveler_id = champions.get("traveler")
    if traveler_id:
        p = players.get(traveler_id, {})
        name = user_map.get(traveler_id, {}).get("canonical_nick", traveler_id)
        loc = self._get_location_for_level(p.get("level", 0))
        parts.append(f"the Traveler: {name} (level {p.get('level', 0)}, {loc['name']})")

    caster_id = champions.get("caster")
    if caster_id:
        p = players.get(caster_id, {})
        name = user_map.get(caster_id, {}).get("canonical_nick", caster_id)
        parts.append(f"the Caster: {name} ({p.get('furthest_cast', 0.0):.1f}m)")

    collector_id = champions.get("collector")
    if collector_id:
        p = players.get(collector_id, {})
        name = user_map.get(collector_id, {}).get("canonical_nick", collector_id)
        count = len(p.get("rare_catches", []))
        parts.append(f"the Collector: {name} ({count} rare/legendary catches)")

    self.safe_reply(connection, event, " | ".join(parts))
    return True
```

**Step 3: Run all tests**

```bash
cd /jeeves && python -m pytest tests/ -v
```
Expected: All PASS

**Step 4: Commit**

```bash
cd /jeeves && git add modules/fishing.py
git commit -m "feat(fishing): add !fishing champions command"
```

---

## Task 8: Annual Reset Logic

**Files:**
- Modify: `tests/test_fishing_champions.py` (add `TestAnnualReset`)
- Modify: `modules/fishing.py` — add `_run_annual_reset()`

**Step 1: Write the failing tests**

Append to `tests/test_fishing_champions.py`:

```python
class TestAnnualReset(unittest.TestCase):
    def _make_fishing_with_players(self):
        players = {
            "alice": {
                "level": 9, "furthest_cast": 5000.0,
                "rare_catches": [{}] * 20, "total_fish": 100,
                "xp": 0, "total_casts": 0, "biggest_fish": 0.0,
                "biggest_fish_name": None, "lines_broken": 0,
                "junk_collected": 0, "catches": {}, "catches_by_location": {},
                "locations_fished": [], "xp_boost_catches": 0,
                "force_rare_legendary": False, "artifact": None, "junk_curse_date": None,
            },
            "bob": {
                "level": 3, "furthest_cast": 100.0,
                "rare_catches": [], "total_fish": 10,
                "xp": 0, "total_casts": 0, "biggest_fish": 0.0,
                "biggest_fish_name": None, "lines_broken": 0,
                "junk_collected": 0, "catches": {}, "catches_by_location": {},
                "locations_fished": [], "xp_boost_catches": 0,
                "force_rare_legendary": False, "artifact": None, "junk_curse_date": None,
            },
        }
        state = {
            "players": players,
            "active_casts": {"alice": {"timestamp": "2025-01-01T00:00:00+00:00"}},
            "active_event": {"type": "test"},
        }
        f = _make_fishing(state)
        # Stub out bot and safe_say so reset doesn't crash
        class _BotStub:
            def get_module_state(self, name): return {"user_map": {}}
            joined_channels = ["#test"]
            config = {"fishing": {}}
        f.bot = _BotStub()
        f._messages_sent = []
        f.safe_say = lambda msg, target=None: f._messages_sent.append(msg)
        return f

    def test_reset_updates_fishing_champions(self):
        from datetime import datetime, timezone
        f = self._make_fishing_with_players()
        reset_year = 2025
        f._run_annual_reset(reset_year)
        champions = f.get_state("fishing_champions", {})
        self.assertEqual(champions["year"], reset_year)
        self.assertEqual(champions["traveler"], "alice")
        self.assertEqual(champions["caster"], "alice")
        self.assertEqual(champions["collector"], "alice")

    def test_reset_wipes_players(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertEqual(f.get_state("players", {}), {})

    def test_reset_clears_active_casts(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertEqual(f.get_state("active_casts", {}), {})

    def test_reset_clears_active_event(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertIsNone(f.get_state("active_event"))

    def test_reset_sends_announcement(self):
        f = self._make_fishing_with_players()
        f._run_annual_reset(2025)
        self.assertTrue(len(f._messages_sent) > 0)
        combined = " ".join(f._messages_sent)
        self.assertIn("RESET", combined)
```

**Step 2: Run tests to verify they fail**

```bash
cd /jeeves && python -m pytest tests/test_fishing_champions.py::TestAnnualReset -v
```
Expected: FAIL with AttributeError

**Step 3: Implement `_run_annual_reset()` in `modules/fishing.py`**

Add after `_cmd_fishing_champions`:

```python
def _run_annual_reset(self, reset_year: Optional[int] = None) -> None:
    """Execute the annual reset: crown champions, announce, wipe player data."""
    if reset_year is None:
        reset_year = datetime.now(UTC).year - 1  # Previous year's season

    players = self.get_state("players", {})
    user_map = self.bot.get_module_state("users").get("user_map", {})

    # Compute champions from current player data
    champions = self._compute_annual_champions(players)
    champions["year"] = reset_year
    self.set_state("fishing_champions", champions)

    # Build announcement lines
    lines = [f"** APRIL 1ST FISHING RESET ** The sea has been cleared! {reset_year} champions:"]

    traveler_id = champions.get("traveler")
    if traveler_id:
        p = players.get(traveler_id, {})
        name = user_map.get(traveler_id, {}).get("canonical_nick", traveler_id)
        loc = self._get_location_for_level(p.get("level", 0))
        lines.append(
            f"the Traveler: {name} (reached {loc['name']}, level {p.get('level', 0)}) "
            "— carries a +20% XP blessing into the new year"
        )
    else:
        lines.append("the Traveler: unclaimed (no one leveled up this year)")

    caster_id = champions.get("caster")
    if caster_id:
        p = players.get(caster_id, {})
        name = user_map.get(caster_id, {}).get("canonical_nick", caster_id)
        lines.append(
            f"the Caster: {name} (cast {p.get('furthest_cast', 0.0):.1f}m) "
            "— carries a +20% distance blessing"
        )
    else:
        lines.append("the Caster: unclaimed (no casts recorded this year)")

    collector_id = champions.get("collector")
    if collector_id:
        p = players.get(collector_id, {})
        name = user_map.get(collector_id, {}).get("canonical_nick", collector_id)
        count = len(p.get("rare_catches", []))
        lines.append(
            f"the Collector: {name} ({count} rare/legendary catches) "
            "— carries a +20% rare blessing"
        )
    else:
        lines.append("the Collector: unclaimed (no rare catches this year)")

    lines.append("Good luck to all in the new season!")

    # Broadcast to all enabled channels
    channels = [ch for ch in self.bot.joined_channels if self.is_enabled(ch)]
    for channel in channels:
        for line in lines:
            self.safe_say(line, target=channel)

    # Wipe player data
    self.set_state("players", {})
    self.set_state("active_casts", {})
    self.set_state("active_event", None)
    self.save_state()
```

**Step 4: Run all tests**

```bash
cd /jeeves && python -m pytest tests/ -v
```
Expected: All PASS

**Step 5: Commit**

```bash
cd /jeeves && git add tests/test_fishing_champions.py modules/fishing.py
git commit -m "feat(fishing): add _run_annual_reset method"
```

---

## Task 9: Scheduler — Auto-Trigger on April 1st

**Files:**
- Modify: `modules/fishing.py` — add `import schedule`, `on_load()`, `on_unload()`, and scheduler helper

**Step 1: Add `import schedule` at the top of `modules/fishing.py`**

Add after the existing imports (around line 6):
```python
import schedule
```

**Step 2: Add `_schedule_next_reset()`, `on_load()`, and `on_unload()` to the `Fishing` class**

Add after `__init__`:

```python
def _schedule_next_reset(self) -> None:
    """Cancel any existing reset jobs and schedule the next April 1st midnight UTC."""
    for job in schedule.get_jobs():
        if any(tag == f"{self.name}-annual-reset" for tag in job.tags):
            schedule.cancel_job(job)

    now = datetime.now(UTC)
    next_reset = datetime(now.year, 4, 1, 0, 0, 0, tzinfo=UTC)
    if now >= next_reset:
        next_reset = datetime(now.year + 1, 4, 1, 0, 0, 0, tzinfo=UTC)

    seconds_until = (next_reset - now).total_seconds()
    (
        schedule.every(seconds_until)
        .seconds
        .do(self._reset_and_reschedule)
        .tag(f"{self.name}-annual-reset")
    )

def _reset_and_reschedule(self):
    """Fire the annual reset and schedule the next one."""
    self._run_annual_reset()
    self._schedule_next_reset()
    return schedule.CancelJob  # Cancel this one-shot job; _schedule_next_reset created a new one

def on_load(self) -> None:
    super().on_load()
    self._schedule_next_reset()

def on_unload(self) -> None:
    super().on_unload()
    for job in schedule.get_jobs():
        if any(tag == f"{self.name}-annual-reset" for tag in job.tags):
            schedule.cancel_job(job)
```

**Step 3: Run all tests**

```bash
cd /jeeves && python -m pytest tests/ -v
```
Expected: All PASS

**Step 4: Manual smoke check**

Verify the module loads cleanly by running:
```bash
cd /jeeves && python -c "
import types, sys
# Install stubs
for m in ['irc','irc.bot','irc.connection']:
    sys.modules[m] = types.ModuleType(m)
sys.modules['irc.bot'].SingleServerIRCBot = object
sys.modules['irc.connection'].Factory = lambda *a,**kw: None
import schedule
from modules.fishing import Fishing
print('Fishing class loads OK')
print('Has get_fishing_suffix_for_user:', hasattr(Fishing, 'get_fishing_suffix_for_user'))
print('Has _compute_annual_champions:', hasattr(Fishing, '_compute_annual_champions'))
print('Has _run_annual_reset:', hasattr(Fishing, '_run_annual_reset'))
"
```
Expected output: All three `True`.

**Step 5: Commit**

```bash
cd /jeeves && git add modules/fishing.py
git commit -m "feat(fishing): add April 1st annual reset scheduler"
```

---

## Task 10: Update `!fishing help` Text

**Files:**
- Modify: `modules/fishing.py` — `_cmd_fishing_help()` help lines

**Step 1: Add champions command to help**

In `_cmd_fishing_help`, find the `help_lines` list and add after `"!aquarium - View your rare/legendary catches"`:

```python
"!fishing champions - Show this year's title holders and their winning stats",
```

**Step 2: Run all tests**

```bash
cd /jeeves && python -m pytest tests/ -v
```
Expected: All PASS

**Step 3: Final commit**

```bash
cd /jeeves && git add modules/fishing.py
git commit -m "docs(fishing): add champions command to help text"
```

---

## Final Verification

```bash
cd /jeeves && python -m pytest tests/ -v
```

All tests should pass. The feature is complete when:
- [ ] `!fishing champions` shows "No champions yet" on a fresh install
- [ ] `_compute_annual_champions` correctly picks winners and applies tiebreakers
- [ ] `get_fishing_suffix_for_user` returns the right title string(s)
- [ ] `title_for("Alice")` includes fishing titles globally
- [ ] Caster champion gets +20% distance on `!cast`
- [ ] Collector champion gets +20% rare/legendary weight on `!reel`
- [ ] Traveler champion sees "+20% XP" tag on successful reels
- [ ] Reset fires automatically via scheduler; wipes players and crowns champions
