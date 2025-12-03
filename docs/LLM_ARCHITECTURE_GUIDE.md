# Jeeves Architecture Guide for LLMs

**Purpose**: This document provides a comprehensive overview of Jeeves' architecture for AI coding assistants. Read this first before making changes to understand how all the pieces fit together.

---

## Table of Contents
1. [High-Level Architecture](#high-level-architecture)
2. [Core Components](#core-components)
3. [How Modules Work](#how-modules-work)
4. [State Management](#state-management)
5. [User Management](#user-management)
6. [Admin System](#admin-system)
7. [How to Write a New Module](#how-to-write-a-new-module)
8. [Common Patterns](#common-patterns)
9. [Common Pitfalls](#common-pitfalls)
10. [File Locations](#file-locations)

---

## High-Level Architecture

Jeeves is a **modular IRC bot** built with Python 3.11 using the `irc` library. The architecture follows these principles:

1. **Single bot instance** (`jeeves.py`) manages the IRC connection
2. **Plugin manager** (`PluginManager` in `jeeves.py`) loads modules dynamically from `modules/`
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

**Location**: `/home/zote/bots/jeeves/jeeves.py`

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

def is_admin(hostmask: str) -> bool:
    # Checks if user is an admin based on hostmask

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

**Location**: `/home/zote/bots/jeeves/modules/base.py`

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

**Location**: Inside `jeeves.py` (lines ~200-300)

**Managed Files** (in `config/`):
- `state.json` - General module state (most modules use this)
- `users.json` - User profiles and UUID mappings
- `games.json` - Quest/game data
- `stats.json` - Usage statistics
- `absurdia.db` - SQLite database for Absurdia game

**How It Works**:
1. On boot: Loads all JSON files into memory
2. During runtime: Modules read/write via `bot.get_module_state()` and `bot.update_module_state()`
3. State is **cached** in memory (fast reads)
4. Writes are **immediate** (save_state() writes to disk)
5. Each module gets its own top-level key in `state.json`

**Example** (`state.json` structure):
```json
{
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
```

**Important**: Always call `self.save_state()` after `self.set_state()` to persist changes!

---

### 4. `modules/users.py` - User Identity Tracking

**Location**: `/home/zote/bots/jeeves/modules/users.py`

**Purpose**: Maps IRC nicknames to persistent UUIDs so users maintain identity across nick changes.

**Data Structure** (`users.json`):
```json
{
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

**Location**: `/home/zote/bots/jeeves/modules/admin.py`

**Admin Detection**:
Admins are defined in `config.yaml`:
```yaml
admins:
  - "alice!~alice@host.example.com"
  - "bob!~bob@192.168.1.1"
```

**Checking Admin Status**:
```python
# Method 1: In jeeves.py or any module
if self.bot.is_admin(event.source):
    # User is admin

# Method 2: Use decorator in module
@admin_required
def _cmd_secret(self, connection, event, msg, username, match):
    # Only admins reach this code
```

**Admin Commands**:
- `!reload` - Reload all modules
- `!reload <module>` - Reload specific module
- `!quit` - Shut down bot
- `!join <channel>` - Join a channel
- `!part [channel]` - Leave a channel

---

### 6. `modules/courtesy.py` - Title System

**Location**: `/home/zote/bots/jeeves/modules/courtesy.py`

**Purpose**: Manages formal titles ("Sir", "Madam", "Lord", etc.) for users.

**How It Works**:
- Titles stored in `users.json` under each user profile
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

## How Modules Work

### Module Lifecycle

1. **Load**: `jeeves.py` imports `modules/<name>.py`
2. **Setup**: Calls `setup(bot)` function which returns module instance
3. **Init**: Module `__init__()` calls `super().__init__(bot)` and `_register_commands()`
4. **Run**: Bot dispatches IRC events to module methods
5. **Unload** (if reloaded): Calls `on_unload()`, saves state

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
        super().__init__(bot)  # MUST call this first!
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
        super().__init__(bot)
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
- `jeeves.py` - Main bot (lines 1-800+)
- `config/config.yaml` - Bot configuration
- `modules/base.py` - Module base classes
- `modules/users.py` - User identity system
- `modules/admin.py` - Admin commands
- `modules/courtesy.py` - Title system

### State Files (in `config/`)
- `state.json` - Module state (most modules)
- `users.json` - User profiles and UUIDs
- `games.json` - Quest data
- `stats.json` - Usage statistics
- `absurdia.db` - SQLite (Absurdia game)

### Module Examples
Simple modules to reference:
- `modules/coffee.py` - Basic command module
- `modules/seen.py` - User tracking example
- `modules/karma.py` - User data with increment/decrement

Complex modules:
- `modules/quest_pkg/` - Package-style module
- `modules/absurdia_pkg/` - Large game with database
- `modules/hunt.py` - Scheduled tasks + state

### Documentation
- `docs/README.md` - General documentation
- `docs/LLM_ARCHITECTURE_GUIDE.md` - This file
- `AGENTS.md` - Contributor guidelines

---

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

1. **Check debug.log**: `tail -f debug.log` (or `debug.log.1`, etc.)
2. **Look for module load**: `[plugins] Loaded module: mymodule`
3. **Check command matches**: `[mymodule] Command 'cmd' matched by user`
4. **Verify state**: `cat config/state.json | jq '.mymodule'`
5. **Test in isolation**: `python3 -c "from modules import mymodule"`

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

## Final Notes

- **Modules should be self-contained** - don't depend on other modules unless necessary
- **Use user_id everywhere** - nicknames change, UUIDs don't
- **Save state frequently** - bot can crash anytime
- **Check is_enabled()** - respect channel configuration
- **Don't block the bot** - use threads for slow operations
- **Log liberally** - debug.log is your friend
- **Test in #bots first** - don't spam main channels

This guide covers ~80% of what you need to understand Jeeves. For specific module examples, see the modules/ directory. For detailed IRC protocol info, see the `irc` library docs.

**When in doubt, grep for examples in existing modules!**
