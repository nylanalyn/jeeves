# Coding Conventions

**Analysis Date:** 2026-01-18

## Naming Patterns

**Files:**
- Module files: `snake_case.py` (e.g., `achievement_hooks.py`, `http_utils.py`)
- Package directories: `snake_case_pkg/` (e.g., `quest_pkg/`, `absurdia_pkg/`)
- Test files: `test_<feature>.py` (e.g., `test_activity_stats.py`)

**Functions:**
- Public methods: `snake_case` (e.g., `get_user_id`, `save_state`)
- Private methods: `_snake_case` with leading underscore (e.g., `_cmd_fortune`, `_load_state`)
- Command handlers: `_cmd_<command_name>` prefix (e.g., `_cmd_weather_self`, `_cmd_reload`)
- Setup function: Always `def setup(bot: Any) -> 'ModuleName':` at module level

**Variables:**
- Local variables: `snake_case` (e.g., `user_id`, `location_obj`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `COFFEE_DRINKS`, `CATEGORIES`)
- Class attributes: `snake_case` (e.g., `name`, `version`, `description`)

**Types:**
- Classes: `PascalCase` (e.g., `SimpleCommandModule`, `MultiFileStateManager`)
- Exception classes: `PascalCase` with `Exception` suffix (e.g., `JeevesException`, `UserInputException`)
- Type aliases: `PascalCase` (rarely used)

## Code Style

**Formatting:**
- No formal formatter configured (no .prettierrc, black, etc.)
- Indentation: 4 spaces
- Line length: Generally kept reasonable but no hard limit enforced
- Quotes: Double quotes preferred for strings, single quotes also used

**Linting:**
- No linter configuration detected (.eslintrc, .flake8, ruff.toml)
- Type hints used inconsistently but present in newer code
- `from typing import Any, Dict, List, Optional, Tuple` common imports

## Import Organization

**Order:**
1. Standard library imports (os, sys, re, time, json, etc.)
2. Third-party imports (requests, pytz, yaml)
3. Local imports from `.base` and other modules

**Path Aliases:**
- Relative imports within `modules/` (e.g., `from .base import SimpleCommandModule`)
- No path alias configuration (no tsconfig equivalent)

**Example Pattern:**
```python
# modules/coffee.py
import re
import random
import time
from datetime import datetime
from typing import Any, Dict, List
import pytz
from timezonefinder import TimezoneFinder
from .base import SimpleCommandModule
from . import achievement_hooks
```

## Error Handling

**Patterns:**
- Use exception classes from `modules/exception_utils.py`:
  - `JeevesException` - Base exception
  - `ModuleException` - Module operation failures
  - `ExternalAPIException` - API failures
  - `UserInputException` - Invalid user input
  - `StateException` - State management errors
  - `PermissionException` - Authorization errors
  - `NetworkException` - Network failures

**Decorator-based handling:**
```python
@handle_exceptions(
    error_message="Failed to send reply message",
    user_message="Unable to send message",
    log_exception=True,
    reraise=False
)
def safe_reply(self, connection, event, text: str) -> bool:
    # ... implementation
```

**Try/except pattern:**
```python
try:
    data = self.http.get_json(weather_url)
    return data
except Exception as e:
    self._record_error(f"API request failed: {e}")
    return None
```

**Silent failure for optional integrations:**
```python
try:
    achievements_module.record_progress(username, metric, amount)
except Exception:
    pass  # Silently fail if achievements module has issues
```

## Logging

**Framework:** Custom logging via `self.bot.log_debug()` and Python `logging` module

**Patterns:**
- Module prefix in brackets: `[module_name] message`
- Debug logging through bot instance: `self.log_debug(f"message")`
- Security events: `log_security_event(module_name, event, user, details)`
- Module events: `log_module_event(module_name, event, details)`

**When to Log:**
- Command execution: `self.log_debug(f"Command '{cmd_info['name']}' matched by user {username}")`
- Errors: `self._record_error(f"API request failed: {e}")`
- State changes: `print(f"[state] Saved {file_type}.json", file=sys.stderr)`

**Sensitive Data Redaction:**
- API keys in URLs redacted via `redact_api_key_from_url()`
- Parameters sanitized via `sanitize_params()`
- Passwords/tokens never logged

## Comments

**When to Comment:**
- Module header: Brief description of purpose
- Version changes: Comment indicating what changed
- Complex logic: Explain non-obvious calculations (e.g., heat index formula)
- Constants: Document purpose of magic values

**Docstrings:**
- Use triple-quoted docstrings for public methods
- Include Args and Returns sections for complex functions
- Keep brief for simple methods

**Example:**
```python
def get_user_id(self, nick: str) -> str:
    """
    Gets the persistent UUID for a nickname.
    Creates a new user profile if the nick has never been seen before.
    """
```

## Function Design

**Size:** Methods typically 10-50 lines. Longer methods exist but are refactored into helpers.

**Parameters:**
- Use type hints: `def _cmd_fortune(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:`
- Command handlers always receive: `connection, event, msg, username, match`
- Optional params use `Optional[Type]` and default to `None`

**Return Values:**
- Command handlers return `bool` (True = handled, False = not handled)
- Data methods return `Optional[Type]` when failure is possible
- Use tuples for multiple return values: `Tuple[str, str]`

## Module Design

**Exports:**
- Single `setup(bot)` function at module level required
- Returns instance of module class
- Pattern: `def setup(bot: Any) -> 'ModuleName':`

**Module Structure:**
```python
# modules/example.py
# Brief description
import re
from typing import Any
from .base import SimpleCommandModule

def setup(bot: Any) -> 'Example':
    return Example(bot)

class Example(SimpleCommandModule):
    name = "example"
    version = "1.0.0"
    description = "Does something useful."

    def __init__(self, bot: Any) -> None:
        super().__init__(bot)
        # Initialize state
        self.set_state("key", self.get_state("key", {}))
        self.save_state()

    def _register_commands(self) -> None:
        self.register_command(r"^\s*!example\s*$", self._cmd_example,
                              name="example", description="Example command.")

    def _cmd_example(self, connection: Any, event: Any, msg: str, username: str, match: re.Match) -> bool:
        self.safe_reply(connection, event, "Example response.")
        return True
```

**Barrel Files:**
- Package `__init__.py` files export `setup` function
- Example: `modules/quest_pkg/__init__.py` re-exports from submodules

## State Management

**Access Pattern:**
```python
# Get state with default
value = self.get_state("key", default_value)

# Set state
self.set_state("key", value)

# Batch update and save
self.update_state({"key1": val1, "key2": val2})
self.save_state()
```

**State Persistence:**
- State automatically managed by `MultiFileStateManager`
- Different file types: `state.json`, `games.json`, `users.json`, `stats.json`
- Module state accessed via `bot.get_module_state(name)`

## Command Registration

**Pattern:**
```python
def _register_commands(self) -> None:
    self.register_command(
        r"^\s*!command(?:\s+(.+))?\s*$",  # Regex pattern
        self._cmd_handler,                  # Handler function
        name="command",                     # Command name for logging
        admin_only=False,                   # Require admin privileges
        cooldown=10.0,                      # Cooldown in seconds
        description="Command description."  # Help text
    )
```

**Command Prefix:**
- Commands use `!` or `,` prefix (converted in `register_command`)
- Pattern: `r'[!,]'` replaces `!` in regex

---

*Convention analysis: 2026-01-18*
