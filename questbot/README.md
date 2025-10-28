# QuestBot

A dedicated IRC bot that runs only the quest module from Jeeves.

## Why a Separate Bot?

The quest module has grown into a full-featured game system with 3000+ lines of code. By running it as a separate bot:
- Quest crashes don't affect Jeeves' core utilities
- Clean separation between butler functions and gaming
- Independent restart/maintenance capabilities
- Focused state management (only games.json)

## Setup

### 1. Install Dependencies

QuestBot uses the same dependencies as Jeeves:

```bash
pip install -r ../requirements.txt
```

### 2. Configure

Copy the default config and edit it:

```bash
cp config.yaml.default config/config.yaml
nano config/config.yaml
```

Edit these settings:
- `connection.server` - Your IRC server
- `connection.nickname` - Bot nickname (e.g., "QuestBot")
- `connection.channels` - Channels to join
- `connection.nickserv_pass` - NickServ password (if needed)
- `core.admins` - Admin users (nick + hostname)
- `quest.quest_channel` - Main quest channel

### 3. Copy Quest Data Files

QuestBot needs access to quest content files from the parent directory. These are accessed via relative paths:

```bash
# These files should already exist in parent directory:
# - quest_content.json
# - challenge_paths.json
```

### 4. Migrate Quest State (Optional)

If you're migrating from Jeeves to QuestBot, copy the quest module state:

```bash
# Extract quest state from Jeeves' games.json
python3 migrate_quest_state.py
```

Or manually copy the `modules.quest` section from Jeeves' `config/games.json` to QuestBot's `config/games.json`.

### 5. Run

```bash
python3 questbot.py
```

Or use a systemd service (see below).

## Running Both Bots

You can run both Jeeves and QuestBot simultaneously. Just make sure:

1. They use different nicknames
2. They join the same channels where you want quest commands
3. Remove quest module from Jeeves' config (add to `module_blacklist`)

### Updating Jeeves Config

In Jeeves' `config/config.yaml`, add quest to the blacklist:

```yaml
core:
  module_blacklist:
    - quest
```

Then reload Jeeves:
```
!admin reload
```

## Systemd Service

Create `/etc/systemd/system/questbot.service`:

```ini
[Unit]
Description=QuestBot IRC Game Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/jeeves/questbot
ExecStart=/usr/bin/python3 questbot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable questbot
sudo systemctl start questbot
```

## Architecture

QuestBot is a simplified version of Jeeves that:
- Only loads the quest module
- Uses simplified state management (only games.json)
- Implements minimal IRC bot functionality
- Shares the quest module code via symlink

### File Structure

```
questbot/
├── questbot.py           # Main bot (simplified Jeeves)
├── config.yaml.default   # Config template
├── config/
│   ├── config.yaml      # Active config (git-ignored)
│   └── games.json       # Quest state (git-ignored)
├── modules -> ../modules  # Symlink to parent modules dir
└── README.md            # This file
```

### State Management

QuestBot only manages `games.json` which contains the quest module state:
- Player data (levels, XP, stats)
- Active quests and boss fights
- Dungeon loadouts
- Challenge paths and abilities
- Prestige/transcendence data

## Admin Commands

QuestBot responds to quest commands just like Jeeves did:
- `!quest` - View your status
- `!quest prestige` - Prestige at level 20
- `!quest dungeon` - Enter dungeon mode
- See the quest module documentation for full command list

Admin-only commands (requires admin in config):
- `!admin debug on/off` - Toggle debug logging

## Troubleshooting

### Bot won't connect
- Check `connection.server` and `connection.port` in config
- Verify SSL settings (`use_ssl: true` for most servers)
- Check firewall/network access

### Quest module not loading
- Verify the `modules` symlink exists: `ls -la modules`
- Check quest content files exist in parent directory
- Enable debug logging: edit questbot.py and set `self._debug = True`

### State not saving
- Check permissions on `config/` directory
- Look for errors in console output
- Verify `games.json` is being created in `config/`

### Commands not working
- Verify bot is in the same channel as users
- Check `quest.quest_channel` matches the channel you're in
- Enable debug mode to see command processing
