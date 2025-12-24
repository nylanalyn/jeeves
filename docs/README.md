# Jeeves Documentation

## 🤖 For AI Coding Assistants

**If you're an LLM helping with Jeeves development, start here:**

📖 **[LLM Architecture Guide](LLM_ARCHITECTURE_GUIDE.md)** - Comprehensive guide covering:
- How jeeves.py, modules, and state management work together
- Step-by-step guide to writing new modules
- Common patterns and pitfalls
- Quick reference for all major systems

This guide is specifically written for AI assistants to quickly understand Jeeves' architecture without reading the entire codebase.

---

## Overview
Jeeves is a modular IRC butler written in Python 3.11. It connects to IRC networks, loads plugins from `modules/`, and persists shared state across JSON files in `config/`. Core responsibilities include utility commands (weather, time, translation), social features (memos, courtesy titles), and the quest game system. A lightweight web dashboard lives under `web/quest/` for viewing quest data.

## Setup & Operation
1. **Create an environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **Configure**: Copy `config/config.yaml` from the provided default or run `python3 jeeves.py` once to scaffold it. Populate IRC credentials, admin accounts, and API keys.
3. **Run the bot**
   ```bash
   python3 jeeves.py
   ```
   The bot validates configuration at startup, connects using TLS (if enabled), and loads all non-blacklisted modules.
4. **Run the web UI (optional)**
   ```bash
   python3 web/quest_web.py --host 127.0.0.1 --port 8080
   ```
   Serves stats at `/` and quest at `/quest` (plus `/activity` and `/achievements`). Override `--games`, `--content`, or `--config` to point at alternative data locations.

## Configuration & Validation
- Use environment variables for secrets: `${OPENAI_API_KEY}`, `${DEEPL_API_KEY}`, `${NICKSERV_PASSWORD}`, etc.
- Run `python3 config_validator.py config/config.yaml` after edits to view the validation report with ERROR/WARNING/INFO tiers.
- Channel access is controlled per module via `allowed_channels`/`blocked_channels`. Leave `allowed_channels` empty to make the module global.
- Core state files live in `config/` (`state.json`, `users.json`, `games.json`, `stats.json`). They are updated by modules through the `MultiFileStateManager`.

## Development Workflow
- Each plugin defines `setup(bot, config)` and typically derives from `SimpleCommandModule` in `modules/base.py`.
- Register commands with regex patterns and keep responses brief; f-strings are preferred for formatting.
- When refactoring, add type hints and keep 4-space indentation consistent with existing style.
- Manual testing: run targeted scripts (for example `python3 test_prestige_display.py`) and trigger commands against a staging IRC channel. Capture `debug.log` when diagnosing issues.
- The repository now keeps working documentation under `docs/`. `docs/AGENTS.md` covers contributor expectations, and `docs/themes.md` catalogs theme operations.

## Automation Notes
Automated assistants should avoid destructive actions (no force pushes, no git resets) and respect the config validator before deploying. When updating modules, document user-visible command changes and clean up temporary files. Use this documentation set as the canonical reference and prefer enriching existing sections over creating new standalone guides.

## Topic Rotation Module
- Configure the `topic` block in `config/config.yaml` with the list of channels to manage, an optional daily window (`start_hour`/`end_hour`), and any overrides for the model, temperature, or prompt used to guide the oracle response.
- The module schedules one rotation per day at a random minute within the configured window and sets the IRC topic via `TOPIC` once a new mood line is generated.
- AI generations reuse the same OpenAI/ArliAI credentials as `oracle`. If the API is unavailable, Jeeves falls back to curated static topics so the channel never ends up blank.
- Anyone in channel can issue `!topic` to request an immediate refresh (rate-limited via `trigger_cooldown_seconds`), while admins retain `!topic refresh`/`!topic status` for forced multi-channel updates and auditing.
