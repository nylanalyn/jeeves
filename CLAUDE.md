# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Jeeves is a modular IRC butler bot written in Python 3.11.9. It connects to IRC servers and provides interactive features through a plugin-based architecture, including games (adventure, quest, hunt), utilities (weather, time, translation), and social features (user profiles, memos, reminders).

## Running the Bot

### First-Time Setup
```bash
pip install -r requirements.txt
python3 jeeves.py  # Creates config/config.yaml from config.yaml.default on first run
```

Edit `config/config.yaml` with your IRC server details and API keys, then run again.

### Normal Operation
```bash
python3 jeeves.py
```

The bot will:
1. Load configuration from `config/config.yaml`
2. Connect to IRC server using settings from `connection` section
3. Identify with NickServ if `nickserv_pass` is configured
4. Load all modules from `modules/` directory (except those in `module_blacklist`)
5. Join all channels in `joined_channels` state (stored in state.json)

## Architecture

### Core Components

**jeeves.py** - Main bot implementation
- `Jeeves` class extends `SingleServerIRCBot` from the `irc` library
- `PluginManager` handles dynamic module loading/unloading
- `MultiFileStateManager` provides thread-safe persistent JSON storage across multiple files (state.json, games.json, users.json, stats.json)
- IRC event handlers (`on_pubmsg`, `on_privmsg`, `on_join`, etc.) dispatch to modules

**modules/base.py** - Base classes for all modules
- `ModuleBase`: Abstract base with state management, command registration, rate limiting
- `SimpleCommandModule`: Subclass that enforces `_register_commands()` pattern
- Provides decorators like `@admin_required` for access control

### Module System

All modules follow this structure:

```python
from .base import SimpleCommandModule

def setup(bot, config):
    """Required entry point. Returns module instance or None."""
    return MyModule(bot, config)

class MyModule(SimpleCommandModule):
    name = "mymodule"  # Must match filename
    version = "1.0.0"
    description = "Module description"

    def _register_commands(self):
        # Register commands with patterns
        self.register_command(
            r"^\s*!mycommand\s+(.+)$",
            self._cmd_handler,
            name="mycommand",
            admin_only=False,
            cooldown=10.0,
            description="Command help text"
        )

    def on_ambient_message(self, connection, event, msg, username):
        """Optional: Handle messages that aren't commands."""
        if not self.is_enabled(event.target):
            return False
        # Natural language triggers go here
        return False  # Return True if message was handled
```

### Configuration System

Configuration is loaded from `config/config.yaml` and is read-only at runtime. The bot reads this file on startup and when `!admin config reload` is called.

**Channel Filtering**: Modules can be restricted to specific channels using:
```yaml
mymodule:
  some_setting: value
  allowed_channels: []  # Empty = module works in all channels (default)
  blocked_channels: ["#private"]  # Blocked from these channels
```

**Channel filtering logic:**
- If `allowed_channels` is not empty, module ONLY works in those channels
- If `allowed_channels` is empty, module works in all channels except `blocked_channels`
- `blocked_channels` only applies when `allowed_channels` is empty

**Configuration access** in module code:
- `self.get_config_value(key, channel, default)` - Get config value (no channel overrides anymore)
- `self.is_enabled(channel)` - Check if module is allowed in channel (uses allowed/blocked lists)

### State Management

**Global State** (jeeves.py):
- `state_manager.get_state()` - Get full state snapshot
- `state_manager.update_state(dict)` - Update top-level state
- `state_manager.get_module_state(name)` - Get module-specific state
- `state_manager.update_module_state(name, dict)` - Update module state

**Module State** (modules/base.py):
- `self.get_state(key, default)` - Get value from module's state
- `self.set_state(key, value)` - Set value (marks dirty)
- `self.update_state(dict)` - Update multiple values
- `self.save_state(force=False)` - Persist changes to disk

State is automatically saved on module unload. Use `force=True` for critical data.

### Command Dispatch Flow

1. IRC message arrives → `Jeeves.on_pubmsg()` or `Jeeves.on_privmsg()`
2. Check if user is ignored → Skip if true (unless `!unignore` command)
3. **Command Phase**: Iterate modules calling `_dispatch_commands()`
   - First module to return `True` stops iteration
4. **Ambient Phase**: If no command handled, iterate modules calling `on_ambient_message()`
   - First module to return `True` stops iteration

Each phase checks:
- Module enabled for channel (`is_enabled(channel)`)
- Admin permissions if required
- Per-user cooldowns

## Module Development Guide

### Creating a New Module

1. Create `modules/mymodule.py`
2. Implement `setup(bot, config)` function returning module instance
3. Inherit from `SimpleCommandModule` or `ModuleBase`
4. Register commands in `_register_commands()`
5. Optionally implement `on_ambient_message()` for natural language triggers
6. Add config section to `config.yaml.default` if needed

### Common Patterns

**Admin-only commands**:
```python
self.register_command(pattern, handler, name="foo", admin_only=True)
# Or use decorator:
@admin_required
def handler(self, connection, event, msg, username, match):
    pass
```

**User cooldowns**:
```python
# Cooldown enforced automatically via register_command()
self.register_command(pattern, handler, name="foo", cooldown=30.0)
```

**Rate limiting** (global, not per-user):
```python
if not self.check_rate_limit("feature_key", seconds=60.0):
    return False
```

**Safe message sending**:
```python
self.safe_reply(connection, event, "Message")  # Reply to channel/DM
self.safe_say("Message", "#channel")            # Send to specific channel
self.safe_privmsg(username, "Message")          # Send DM
```

**Geolocation helpers**:
```python
result = self._get_geocode_data("London, UK")
if result:
    lat, lon, geo_data = result
    location_name = self._format_location_name(geo_data)
```

**HTTP requests with retries**:
```python
session = self.requests_retry_session()
response = session.get(url, timeout=10)
```

### Module Lifecycle Hooks

- `on_load()` - Called after module loads (setup complete)
- `on_unload()` - Called before module unloads (auto-saves state)
- `on_config_reload(new_config)` - Called when `!admin config reload` runs

## Key Files and Directories

```
jeeves.py              # Main bot entry point
config.yaml.default    # Template configuration
config/
  config.yaml          # Active config (git-ignored)
  state.json           # Persistent state (git-ignored)
modules/
  base.py              # Base classes for all modules
  admin.py             # Admin commands (!admin, !reload, !say, etc.)
  *.py                 # Individual feature modules
fortunes/              # Fortune cookie text files
commandreference       # User-facing command documentation
debug.log              # Debug output (when debug mode enabled)
```

## Admin Commands

Admins are defined in `config.yaml` under `core.admins`. The bot verifies both nickname and hostname.

- `!admin reload` or `!reload` - Reload all modules from disk
- `!admin load <module>` - Load a specific module
- `!admin unload <module>` - Unload a specific module
- `!admin modules` - List all loaded modules
- `!admin config reload` - Reload config.yaml (without reloading modules)
- `!admin join <#channel>` - Join channel
- `!admin part <#channel> [msg]` - Leave channel
- `!say [#channel] <msg>` - Send message as bot
- `!admin debug <on|off>` - Toggle debug logging
- `!emergency quit [msg]` - Shutdown bot

**Note:** Configuration is now read-only at runtime. To change settings, edit `config/config.yaml` and use `!admin config reload`.

## Important Implementation Notes

### Thread Safety
- `StateManager` uses `threading.RLock()` for all operations
- Module state access via `ModuleBase` also uses locks
- State writes are batched with 1-second debounce timer
- Call `state_manager.force_save()` or `self.save_state(force=True)` for critical writes

### Configuration vs State
- **Configuration** lives in `config/config.yaml` and is read-only at runtime
- **Module state** lives in state files (state.json, games.json, users.json, stats.json) under `modules.<module_name>`
- Config is for settings; state is for runtime data (scores, profiles, game state, etc.)
- To modify config, edit `config.yaml` and reload with `!admin config reload`

### IRC Event Handling
- Use `event.source` for full hostmask (`nick!user@host`)
- Use `event.source.nick` for nickname
- Use `event.target` for channel name or bot's nick (in DMs)
- Use `event.arguments[0]` for message text

### User Identification
- `bot.get_user_id(nick)` returns stable user ID (uses `users` module if available)
- `bot.is_admin(event.source)` checks admin status via nickname + hostname
- `bot.is_user_ignored(username)` checks ignore list (via `courtesy` module)

### Natural Language Triggers
- Check if bot mentioned: `self.is_mentioned(msg)` uses `core.name_pattern` regex
- Implement `on_ambient_message()` for non-command triggers
- **Must** check `if not self.is_enabled(event.target): return False` as first line
- Return `True` if message handled, `False` otherwise

### Scheduled Tasks
- Bot runs `schedule` library in background thread (started in `on_welcome`)
- Use `schedule.every(N).hours.do(func)` for periodic tasks
- Schedule tasks in module's `on_load()` hook

## Development Workflow

1. Edit module code in `modules/`
2. Use `!reload` command in IRC to reload all modules without restarting bot
3. Check `debug.log` for errors (enable with `!admin debug on`)
4. Test with non-admin account by temporarily adding it to config admins list
5. Use per-channel config to test features in test channel before deploying to main channel

## Recent Refactoring (refactor-fixes branch)

The following improvements were made to enhance security and code quality:

### Security Fixes
- **quest.py**: Replaced unsafe `eval()` calls for XP formula calculation with safer `_calculate_xp_for_level()` method that validates expressions before evaluation
- **Schedule namespace collisions**: Fixed all schedule tags to use module-namespaced format (`{module}-tag`) to prevent cross-module interference in `bell.py`, `chatter.py`, and `quest.py`

### Code Quality Improvements
- **Module signatures**: Removed unused `config` parameter from all `setup()` and `__init__()` functions across all modules
- **Error logging**: Added traceback output to `StateManager._save_now()` for better debugging
- **Efficiency**: Removed redundant BeautifulSoup usage in `convenience.py` title extraction

### Breaking Changes
- Module `setup()` functions now only take `bot` parameter: `def setup(bot):` (was `def setup(bot, config):`)
- Module `__init__()` methods now only take `bot` parameter (except `gif.py` which also takes `api_key`)
- All config access is now done via `self.bot.config` or `self.get_config_value()`