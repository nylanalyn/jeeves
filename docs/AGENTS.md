# Repository Guidelines

## Project Structure & Module Organization
Jeeves runs from `jeeves.py`, loading plugins from `modules/` (utility, social, quest, admin) while persisting JSON state in `config/`. The quest web dashboard lives under `web/quest/` alongside `web/static/` assets. Game narrative data and themes are bundled in the consolidated `quest_content.json` (with multiple theme entries) alongside `challenge_paths.json`, and documentation now lives in `docs/`.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: isolate project dependencies.
- `pip install -r requirements.txt`: install runtime and web UI packages.
- `python3 config_validator.py config/config.yaml`: verify config schema and environment substitutions.
- `python3 jeeves.py`: launch the IRC bot with the active configuration.
- `python3 web/quest_web.py --host 127.0.0.1 --port 8080`: start the quest dashboard for local QA.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation. Modules, functions, and files use snake_case; reserve CamelCase for classes. Add type hints for new APIs or refactors. Keep logging concise, prefer f-strings, and colocate related constants at the top of each module. Use docstrings to summarize module intent in one sentence.

## Testing Guidelines
Current automated coverage is light. Extend `test_prestige_display.py` or add pytest suites under `tests/` when implementing logic changes. For regression checks run `python3 test_prestige_display.py` and inspect console output. After editing configuration or state management, rerun `python3 config_validator.py` to catch schema regressions. When testing modules that write to JSON state, snapshot files in `config/` before manual runs and restore as needed.

## Commit & Pull Request Guidelines
Match the terse, lowercase commit titles in history (`fix quest prestige tiers`). Squash incidental WIP commits before pushing. Pull requests should describe feature scope, configuration impacts, and manual test steps; link related issues or quest logs. Include screenshots for web UI changes and sample IRC transcripts when altering command flows.

## Security & Configuration Tips
Do not commit populated files from `config/` or expose API keys—stick to environment variables supported by the validator. Mask channel names and user handles when sharing logs. Review `jeeves.service` before deploying changes, and document any new environment toggles in `docs/README.md`.
