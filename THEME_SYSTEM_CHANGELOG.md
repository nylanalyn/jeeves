# Quest Theme System - Injury Integration Update

## Summary

Injuries are now part of the theme files! When you switch themes, injuries automatically change to match the theme's setting.

## Changes Made

### 1. Code Updates

**modules/quest_pkg/quest_utils.py:182**
- Changed from `get_config_value("injury_system", ...)`
- To: `_get_content("injury_system", ...)`
- Now checks theme file first, falls back to config if not found

**modules/quest_pkg/__init__.py:770**
- Changed from `get_config_value("injury_system", ...)`
- To: `_get_content("injury_system", ...)`
- Admin injury command now uses themed injuries

### 2. Theme Files Updated

All theme files now include `injury_system` with themed injuries:

**quest_content.json** (Current - Noir November)
- Pistol Whipped
- Knife Wound
- Bourbon Hangover
- Cigarette Burn
- Broken Ribs

**quest_content_noir.json** (Noir Theme)
- Same as above

**quest_content_december.json** (December Shopping Theme)
- Paper Cut
- Sore Feet
- Stress Headache
- Cookie Burn
- Wallet Strain

**quest_content_scifi.json** (Sci-Fi Theme)
- Neural Feedback
- System Overload
- Code Injection
- Data Corruption
- Power Drain

## Backwards Compatibility

The system remains backwards compatible:
- If a theme file doesn't have `injury_system`, it falls back to config.yaml
- Existing config.yaml injury definitions still work
- Theme files override config when both are present

## How to Use

### Switching Themes (New Simple Method)
```bash
cp quest_content_december.json quest_content.json
!admin reload quest
```

That's it! Injuries automatically switch with the theme.

### Old Method (No Longer Required)
~~You used to need to manually edit config.yaml and reload config.~~
~~This is no longer necessary!~~

## Testing

Verified that:
✅ December theme loads 5 shopping-themed injuries
✅ Noir theme loads 5 detective-noir injuries
✅ Sci-fi theme loads 5 cyberpunk injuries
✅ All injuries have proper structure (name, description, duration_hours, effects)
✅ Code successfully loads from theme files

## Future Improvements

Consider adding to theme files next:
- Item names (medkit → Coffee, etc.)
- Custom ability names and descriptions
- Dungeon room themes
