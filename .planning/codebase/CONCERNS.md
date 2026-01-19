# Codebase Concerns

**Analysis Date:** 2026-01-18

## Tech Debt

**Large Module Files:**
- Issue: Several modules exceed 1000 lines, making them difficult to maintain and test
- Files:
  - `modules/absurdia_pkg/absurdia_main.py` (1806 lines)
  - `modules/quest_pkg/quest_progression.py` (1546 lines)
  - `web/stats/templates.py` (1551 lines)
  - `web/quest/templates.py` (1537 lines)
  - `modules/hunt.py` (1371 lines)
  - `modules/fishing.py` (1242 lines)
  - `modules/quest_pkg/quest_core.py` (1203 lines)
- Impact: Code readability, testing complexity, onboarding difficulty
- Fix approach: Continue splitting into subpackages like absurdia_pkg and quest_pkg patterns

**Bare Except Clauses:**
- Issue: Two locations use bare `except:` which swallows all exceptions including KeyboardInterrupt
- Files:
  - `modules/quest_pkg/__init__.py:875` - catches date parsing errors
  - `web/quest/templates.py:759` - catches template rendering errors
- Impact: Hides bugs, makes debugging difficult, can mask critical errors
- Fix approach: Replace with specific exception types (ValueError, AttributeError, etc.)

**Silent Exception Swallowing:**
- Issue: Multiple `except Exception: pass` patterns hide errors
- Files:
  - `modules/achievement_hooks.py:18-20` - silently ignores achievement errors
  - `file_lock.py:70-71` - ignores lock cleanup errors
  - `modules/quest_pkg/quest_combat.py:450-451` - ignores effect removal errors
  - `modules/quest_pkg/quest_utils.py:220-222` - silently skips invalid injuries
- Impact: Production bugs go unnoticed, state corruption possible
- Fix approach: Log errors before continuing, or handle specific exception types

**Hardcoded Configuration in Code:**
- Issue: Game data (fish, locations, etc.) embedded directly in Python files
- Files:
  - `modules/fishing.py:20-240` - LOCATIONS and FISH_DATABASE hardcoded
  - `modules/hunt.py:32-76` - COLLECTIVE_NOUNS, message templates hardcoded
  - `modules/absurdia_pkg/absurdia_creatures.py` - creature templates
- Impact: Requires code changes for content updates, no admin control
- Fix approach: Move to JSON config files like `quest_content.json` pattern

**Legacy Code and Compatibility Shims:**
- Issue: Multiple legacy aliases and backward compatibility code scattered throughout
- Files:
  - `modules/quest_pkg/__init__.py:313-318` - Legacy command aliases for mob_ping, mob, join, medkit, inventory
  - `modules/quest_pkg/quest_core.py:92` - Legacy single-theme structure handling
  - `modules/quest_pkg/quest_core.py:448-459` - Legacy knob handling for search functionality
  - `modules/quotes.py:31-42` - Legacy state migration from old module state format
  - `web/quest/themes.py:187-237` - Legacy theme file loading
  - `config_validator.py:299` - Legacy 'channel' key support alongside 'main_channel'
  - `web/server.py:166` - Legacy URL aliases for compatibility
- Impact: Increases complexity; unclear when legacy code can be removed
- Fix approach: Document deprecation timeline; add removal TODOs with dates; eventually remove after migration period

**State Migration in Player Data:**
- Issue: Player data migration happens at runtime in get_player() function
- Files:
  - `modules/quest_pkg/quest_progression.py:134-141` - Migrates old medkits format and inventory keys
  - `modules/quest_pkg/quest_progression.py:477-479` - Migrates active_injury to active_injuries
  - `modules/hunt.py:86-93` - Migrates active_animal to active_animals list
- Impact: Runtime overhead on every player lookup; potential for migration bugs
- Fix approach: Create one-time migration script; run migrations on bot startup once; remove inline migration code

**Duplicated Exception Classes:**
- Issue: Exception classes defined in multiple places with identical structure
- Files:
  - `modules/base.py:44-47` - ModuleException, ExternalAPIException, UserInputException, StateException (fallback imports)
  - `modules/exception_utils.py:22-54` - Same exception classes with docstrings (canonical location)
  - `modules/convenience.py:28-30` - ExternalAPIException, NetworkException, UserInputException stubs
  - `modules/quest_pkg/quest_core.py:22-24` - FileOperationException, ConfigurationException, ExternalAPIException
- Impact: Inconsistent exception handling; unclear which class to import
- Fix approach: Consolidate all exceptions into `modules/exception_utils.py`; update imports across codebase

**Deprecated Function:**
- Issue: Deprecated function kept for backward compatibility
- Files:
  - `modules/shorten.py:121` - `shorten_url_legacy()` marked deprecated but still present
  - `web/quest/themes.py:400` - Legacy function for backward compatibility
- Impact: API surface clutter; potential for accidental use
- Fix approach: Add deprecation warning; schedule removal

**Inconsistent State Management:**
- Issue: Quest module overrides base class state methods for cache refresh
- Files: `modules/quest_pkg/__init__.py:54-74`
- Impact: Inconsistent behavior between modules, potential race conditions
- Fix approach: Move refresh logic to base class or use consistent pattern across modules

## Known Bugs

**Debug Logging of Sensitive Data:**
- Symptoms: Password hash representation logged to debug file
- Files: `jeeves.py:597`
- Trigger: Super admin authentication attempt with debug mode on
- Workaround: Log message sanitization exists but this line bypasses it with explicit repr()

**Return None Pattern Overuse:**
- Symptoms: Many functions return None on error with no indication of failure reason
- Files: Throughout codebase, notably:
  - `modules/weather.py:70-98` - Multiple return None paths
  - `modules/convenience.py:256-257, 445, 537-540, 567` - Silent failures
  - `modules/fishing.py:433, 461, 526-599` - Many return None paths
  - `web/quest/utils.py:23-117` - Returns empty dict on errors
- Trigger: Any error condition in these functions
- Workaround: Errors are silently swallowed; check logs for actual issues

## Security Considerations

**API Key Management:**
- Risk: API keys stored in config file, validated at startup
- Files:
  - `config_validator.py:351-418` - API key validation
  - `modules/weather.py:67-68` - PirateWeather API key access
- Current mitigation: Environment variable substitution supported, sensitive data redaction in logs
- Recommendations: Document env var approach in setup, audit all API key usages

**Password Hash Exposure in Debug Logs:**
- Risk: Debug log at line 597 of jeeves.py explicitly logs password_hash representation
- Files: `jeeves.py:597`
- Current mitigation: Debug mode is off by default
- Recommendations: Remove or redact this debug line, use log sanitizer consistently

**Admin Hostname Trust:**
- Risk: Admin verification relies on IRC hostname which can be spoofed on some networks
- Files: `jeeves.py:510-538`
- Current mitigation: Hostname is tracked and updated per session, NickServ identification assumed
- Recommendations: Consider IP-based verification or challenge-response for critical actions

**bcrypt Password Verification:**
- Risk: Super admin authentication uses bcrypt
- Files: `jeeves.py:581-626` - `authenticate_super_admin()` method
- Current mitigation: Session expiry, bcrypt verification, admin list check
- Recommendations: Consider rate limiting failed authentication attempts

**SQL Injection Prevention:**
- Risk: Dynamic SQL column names in database operations
- Files: `modules/absurdia_pkg/absurdia_main.py:1117-1134` - `_update_creature_stat()` method
- Current mitigation: Whitelist validation of stat names before SQL execution
- Recommendations: Pattern is correct; ensure any new database methods follow same pattern

**Environment Variable Handling:**
- Risk: Secrets could be exposed if env vars not set
- Files: `config_validator.py:120-155` - `_substitute_env_string()` method
- Current mitigation: Logs warning when sensitive env vars missing; skips bcrypt hash substitution
- Recommendations: Ensure .env files are in .gitignore; document required env vars

## Performance Bottlenecks

**Blocking Sleep in IRC Handlers:**
- Problem: `time.sleep()` calls block the IRC event loop
- Files:
  - `modules/quest_pkg/quest_combat.py:440` - 1.5 second sleep
  - `modules/quest_pkg/quest_core.py:212` - 1.5 second sleep
- Cause: Dramatic pause effects in quest combat
- Improvement path: Use threaded message scheduling or async patterns

**State File I/O on Every Access:**
- Problem: State files may be re-read from disk frequently
- Files: `jeeves.py:179-191` - _ensure_latest checks mtime on every state access
- Cause: Support for external state file modifications
- Improvement path: Increase polling interval or use file watchers

**Large In-Memory State:**
- Problem: All player data loaded into memory for each state file
- Files: `jeeves.py:60-255` - MultiFileStateManager loads full JSON
- Cause: Simple flat-file storage design
- Improvement path: Consider SQLite for large state (absurdia already uses this pattern)

**Synchronous HTTP Client:**
- Problem: All external API calls block the main thread
- Files:
  - `modules/http_utils.py` - Centralized HTTP client
  - `modules/base.py:164-178` - `_get_geocode_data()` uses blocking requests
  - `modules/convenience.py:377-425` - Various blocking API calls
- Cause: IRC bot is single-threaded; blocking calls delay message processing
- Improvement path: Consider using threading for API calls or async IRC framework

**Template Rendering:**
- Problem: HTML templates rendered as string concatenation in Python
- Files:
  - `web/stats/templates.py` (1551 lines of template code)
  - `web/quest/templates.py` (1537 lines of template code)
- Cause: No template caching; templates rebuilt on every request
- Improvement path: Consider using Jinja2 with caching; move templates to separate files

## Fragile Areas

**Quest State Parsing:**
- Files:
  - `modules/quest_pkg/__init__.py:872-876`
  - `modules/quest_pkg/quest_progression.py:1188-1190`
- Why fragile: ISO datetime parsing with bare except, any format change breaks silently
- Safe modification: Add explicit ValueError/TypeError handling, validate datetime formats
- Test coverage: No direct unit tests for injury parsing

**Multi-File State Coordination:**
- Files: `jeeves.py:60-255`
- Why fragile: State split across 4 JSON files (state, games, users, stats) with module mapping
- Safe modification: Ensure STATE_FILE_MAPPING is updated when adding new modules
- Test coverage: No automated tests for state manager

**Theme/Content Loading:**
- Files:
  - `modules/quest_pkg/quest_core.py:41-96` - theme loading
  - `web/quest/templates.py` - theme rendering
- Why fragile: Complex fallback chain for themes, bare except in template rendering
- Safe modification: Validate theme structure at load time, add schema validation
- Test coverage: No tests for theme fallback behavior

**Scheduled Job Management:**
- Files:
  - `modules/hunt.py:289-309` - on_load scheduling resume
  - `modules/hunt.py:311-324` - `_clear_scheduled_jobs()` to prevent duplicates
  - `modules/absurdia_pkg/absurdia_main.py:41-44` - Schedule setup in __init__
- Why fragile: Jobs can duplicate if module reloads; clearing by tag requires exact matching
- Safe modification: Always use `schedule.clear(tag)` before adding new jobs; use unique tags per module
- Test coverage: No automated tests for scheduler edge cases

**Dungeon State Machine:**
- Files:
  - `modules/quest_pkg/quest_progression.py:1120-1446` - `cmd_dungeon_run()` function
  - `modules/quest_pkg/quest_progression.py:1077-1107` - `_auto_prepare_dungeon_loadout()`
- Why fragile: Complex multi-room progression with safe havens, momentum, and item effects
- Safe modification: Trace full state flow before changes; test edge cases like disconnect mid-run
- Test coverage: No automated tests for dungeon runs

**IRC Event Handling:**
- Files:
  - `jeeves.py:637-790` - on_connect, on_welcome, on_join, on_part, on_kick, on_nick, on_pubmsg, on_privmsg
- Why fragile: Module dispatch relies on specific method names (on_join, on_ambient_message, etc.)
- Safe modification: Check all modules for matching method signatures before changing core dispatch
- Test coverage: Minimal; only `tests/test_title_for.py` tests Jeeves class

## Scaling Limits

**IRC Message Rate Limits:**
- Current capacity: No explicit rate limiting implemented
- Limit: IRC servers typically limit to 5-10 messages per second
- Scaling path: Add message queue with rate limiting in base module

**State File Size:**
- Current capacity: JSON files can grow unbounded
- Limit: Performance degrades with files >10MB, memory pressure with many players
- Scaling path: Archive old data, implement SQLite migration like absurdia module

**Single IRC Connection:**
- Current capacity: One IRC server, one bot instance
- Limit: Cannot scale horizontally; single thread for all messages
- Scaling path: Would require architectural redesign for multiple bot instances

## Dependencies at Risk

**schedule Library:**
- Risk: Global scheduler state shared across all modules
- Impact: Schedule jobs tagged by module name, but no isolation
- Migration plan: Consider per-module schedulers or asyncio-based scheduling

**requests Library:**
- Risk: Synchronous HTTP calls block IRC handling
- Impact: Slow API responses cause bot unresponsiveness
- Migration plan: http_utils module exists but not all modules use it consistently

## Missing Critical Features

**Input Validation Inconsistency:**
- Problem: User input validation varies between modules
- Blocks: Consistent security posture, predictable error messages
- Files: `modules/base.py:35-37` has validate_user_input but not widely used

**Centralized Error Reporting:**
- Problem: Errors logged to debug file only, no alerting
- Blocks: Proactive issue detection, production monitoring
- Files: `modules/exception_utils.py` provides patterns but no aggregation

**Rate Limiting:**
- Problem: No global rate limiting for commands
- Blocks: Protection against spam/abuse
- Note: Per-command cooldowns exist but no global flood protection

**Health Monitoring:**
- Problem: No health check endpoint or monitoring integration
- Blocks: Automated deployment health verification

## Test Coverage Gaps

**Core Bot Functions:**
- What's not tested: MultiFileStateManager, PluginManager, IRC event handlers
- Files: `jeeves.py` - 907 lines with 0 direct tests
- Risk: State corruption, connection issues, module loading failures
- Priority: High

**Game Modules:**
- What's not tested: Quest combat, fishing mechanics, hunt spawning, absurdia battles
- Files:
  - `modules/quest_pkg/` - ~4000 lines total
  - `modules/fishing.py` - 1242 lines
  - `modules/hunt.py` - 1371 lines
  - `modules/absurdia_pkg/` - ~3100 lines total
- Risk: Game balance issues, state corruption, edge case crashes
- Priority: Medium

**Web Interface:**
- What's not tested: Template rendering, data loading, route handlers
- Files:
  - `web/stats/templates.py` - 1551 lines
  - `web/quest/templates.py` - 1537 lines
  - `web/server.py` - 514 lines
- Risk: XSS vulnerabilities, broken pages, data display errors
- Priority: Medium

**Existing Test Files:**
- Files: `tests/` directory contains only 4 test files
  - `test_achievements_loader.py`
  - `test_achievements_page.py`
  - `test_activity_stats.py`
  - `test_title_for.py`
- Total: ~12 tests for ~31,000 lines of code
- Coverage estimate: <1%
- Priority: High - need test infrastructure and module isolation patterns

---

*Concerns audit: 2026-01-18*
