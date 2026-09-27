# Cline Hooks for Maire Project

This document describes the automated testing hooks that run when Cline makes code changes.

## Overview

Hooks are bash scripts located in `.clinerules/hooks/` that automatically run tests when critical files are modified. They help catch bugs early by running targeted tests before and after file changes.

## Hook Structure

```
maire/.clinerules/
└── hooks/
    ├── PreToolUse          # Runs BEFORE file changes
    ├── PostToolUse         # Runs AFTER file changes
    ├── hook_history.jsonl  # Log of all hook executions
    └── lib/
        ├── run_tests.py    # Test runner helper
        └── check_prompt.py # Prompt validation helper
```

## Critical File Paths

The following files trigger automated testing when modified:

| Path Pattern | Tests Run |
|--------------|-----------|
| `utils/adb_client.py` | `pytest maire/test/test_adb_client.py` |
| `judge_worker/*.py` | `pytest maire/test/test_response_scorer_scoring.py` |
| `agent_testers/device_managers/` | Device manager tests |
| `apps/*/config.py` | Config structure validation |
| `apps/*/prompt.json` | JSON + BASE_JUDGE_TEMPLATE check |

## Hook Behavior

### PreToolUse (Blocking)

Runs **before** file changes are applied:

1. Detects if modified file is in critical path
2. Runs targeted tests on the **current** (pre-change) code
3. If tests **fail**: blocks the change with error message
4. If tests **pass**: allows the change

**Purpose:** Prevent breaking changes from being made to critical files.

### PostToolUse (Reporting)

Runs **after** file changes are applied:

1. Detects if modified file is in critical path
2. Runs targeted tests on the **new** (post-change) code
3. Logs results to `hook_history.jsonl`
4. Reports results but does NOT block

**Purpose:** Validate changes and maintain audit trail.

## Hook History

All hook executions are logged to `.clinerules/hooks/hook_history.jsonl`:

```json
{
  "timestamp": "2026-09-10T12:00:00+05:30",
  "hook": "PostToolUse",
  "file": "utils/adb_client.py",
  "cancel": false,
  "message": "All tests passed"
}
```

## Viewing Hook Logs

```bash
# View recent hook executions
tail -20 maire/.clinerules/hooks/hook_history.jsonl | jq .

# View failed hook executions
grep '"cancel": true' maire/.clinerules/hooks/hook_history.jsonl | jq .

# Count hooks by file
cat maire/.clinerules/hooks/hook_history.jsonl | jq -r '.file' | sort | uniq -c
```

## Manual Testing

Test hooks manually:

```bash
# Test PreToolUse hook
echo '{"preToolUse": {"toolName": "write_to_file", "parameters": {"path": "utils/adb_client.py"}}}' | ./maire/.clinerules/hooks/PreToolUse

# Test PostToolUse hook
echo '{"postToolUse": {"toolName": "write_to_file", "success": true, "parameters": {"path": "utils/adb_client.py"}}}' | ./maire/.clinerules/hooks/PostToolUse
```

## Enabling/Disabling Hooks

Hooks are enabled automatically when Cline SR is configured to use them.

To temporarily disable:
```bash
chmod -x maire/.clinerules/hooks/PreToolUse
chmod -x maire/.clinerules/hooks/PostToolUse
```

To re-enable:
```bash
chmod +x maire/.clinerules/hooks/PreToolUse
chmod +x maire/.clinerules/hooks/PostToolUse
```

## Adding New Critical Paths

Edit `maire/.clinerules/hooks/lib/run_tests.py` and add entries to `CRITICAL_PATHS`:

```python
CRITICAL_PATHS = {
    "your/new/path.py": {
        "test": "pytest maire/test/your_test.py -v",
        "description": "Description of what this tests"
    },
    # ... existing entries
}
```

## Troubleshooting

### Hook not running?

1. Check executable permission: `ls -la maire/.clinerules/hooks/`
2. Check Cline settings: Hooks must be enabled in Cline SR settings
3. Check file path: Only critical paths trigger tests

### Tests timing out?

Default timeout is 120 seconds per test. Increase in `run_tests.py`:
```python
timeout=120  # Change this value
```

### False positives?

If a valid change is blocked:
1. Check the test output in the error message
2. Fix the underlying issue OR
3. Temporarily disable hook, make change, re-enable hook

## Related Documentation

- [Cline Hooks Documentation](../../Cline/cline.wiki/Hooks(Eng).md)
- [Test Infrastructure](../test/README.md)
- [Run Batch Script](../scripts/run_batch.py)
