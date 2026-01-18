# External Integrations

**Analysis Date:** 2026-01-18

## APIs & External Services

**AI/LLM:**
- ArliAI (OpenAI-compatible) - Conversational AI responses
  - SDK/Client: `openai` Python library
  - Auth: `api_keys.openai_api_key` in config
  - Base URL: Configurable via `oracle.openai_base_url`
  - Used by: `modules/oracle.py`, `modules/topic.py`

**Translation:**
- DeepL API - Text translation service
  - SDK/Client: `deepl` Python library
  - Auth: `api_keys.deepl_api_key` in config
  - Used by: `modules/translate.py`

**Media:**
- Giphy API - GIF search
  - SDK/Client: Direct HTTP via `requests`
  - Auth: `api_keys.giphy` in config
  - Used by: `modules/gif.py`

- YouTube Data API v3 - Video search and metadata
  - SDK/Client: `googleapiclient.discovery.build()`
  - Auth: `api_keys.youtube` in config
  - Used by: `modules/convenience.py`

**Weather:**
- PirateWeather API - US weather data (DarkSky-compatible)
  - SDK/Client: Direct HTTP via `modules/http_utils.py`
  - Auth: `api_keys.pirateweather` in config
  - Used by: `modules/weather.py`

- MET Norway (yr.no) - International weather data
  - SDK/Client: Direct HTTP via `modules/http_utils.py`
  - Auth: None (public API, User-Agent required)
  - Used by: `modules/weather.py`

**Geocoding:**
- Nominatim (OpenStreetMap) - Address to coordinates
  - SDK/Client: Direct HTTP via `modules/base.py` `_get_geocode_data()`
  - Auth: None (User-Agent required)
  - Used by: `modules/weather.py`, `modules/base.py`

**URL Shortening:**
- Shlink (self-hosted) - URL shortening service
  - SDK/Client: Direct HTTP via `requests`
  - Auth: `api_keys.shlink_url`, `api_keys.shlink_key` in config
  - Used by: `modules/shorten.py`

**Search:**
- DuckDuckGo Instant Answer API - Search results
  - SDK/Client: Direct HTTP via `requests`
  - Auth: None (public API)
  - Used by: `modules/convenience.py`

**Dictionaries:**
- Free Dictionary API - Word definitions
  - SDK/Client: Direct HTTP via `requests`
  - Auth: None (public API)
  - Used by: `modules/convenience.py`

**Wikipedia:**
- Wikipedia API - Article summaries
  - SDK/Client: Direct HTTP via `requests`
  - Auth: None (User-Agent required)
  - Used by: `modules/convenience.py`

**News:**
- Google News RSS - Headlines
  - SDK/Client: Direct HTTP + XML parsing
  - Auth: None (public RSS)
  - Used by: `modules/convenience.py`

**Cryptocurrency:**
- CoinGecko API - Crypto prices
  - SDK/Client: Direct HTTP via `modules/http_utils.py`
  - Auth: None (public API)
  - Used by: `modules/crypto.py`

## Data Storage

**Databases:**
- SQLite 3 (local file)
  - Connection: `config/absurdia.db`
  - Client: Python `sqlite3` stdlib
  - Used by: `modules/absurdia_pkg/absurdia_db.py`

**JSON State Files:**
- File-based persistence in `config/`
  - Client: Python `json` stdlib + custom `MultiFileStateManager`
  - Atomic writes with `.tmp` + rename pattern
  - File locking via `filelock` library

**File Storage:**
- Local filesystem only
- Config: `config/` directory
- Quotes: `config/quotes.json`
- Fortunes: `fortunes/` directory

**Caching:**
- In-memory only (Python dicts)
- State cache per module in `ModuleBase._state_cache`

## Authentication & Identity

**Auth Provider:**
- NickServ (IRC) - Bot nickname authentication
  - Implementation: IDENTIFY command on connect
  - Config: `connection.nickserv_pass`

- Custom admin system
  - Two-tier: Admin (nick-based) and Super Admin (password-based)
  - Admin verification: Nick + hostname matching
  - Super admin: bcrypt password hash, time-limited sessions
  - Config: `core.admins`, `core.super_admin_password_hash`

## Monitoring & Observability

**Error Tracking:**
- None (no external error tracking service)

**Logs:**
- Rotating file logs via `logging.handlers.RotatingFileHandler`
- Log file: `debug.log` (configurable)
- Rotation: 100KB per file, 10 backups
- Sensitive data redaction in `Jeeves._redact_sensitive_data()`
- Per-module debug flags

## CI/CD & Deployment

**Hosting:**
- Self-hosted Linux server
- systemd user service

**CI Pipeline:**
- None configured

**Deployment Method:**
```bash
# Manual deployment
git pull
systemctl --user restart jeeves
```

## Environment Configuration

**Required env vars (loaded from `~/.env`):**
- API keys can be referenced as `${VAR_NAME}` in config.yaml
- No strictly required env vars (can be inline in config)

**Recommended secrets in env:**
- `OPENAI_API_KEY` - LLM API key
- `DEEPL_API_KEY` - Translation API key
- `SHLINK_KEY` - URL shortener API key
- `PIRATEWEATHER_KEY` - Weather API key
- `GIPHY_KEY` - GIF search API key
- `YOUTUBE_KEY` - YouTube API key

**Secrets location:**
- `~/.env` (systemd EnvironmentFile)
- Alternatively inline in `config/config.yaml` (not recommended)

## Webhooks & Callbacks

**Incoming:**
- None

**Outgoing:**
- None

## IRC Protocol

**Server Connection:**
- Server: Configurable (default: `irc.libera.chat`)
- Port: Configurable (default: 6697 for SSL)
- SSL: Automatic for port 6697
- Channels: Auto-join from config + persisted list

**IRC Features Used:**
- PRIVMSG - Public/private messages
- JOIN/PART/KICK - Channel management
- NICK - Nick change tracking
- MODE - Bot mode (+B)
- QUIT - Graceful disconnect

---

*Integration audit: 2026-01-18*
