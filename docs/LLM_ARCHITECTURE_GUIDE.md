# Jeeves Architecture Guide for LLMs

**Purpose**: This document provides a comprehensive overview of Jeeves' architecture for AI coding assistants. Read this first before making changes to understand how all the pieces fit together.

---

## Table of Contents
1. [High-Level Architecture](#high-level-architecture)
2. [Core Components](#core-components)
3. [How Modules Work](#how-modules-work)
4. [State Management](#state-management)
5. [User Identity Tracking](#4-modulesuserspy---user-identity-tracking)
6. [Admin System](#5-modulesadminpy---admin-system)
7. [How to Write a New Module](#how-to-write-a-new-module)
8. [Common Patterns](#common-patterns)
9. [Common Pitfalls](#common-pitfalls)
10. [File Locations](#file-locations)
11. [Development & Testing Tools](#development--testing-tools)

---

## High-Level Architecture

Jeeves is a **modular IRC bot** built with Python 3.11 using the `irc` library. The architecture follows these principles:

1. **Single bot instance** (`jeeves.py`) manages the IRC connection
2. **Plugin manager** (`PluginManager` in `jeeves.py`) loads modules dynamically from `modules/` (respects `core.module_blacklist`)
3. **Modules** inherit from `ModuleBase` or `SimpleCommandModule` (in `modules/base.py`)
4. **Shared state** is managed through `MultiFileStateManager` and persisted to JSON files in `config/`
5. **User identity** is tracked persistently across nickname changes via `modules/users.py`

### Data Flow

```
IRC Server
    ↓
jeeves.py (IRC event handlers)
    ↓
PluginManager dispatches to modules
    ↓
Module processes command/message
    ↓
Module updates state via bot.update_module_state()
    ↓
MultiFileStateManager writes to config/*.json
    ↓
Module sends response via connection.privmsg()
```

---

## Core Components

### 1. `jeeves.py` - The Main Bot

**Location**: `jeeves.py`

**Key Responsibilities**:
- IRC connection management (connect, reconnect, TLS)
- IRC event handling (pubmsg, privmsg, join, part, nick changes)
- Plugin management (loading, unloading, reloading modules)
- State management coordination
- User identity tracking
- Admin/courtesy title system
- Scheduler thread for hourly/daily tasks

**Important Methods**:
```python
def on_pubmsg(connection, event):
    # Handles public channel messages
    # Dispatches to module.on_pubmsg() for each loaded module

def on_privmsg(connection, event):
    # Handles private messages
    # Dispatches to module.on_privmsg() for each loaded module

def get_user_id(username: str) -> str:
    # Returns persistent UUID for a user (via users module)

def is_admin(event_source: str) -> bool:
    # Checks if user nick is in config admins (hostname recorded for reference)

def title_for(username: str) -> str:
    # Returns courtesy title for user (e.g., "Sir Bob", "Madam Alice")

def get_module_state(module_name: str) -> dict:
    # Gets state dict for a module

def update_module_state(module_name: str, state: dict):
    # Saves state dict for a module
```

**Critical Attributes**:
```python
self.connection         # IRC connection object (use this to send messages)
self.pm                 # PluginManager instance (access loaded modules)
self.config             # Loaded config from config.yaml
self.ROOT               # Path to bot root directory
self.primary_channel    # Main channel (usually first in config)
self.joined_channels    # Set of currently joined channels
```

---

### 2. `modules/base.py` - Module Base Classes

**Location**: `modules/base.py`

**Two Base Classes**:

#### `ModuleBase` (Abstract Base)
- Low-level base for all modules
- Provides state management, command registration, rate limiting
- Must implement event handlers manually

#### `SimpleCommandModule` (Recommended)
- Extends `ModuleBase`
- Automatically calls `_register_commands()` on init
- Best for command-based modules (most modules)

**Key Methods**:

```python
def register_command(pattern, handler, name, admin_only=False, cooldown=0.0, description=""):
    # Register a command with regex pattern
    # pattern: str or re.Pattern (use r'^\s*!commandname\s*$')
    # handler: method to call when command matches
    # admin_only: if True, only admins can use
    # cooldown: seconds between uses per user

def get_state(key=None, default=None):
    # Get module state (cached)
    # key=None returns entire state dict

def set_state(key, value):
    # Set a state value (marks dirty)

def save_state(force=False):
    # Persist state to disk (only if dirty or force=True)

def get_config_value(key, channel=None, default=None):
    # Get config value with channel override support
    # Supports dotted keys: "energy_system.enabled"

def is_enabled(channel):
    # Check if module is enabled for a channel
    # Uses allowed_channels/blocked_channels from config

def safe_reply(connection, event, text):
    # Send message to event.target (channel or user)
    # Handles multi-line messages automatically

def safe_say(text, target=None):
    # Send message to channel (default: primary_channel)

def log_debug(message):
    # Log debug message with module name prefix
```

**Important Decorators**:
```python
@admin_required
def _cmd_admin_thing(self, connection, event, msg, username, match):
    # Automatically checks if user is admin
    # Returns False if not admin (command ignored)
```

---

### 3. `MultiFileStateManager` - State Persistence

**Location**: Inside `jeeves.py` (class `MultiFileStateManager`)

**Managed Files** (in `config/`, data lives under a top-level `modules` key):
- `state.json` - General module state (default bucket)
- `users.json` - User profiles and UUID mappings (for `users`, `weather`, `memos`, `profiles`)
- `games.json` - Quest/game data (`quest`, `hunt`, `bell`, `adventure`, `roadtrip`)
- `stats.json` - Usage statistics (`coffee`, `courtesy`, `leveling`, `duel`)
- `absurdia.db` - SQLite database for Absurdia game

**How It Works**:
1. On boot: Loads all JSON files into memory, creating backups when possible
2. Runtime: Modules read/write via `bot.get_module_state()` and `bot.update_module_state()`
3. State is **cached** in memory (fast reads)
4. Writes are buffered: `save_state()` marks dirty and a 0.5s timer flushes to disk via temp file swap + file lock
5. Module data is stored at `modules.<module_name>` inside the routed file (routing is automatic via `STATE_FILE_MAPPING`)

**Example** (`state.json` structure):
```json
{
  "modules": {
    "adventure": {
      "active_users": {}
    },
    "hunt": {
      "animals": {},
      "spawn_locations": ["#transience", "#absurdia"]
    },
    "quest": {
      "active_quests": {}
    }
  }
}
```

**Important**: Always call `self.save_state()` after `self.set_state()` to persist changes!

---

### 4. `modules/users.py` - User Identity Tracking

**Location**: `modules/users.py`

**Purpose**: Maps IRC nicknames to persistent UUIDs so users maintain identity across nick changes.

**Data Structure** (`users.json`, stored under `modules.users`):
```json
{
  "modules": {
    "users": {
      "user_map": {
        "uuid-1234-5678": {
          "id": "uuid-1234-5678",
          "canonical_nick": "Alice",
          "seen_nicks": ["alice", "alice_afk", "alice_mobile"],
          "first_seen": "2024-01-15T10:30:00Z",
          "flavor_enabled": true
        }
      },
      "nick_map": {
        "alice": "uuid-1234-5678",
        "alice_afk": "uuid-1234-5678",
        "alice_mobile": "uuid-1234-5678"
      }
    }
  }
}
```

**How to Use**:
```python
# In any module:
user_id = self.bot.get_user_id(username)  # Returns UUID
# user_id is stable across nick changes!

# Store data by user_id, not username
user_data = self.get_state("user_data", {})
user_data[user_id] = {"coins": 100, "level": 5}
self.set_state("user_data", user_data)
self.save_state()
```

**Why This Matters**:
- Don't use nicknames as keys! They change.
- Always get `user_id` via `bot.get_user_id(username)`
- Store data keyed by `user_id`

---

### 5. `modules/admin.py` - Admin System

**Location**: `modules/admin.py`

**Admin Detection**:
- Admins are listed by **nickname** in `core.admins` inside `config.yaml` (hostnames are recorded at runtime but not matched).
- Sensitive operations require **super admin** auth via `core.super_admin_password_hash`; authenticate in /msg with `!pass <password>`.
- When an admin speaks, their hostname is stored in courtesy state for informational/logging purposes.

**Checking Admin Status**:
```python
if self.bot.is_admin(event.source):
    ...

@admin_required
def _cmd_secret(self, connection, event, msg, username, match):
    ...
```

**Admin/Super-Admin Commands** (through `!admin ...`, plus aliases):
- `!admin reload` / `!reload` – reload all modules (super admin)
- `!admin load <module>` / `!admin unload <module>` – load/unload module (super admin)
- `!admin config reload` – reload config without reloading modules (super admin)
- `!emergency quit [msg]` – emergency shutdown (super admin)
- `!admin modules` – list loaded modules
- `!admin join <#channel>` / `!admin part <#channel> [msg]`
- `!say [#channel] <message>` – speak (alias for `!admin say`)
- `!admin debug <on|off>` or `!admin debug <module> <on|off>`
- `!pass <password>` – authenticate as super admin (use in private message)

---

### 6. `modules/courtesy.py` - Title System

**Location**: `modules/courtesy.py`

**Purpose**: Manages formal titles ("Sir", "Madam", "Lord", etc.) for users.

**How It Works**:
- Titles/profiles stored in `config/stats.json` under the courtesy module state (`modules.courtesy.profiles`)
- Earned via quest system or granted by admins
- Retrieved via `self.bot.title_for(username)`

**Usage in Modules**:
```python
# When addressing a user formally:
response = f"{self.bot.title_for(username)}, you have 100 coins."
# Output: "Sir Bob, you have 100 coins."

# Or just use username for casual responses:
response = f"{username}, you have 100 coins."
# Output: "bob, you have 100 coins."
```

---

### 7. `config_validator.py` - Configuration Validation

**Location**: `config_validator.py`

**Purpose**: Pre-flight configuration validation with environment variable substitution.

**Key Features**:
- Validates YAML structure, required fields, and API key formats
- Performs environment variable substitution (supports `${VAR_NAME}` syntax)
- Checks for placeholder values and provides actionable error messages
- Creates configuration backups when possible

**Usage**:
```bash
python3 config_validator.py config/config.yaml
```

**When to Use**:
- Before starting the bot for the first time
- After making configuration changes
- When troubleshooting startup failures
- As part of CI/CD pipelines

**Important**: Always run the validator before starting the bot to catch configuration errors early.

## How Modules Work

### Module Lifecycle

1. **Load**: `jeeves.py` imports `modules/<name>.py`
2. **Setup**: Calls `setup(bot)` function which returns module instance
3. **Init**: Module `__init__()` calls `super().__init__(bot)` (SimpleCommandModule will call `_register_commands()` for you)
4. **Run**: Bot dispatches IRC events to module methods
5. **Unload** (if reloaded): Calls `on_unload()`, saves state

**Plugin loading details**:
- Discovers `modules/*.py` (sorted), skipping `__init__.py` and `base.py`.
- Filters out any filenames listed in `core.module_blacklist` in `config.yaml`.

### Required Module Structure

```python
# modules/mymodule.py
from typing import Any
import re
from .base import SimpleCommandModule

def setup(bot: Any) -> 'MyModule':
    """Required: Entry point for module loading."""
    return MyModule(bot)

class MyModule(SimpleCommandModule):
    name = "mymodule"
    version = "1.0.0"
    description = "Does cool things"

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)  # MUST call this first; this also triggers _register_commands()
        # Custom initialization here

    def _register_commands(self) -> None:
        """Required by SimpleCommandModule."""
        self.register_command(
            r'^\s*!hello\s*$',
            self._cmd_hello,
            name="hello",
            description="Say hello"
        )

    def _cmd_hello(self, connection: Any, event: Any,
                   msg: str, username: str, match: re.Match) -> bool:
        """Command handler signature."""
        self.safe_reply(connection, event, f"Hello, {username}!")
        return True  # Return True if handled
```

### Event Handlers

Modules can implement these methods to handle IRC events:

```python
def on_pubmsg(self, connection, event) -> bool:
    """Handle public channel messages."""
    # Access message: event.arguments[0]
    # Access username: event.source.nick
    # Access channel: event.target
    # Return True if handled (stops propagation)

def on_privmsg(self, connection, event) -> bool:
    """Handle private messages."""
    # Similar to on_pubmsg

def on_ambient_message(self, connection, event, msg: str) -> bool:
    """Handle messages that don't match commands (passive listening)."""
    # Called after command dispatch fails
    # Use for triggers like "mentions jeeves"

def on_join(self, connection, event):
    """User joined a channel."""
    # event.source.nick = who joined
    # event.target = channel

def on_part(self, connection, event):
    """User left a channel."""

def on_nick(self, connection, event, old_nick: str, new_nick: str):
    """User changed nickname."""
```

---

## State Management

### Module State Pattern

Every module gets its own state namespace:

```python
class MyModule(SimpleCommandModule):
    def __init__(self, bot):
        super().__init__(bot)
        # Load or initialize state
        if not self.get_state("users"):
            self.set_state("users", {})
            self.save_state()

    def _cmd_award_coins(self, connection, event, msg, username, match):
        user_id = self.bot.get_user_id(username)

        # Get current state
        users = self.get_state("users", {})

        # Modify
        if user_id not in users:
            users[user_id] = {"coins": 0}
        users[user_id]["coins"] += 10

        # Save
        self.set_state("users", users)
        self.save_state()

        self.safe_reply(connection, event,
                       f"Awarded 10 coins! Total: {users[user_id]['coins']}")
        return True
```

### State Best Practices

1. **Always use user_id, never username**:
   ```python
   # WRONG
   users[username] = {"coins": 100}

   # CORRECT
   user_id = self.bot.get_user_id(username)
   users[user_id] = {"coins": 100}
   ```

2. **Save after modifications**:
   ```python
   self.set_state("data", new_data)
   self.save_state()  # Don't forget this!
   ```

3. **Use defaults**:
   ```python
   users = self.get_state("users", {})  # Returns {} if not set
   ```

4. **State is cached** - get_state() is fast, call it freely

---

## How to Write a New Module

### Step-by-Step Guide

1. **Create file**: `modules/mymodule.py`

2. **Copy template**:
```python
from typing import Any
import re
from .base import SimpleCommandModule

def setup(bot: Any) -> 'MyModule':
    return MyModule(bot)

class MyModule(SimpleCommandModule):
    name = "mymodule"
    version = "1.0.0"
    description = "My cool module"

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)  # This automatically calls _register_commands()
        # Initialize state
        if not self.get_state("initialized"):
            self.set_state("initialized", True)
            self.set_state("data", {})
            self.save_state()

    def _register_commands(self) -> None:
        self.register_command(
            r'^\s*!mycommand\s*$',
            self._cmd_mycommand,
            name="mycommand",
            description="Does a thing"
        )

    def _cmd_mycommand(self, connection: Any, event: Any,
                       msg: str, username: str, match: re.Match) -> bool:
        user_id = self.bot.get_user_id(username)
        self.safe_reply(connection, event, "It works!")
        return True
```

3. **Add to config** (optional): `config/config.yaml`
```yaml
mymodule:
  enabled: true
  allowed_channels: []  # Empty = all channels
  cooldown_seconds: 5
  custom_setting: 42
```

4. **Test**:
   - Restart bot or use `!reload mymodule`
   - Try command in IRC: `!mycommand`
   - Check `debug.log` for errors

---

## Common Patterns

### Pattern 1: User Data Tracking

```python
def _cmd_register(self, connection, event, msg, username, match):
    user_id = self.bot.get_user_id(username)

    users = self.get_state("users", {})
    if user_id in users:
        self.safe_reply(connection, event, "Already registered!")
        return True

    users[user_id] = {
        "registered_at": self.bot.get_utc_time(),
        "level": 1,
        "xp": 0
    }
    self.set_state("users", users)
    self.save_state()

    self.safe_reply(connection, event, "Registered!")
    return True
```

### Pattern 2: Cooldowns

```python
def _register_commands(self):
    self.register_command(
        r'^\s*!daily\s*$',
        self._cmd_daily,
        name="daily",
        cooldown=86400  # 24 hours in seconds
    )

def _cmd_daily(self, connection, event, msg, username, match):
    # Cooldown automatically enforced by base class!
    self.safe_reply(connection, event, "Here's your daily reward!")
    return True
```

### Pattern 3: Channel-Specific Behavior

```python
def on_pubmsg(self, connection, event) -> bool:
    # Check if enabled in this channel
    if not self.is_enabled(event.target):
        return False

    # Get channel-specific config
    spawn_chance = self.get_config_value(
        "spawn_chance",
        channel=event.target,
        default=0.01
    )

    # ... do something
    return False
```

### Pattern 4: Scheduled Tasks

```python
import schedule

class MyModule(SimpleCommandModule):
    def __init__(self, bot):
        super().__init__(bot)
        # Schedule hourly task
        schedule.every().hour.at(":00").do(self._hourly_task).tag(self.name)

    def _hourly_task(self):
        self.log_debug("Running hourly task")
        # Do something every hour
        self.safe_say("Hourly reminder!", target="#mychannel")
```

### Pattern 5: External API Calls

```python
def _cmd_weather(self, connection, event, msg, username, match):
    location = match.group(1)

    try:
        # Use centralized HTTP client
        url = "https://api.weather.com/data"
        data = self.http.get_json(url, params={"q": location})

        temp = data['temp']
        self.safe_reply(connection, event, f"Temperature: {temp}°F")
    except Exception as e:
        self.log_debug(f"Weather API error: {e}")
        self.safe_reply(connection, event, "Weather service unavailable.")

    return True
```

---

## Common Pitfalls

### ❌ Pitfall 1: Using Username as Key
```python
# WRONG - nicknames change!
users = self.get_state("users", {})
users[username] = {"coins": 100}

# CORRECT - use persistent UUID
user_id = self.bot.get_user_id(username)
users[user_id] = {"coins": 100}
```

### ❌ Pitfall 2: Forgetting to Save State
```python
# WRONG - state not persisted!
self.set_state("data", new_data)
# If bot crashes here, data is lost

# CORRECT
self.set_state("data", new_data)
self.save_state()  # Now it's on disk
```

### ❌ Pitfall 3: Not Calling super().__init__()
```python
# WRONG
class MyModule(SimpleCommandModule):
    def __init__(self, bot):
        self.custom_thing = []  # Missing super call!

# CORRECT
class MyModule(SimpleCommandModule):
    def __init__(self, bot):
        super().__init__(bot)  # MUST be first!
        self.custom_thing = []
```

### ❌ Pitfall 4: Blocking the Bot
```python
# WRONG - blocks bot for 10 seconds!
def _cmd_slow(self, connection, event, msg, username, match):
    time.sleep(10)  # BAD!
    self.safe_reply(connection, event, "Done")

# CORRECT - use threads for slow operations
def _cmd_slow(self, connection, event, msg, username, match):
    def slow_task():
        time.sleep(10)
        self.safe_say("Done", target=event.target)

    threading.Thread(target=slow_task, daemon=True).start()
    self.safe_reply(connection, event, "Working on it...")
    return True
```

### ❌ Pitfall 5: Timezone-Naive Datetimes
```python
# WRONG - causes comparison errors!
from datetime import datetime
now = datetime.now()  # No timezone!

# CORRECT - always use UTC with timezone
from datetime import datetime, timezone
now = datetime.now(timezone.utc)  # Timezone-aware

# Or use bot's helper
now_str = self.bot.get_utc_time()  # Returns ISO string
```

### ❌ Pitfall 6: Not Checking Channel Enabled
```python
# WRONG - ignores allowed_channels config
def on_ambient_message(self, connection, event, msg):
    if "jeeves" in msg.lower():
        self.safe_reply(connection, event, "You called?")

# CORRECT
def on_ambient_message(self, connection, event, msg):
    if not self.is_enabled(event.target):
        return False
    if "jeeves" in msg.lower():
        self.safe_reply(connection, event, "You called?")
```

---

## File Locations

### Core Files
- `jeeves.py` - Main bot
- `config/config.yaml` - Bot configuration
- `modules/base.py` - Module base classes
- `modules/users.py` - User identity system
- `modules/admin.py` - Admin commands
- `modules/courtesy.py` - Title system

### State Files (in `config/`)
- `state.json` - Default module bucket (stored under `modules.<name>`)
- `users.json` - User profiles and UUIDs (`users`, `weather`, `memos`, `profiles`)
- `games.json` - Quest data (`quest`, `hunt`, `bell`, `adventure`, `roadtrip`)
- `stats.json` - Usage statistics (`coffee`, `courtesy`, `leveling`, `duel`)
- `absurdia.db` - SQLite (Absurdia game)

**Note**: The `config/` directory is created at runtime; JSON files are generated by the bot. Do not commit populated state files to version control.

### Quest Data Files (in repository root)
- `quest_content.json` - Quest narrative content, themes, and display configuration
- `challenge_paths.json` - Special prestige options that modify gameplay (hard mode, etc.)

### Module Examples
Simple modules to reference:
- `modules/coffee.py` - Basic command module
- `modules/seen.py` - User tracking example
- `modules/karma.py` - User data with increment/decrement
- `modules/exception_utils.py` - Standardized error handling with custom exception classes
- `modules/http_utils.py` - Centralized HTTP client with retry logic and error handling
- `modules/config_manager.py` - Configuration management utilities
- `modules/admin_validator.py` - Admin permission validation utilities
- `modules/state_manager.py` - State file operation utilities

Complex modules:
- `modules/quest_pkg/` - Package-style module
- `modules/absurdia_pkg/` - Large game with database
- `modules/hunt.py` - Scheduled tasks + state

### Plugin Loading
- Modules are loaded from `modules/*.py` on startup (sorted) and filtered by `core.module_blacklist` in config.

### Documentation
- `docs/README.md` - General documentation
- `docs/LLM_ARCHITECTURE_GUIDE.md` - This file
- `AGENTS.md` - Contributor guidelines

---

## Development & Testing Tools

### Configuration Validation
- `config_validator.py` - Pre-flight configuration validation with environment variable substitution
- Usage: `python3 config_validator.py config/config.yaml`
- Validates YAML structure, required fields, API key formats, and checks for placeholder values
- **Always run this before starting the bot** to catch configuration errors early

### Web Quest Dashboard
- `web/quest_web.py` - Web interface for testing quest narratives and monitoring bot state
- Usage: `python3 web/quest_web.py --host 127.0.0.1 --port 8080`
- Provides real-time visualization of quest progress, challenge paths, and user interactions
- Essential for QA testing narrative changes without needing IRC access

### Testing Utilities
- `test_prestige_display.py` - Example test suite for prestige display functionality
- Run with: `python3 test_prestige_display.py`
- **Testing philosophy**: Add pytest-style tests under `tests/` following naming pattern `test_<feature>.py`
- For modules with IRC output: script sample events in a temporary channel and capture transcripts

### Utility Modules
- `modules/exception_utils.py` - Standardized error handling with custom exception classes
- `modules/http_utils.py` - Centralized HTTP client with retry logic and error handling
- `modules/config_manager.py` - Configuration management with dot-notation and API key access
- `modules/admin_validator.py` - Admin permission validation with security logging
- `modules/state_manager.py` - State file operations for independent JSON file management
- `file_lock.py` - Cross-process file locking for safe concurrent access to shared files
- These are imported by other modules for consistent error reporting, external API calls, configuration access, and state management.

## Quick Reference Card

### Accessing Bot Features
```python
self.bot.get_user_id(username)          # Get persistent UUID
self.bot.is_admin(event.source)         # Check if admin
self.bot.title_for(username)            # Get courtesy title
self.bot.connection.privmsg(target, msg) # Send IRC message
self.bot.config.get('mymodule', {})     # Get module config
self.bot.ROOT                           # Path to bot directory
```

### State Operations
```python
self.get_state(key, default)            # Read state
self.set_state(key, value)              # Write state (cached)
self.save_state()                       # Flush to disk
self.get_config_value(key, channel)     # Get config with override
self.is_enabled(channel)                # Check if module enabled
```

### Communication
```python
self.safe_reply(connection, event, text) # Reply to user/channel
self.safe_say(text, target)              # Say in channel
self.safe_privmsg(username, text)        # Private message
self.log_debug(message)                  # Debug log
```

### Command Patterns
```python
# Simple command: !hello
r'^\s*!hello\s*$'

# With argument: !weather Boston
r'^\s*!weather\s+(.+)$'

# With optional arg: !roll [sides]
r'^\s*!roll(?:\s+(\d+))?\s*$'

# Multiple words: !quote add <text>
r'^\s*!quote\s+add\s+(.+)$'
```

---

## When Debugging

0. **Validate configuration**: `python3 config_validator.py config/config.yaml` - catch config errors before startup
1. **Check debug.log**: `tail -f debug.log` (or `debug.log.1`, etc.)
2. **Look for module load**: `[plugins] Loaded module: mymodule`
3. **Check command matches**: `[mymodule] Command 'cmd' matched by user`
4. **Verify state**: `cat config/state.json | jq '.mymodule'`
5. **Test in isolation**: `python3 -c "from modules import mymodule"`
6. **Test web dashboard**: `python3 web/quest_web.py --host 127.0.0.1 --port 8080` - for quest narrative testing

**Tip**: For immediate state persistence (e.g., after critical changes), use `self.save_state(force=True)` instead of `self.save_state()` to bypass the 0.5s timer.

### Common Errors

- `AttributeError: 'JeevesBot' object has no attribute 'get_user_id'`
  → Missing `users` module or wrong bot reference

- `KeyError: 'mymodule'` in state.json
  → Module never saved state, or state.json corrupted

- `TypeError: can't subtract offset-naive and offset-aware datetimes`
  → Mixing naive and aware datetimes (use `timezone.utc`)

- `Module 'mymodule' not loaded`
  → Syntax error in module file, check debug.log

---

## Specialized Module Guides

Some modules are large and complex enough to warrant their own dedicated guides. **Always read these guides before working on these modules:**

### Quest Module

**File**: `docs/LLM_QUEST_GUIDE.md`

The Quest module is Jeeves' largest module - a full RPG system with prestige, transcendence, hardcore mode, dungeons, boss hunts, and more. It's split across multiple submodules (`quest_core`, `quest_combat`, `quest_progression`, etc.) and has its own data files (`quest_content.json`, `challenge_paths.json`).

**Read the Quest Guide when**:
- Working on any quest commands (`!quest`, `!dungeon`, `!mob`)
- Modifying prestige, transcendence, or hardcore systems
- Adding new items, abilities, or challenge paths
- Creating new themes
- Debugging quest-related issues

### Absurdia Module

**File**: `docs/LLM_ABSURDIA_GUIDE.md`

The Absurdia module is a creature catching and battling game with SQLite database storage. Unlike Quest (which uses JSON state), Absurdia has persistent database tables for players, creatures, traps, arena matches, and inventory.

**Read the Absurdia Guide when**:
- Working on any Absurdia commands (`!catch`, `!feed`, `!arena`, `!explore`)
- Modifying catching, care, or combat systems
- Adding new creatures or trap tiers
- Debugging database issues
- Working with hourly arena tournaments

---

## Final Notes

- **Modules should be self-contained** - don't depend on other modules unless necessary
- **Use user_id everywhere** - nicknames change, UUIDs don't
- **Save state frequently** - bot can crash anytime
- **Check is_enabled()** - respect channel configuration
- **Don't block the bot** - use threads for slow operations
- **Log liberally** - debug.log is your friend
- **Test in #bots first** - don't spam main channels
- **Read specialized guides** - Quest and Absurdia have dedicated documentation

This guide covers ~90% of what you need to understand Jeeves. For specific module examples, see the modules/ directory. For detailed IRC protocol info, see the `irc` library docs.

**When in doubt, grep for examples in existing modules!**
