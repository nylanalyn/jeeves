# Running Jeeves and QuestBot Together

This guide explains how to run both bots simultaneously.

## Quick Start

### 1. Set up QuestBot

```bash
cd questbot
cp config.yaml.default config/config.yaml
nano config/config.yaml  # Edit with your settings
```

### 2. Migrate Quest State (Optional)

If you have existing quest data in Jeeves:

```bash
cd questbot
python3 migrate_quest_state.py
```

### 3. Update Jeeves Config

Add quest to the module blacklist so Jeeves doesn't load it:

```yaml
# In config/config.yaml
core:
  module_blacklist:
    - quest
```

Then reload Jeeves (if running):
```
!admin reload
```

### 4. Start Both Bots

```bash
# Terminal 1 - Jeeves
python3 jeeves.py

# Terminal 2 - QuestBot
cd questbot
python3 questbot.py
```

## Configuration Tips

### Different Nicknames

Give each bot a distinct nickname:

**Jeeves config** (`config/config.yaml`):
```yaml
connection:
  nickname: "Jeeves"
```

**QuestBot config** (`questbot/config/config.yaml`):
```yaml
connection:
  nickname: "QuestBot"
```

### Same Channels

Both bots should join the same channels:

```yaml
connection:
  channels:
    - "#main"
    - "#gaming"
```

### Admin Access

Make sure your admin credentials are in both configs:

```yaml
core:
  admins:
    - nick: "YourNick"
      host: "your.hostname.here"
```

## What Each Bot Does

### Jeeves (Butler)
- `!weather` - Weather lookups
- `!time` - World times
- `!translate` - Translation
- `!fortune` - Fortune cookies
- `!coffee` - Coffee tracking
- `!memo` - User memos
- `!profile` - User profiles
- Social features (greetings, courtesy titles)
- All utility modules

### QuestBot (Game)
- `!quest` - Quest system
- `!mob` - Boss spawning
- All quest-related commands
- Dungeon system
- Challenge paths
- Prestige system
- Quest web UI (if enabled)

## Running as Services

### Jeeves Service

`/etc/systemd/system/jeeves.service`:
```ini
[Unit]
Description=Jeeves IRC Butler Bot
After=network.target

[Service]
Type=simple
User=youruser
WorkingDirectory=/path/to/jeeves
ExecStart=/usr/bin/python3 jeeves.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

### QuestBot Service

`/etc/systemd/system/questbot.service`:
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

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable jeeves questbot
sudo systemctl start jeeves questbot

# Check status
sudo systemctl status jeeves
sudo systemctl status questbot
```

## Benefits of Separation

1. **Stability**: Quest crashes don't affect Jeeves utilities
2. **Maintenance**: Can restart quest bot without disrupting other features
3. **Clarity**: Each bot has a focused purpose
4. **Scaling**: Can run on different machines if needed
5. **State Management**: Quest state isolated in its own files

## Troubleshooting

### Both bots fighting over nickname
- Make sure they have different nicknames in their configs

### Commands not working
- Check which bot is supposed to handle each command
- Verify both bots are in the target channel
- Use `!admin modules` to see what's loaded (Jeeves only)

### Quest state not migrating
- Run `migrate_quest_state.py` from the `questbot/` directory
- Manually check `config/games.json` for quest data

### One bot keeps disconnecting
- Check for NickServ conflicts
- Verify SSL settings match your IRC server
- Check logs for connection errors

## Going Back to Single Bot

If you want to merge back to a single bot:

1. Stop QuestBot
2. Copy quest state from `questbot/config/games.json` back to `config/games.json`
3. Remove `quest` from Jeeves' `module_blacklist`
4. Reload Jeeves: `!admin reload`
