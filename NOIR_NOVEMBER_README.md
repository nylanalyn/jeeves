# Noir November Theme Guide

## Overview

This document describes the Noir November theme for Jeeves bot, which automatically activates on November 1st to transform the spooky Halloween theme into a hardboiled detective noir aesthetic.

## Theme Features

### Quest Module
- **Monsters**: Classic noir antagonists like Two-Bit Hoodlums, Crooked Cops, Speakeasy Goons, Blackmailers, Crime Syndicate Kingpins
- **Bosses**: The Crime Lord, The Femme Fatale, The Big Cheese
- **Character Classes**:
  - **Detective**: Hardboiled private eye with trusty revolver
  - **Reporter**: Investigative journalist seeking the big story
  - **Insider**: Street-smart character who knows the underbelly
- **Story Beats**: Noir-themed narrative with rain-soaked streets, smoke-filled offices, and mysterious dames
- **World Lore**: Atmospheric descriptions of perpetual darkness and urban decay

### Hunt Module
- **Animals**: Urban wildlife like Rats, Stray Cats, Watchdogs, Pigeons, Rooftop Crows
- **Theme**: Each animal has noir flavor text about surviving the streets, carrying secrets, or being witnesses
- **ASCII Art**: Maintains the visual appeal with appropriate representations

### Web UI Theme
- **Color Scheme**: Black and silver aesthetic (#0a0a0a, #f5f5f5, #c0c0c0)
- **Prestige Tiers**:
  - Casefile (📋) - Silver
  - Magnifier (🔍) - White with "SHADOW" banner
  - Detective (🏅️) - Gold with "BADGE" banner
- **Styling**: Sleek, minimalist noir design

## Installation

### Quick Setup
1. Run the theme switcher script to activate noir theme:
   ```bash
   python3 theme_switcher.py
   ```

2. Set up automatic theme switching for November 1st:
   ```bash
   ./setup_theme_cron.sh
   ```

### Manual Activation (For Testing)
The quest module will automatically detect the noir theme file even in non-November months. Simply ensure `quest_content_noir.json` exists in the root directory.

### Web UI Theme
The web UI theme requires manual theme file copying:
```bash
cp web_theme_noir.json web/quest/theme.json
```

## Files Created

### Core Theme Files
- `quest_content_noir.json` - Noir quest content (monsters, classes, stories)
- `web_theme_noir.json` - Noir web UI theme colors
- `config_hunt_noir.yaml` - Noir hunt animal configuration

### Automation Scripts
- `theme_switcher.py` - Main theme switching script
- `setup_theme_cron.sh` - Cron job setup for automatic switching

### Documentation
- `NOIR_NOVEMBER_README.md` - This guide

## Usage Instructions

### Before November 1st
1. **Test the theme** by running `python3 theme_switcher.py` - it will detect that noir files exist and apply them
2. **Review the content** to ensure everything looks good
3. **Set up the cron job** using `./setup_theme_cron.sh` for automatic activation

### On November 1st (Automatic)
The cron job will automatically:
1. Backup Halloween theme files
2. Apply noir theme to all modules
3. Update web UI theme
4. Update hunt module configuration
5. Log the changes to `theme_switch.log`

### After November
To restore the Halloween theme in December, modify the theme switcher or run it manually during October.

## Theme Switching Details

### What Gets Switched
1. **Quest Content**: `quest_content.json` ← `quest_content_noir.json`
2. **Web UI Theme**: `web/quest/theme.json` ← `web_theme_noir.json`
3. **Hunt Config**: Hunt section in `config/config.yaml` ← `config_hunt_noir.yaml`

### Backup Strategy
- Original files are backed up with `_halloween_backup` suffix
- Backups are only created once to prevent overwriting
- Restoration happens automatically when switching back to October

### Detection Logic
The quest module uses this priority:
1. **November**: Force noir theme
2. **October**: Force halloween theme
3. **Other months**: Use noir file if exists (for testing), otherwise default

## Customization

### Adding New Noir Content
Edit `quest_content_noir.json`:
- Add monsters to the `monsters` array
- Add bosses to `boss_monsters` array
- Modify classes in the `classes` object
- Update story_beats for new narrative elements

### Adjusting Colors
Edit `web_theme_noir.json`:
- Modify color values for different noir aesthetics
- Adjust prestige tier icons and banners
- Customize CSS variables

### Hunt Animals
Edit `config_hunt_noir.yaml`:
- Add or modify animals in the `hunt.animals` array
- Update ASCII art and flavor text
- Maintain the noir urban wildlife theme

## Troubleshooting

### Theme Not Applying
1. Check file permissions on theme files
2. Verify cron job is installed: `crontab -l`
3. Check log file: `cat theme_switch.log`
4. Run manually: `python3 theme_switcher.py`

### Web UI Not Updating
1. Restart the web server after theme change
2. Clear browser cache
3. Verify `web/quest/theme.json` exists and has correct content

### Hunt Module Not Using Theme
1. Check that `config/config.yaml` was updated
2. Verify YAML syntax is correct
3. Reload bot configuration with `!admin config reload`

## Rollback

To immediately restore Halloween theme:
```bash
# Restore quest content
cp quest_content_halloween_backup.json quest_content.json

# Restore web theme
cp web/quest/theme_halloween_backup.json web/quest/theme.json

# Restore hunt config
cp config/config_halloween_backup.yaml config/config.yaml

# Reload bot config (in IRC)
!admin config reload
```

Enjoy the Noir November atmosphere! 🎩🔍