# Architecture

**Analysis Date:** 2026-01-18

## Pattern Overview

**Overall:** Plugin-based IRC Bot with Modular Game Systems

**Key Characteristics:**
- Single entry point IRC bot core (`jeeves.py`) with dynamic plugin loading
- Inheritance-based module system using abstract base class (`ModuleBase`)
- Multi-file state management with per-category JSON persistence
- Event-driven command dispatch via regex pattern matching
- Scheduled tasks using the `schedule` library for background operations

## Layers

**Core Layer:**
- Purpose: IRC connection management, plugin orchestration, authentication
- Location: `/home/nylan/code/jeeves/jeeves.py`
- Contains: `Jeeves` bot class, `PluginManager`, `MultiFileStateManager`, main entry point
- Depends on: `irc.bot.SingleServerIRCBot`, `config_validator.py`, `file_lock.py`
- Used by: All modules access bot instance for state, config, and IRC operations

**Configuration Layer:**
- Purpose: Validate and load YAML configuration with environment variable substitution
- Location: `/home/nylan/code/jeeves/config_validator.py`
- Contains: `ConfigValidator` class, `load_and_validate_config()` function
- Depends on: PyYAML, environment variables
- Used by: Core layer on startup and config reload

**Module Base Layer:**
- Purpose: Common utilities, state management, command registration for all modules
- Location: `/home/nylan/code/jeeves/modules/base.py`
- Contains: `ModuleBase` abstract class, `SimpleCommandModule` class, decorators (`admin_required`, `debug_log`)
- Depends on: `exception_utils.py`, `http_utils.py`
- Used by: All game/feature modules inherit from this

**Utility Layer:**
- Purpose: Shared infrastructure for HTTP requests, exception handling, file locking
- Location: `/home/nylan/code/jeeves/modules/exception_utils.py`, `/home/nylan/code/jeeves/modules/http_utils.py`, `/home/nylan/code/jeeves/file_lock.py`
- Contains: Custom exceptions, `HTTPClient`, `safe_execute()`, `FileLock` context manager
- Depends on: `requests`, `fcntl`
- Used by: All modules via `ModuleBase.http` or direct import

**Game Module Layer:**
- Purpose: Implement IRC games and interactive features
- Location: `/home/nylan/code/jeeves/modules/*.py`
- Contains: Quest, Hunt, Fishing, Adventure, Roadtrip, Bell, Duel, and other game modules
- Depends on: `ModuleBase`, core bot instance
- Used by: End users via IRC commands

**Service Module Layer:**
- Purpose: Provide core services (user identity, admin commands, courtesy/profiles)
- Location: `/home/nylan/code/jeeves/modules/users.py`, `/home/nylan/code/jeeves/modules/admin.py`, `/home/nylan/code/jeeves/modules/courtesy.py`
- Contains: User ID mapping, admin command handlers, user profiles
- Depends on: `ModuleBase`, core bot instance
- Used by: Other modules for user identity resolution and permissions

**Web Layer:**
- Purpose: HTTP dashboard for viewing game stats and leaderboards
- Location: `/home/nylan/code/jeeves/web/`
- Contains: `server.py` (unified HTTP server), `quest/` subpackage, `stats/` subpackage
- Depends on: State JSON files in `config/`, `http.server` stdlib
- Used by: External users via web browser (runs as separate process)

## Data Flow

**IRC Message Processing:**

1. IRC library receives PUBMSG/PRIVMSG event
2. `Jeeves.on_pubmsg()` or `on_privmsg()` receives event
3. Bot checks if user is ignored via `courtesy` module
4. For each loaded plugin, call `_dispatch_commands()` with message
5. Module's regex patterns match against message text
6. Matching handler function executes, may modify state
7. Handler calls `safe_reply()` to send response back to IRC

**State Persistence:**

1. Module calls `self.set_state(key, value)` or `self.update_state(updates)`
2. State cached in module's `_state_cache` dictionary
3. `_state_dirty` flag set to True
4. Module calls `self.save_state()` (or auto-save on unload)
5. `MultiFileStateManager` determines target file (games.json, users.json, stats.json, state.json)
6. Timer-based debounced write (0.5s delay) with atomic temp file swap
7. `FileLock` ensures cross-process safety with web server

**Configuration Flow:**

1. On startup, `config_validator.py` loads `config/config.yaml`
2. Environment variable substitution applied (`${VAR_NAME}` syntax)
3. Validation checks run for all sections
4. Validated config passed to `Jeeves` constructor
5. Modules access config via `self.bot.config` or `self.get_config_value()`
6. `!admin config reload` triggers re-validation and module notification

**State Management:**
- Multi-file approach splits data by category to reduce file size and contention
- `games.json`: quest, hunt, bell, adventure, roadtrip, fishing
- `users.json`: user profiles, weather locations, memos
- `stats.json`: coffee counts, courtesy data, leveling, duel, karma, activity
- `state.json`: core config, misc module data

## Key Abstractions

**ModuleBase:**
- Purpose: Standard interface for all bot modules
- Examples: `/home/nylan/code/jeeves/modules/hunt.py`, `/home/nylan/code/jeeves/modules/quest.py`
- Pattern: Template Method - subclasses override `_register_commands()` and hook methods

**SimpleCommandModule:**
- Purpose: Convenience base for command-only modules
- Examples: `/home/nylan/code/jeeves/modules/admin.py`, `/home/nylan/code/jeeves/modules/users.py`
- Pattern: Calls `_register_commands()` automatically in constructor

**MultiFileStateManager:**
- Purpose: Persistent JSON storage with category-based file splitting
- Examples: Used by all modules via `bot.get_module_state()`, `bot.update_module_state()`
- Pattern: Repository with caching and debounced persistence

**HTTPClient:**
- Purpose: Centralized HTTP requests with retry logic and credential redaction
- Examples: Used via `self.http.get_json()` in weather, translate, crypto modules
- Pattern: Facade over `requests` library

**Quest Package:**
- Purpose: Large game system split into focused submodules
- Examples: `/home/nylan/code/jeeves/modules/quest_pkg/quest_core.py`, `quest_combat.py`, `quest_progression.py`
- Pattern: Package-as-module with thin wrapper (`quest.py` imports from `quest_pkg`)

## Entry Points

**IRC Bot (`jeeves.py`):**
- Location: `/home/nylan/code/jeeves/jeeves.py`
- Triggers: `python3 jeeves.py` or systemd service
- Responsibilities: Connect to IRC, load plugins, handle events, manage state

**Web Server (`web/server.py`):**
- Location: `/home/nylan/code/jeeves/web/server.py`
- Triggers: `python3 -m web.server` or dedicated launcher
- Responsibilities: Serve quest leaderboard, stats dashboard, activity pages

**Config Validator (`config_validator.py`):**
- Location: `/home/nylan/code/jeeves/config_validator.py`
- Triggers: `python3 config_validator.py [config_path]` for standalone validation
- Responsibilities: Validate YAML config, report errors

## Error Handling

**Strategy:** Layered exception handling with user-friendly messages

**Patterns:**
- Custom exception hierarchy in `exception_utils.py` (`JeevesException`, `ModuleException`, `ExternalAPIException`, etc.)
- `safe_execute()` wrapper for catching and logging exceptions without crashing
- `@handle_exceptions` decorator for standardized error handling on methods
- Per-module `log_debug()` for debug logging to rotating log files
- Sensitive data redaction in logs (`_redact_sensitive_data()`)

## Cross-Cutting Concerns

**Logging:**
- Debug logging to `debug.log` via `RotatingFileHandler` (100KB per file, 10 backups)
- Per-module debug toggle via `!admin debug <module> on|off`
- Sensitive data automatically redacted from logs

**Validation:**
- Config validation at startup via `ConfigValidator`
- User input validation in modules via regex patterns
- API key format validation with warnings

**Authentication:**
- Two-tier admin system: regular admins (hostname-based) and super admins (password + hostname)
- `bot.is_admin(event.source)` checks nick + stored hostname
- `bot.is_super_admin(nick)` for dangerous operations (reload, quit)
- BCrypt password hashing for super admin authentication

**Rate Limiting:**
- Per-user, per-command cooldowns via `check_user_cooldown()` and `record_user_cooldown()`
- Global rate limits via `check_rate_limit()`
- Admin authentication rate limiting (5 attempts per 5 minutes)

---

*Architecture analysis: 2026-01-18*
