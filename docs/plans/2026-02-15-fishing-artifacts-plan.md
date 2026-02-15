# Fishing Artifacts Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add rare artifact finds to the fishing game that modify cast flavor text and grant small mechanical bonuses.

**Architecture:** Single-file change to `modules/fishing.py`. Add an `ARTIFACTS` constant pool, modify `_cmd_cast` to use artifact text, modify `_cmd_reel` to discover artifacts from junk rolls, apply artifact bonuses at four existing calculation points, and add a `!discard` command. Player state gets one new field: `"artifact"`.

**Tech Stack:** Python, existing Jeeves module system (SimpleCommandModule base class, get_state/set_state persistence).

---

### Task 1: Add ARTIFACTS constant and artifact chance constant

**Files:**
- Modify: `modules/fishing.py:272-278` (after XP constants)

**Step 1: Add the constants**

Add after line 278 (`XP_BONUS_LARGE_RANGE = (40, 90)`):

```python
# Artifact discovery chance (portion of junk rolls that become artifacts)
ARTIFACT_CHANCE = 0.15

# Artifact pool - each modifies cast text and grants a small bonus
ARTIFACTS = [
    {
        "name": "Rod of Indifference",
        "cast_text": "You cast your line apathetically",
        "float_text": "and floats with profound disinterest",
        "bonus_type": "distance",
        "bonus_value": 0.10,
    },
    {
        "name": "Bobber of Passion",
        "cast_text": "You cast your line with burning intensity",
        "float_text": "and floats seductively",
        "bonus_type": "rarity",
        "bonus_value": 0.05,
    },
    {
        "name": "Line of Questionable Intent",
        "cast_text": "You cast your line suspiciously",
        "float_text": "and floats with unclear motives",
        "bonus_type": "junk_shield",
        "bonus_value": 0.25,
    },
    {
        "name": "Rod of Excessive Enthusiasm",
        "cast_text": "You cast your line with WAY too much energy",
        "float_text": "and floats aggressively",
        "bonus_type": "distance",
        "bonus_value": 0.15,
    },
    {
        "name": "Bobber of Existential Dread",
        "cast_text": "You cast your line into the uncaring void",
        "float_text": "and floats, contemplating its existence",
        "bonus_type": "xp",
        "bonus_value": 0.10,
    },
    {
        "name": "Line of Mild Disappointment",
        "cast_text": "You cast your line with a heavy sigh",
        "float_text": "and floats, barely trying",
        "bonus_type": "rarity",
        "bonus_value": 0.10,
    },
    {
        "name": "Rod of Unearned Confidence",
        "cast_text": "You cast your line like you own the place",
        "float_text": "and floats with smug satisfaction",
        "bonus_type": "xp",
        "bonus_value": 0.10,
    },
    {
        "name": "Bobber of Chaotic Energy",
        "cast_text": "You cast your line in a wild frenzy",
        "float_text": "and floats unpredictably",
        "bonus_type": "distance",
        "bonus_value": 0.20,
    },
    {
        "name": "Line of Ancient Wisdom",
        "cast_text": "You cast your line thoughtfully",
        "float_text": "and floats with quiet dignity",
        "bonus_type": "rarity",
        "bonus_value": 0.15,
    },
    {
        "name": "Rod of Procrastination",
        "cast_text": "You eventually get around to casting your line",
        "float_text": "and floats, putting things off",
        "bonus_type": "junk_shield",
        "bonus_value": 0.30,
    },
]
```

**Step 2: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "add artifact pool and chance constant to fishing module"
```

---

### Task 2: Add artifact field to player record

**Files:**
- Modify: `modules/fishing.py:453-479` (`_get_player` method)

**Step 1: Add artifact field to new player defaults**

In the `_get_player` method, add `"artifact": None,` to the player dict, after the `"force_rare_legendary"` field (line 476):

```python
                "force_rare_legendary": False,
                "artifact": None,
```

**Step 2: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "add artifact field to fishing player record"
```

---

### Task 3: Apply distance bonus in _get_cast_distance

**Files:**
- Modify: `modules/fishing.py:540-547` (`_get_cast_distance` method)

**Step 1: Add artifact_bonus parameter and apply it**

Change `_get_cast_distance` to accept an optional `artifact_bonus` parameter:

```python
    def _get_cast_distance(self, level: int, location: Dict[str, Any], artifact_bonus: float = 0.0) -> float:
        """Generate a random cast distance based on level and location."""
        max_dist = location["max_distance"]
        # Base distance is 30-70% of max, with level adding potential
        min_dist = max_dist * 0.3
        level_bonus = (level / 9) * 0.3  # Up to 30% bonus at max level
        base_max = max_dist * (0.7 + level_bonus)
        distance = random.uniform(min_dist, base_max)
        # Apply artifact distance bonus
        distance *= (1.0 + artifact_bonus)
        return round(distance, 1)
```

**Step 2: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "add artifact distance bonus support to _get_cast_distance"
```

---

### Task 4: Apply rarity bonus in _select_rarity

**Files:**
- Modify: `modules/fishing.py:549-593` (`_select_rarity` method)

**Step 1: Add artifact_rarity_boost parameter**

Change signature to add `artifact_rarity_boost: float = 0.0` and apply it alongside water boost. Add after the water boost block (after line 583):

```python
        # Apply artifact rarity boost
        if artifact_rarity_boost > 0:
            common_reduction = weights["common"] * artifact_rarity_boost
            weights["common"] = max(1, int(weights["common"] - common_reduction))
            weights["rare"] = int(weights["rare"] + common_reduction * 0.6)
            weights["legendary"] = int(weights["legendary"] + common_reduction * 0.4)
```

**Step 2: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "add artifact rarity bonus support to _select_rarity"
```

---

### Task 5: Modify _cmd_cast to use artifact text and distance bonus

**Files:**
- Modify: `modules/fishing.py:705-792` (`_cmd_cast` method)

**Step 1: Get player's artifact and apply distance bonus**

Replace the distance calculation (line 757) and cast message block (lines 779-783) with artifact-aware versions.

Around line 757, change:
```python
        distance = self._get_cast_distance(player["level"], location)
```
to:
```python
        # Apply artifact distance bonus if applicable
        artifact = player.get("artifact")
        artifact_distance_bonus = 0.0
        if artifact and artifact.get("bonus_type") == "distance":
            artifact_distance_bonus = artifact.get("bonus_value", 0.0)
        distance = self._get_cast_distance(player["level"], location, artifact_distance_bonus)
```

**Step 2: Replace cast message block with artifact-aware version**

Replace lines 779-783:
```python
        cast_msg = random.choice(CAST_MESSAGES).format(
            distance=distance,
            location=location["name"]
        )
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cast_msg}")
```
with:
```python
        if artifact:
            cast_msg = (
                f"{artifact['cast_text']}, it sails {distance}m into the {location['name']}, "
                f"{artifact['float_text']}..."
            )
        else:
            cast_msg = random.choice(CAST_MESSAGES).format(
                distance=distance,
                location=location["name"]
            )
        self.safe_reply(connection, event, f"{self.bot.title_for(username)}, {cast_msg}")
```

**Step 3: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "integrate artifact text and distance bonus into cast command"
```

---

### Task 6: Modify _cmd_reel for artifact discovery, junk_shield, rarity bonus, and XP bonus

**Files:**
- Modify: `modules/fishing.py:794-1056` (`_cmd_reel` method)

This is the largest change. Four insertion points:

**Step 1: Add junk_shield bonus (reduces junk chance)**

Around line 873-878 where junk_chance is calculated, change:
```python
        if not forced_rare_flag:
            junk_chance = 0.10
            if active_event and active_event.get("effect") == "junk_boost":
                junk_chance *= active_event.get("multiplier", 1.0)
```
to:
```python
        if not forced_rare_flag:
            junk_chance = 0.10
            if active_event and active_event.get("effect") == "junk_boost":
                junk_chance *= active_event.get("multiplier", 1.0)

            # Apply artifact junk shield
            artifact = player.get("artifact")
            if artifact and artifact.get("bonus_type") == "junk_shield":
                junk_chance *= (1.0 - artifact.get("bonus_value", 0.0))
```

**Step 2: Add artifact discovery inside the junk block**

Inside the `if random.random() < junk_chance:` block (around line 878), BEFORE the existing junk logic, add an artifact discovery check:

Replace the junk block (lines 878-891):
```python
            if random.random() < junk_chance:
                junk = self._get_junk(location["type"])
                player["junk_collected"] += 1
                self._save_player(user_id, player)
                achievement_hooks.record_achievement(self.bot, username, "junk_collected", 1)
                xp_gain = 5  # Small XP for junk
                player["xp"] += xp_gain
                self._save_player(user_id, player)
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)} reels in... {junk}. "
                    f"Well, at least you're cleaning up! (+{xp_gain} XP)"
                )
                return True
```
with:
```python
            if random.random() < junk_chance:
                # Chance for artifact instead of junk
                if random.random() < ARTIFACT_CHANCE:
                    new_artifact = random.choice(ARTIFACTS)
                    old_artifact = player.get("artifact")
                    player["artifact"] = new_artifact.copy()
                    self._save_player(user_id, player)
                    response = (
                        f"{self.bot.title_for(username)} reels in... wait, something else is tangled in the line! "
                        f"You found the {new_artifact['name']}! Your casts will never be the same."
                    )
                    if old_artifact:
                        response += f" (Replaced: {old_artifact['name']})"
                    self.safe_reply(connection, event, response)
                    return True

                junk = self._get_junk(location["type"])
                player["junk_collected"] += 1
                self._save_player(user_id, player)
                achievement_hooks.record_achievement(self.bot, username, "junk_collected", 1)
                xp_gain = 5  # Small XP for junk
                player["xp"] += xp_gain
                self._save_player(user_id, player)
                self.safe_reply(
                    connection, event,
                    f"{self.bot.title_for(username)} reels in... {junk}. "
                    f"Well, at least you're cleaning up! (+{xp_gain} XP)"
                )
                return True
```

**Step 3: Add artifact rarity bonus to the _select_rarity call**

Around line 895, change:
```python
        rarity = self._select_rarity(effective_wait, active_event, water_boost)
```
to:
```python
        artifact = player.get("artifact")
        artifact_rarity_boost = 0.0
        if artifact and artifact.get("bonus_type") == "rarity":
            artifact_rarity_boost = artifact.get("bonus_value", 0.0)
        rarity = self._select_rarity(effective_wait, active_event, water_boost, artifact_rarity_boost)
```

Note: `artifact` may already be defined earlier in the junk block scope — but that's inside a conditional `if not forced_rare_flag` block that returned. At this point we're past the junk check, so we re-fetch it here.

**Step 4: Add artifact XP bonus**

Around line 982-986 where `xp_gain` is calculated, after the event XP boost block:
```python
        # Event XP boost
        if active_event and active_event.get("effect") == "xp_boost":
            xp_gain = int(xp_gain * active_event.get("multiplier", 1.0))
```
add:
```python
        # Artifact XP boost
        artifact = player.get("artifact")
        if artifact and artifact.get("bonus_type") == "xp":
            xp_gain = int(xp_gain * (1.0 + artifact.get("bonus_value", 0.0)))
```

**Step 5: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "add artifact discovery, junk shield, rarity and XP bonuses to reel command"
```

---

### Task 7: Add !discard command

**Files:**
- Modify: `modules/fishing.py:384-451` (`_register_commands` method)
- Add new method after `_cmd_water`

**Step 1: Register the command**

Add to `_register_commands`, after the `!real` registration (around line 451):

```python
        self.register_command(
            r'^\s*!discard\s*$',
            self._cmd_discard,
            name="discard",
            description="Discard your current fishing artifact"
        )
```

**Step 2: Add the handler method**

Add after `_cmd_water` (end of file):

```python
    def _cmd_discard(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        if not self.is_enabled(event.target):
            return False

        user_id = self.bot.get_user_id(username)
        player = self._get_player(user_id)
        artifact = player.get("artifact")

        if not artifact:
            self.safe_reply(
                connection, event,
                f"{self.bot.title_for(username)}, you don't have an artifact to discard."
            )
            return True

        artifact_name = artifact["name"]
        player["artifact"] = None
        self._save_player(user_id, player)

        self.safe_reply(
            connection, event,
            f"{self.bot.title_for(username)} tosses the {artifact_name} into the water. "
            "All bonuses lost. Your casts return to normal."
        )
        return True
```

**Step 3: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "add !discard command for fishing artifacts"
```

---

### Task 8: Update fishing help to mention artifacts and !discard

**Files:**
- Modify: `modules/fishing.py:1316-1345` (`_cmd_fishing_help` method)

**Step 1: Add artifact info to help lines**

Add these lines to the `help_lines` list, before the empty string separator:

```python
            "!discard - Discard your current artifact and return to normal casts",
```

And add to the Tips section:

```python
            "Artifacts: Rare finds hidden among the junk! They change your cast style and grant small bonuses.",
```

**Step 2: Commit**

```bash
git add modules/fishing.py
git commit --no-verify -m "update fishing help with artifact and discard info"
```

---

### Task 9: Manual smoke test

**Step 1: Verify syntax**

```bash
python -c "import modules.fishing"
```

Expected: No errors.

**Step 2: Verify the module loads**

```bash
python -c "from modules.fishing import ARTIFACTS, ARTIFACT_CHANCE; print(f'{len(ARTIFACTS)} artifacts, {ARTIFACT_CHANCE} chance')"
```

Expected: `10 artifacts, 0.15 chance`
