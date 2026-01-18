# Technology Stack

**Analysis Date:** 2026-01-18

## Languages

**Primary:**
- Python 3.11.9 - All application code, IRC bot core, modules, web server

**Secondary:**
- YAML - Configuration files (`config.yaml`, `config.yaml.default`)
- JSON - State persistence, quest content, creature templates

## Runtime

**Environment:**
- Python 3.11.9 (specified in `.python-version`)
- Virtual environment at `.venv/`

**Package Manager:**
- pip (via venv)
- Lockfile: None (only `requirements.txt` with unpinned versions)

## Frameworks

**Core:**
- `irc` (jaraco.irc) - IRC protocol handling via `SingleServerIRCBot`
- `jaraco.stream` - IRC buffer and encoding handling

**Testing:**
- pytest - Test framework (see `tests/` directory)

**Build/Dev:**
- No build system - Pure Python application
- systemd user service for deployment (`jeeves.service`)

## Key Dependencies

**Critical (from `requirements.txt`):**
- `irc` - IRC bot framework, core connectivity
- `pyyaml` - Configuration file parsing
- `requests` - HTTP client for API integrations
- `schedule` - Scheduled task execution (timers, periodic events)
- `filelock` - Cross-process file locking for state persistence

**API Integrations:**
- `openai` - AI/LLM integration (ArliAI/OpenAI compatible)
- `deepl` - Translation service
- `google-api-python-client` - YouTube Data API
- `beautifulsoup4` - HTML parsing for URL title extraction
- `bcrypt` - Password hashing for super admin authentication

**Utilities:**
- `pytz` - Timezone handling
- `timezonefinder` - Geographic timezone lookup

## Configuration

**Environment:**
- Environment variables loaded from `~/.env` via systemd EnvironmentFile
- Supports `${VARIABLE_NAME}` syntax in YAML for sensitive values
- Config validator: `config_validator.py`

**Configuration Files:**
- `config/config.yaml` - Active configuration (not in repo)
- `config.yaml.default` - Template configuration
- `config_with_env_vars.yaml.example` - Example with environment variable usage

**Build:**
- No build step required
- Run directly: `python jeeves.py`

## State Persistence

**JSON State Files (in `config/`):**
- `state.json` - Core config and non-critical module data
- `games.json` - Game state (quest, hunt, bell, adventure, roadtrip, fishing)
- `users.json` - User profiles, locations, memos
- `stats.json` - Statistics and tracking data

**SQLite Database:**
- `config/absurdia.db` - Absurdia creature battle game persistent storage

**File Locking:**
- `.lock` files for atomic JSON writes via `file_lock.py`

## Platform Requirements

**Development:**
- Python 3.11+
- Linux/macOS (systemd optional, can run directly)
- Virtual environment recommended

**Production:**
- systemd user service (`jeeves.service`)
- Environment: `~/.env` for secrets
- Working directory: project root
- Runs as user service (not system service)

**Deployment:**
```bash
# Activate venv and run
cd ~/CODE/jeeves && source .venv/bin/activate && python jeeves.py
```

---

*Stack analysis: 2026-01-18*
