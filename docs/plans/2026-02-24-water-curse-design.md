# !water Curse Design
**Date:** 2026-02-24

## Summary
The `!water` command, previously removed for abuse, is repurposed as a punishment. When a user types `!water`, Jeeves curses them with a full day of junk catches.

## Behaviour
- First `!water` of the UTC day: Jeeves responds with a butler-style curse message and sets a daily junk curse on the player.
- Subsequent `!water` calls the same day: silently ignored.
- While cursed: every `!reel` produces junk, bypassing junk_shield artifacts and rarity selection. No XP awarded.
- Curse expires automatically at the end of the UTC day (date comparison resets naturally).

## Implementation

### Player state
Add `"junk_curse_date": None` to the default player dict. Value is `"YYYY-MM-DD"` (UTC) when cursed.

### New command: `!water`
- Pattern: `r'^\s*!water\s*$'`
- Check `player["junk_curse_date"] == today` → silent return if already cursed
- Otherwise: set `junk_curse_date = today`, save, reply with curse message

### `_cmd_reel` change
Before the existing junk check, add:
```python
today = datetime.now(UTC).strftime("%Y-%m-%d")
if player.get("junk_curse_date") == today:
    junk = self._get_junk(location["type"])
    player["junk_collected"] += 1
    self._save_player(user_id, player)
    self.safe_reply(connection, event, f"{self.bot.title_for(username)} reels in... {junk}. The curse holds.")
    return True
```

## Design Decisions
- Curse bypasses `junk_shield` artifacts — thematically appropriate ("cheaters never prosper")
- No XP for cursed junk catches
- UTC day boundary for simplicity and consistency with the rest of the module
