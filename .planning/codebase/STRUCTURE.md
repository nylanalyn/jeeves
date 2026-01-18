# Codebase Structure

**Analysis Date:** 2026-01-18

## Directory Layout

```
jeeves/
├── jeeves.py                    # Main bot entry point
├── config_validator.py          # YAML config validation
├── file_lock.py                 # Cross-process file locking utility
├── config.yaml.default          # Default config template
├── quest_content.json           # Quest game content data
├── challenge_paths.json         # Quest challenge path definitions
├── requirements.txt             # Python dependencies
├── jeeves.service               # Systemd service file
│
├── config/                      # Runtime configuration and state (not committed)
│   ├── config.yaml              # Active bot configuration
│   ├── games.json               # Game module state
│   ├── users.json               # User profile state
│   ├── stats.json               # Statistics state
│   ├── state.json               # Core/misc module state
│   ├── absurdia.db              # SQLite database for Absurdia game
│   └── quotes.json              # Quotes database
│
├── modules/                     # Plugin modules
│   ├── base.py                  # ModuleBase and SimpleCommandModule classes
│   ├── exception_utils.py       # Custom exceptions and error handling
│   ├── http_utils.py            # Centralized HTTP client
│   ├── admin.py                 # Admin commands module
│   ├── users.py                 # User identity service
│   ├── courtesy.py              # User profiles and titles
│   ├── quest.py                 # Quest game (thin wrapper)
│   ├── hunt.py                  # Hunt game
│   ├── fishing.py               # Fishing game
│   ├── adventure.py             # Adventure game
│   ├── roadtrip.py              # Roadtrip game
│   ├── bell.py                  # Bell game
│   ├── duel.py                  # Duel game
│   ├── weather.py               # Weather lookup
│   ├── translate.py             # Translation service
│   └── ... (50+ module files)
│
├── modules/quest_pkg/           # Quest game subpackage
│   ├── __init__.py              # Quest class and setup()
│   ├── constants.py             # Quest constants and enums
│   ├── quest_core.py            # Core quest logic
│   ├── quest_combat.py          # Combat mechanics
│   ├── quest_progression.py     # Leveling, prestige, dungeons
│   ├── quest_display.py         # Output formatting
│   ├── quest_boss_hunt.py       # Boss hunt feature
│   └── quest_utils.py           # Quest utility functions
│
├── modules/absurdia_pkg/        # Absurdia game subpackage
│   ├── __init__.py              # Package initialization
│   ├── absurdia_main.py         # Main game logic
│   ├── absurdia_db.py           # SQLite database operations
│   ├── absurdia_combat.py       # Combat system
│   ├── absurdia_creatures.py    # Creature definitions
│   └── absurdia_exploration.py  # Exploration mechanics
│
├── web/                         # Web dashboard
│   ├── __init__.py
│   ├── server.py                # Unified HTTP server
│   ├── README.md                # Web server documentation
│   ├── quest/                   # Quest web UI
│   │   ├── __init__.py
│   │   ├── app.py               # Quest route handlers (legacy)
│   │   ├── utils.py             # Quest data loading utilities
│   │   ├── templates.py         # Quest HTML rendering
│   │   └── themes.py            # Quest theming system
│   └── stats/                   # Stats web UI
│       ├── __init__.py
│       ├── config.py            # Stats config loading
│       ├── data_loader.py       # Stats data aggregation
│       └── templates.py         # Stats HTML rendering
│
├── tests/                       # Test files
│   ├── test_achievements_loader.py
│   ├── test_achievements_page.py
│   ├── test_activity_stats.py
│   └── test_title_for.py
│
├── docs/                        # Documentation
│   ├── LLM_ARCHITECTURE_GUIDE.md
│   ├── LLM_QUEST_GUIDE.md
│   ├── LLM_ABSURDIA_GUIDE.md
│   ├── README.md
│   └── themes.md
│
├── fortunes/                    # Fortune cookie text files
│
└── team_reports/                # Generated team reports
```

## Directory Purposes

**Root Directory:**
- Purpose: Core application files and entry points
- Contains: Main bot script, config validator, lock utility, service file
- Key files: `jeeves.py`, `config_validator.py`, `file_lock.py`

**config/:**
- Purpose: Runtime configuration and persistent state
- Contains: YAML config, JSON state files, SQLite databases
- Key files: `config.yaml`, `games.json`, `users.json`, `stats.json`, `state.json`
- Generated: Yes (state files created at runtime)
- Committed: No (gitignored, contains user data)

**modules/:**
- Purpose: All plugin modules implementing bot features
- Contains: Base classes, utility modules, game modules, service modules
- Key files: `base.py` (must read first), `admin.py`, `users.py`, game files

**modules/quest_pkg/:**
- Purpose: Quest game implementation split for maintainability
- Contains: Submodules for different aspects of the quest game
- Key files: `__init__.py` (main Quest class), `quest_core.py`, `quest_combat.py`

**modules/absurdia_pkg/:**
- Purpose: Absurdia game with SQLite persistence
- Contains: Game logic, database operations, combat, creatures
- Key files: `absurdia_main.py`, `absurdia_db.py`

**web/:**
- Purpose: HTTP dashboard for viewing game data
- Contains: Unified server, quest UI, stats UI
- Key files: `server.py` (entry point), `quest/templates.py`, `stats/templates.py`

**tests/:**
- Purpose: Unit and integration tests
- Contains: Test files for specific features
- Key files: Tests use pytest

**docs/:**
- Purpose: Developer documentation and LLM guides
- Contains: Architecture guides, module documentation
- Key files: `LLM_ARCHITECTURE_GUIDE.md`, `LLM_QUEST_GUIDE.md`

## Key File Locations

**Entry Points:**
- `/home/nylan/code/jeeves/jeeves.py`: Main bot entry point
- `/home/nylan/code/jeeves/web/server.py`: Web dashboard entry point
- `/home/nylan/code/jeeves/config_validator.py`: Standalone config validation

**Configuration:**
- `/home/nylan/code/jeeves/config.yaml.default`: Default config template
- `/home/nylan/code/jeeves/config/config.yaml`: Active configuration (runtime)
- `/home/nylan/code/jeeves/quest_content.json`: Quest game content
- `/home/nylan/code/jeeves/challenge_paths.json`: Quest challenge definitions

**Core Logic:**
- `/home/nylan/code/jeeves/modules/base.py`: Module base classes
- `/home/nylan/code/jeeves/modules/exception_utils.py`: Exception handling
- `/home/nylan/code/jeeves/modules/http_utils.py`: HTTP client

**Testing:**
- `/home/nylan/code/jeeves/tests/`: All test files

## Naming Conventions

**Files:**
- `snake_case.py`: All Python modules
- `UPPERCASE.md`: Documentation files
- `lowercase.json`: Data/state files
- `lowercase.yaml`: Configuration files

**Directories:**
- `lowercase/`: Standard directories
- `name_pkg/`: Package directories for complex modules
- `.hidden/`: Hidden directories (`.claude/`, `.planning/`, `.agents/`)

**Modules:**
- Module files: `modulename.py` (e.g., `hunt.py`, `weather.py`)
- Package wrappers: `modulename.py` imports from `modulename_pkg/`
- Submodules: `packagename_submodule.py` (e.g., `quest_combat.py`)

**Classes:**
- Module classes: `PascalCase` matching module name (e.g., `Hunt`, `Weather`)
- Base classes: `ModuleBase`, `SimpleCommandModule`

## Where to Add New Code

**New Module (Simple):**
- Create `/home/nylan/code/jeeves/modules/newmodule.py`
- Inherit from `SimpleCommandModule`
- Implement `_register_commands()` method
- Add `setup(bot)` function that returns module instance
- Add config section to `config.yaml.default` if needed

**New Module (Complex/Large):**
- Create `/home/nylan/code/jeeves/modules/newmodule_pkg/` directory
- Add `__init__.py` with main class and `setup()` function
- Split logic into focused submodules (`newmodule_core.py`, etc.)
- Create thin wrapper `/home/nylan/code/jeeves/modules/newmodule.py` that imports from package

**New Command to Existing Module:**
- Add pattern and handler in `_register_commands()` method
- Follow existing command patterns in the module
- Use `self.register_command(pattern, handler, name, ...)` method

**New Utility Function:**
- Module-specific: Add to the module file
- Shared across modules: Add to `/home/nylan/code/jeeves/modules/base.py` or create new utility module

**New Web Page:**
- Add handler method to `/home/nylan/code/jeeves/web/server.py`
- Add route in `do_GET()` method
- Create template function in appropriate `templates.py`

**New Test:**
- Create `/home/nylan/code/jeeves/tests/test_featurename.py`
- Use pytest patterns consistent with existing tests

## Special Directories

**config/:**
- Purpose: Runtime state and configuration (gitignored)
- Generated: Yes (created on first run)
- Committed: No

**.venv/:**
- Purpose: Python virtual environment
- Generated: Yes
- Committed: No

**__pycache__/:**
- Purpose: Python bytecode cache
- Generated: Yes
- Committed: No

**.planning/:**
- Purpose: GSD planning documents and codebase analysis
- Generated: Yes (by Claude)
- Committed: Optional

**.claude/:**
- Purpose: Claude Code settings
- Generated: Yes
- Committed: Optional

**.agents/:**
- Purpose: Agent configuration files
- Generated: No
- Committed: Yes

**team_reports/:**
- Purpose: Generated team activity reports
- Generated: Yes (by bot)
- Committed: Optional

---

*Structure analysis: 2026-01-18*
