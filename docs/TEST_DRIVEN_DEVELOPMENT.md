# Test-Driven Development (TDD) Guide for MAIRE

This document explains **why** we follow TDD for the MAIRE project, **how** to write new tests and design new components based on tests, **how** the test suite is structured, **how to run** the tests, and **how to interpret** failures.

---

## Table of Contents

1. [Why TDD for MAIRE?](#1-why-tdd-for-maire)
2. [How to Write New Tests & Design Components](#2-how-to-write-new-tests--design-components)
3. [Test Suite Structure](#3-test-suite-structure)
4. [How to Run Tests](#4-how-to-run-tests)
5. [How to Interpret Test Output & Failures](#5-how-to-interpret-test-output--failures)
6. [Conventions & Best Practices](#6-conventions--best-practices)

---

## 1. Why TDD for MAIRE?

### 1.1 The Problem MAIRE Solves

MAIRE is an **automated evaluation framework** for Android app automation agents (Gemini Live, GPT Live, Claude Live, etc.). It:

- Sends voice queries to an AI assistant on a physical device
- Captures the assistant's spoken response (via transcription)
- Verifies whether the device state actually changed (via XRClaw state collectors)
- Scores the response using deterministic judges and LLM judges

This is a **multi-system integration** — device managers, transcription servers, judge workers, state collectors, and report generators all interact. A bug in any component can produce silently wrong evaluation scores.

### 1.2 Why TDD Is Critical Here

| Risk | How TDD Mitigates |
|------|-------------------|
| **State collector false positives** — a bug in `verify()` could give a passing score to a failed action | Integration tests simulate the full pre→action→verify flow with known state, catching logic errors |
| **Mock/real API drift** — if the mock doesn't match XRClaw's real API, tests pass but production fails | Mock objects mirror XRClaw's exact field names and `to_dict()` schemas; integration tests catch mismatches |
| **Judge scoring regressions** — changing a judge prompt or threshold can silently change all scores | Unit tests pin specific scoring outcomes for known inputs |
| **App registry breakage** — adding a new app can break existing app key routing | Registry tests verify all app keys resolve to state collectors |
| **Refactoring safety** — refactoring state collectors or judges without tests is dangerous | 183 tests provide a safety net for refactoring |

### 1.3 The TDD Cycle for MAIRE

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   1. RED     │────▶│  2. GREEN   │────▶│  3. REFACTOR│
│ Write a test │     │ Make it pass│     │ Clean it up │
│ that fails   │     │ (minimal)   │     │ (keep green)│
└─────────────┘     └─────────────┘     └─────────────┘
```

**Example TDD flow for a new state collector:**

1. **RED**: Write a test that creates a `MockXRClawDeviceManager`, simulates an agent action, and calls `verify()` — before the state collector exists. The test fails with `ImportError`.

2. **GREEN**: Create the state collector module with `capture_pre()` and `verify()` functions. Implement minimal logic to make the test pass.

3. **REFACTOR**: Extract shared logic into `helpers.py`, add edge-case tests (not found, pre-state missing, etc.), and ensure all tests still pass.

---

## 2. How to Write New Tests & Design New Components

### 2.1 Adding a New App State Collector

**Step 1: Write the test first**

Create `test/integration/test_state_collectors.py` and add a test class:

```python
class TestMyNewAppStateCollector:
    """Tests for agent_testers/apps/my_new_app/state_collector.py"""

    def test_state_collector_exists(self):
        assert "mynewapp" in STATE_COLLECTORS

    def test_create_success(self, dm):
        from agent_testers.apps.my_new_app.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        dm.my_accessor.create_item("Test Item", "test content")

        result = verify(dm, "mynewapp", "create", "Create a test item",
                        "A test item titled Test Item", pre)
        assert result["verified"] is True
        assert result["rating"] == 5
```

**Step 2: Run the test — it should fail (RED)**

```bash
python -m pytest test/integration/test_state_collectors.py::TestMyNewAppStateCollector -v
```

**Step 3: Implement the state collector (GREEN)**

Create `agent_testers/apps/my_new_app/state_collector.py`:

```python
from ..helpers import extract_keyword, result, pre_items_by_id, new_or_changed

APP_KEYS = ("mynewapp",)
ACCESSOR = "my_accessor"
PACKAGE_NAME = "com.example.myapp"

def capture_pre(dm):
    items = dm.my_accessor.find_items()
    return {"items": [i.to_dict() for i in items], "count": len(items)}

def verify(dm, app_key, mode, question, gt_answer, pre_state=None):
    # ... verification logic ...
    return result(app_key, verified, rating, analysis, actual_state, gt_answer)
```

**Step 4: Register the app**

Add the app key to `agent_testers/apps/__init__.py` in `APP_KEY_MAP` and `STATE_COLLECTORS`.

**Step 5: Add mock accessor if needed**

If the app uses a new XRClaw accessor, add it to `test/mocks/mock_xrclaw.py`:

```python
class MockMyAppAccessor:
    def __init__(self, dm):
        self._dm = dm

    def find_items(self, query=""):
        if query:
            return [i for i in self._dm._my_items if query.lower() in i.title.lower()]
        return list(self._dm._my_items)

    def create_item(self, title, content=""):
        item = MockMyItem(f"item_{len(self._dm._my_items)}", title, content)
        self._dm._my_items.append(item)
        return item.id
```

And add the property to `MockXRClawDeviceManager`:

```python
@property
def my_accessor(self):
    return MockMyAppAccessor(self)
```

**Step 6: Run all tests — they should pass (GREEN)**

### 2.2 Adding a New Judge

**Step 1: Write the test**

```python
# test/unit/test_my_new_judge.py
import json
from judge_worker.my_new_judge import MyNewJudge

class TestMyNewJudge:
    def test_correct_answer_gets_5(self):
        judge = MyNewJudge()
        result = judge.evaluate(
            "online_samsung_notes_create",
            "Create a note titled Shopping List",
            "I created a note titled Shopping List",
            {"verified": True, "rating": 5, "analysis": "Note found."},
        )
        response = json.loads(result[0])
        assert response["rating"] == 5

    def test_wrong_answer_gets_low_score(self):
        judge = MyNewJudge()
        result = judge.evaluate(
            "online_samsung_notes_create",
            "Create a note titled Shopping List",
            "I set an alarm for 7am",  # Wrong action
            {"verified": False, "rating": 0, "analysis": "No note found."},
        )
        response = json.loads(result[0])
        assert response["rating"] <= 2
```

**Step 2: Implement the judge** — make the test pass.

### 2.3 Adding a New Device Manager

**Step 1: Write tests using the `MockDeviceManager` interface**

```python
# test/unit/test_my_device_manager.py
class TestMyDeviceManager:
    def test_invoke_and_close(self):
        dm = MockDeviceManager()
        dm.invoke("test_config.json")
        assert dm.is_connected()
        dm.close_session()
        assert not dm.is_connected()
```

**Step 2: Implement the device manager** following the `BaseDeviceManager` interface.

---

## 3. Test Suite Structure

```
test/
├── TEST_DRIVEN_DEVELOPMENT.md      ← This document
├── __init__.py
├── test_config_schema.py           ← Config validation tests
├── test_entropy.py                 ← Entropy calculation tests
├── test_message.py                 ← Message transport tests
├── test_response_scorer_scoring.py ← Response scorer tests
│
├── unit/                           ← Unit tests (fast, no I/O, no device)
│   ├── test_app_registry.py        ← App key → state collector mapping
│   ├── test_deterministic_judge.py ← DeterministicJudge scoring logic
│   ├── test_helpers.py             ← State collector helper functions
│   └── test_question_type.py       ← Question type parsing
│
├── integration/                    ← Integration tests (mock I/O, no real device)
│   └── test_state_collectors.py    ← 22-app parametrized state collector matrix
│
├── mocks/                          ← Mock objects (drop-in replacements)
│   ├── __init__.py
│   ├── mock_xrclaw.py              ← MockXRClawDeviceManager (in-memory device)
│   ├── mock_arap.py                ← MockARAPManager (audio routing)
│   ├── mock_judge.py               ← Mock LLM judge server
│   ├── mock_transcription.py        ← Mock transcription server
│   └── mock_judge.yaml             ← Mock judge fixture data
│
└── fixtures/                       ← JSON fixture data for tests
    ├── notes.json
    ├── reminders.json
    ├── alarms.json
    ├── events.json
    ├── device_info.json
    └── ...
```

### 3.1 Test Categories

| Category | Location | Speed | Dependencies | Purpose |
|----------|----------|-------|-------------|---------|
| **Unit** | `test/unit/` | <1s | None | Test individual functions/classes in isolation |
| **Integration** | `test/integration/` | <1s | Mock objects | Test component interactions with mock I/O |
| **Examples** | `examples/` | <1s | Mock objects | Runnable demos for developers |
| **Real service** | (future) | 10-60s | Physical device, running servers | End-to-end with real services |

### 3.2 Mock Object Hierarchy

```
MockXRClawDeviceManager          ← Main mock, mirrors XRClaw DeviceManager
├── .notes → MockNotesAccessor   ← find_notes(), create_note(), delete_notes()
├── .reminders → MockRemindersAccessor
├── .calendar → MockCalendarAccessor
├── .google_calendar → MockGoogleCalendarAccessor
├── .alarms → MockAlarmAccessor
├── .stopwatch → MockStopwatchAccessor
├── .media → MockMediaAccessor
├── .maps → MockMapsAccessor
├── .messages → MockMessagesAccessor
├── .device_info → MockDeviceInfoAccessor
├── .translation → MockTranslationAccessor
└── .notifications → MockNotificationsAccessor
```

Each accessor mirrors the real XRClaw accessor's method signatures and return types (including `to_dict()`).

---

## 4. How to Run Tests

### 4.1 Prerequisites

Activate the virtual environment:

```bash
source /home/shouvik/Amartya/work_2026/Evaluation_Framework/agent_evaluation_env/bin/activate
```

### 4.2 Run All Tests

```bash
cd /home/shouvik/Ashutosh/Projects/GeminiEvaluation/maire
python -m pytest test/ -v
```

### 4.3 Run a Specific Test File

```bash
python -m pytest test/unit/test_deterministic_judge.py -v
python -m pytest test/integration/test_state_collectors.py -v
```

### 4.4 Run a Specific Test Class or Method

```bash
# By class
python -m pytest test/integration/test_state_collectors.py::TestSamsungNotesStateCollector -v

# By method
python -m pytest test/integration/test_state_collectors.py::TestSamsungNotesStateCollector::test_create_note_success -v
```

### 4.5 Run with Keyword Filter

```bash
# Run all tests with "alarm" in the name
python -m pytest test/ -v -k "alarm"

# Run all tests with "create" in the name
python -m pytest test/ -v -k "create"
```

### 4.6 Run with Coverage (if pytest-cov is installed)

```bash
python -m pytest test/ --cov=agent_testers --cov=judge_worker --cov-report=term-missing
```

### 4.7 Run Examples

```bash
python examples/01_mock_state_collector/run_example.py
python examples/02_deterministic_judge/run_example.py
```

### 4.8 Quick Smoke Test

```bash
python -m pytest test/ --tb=line -q
```

### 4.9 Stop on First Failure

```bash
python -m pytest test/ -x
```

---

## 5. How to Interpret Test Output & Failures

### 5.1 Successful Run

```
============================= 183 passed in 0.95s ==============================
```

- **183 passed** — all tests passed
- **0.95s** — total runtime (should be <2s for unit/integration tests)

### 5.2 Failed Run

```
FAILED test/integration/test_state_collectors.py::TestSamsungNotesStateCollector::test_create_note_success
E   assert False is True
```

This means:
- **File**: `test/integration/test_state_collectors.py`
- **Class**: `TestSamsungNotesStateCollector`
- **Method**: `test_create_note_success`
- **Error**: `assert False is True` — the `result["verified"]` was `False` but the test expected `True`

### 5.3 Reading Tracebacks

```
test/integration/test_state_collectors.py:72: in test_create_note_success
    assert result["verified"] is True
E   assert False is True
```

**Line-by-line:**
1. `test/integration/test_state_collectors.py:72:` — the failure is at line 72 of the test file
2. `assert result["verified"] is True` — this is the assertion that failed
3. `E   assert False is True` — `result["verified"]` was `False`, expected `True`

### 5.4 Common Failure Patterns & How to Debug

#### Pattern 1: `ImportError: No module named ...`

```
E   ModuleNotFoundError: No module named 'agent_testers.apps.my_new_app.state_collector'
```

**Cause**: The state collector module doesn't exist yet (expected in TDD RED phase), or the module path is wrong.

**Fix**: Create the module file, or fix the import path.

#### Pattern 2: `AttributeError: 'MockXxxItem' object has no attribute 'yyy'`

```
E   AttributeError: 'MockEventItem' object has no attribute 'start_time'
```

**Cause**: The mock data model is missing a field that the real XRClaw data model has. The state collector code accesses `event.start_time` but the mock doesn't provide it.

**Fix**: Add the missing attribute to the mock data class in `test/mocks/mock_xrclaw.py`:

```python
class MockEventItem:
    def __init__(self, id, title, description="", location="",
                 start_time="", end_time="", all_day=False):  # ← add start_time
        self.start_time = start_time
```

#### Pattern 3: `AssertionError: assert 'samsungvoicerecorder' in {...}`

```
E   AssertionError: assert 'samsungvoicerecorder' in {'device': ..., 'clockalarm': ...}
```

**Cause**: The test uses the wrong app key. The registered key is `voicerecorder`, not `samsungvoicerecorder`.

**Fix**: Check the actual registered keys:

```bash
python -c "from agent_testers.apps import STATE_COLLECTORS; print(sorted(STATE_COLLECTORS.keys()))"
```

Then fix the test to use the correct key.

#### Pattern 4: `assert False is True` in state collector tests

```
E   assert False is True
```

**Cause**: The state collector's `verify()` returned `verified=False`. This usually means the `gt_answer` doesn't match the device state in the way the collector expects.

**Debug steps**:

1. Print the full result to see the analysis:
```python
result = verify(dm, "samsungnote", "create", ...)
print(f"verified: {result['verified']}")
print(f"analysis: {result['analysis']}")
```

2. Check what `extract_keyword()` returns:
```python
from agent_testers.apps.helpers import extract_keyword
print(extract_keyword(gt_answer))
```

3. Check what `content_overlaps()` returns:
```python
from agent_testers.apps.helpers import content_overlaps
print(content_overlaps(gt_answer, note.content))
```

**Common root causes**:
- **Quoted words in gt_answer**: `content_overlaps()` splits on whitespace, so `'milk` ≠ `milk`. Remove quotes from gt_answer in tests.
- **Time format mismatch**: Alarm collector formats time as `07:00` (zero-padded), but test uses `7:00`.
- **Keyword extraction returns too many words**: `extract_keyword()` strips stopwords but may return multi-word keywords that don't match the title.

#### Pattern 5: `KeyError: 'rating'`

```
E   KeyError: 'rating'
```

**Cause**: The `verify()` function returned a dict without the `rating` key. This happens when the state collector returns an error or unsupported result.

**Fix**: Check the state collector's return value — it should always include `rating`, `verified`, `analysis`, `method`, `actual_state`, and `expected` keys. Use the `result()` helper from `helpers.py`.

#### Pattern 6: Tests pass locally but fail in CI

**Cause**: Usually a path issue — tests use relative paths that work from the project root but not from other directories.

**Fix**: Always run tests from the project root:
```bash
cd /home/shouvik/Ashutosh/Projects/GeminiEvaluation/maire
python -m pytest test/ -v
```

### 5.5 Using `--tb=long` for Detailed Tracebacks

```bash
python -m pytest test/integration/test_state_collectors.py::TestSamsungNotesStateCollector::test_create_note_success -v --tb=long
```

This shows the full traceback with local variables, making it easier to see what values were passed.

### 5.6 Using `--tb=short` for Concise Output

```bash
python -m pytest test/ --tb=short
```

Shows just the assertion line and error — good for quick scanning.

---

## 6. Conventions & Best Practices

### 6.1 Naming Conventions

| Item | Convention | Example |
|------|-----------|---------|
| Test files | `test_*.py` | `test_state_collectors.py` |
| Test classes | `Test*` | `TestSamsungNotesStateCollector` |
| Test methods | `test_*` | `test_create_note_success` |
| Mock files | `mock_*.py` | `mock_xrclaw.py` |
| Mock classes | `Mock*` | `MockXRClawDeviceManager` |
| Fixture files | `*.json` | `notes.json` |

### 6.2 Test Structure (AAA Pattern)

```python
def test_create_note_success(self, dm):
    # ── Arrange ──
    pre = capture_pre(dm)
    dm.notes.create_note("Shopping List", "milk and eggs")

    # ── Act ──
    result = verify(dm, "samsungnote", "create", "...", "...", pre)

    # ── Assert ──
    assert result["verified"] is True
    assert result["rating"] == 5
```

### 6.3 What to Test

For each state collector, test:
- **Happy path**: Action succeeds, state changes correctly → `verified=True, rating=5`
- **Failure path**: Action doesn't happen → `verified=False, rating=0`
- **Edge cases**: No pre-state, empty device, partial match
- **Launch mode**: App in foreground
- **Read mode**: Item exists with matching content

For each judge, test:
- **Correct answer**: High score
- **Wrong answer**: Low score
- **Partial match**: Intermediate score
- **Edge cases**: Empty response, very long response

### 6.4 Mock Object Rules

1. **Mirror the real API exactly** — same method names, same parameter names, same return types
2. **All state is in-memory** — no file I/O, no network calls
3. **Use `to_dict()` on all data items** — state collectors call this
4. **Add new fields when the real API adds them** — if XRClaw adds a field, the mock must follow
5. **Fixtures load from JSON** — for complex pre-state scenarios

### 6.5 When to Add a New Mock

Add a new mock when:
- A new XRClaw accessor is introduced (e.g., `dm.contacts`)
- A new external service is integrated (e.g., a new transcription provider)
- A new device manager type is added (e.g., a new glasses model)

### 6.6 Test File Organization

- **Unit tests** go in `test/unit/` — one file per module being tested
- **Integration tests** go in `test/integration/` — one file per subsystem
- **Mock objects** go in `test/mocks/` — one file per mock type
- **Fixtures** go in `test/fixtures/` — JSON files for complex state

---

## Appendix: Quick Reference

### Running tests by category

```bash
# Unit tests only
python -m pytest test/unit/ -v

# Integration tests only
python -m pytest test/integration/ -v

# Everything
python -m pytest test/ -v

# Just the state collector matrix
python -m pytest test/integration/test_state_collectors.py -v

# Just the deterministic judge
python -m pytest test/unit/test_deterministic_judge.py -v
```


