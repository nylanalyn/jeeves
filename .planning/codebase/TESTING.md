# Testing Patterns

**Analysis Date:** 2026-01-18

## Test Framework

**Runner:**
- `unittest` (Python standard library)
- No pytest configuration detected
- No dedicated test config file (pytest.ini, conftest.py in project root)

**Assertion Library:**
- `unittest.TestCase` built-in assertions
- `self.assertEqual()`, `self.assertIn()`, `self.assertIsNone()`, etc.

**Run Commands:**
```bash
python -m unittest tests/test_activity_stats.py     # Run single test file
python -m unittest discover tests/                   # Run all tests
python tests/test_title_for.py                       # Run directly
```

## Test File Organization

**Location:**
- Tests in `/home/nylan/code/jeeves/tests/` directory (separate from source)
- Not co-located with modules

**Naming:**
- Pattern: `test_<feature>.py`
- Examples: `test_activity_stats.py`, `test_achievements_loader.py`, `test_title_for.py`

**Structure:**
```
tests/
├── test_achievements_loader.py    # Data loader tests
├── test_achievements_page.py      # Template rendering tests
├── test_activity_stats.py         # Stats aggregation tests
└── test_title_for.py              # Bot method tests
```

## Test Structure

**Suite Organization:**
```python
import unittest
from module_to_test import ClassToTest

class TestFeatureName(unittest.TestCase):
    def test_specific_behavior_description(self) -> None:
        # Arrange
        test_input = {...}

        # Act
        result = function_under_test(test_input)

        # Assert
        self.assertEqual(result, expected_value)

if __name__ == "__main__":
    unittest.main()
```

**Patterns:**
- Class per test group: `class TestActivityStats(unittest.TestCase):`
- Method per test case: `def test_loader_missing_stats_file_returns_defaults(self) -> None:`
- Type hints on test methods: `-> None`
- Direct execution support: `if __name__ == "__main__": unittest.main()`

## Mocking

**Framework:** Manual stub classes (no unittest.mock or pytest fixtures)

**Patterns:**
```python
# Stub classes for dependencies
class _CourtesyStub:
    def __init__(self, profile):
        self._profile = profile

    def _get_user_profile(self, user_id):
        return self._profile

class _PluginManagerStub:
    def __init__(self, plugins):
        self.plugins = plugins

# Factory function for creating test instances
def _make_bot(*, courtesy_profile=None, quest_suffix=None):
    bot = Jeeves.__new__(Jeeves)  # Create without __init__
    plugins = {}
    if courtesy_profile is not None:
        plugins["courtesy"] = _CourtesyStub(courtesy_profile)
    bot.pm = _PluginManagerStub(plugins)
    bot.get_user_id = lambda nick: f"user-id-for:{nick}"
    return bot
```

**Dependency Stubs for Import Issues:**
```python
def _install_dependency_stubs():
    if "irc" not in sys.modules:
        irc_module = types.ModuleType("irc")
        irc_bot_module = types.ModuleType("irc.bot")

        class SingleServerIRCBot:
            pass

        irc_bot_module.SingleServerIRCBot = SingleServerIRCBot
        sys.modules["irc"] = irc_module
        sys.modules["irc.bot"] = irc_bot_module

_install_dependency_stubs()  # Run before imports
```

**What to Mock:**
- External dependencies (IRC library, schedule)
- Plugin manager and plugins
- Bot methods like `get_user_id()`

**What NOT to Mock:**
- The class under test
- Simple data transformations
- Standard library utilities

## Fixtures and Factories

**Test Data:**
```python
# Inline test data in test methods
def test_aggregator_user_lookup_and_top_hours(self) -> None:
    fake_stats = {
        "users": {
            "u1": {"canonical_nick": "Alice", "seen_nicks": ["alice", "alice_away"]},
        },
        "activity": {
            "global": {"grid": [0] * (7 * 24), "total": 0},
            "channels": {},
            "users": {
                "u1": {"grid": [0] * (7 * 24), "total": 0},
            },
        },
        # ... more nested data
    }
```

**Temporary Files:**
```python
import tempfile
from pathlib import Path

def test_loader_reads_achievements_from_state_json(self) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir)

        state_payload = {"modules": {"achievements": {...}}}
        (config_path / "state.json").write_text(
            json.dumps(state_payload), encoding="utf-8"
        )

        loader = JeevesStatsLoader(config_path)
        result = loader.load_achievements_stats()
        # assertions...
```

**Location:**
- No separate fixtures directory
- Test data defined inline in test methods
- Factory functions in test file (e.g., `_make_bot()`)

## Coverage

**Requirements:** None enforced

**View Coverage:**
```bash
# No coverage configuration detected
# Would use:
python -m coverage run -m unittest discover tests/
python -m coverage report
```

## Test Types

**Unit Tests:**
- Focus on individual methods and classes
- Mock dependencies to isolate units
- Found in: `tests/test_*.py`

**Integration Tests:**
- Test data loaders with actual file I/O (using tempfiles)
- Test template rendering with real data structures
- Example: `test_loader_reads_achievements_from_state_json()`

**E2E Tests:**
- Not present in codebase
- No browser/IRC integration tests

## Common Patterns

**Async Testing:**
```python
# Not applicable - codebase is synchronous
# No async/await patterns in tests
```

**Error Testing:**
```python
# Test missing data returns defaults
def test_loader_missing_stats_file_returns_defaults(self) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir)
        loader = JeevesStatsLoader(config_path)
        stats = loader.load_all()

        self.assertIn("activity", stats)
        self.assertEqual(stats["activity"]["global"]["total"], 0)
```

**Parameterized Tests:**
```python
# Manual parameterization via multiple assertions
def test_title_for_uses_sir_and_madam(self):
    bot = _make_bot(courtesy_profile={"title": "sir"})
    self.assertEqual(bot.title_for("Alice"), "Sir")

    bot = _make_bot(courtesy_profile={"title": "madam"})
    self.assertEqual(bot.title_for("Alice"), "Madam")
```

**Testing HTML Output:**
```python
def test_hides_undiscovered_achievements(self) -> None:
    stats = {"users": {...}, "achievements": {...}}
    html = render_achievements_page(stats)

    self.assertIn("Unlucky", html)           # Present text
    self.assertNotIn("Quest Novice", html)   # Absent text
```

## Test File Template

```python
import unittest

# Optionally stub dependencies before importing
def _install_dependency_stubs():
    # ... stub creation
    pass

_install_dependency_stubs()

from module_under_test import ClassUnderTest


class _StubDependency:
    """Stub for dependency injection."""
    def __init__(self, return_value):
        self._return_value = return_value

    def method(self):
        return self._return_value


class TestClassName(unittest.TestCase):
    def test_method_does_expected_thing(self) -> None:
        # Arrange
        stub = _StubDependency(expected_return)
        instance = ClassUnderTest(stub)

        # Act
        result = instance.method_under_test()

        # Assert
        self.assertEqual(result, expected_value)

    def test_handles_edge_case(self) -> None:
        # Test edge cases
        pass


if __name__ == "__main__":
    unittest.main()
```

## Test Coverage Gaps

**Untested Areas:**
- Module command handlers (`_cmd_*` methods)
- IRC event handlers (`on_pubmsg`, `on_join`, etc.)
- State persistence and file locking
- Error recovery paths
- Most game modules (quest, hunt, fishing, etc.)

**Currently Tested:**
- Web stats data loading (`test_activity_stats.py`)
- Achievements loading from JSON (`test_achievements_loader.py`)
- Achievements page rendering (`test_achievements_page.py`)
- Bot `title_for()` method (`test_title_for.py`)

---

*Testing analysis: 2026-01-18*
