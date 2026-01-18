# Repository Guidelines

## 🤖 For AI Coding Assistants

**Before making changes to Jeeves, read this first:**

📖 **[docs/LLM_ARCHITECTURE_GUIDE.md](docs/LLM_ARCHITECTURE_GUIDE.md)** - Complete architecture reference covering:
- How jeeves.py, modules, state management, and user tracking work
- Step-by-step module creation guide
- Common patterns and pitfalls
- Quick reference card

This guide was written specifically for LLMs to quickly understand Jeeves without reading the entire codebase. **Start there before modifying any code.**

---

## Working agreements
- Ask clarifying questions when scope is unclear.
- Keep changes small and reviewable.
- Run tests before finishing.

## Project Structure & Module Organization
`jeeves.py` is the entry point; it boots the IRC bot, loads feature modules from `modules/`, and writes shared JSON state under `config/`. Web-facing quest surfaces live in `web/` (`quest_web.py` plus static assets under `web/static/` and templates under `web/quest/`). Runtime data sits in `quest_content.json` and `challenge_paths.json`, while CLI helpers (password hashing, config validation) live in the repo root. Operational notes belong in `docs/`.

## Build, Test, and Development Commands
- `python3 -m venv venv && source venv/bin/activate.fish`: create an isolated Python toolchain.
- `pip install -r requirements.txt`: install bot, web, and validator dependencies.
- `python3 config_validator.py config/config.yaml`: confirm YAML structure, env substitutions, and required secrets before running.
- `python3 jeeves.py`: launch Jeeves against the active config; expects IRC credentials in `config/config.yaml`.
- `python3 web/quest_web.py --host 127.0.0.1 --port 8080`: serve the quest dashboard for local QA of narrative changes.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation and snake_case filenames/functions; reserve CamelCase for classes. Prefer explicit imports from `modules.*` so it is obvious which subsystem is touched. Use f-strings for logging, keep logger names module-scoped, and co-locate constants near the top of each file. Add short docstrings when creating new modules or commands, and include type hints for cross-module APIs to keep contracts clear.

## Testing Guidelines
Existing regression coverage is minimal (`test_prestige_display.py` near the repo root). Extend that file or add pytest-style suites under `tests/` following the naming pattern `test_<feature>.py`. Run smoke tests with `python3 test_prestige_display.py`. When touching configuration flows, rerun `python3 config_validator.py` and snapshot JSON in `config/` to avoid clobbering state. For modules that emit IRC output, script sample events in a temporary channel and capture transcripts in the PR.

## Commit & Pull Request Guidelines
Git history favors short, imperative subjects (e.g., `tighten prestige thresholds`). Keep commits focused on a single module or concern, and squash noisy WIP commits before review. Pull requests should describe the feature, note config or data migrations, and summarize manual test steps. Link to relevant issues or quest logs, and attach screenshots for web UI changes or IRC transcripts for conversational flows.

## Security & Configuration Tips
Never commit populated files from `config/`; rely on `.example` templates plus env vars. Mask network addresses, channel names, and tokens in logs. If you change systemd units such as `jeeves.service`, include deployment notes in `docs/README.md` and call out any new environment toggles.
