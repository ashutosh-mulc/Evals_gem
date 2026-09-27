# Maire Apps Configuration

This directory contains the **app-specific configurations, state collectors, and judge prompts** for all applications supported by the Maire evaluation framework. Each app folder encapsulates everything needed to evaluate AI agent interactions with that specific application.

## Overview

The `maire/apps/` directory structure provides:
- **State Collection**: Capture app state before/after agent actions
- **Judge Prompts**: LLM prompts for evaluating task completion
- **Device Manager Integration**: XRClaw-based device interaction
- **Verification Logic**: Mode-specific pass/fail criteria

## Directory Structure

```
maire/apps/
├── __init__.py              # App registry and config exports
├── base.py                  # Base classes for app configurations
├── helpers.py               # Shared utility functions
├── judge_helpers.py         # Judge prompt templates
├── registry.py              # App registration system
├── precondition_helpers.py  # Precondition checking utilities
├── README.md                # This documentation
│
├── device/                  # Device-level operations (WiFi, Bluetooth, etc.)
│   ├── config.json
│   ├── prompt.json
│   ├── state_collector.py
│   └── judge_rules.py
│
├── samsung_notes/           # Example: Samsung Notes app
│   ├── config.json          # App metadata and task definitions
│   ├── prompt.json          # Judge prompt for evaluation
│   └── state_collector.py   # State capture and verification logic
│
├── google_calendar/         # Example: Google Calendar app
│   ├── config.json
│   ├── prompt.json
│   └── state_collector.py
│
└── ... (other apps)
```

## Core Components

### 1. State Collector (`state_collector.py`)

The state collector captures app state before and after agent actions. Each state collector must implement:

```python
# App identifiers
APP_KEYS = ("samsungnote",)          # App key used in questions
ACCESSOR = "notes"                    # Device manager accessor
PACKAGE_NAME = "com.samsung.android.app.notes"

def capture_pre(dm) -> dict:
    """
    Snapshot current app state BEFORE the agent acts.
    
    Args:
        dm: Device manager instance (e.g., JinjuGeminiManager)
    
    Returns:
        dict with state data (e.g., {"notes": [...], "count": 2})
    """
    notes = dm.notes.find_notes()
    return {"notes": [n.to_dict() for n in notes], "count": len(notes)}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """
    Verify app state AFTER the agent has acted.
    
    Args:
        dm: Device manager instance
        app_key: App identifier (e.g., "samsungnote")
        mode: Evaluation mode ("create", "modify", "delete", "launch", "read")
        question: User query that was executed
        gt_answer: Ground truth answer
        pre_state: State snapshot from capture_pre() (optional)
    
    Returns:
        dict with verification results including "actual_state" for judge
    """
    # Mode-specific verification logic
    if mode == "launch":
        foreground_pkg = dm.get_foreground_app()
        verified = PACKAGE_NAME in (foreground_pkg or "")
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)
    
    # For create/modify/delete/read modes
    notes = dm.notes.find_notes()
    actual_state = {"notes": [n.to_dict() for n in notes], "count": len(notes)}
    
    # ... verification logic ...
    
    return result(app_key, verified, rating, analysis, actual_state, gt_answer)
```

### 2. Judge Prompts (`prompt.json`)

Judge prompts define how the LLM evaluates task completion. They use placeholders that get replaced at runtime:

```json
{
  "prompt": "Use the BASE_JUDGE_TEMPLATE from judge_helpers.py.\n\nTASK TYPES FOR SAMSUNG NOTES:\n- LAUNCH: Verify screenshot shows Samsung Notes app.\n- CREATE: Verify expected note exists in <app_state> with matching title and content.\n- MODIFY: Verify note exists in <app_state> AND contains new/appended text.\n- DELETE: Verify expected note is ABSENT from <app_state>.\n- READ: Compare AI's spoken response against note content in <app_state>.\n\nReturn: { \"question\": \"...\", \"analysis\": \"...\", \"rating\": 0-5 }"
}
```

**Available Placeholders:**
| Placeholder | Replaced With |
|-------------|---------------|
| `<<question>>` | User query |
| `<<ai_response>>` | Agent's spoken response |
| `<<gt_answer>>` | Ground truth answer |
| `<<category>>` | Question type |
| `<<app_state>>` | JSON dump of app state from state collector |
| `<<image_captured>>` | Camera flag (True/False) |
| `<<video_captured>>` | Video flag (True/False) |

### 3. App Configuration (`config.json`)

Defines app metadata, activities, and task definitions:

```json
{
  "app_key": "samsungnote",
  "package_name": "com.samsung.android.app.notes",
  "activity_name": "com.samsung.android.app.notes/.memolist.MemoListActivity",
  "tasks": {
    "create": [
      ["open_app"],
      ["click", 100, 200],
      ...
    ],
    "modify": [...],
    "delete": [...]
  }
}
```

## How State Collection Works (Flow)

### 1. Pre-State Capture (Before Agent Acts)

```python
# In device manager (e.g., jinju_gemini_manager.py)
from apps.samsung_notes import state_collector

# Capture state before executing the task
pre_state = state_collector.capture_pre(self._dm)
# Returns: {"notes": [{"id": "1", "title": "Meeting", ...}], "count": 1}
```

### 2. Agent Executes Task

The agent performs the task (opens app, creates note, etc.)

### 3. Post-State Verification (After Agent Acts)

```python
# Verify state after task completion
verification_result = state_collector.verify(
    dm=self._dm,
    app_key="samsungnote",
    mode="create",
    question=user_query,
    gt_answer=ground_truth,
    pre_state=pre_state
)
# Returns: {"actual_state": {...}, "verified": True, "rating": 5, "analysis": "..."}
```

### 4. State Injection into Judge Prompt

```python
# In response_scorer.py → _inject_placeholders()
metadata = eval_json.get("metadata", {})
collected_state = metadata.get("app_state")  # From verification_result

if collected_state:
    actual_state = collected_state.get("actual_state", {})
    app_state_str = json.dumps(actual_state, indent=2)
    prompt = prompt.replace("<<app_state>>", app_state_str)
```

### 5. Judge Evaluation

The VLM judge receives the prompt with injected state and evaluates:
- Did the agent complete the task correctly?
- What evidence supports this conclusion?
- Rating: 0-5

## Usage in Device Managers

The state collectors are used in device managers like `JinjuGeminiManager`:

```python
# maire/agent_testers/device_managers/jinju_gemini_manager.py

class JinjuGeminiManager(DeviceManagerTemplate):
    
    def _collect_app_state(self, app_key, mode, question, gt_answer, pre_state):
        """Collect and verify app state after task execution."""
        from apps import get_state_collector
        
        state_collector = get_state_collector(app_key)
        if state_collector is None:
            return None
        
        result = state_collector.verify(
            dm=self._dm,
            app_key=app_key,
            mode=mode,
            question=question,
            gt_answer=gt_answer,
            pre_state=pre_state
        )
        
        # Store in metadata for judge injection
        self._eval_metadata["app_state"] = result
        return result
```

## Adding a New App

### Step 1: Create App Directory

```bash
mkdir -p maire/apps/my_new_app
```

### Step 2: Create `config.json`

```json
{
  "app_key": "mynewapp",
  "package_name": "com.example.myapp",
  "activity_name": "com.example.myapp/.MainActivity",
  "tasks": {
    "create": [
      ["open_app"],
      ["click", 100, 200],
      ["wait", 2]
    ],
    "read": [
      ["open_app"],
      ["screenshot"]
    ]
  }
}
```

### Step 3: Create `state_collector.py`

```python
"""State collector for My New App."""

from __future__ import annotations

from ..helpers import (
    extract_keyword,
    pre_items_by_id,
    new_or_changed,
    result,
)

APP_KEYS = ("mynewapp",)
ACCESSOR = "myapp"  # Must match device manager accessor
PACKAGE_NAME = "com.example.myapp"


def capture_pre(dm) -> dict:
    """Snapshot current app state before the agent acts."""
    items = dm.myapp.find_items()
    return {"items": [i.to_dict() for i in items], "count": len(items)}


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify app state after the agent has acted."""
    
    # Launch mode: verify app is in foreground
    if mode == "launch":
        foreground_pkg = dm.get_foreground_app()
        actual_state = {"foreground_package": foreground_pkg}
        verified = PACKAGE_NAME in (foreground_pkg or "")
        rating = 5 if verified else 0
        analysis = f"Launch verification: {'App is in foreground.' if verified else 'App NOT in foreground.'}"
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)
    
    # Read mode: return all items for LLM judge
    if mode == "read":
        items = dm.myapp.find_items()
        actual_state = {"items": [i.to_dict() for i in items], "count": len(items)}
        verified = True
        rating = 5
        analysis = f"Read verification: {len(items)} items found."
        return result(app_key, verified, rating, analysis, actual_state, gt_answer)
    
    # Create/Modify/Delete modes
    items = dm.myapp.find_items()
    pre_by_id = pre_items_by_id(pre_state, "items")
    
    if mode == "delete":
        # Check for deleted items
        post_ids = {i.id for i in items}
        deleted = [v for eid, v in pre_by_id.items() if eid not in post_ids]
        actual_state = {"deleted": deleted, "remaining": len(items)}
        verified = len(deleted) > 0
        rating = 5 if verified else 0
        analysis = f"Delete verification: {len(deleted)} items deleted."
    
    elif mode == "modify":
        # Check for modified items
        changed = new_or_changed(items, pre_by_id, ("title", "content"))
        actual_state = {"changed": [c.to_dict() for c in changed], "count": len(changed)}
        verified = len(changed) > 0
        rating = 5 if verified else 0
        analysis = f"Modify verification: {len(changed)} items modified."
    
    else:  # create
        # Check for new items
        pre_ids = set(pre_by_id.keys()) if pre_by_id else set()
        new_items = [i for i in items if i.id not in pre_ids]
        actual_state = {"new": [n.to_dict() for n in new_items], "count": len(new_items)}
        verified = len(new_items) > 0
        rating = 5 if verified else 0
        analysis = f"Create verification: {len(new_items)} new items created."
    
    return result(app_key, verified, rating, analysis, actual_state, gt_answer)
```

### Step 4: Create `prompt.json`

```json
{
  "prompt": "You are evaluating whether the AI agent successfully completed a task in My New App.\n\nTASK TYPES:\n- LAUNCH: Verify the app screenshot shows My New App interface.\n- CREATE: Verify new item exists in <app_state> with expected content.\n- MODIFY: Verify item in <app_state> was changed from pre-state.\n- DELETE: Verify item is ABSENT from <app_state>.\n- READ: Compare AI's spoken response against item content in <app_state>.\n\nReturn: { \"question\": \"...\", \"analysis\": \"...\", \"rating\": 0-5 }"
}
```

### Step 5: Create `xrclaw_accessor.py` (Optional)

If your app needs custom XRClaw device manager integration:

```python
"""XRClaw accessor for My New App."""

from claw_engine import XRClawEngine

class MyNewAppAccessor:
    def __init__(self, engine: XRClawEngine):
        self.engine = engine
    
    def find_items(self) -> list:
        """Find all items in the app."""
        # Use XRClaw content provider or UI automation
        pass
    
    def get_items(self, ids: list) -> list:
        """Get specific items by ID."""
        pass
```

### Step 6: Register the App

Add to `maire/apps/registry.py`:

```python
from .my_new_app import state_collector

# Register app key
APP_KEYS.extend(state_collector.APP_KEYS)
```

## Updating Existing Apps

To update an existing app configuration:

1. **Modify `config.json`**: Update activities, package names, or task definitions
2. **Update `state_collector.py`**: Change what state is captured or how verification works
3. **Update `prompt.json`**: Refine judge prompts for better evaluation
4. **Test**: Run evaluation to verify changes work correctly

## Helper Functions

### From `helpers.py`

| Function | Description |
|----------|-------------|
| `extract_keyword(text)` | Extract primary keyword from text |
| `extract_content_from_gt(gt_answer)` | Extract content portion from ground truth |
| `content_overlaps(gt_answer, content)` | Check if content matches expected |
| `pre_items_by_id(pre_state, key)` | Get pre-state items indexed by ID |
| `new_or_changed(post_items, pre_by_id, fields)` | Find new or modified items |
| `result(app_name, verified, rating, analysis, actual_state, gt_answer)` | Create verification result dict |

### From `judge_helpers.py`

| Template | Description |
|----------|-------------|
| `BASE_JUDGE_TEMPLATE` | Base template for all judge prompts |
| `qa_prompt` | Generic QA task prompts |
| `app_eval_prompt` | App evaluation prompts |
| `vqa_prompt` | Visual QA prompts |
| `hallucination_vqa_prompt` | Hallucination detection prompts |

## Example: Samsung Notes Complete Flow

```
User Query: "Create a note titled 'Meeting' with content 'Discuss project timeline'"

1. PRE-STATE CAPTURE
   pre_state = state_collector.capture_pre(dm)
   → {"notes": [], "count": 0}

2. AGENT EXECUTES TASK
   - Opens Samsung Notes
   - Creates new note
   - Enters title "Meeting"
   - Enters content "Discuss project timeline"
   - Saves note

3. POST-STATE VERIFICATION
   result = state_collector.verify(dm, "samsungnote", "create", question, gt_answer, pre_state)
   → {
       "actual_state": {"notes": [{"title": "Meeting", "content": "Discuss project timeline"}], "count": 1},
       "verified": True,
       "rating": 5,
       "analysis": "New note 'Meeting' found with matching content."
     }

4. STATE INJECTION
   prompt = prompt.replace("<<app_state>>", json.dumps(result["actual_state"]))

5. JUDGE EVALUATION
   VLM receives prompt with app_state and returns:
   → {"question": "...", "analysis": "Note created successfully", "rating": 5}
```

## Testing Your App Configuration

After adding or updating an app:

```bash
# Run a single test
python maire/scripts/run_test_case.py --app mynewapp --mode create

# Run all tests for an app
python maire/scripts/run_test_case.py --app mynewapp

# Verify state collector works
python -c "
from apps.my_new_app import state_collector
from agent_testers.device_managers.jinju_gemini_manager import JinjuGeminiManager

dm = JinjuGeminiManager(...)
pre = state_collector.capture_pre(dm)
print(f'Pre-state: {pre}')
"
```

## App Evaluation Preconditions

Before each evaluation query, the framework sets up device state so the AI agent has something to act on. 
For example, a "delete note" query needs a note to already exist; a "pause music" query needs music to be playing.

The `PreconditionManager` runs before the agent is invoked. It parses the question type, force-stops the app for launch actions, and dispatches to the app's `precondition.py` module if one exists. Apps without a precondition module are skipped — their state must be set up manually.

**Common patterns across all automated apps:**
- **Launch** actions always clear existing state (notes, reminders, events, alarms, etc.) so no stale data from previous runs causes false results. The app is also force-stopped via ADB.
- **Delete/modify/read** actions create a pre-existing entity (note, reminder, event, alarm) with a title or time extracted from the ground truth answer.


### Apps with Automated Preconditions

#### Device (System-Level Queries)

- **Package:** N/A (device-level) · **App key:** `device`
- **Features:** volume, datetime, battery, DND, mediacontrol, notification

| Feature | Action | Precondition |
|---------|--------|-------------|
| DND | `on` | DND must be off |
| DND | `off` | DND must be on |
| Volume | `up`, `uprelative` | Volume must be low |
| Volume | `down`, `downrelative` | Volume must be high |
| Volume | `mute` | Volume must be unmuted |
| Volume | `unmute` | Volume must be muted |
| Volume | `set` | None needed |
| MediaControl | `pause`, `skip`, `previous`, `like`, `dislike`, `seek`, `seekrelative` | Media must be playing |
| MediaControl | `play`, `resume`, `replay` | Media must be paused |
| Notification | `read`, `auto` | A notification must exist |
| Notification | `notread` | Notification panel must be empty |
| DateTime | `time`, `date` | None needed |
| Battery | `glasses`, `phone`, `companion` | None needed |

---

#### Samsung Notes

- **Package:** `com.samsung.android.app.notes` · **App key:** `samsungnote`

| Action | Precondition |
|--------|-------------|
| `launch` | All existing notes cleared |
| `create`, `visualcreate` | None needed |
| `delete` | A note with matching title must exist |
| `modify` | A note with matching title must exist |
| `read` | A note with matching title must exist |

---

#### Samsung Reminders

- **Package:** `com.samsung.android.app.reminder` · **App key:** `samsungreminder`

| Action | Precondition |
|--------|-------------|
| `launch` | All existing reminders cleared |
| `create` | None needed |
| `delete` | A reminder with matching title must exist |
| `modify` | A reminder with matching title must exist |
| `read` | A reminder with matching title must exist |
| `noread` | A reminder with matching title must exist |

---

#### Samsung Calendar

- **Package:** `com.samsung.android.calendar` · **App key:** `samsungcalendar`

| Action | Precondition |
|--------|-------------|
| `launch` | All existing events cleared (including holidays) |
| `create` | None needed |
| `delete` | An event with matching title must exist |
| `modify` | An event with matching title must exist |
| `read` | An event with matching title must exist |

**Consent audio:** `create`, `modify`, `delete` → play `Yes.wav` (pause 18s, wait 5s).

---

#### Samsung Clock Alarm

- **Package:** `com.sec.android.app.clockpackage` · **App key:** `clockalarm`

| Action | Precondition |
|--------|-------------|
| `launch` | All alarms cleared, stopwatch reset |
| `create` | None needed |
| `delete` | An alarm must exist |
| `modify` | An alarm must exist |
| `disable` | An alarm must exist |
| `read` | An alarm must exist |
| `stop` | An alarm must exist |

---

#### Samsung Clock Stopwatch

- **Package:** `com.sec.android.app.clockpackage` · **App key:** `clockstopwatch`

| Action | Precondition |
|--------|-------------|
| `launch` | All alarms cleared, stopwatch reset |
| `start` | None needed |
| `lap` | Stopwatch must be running |
| `stop` | Stopwatch must be running |
| `reset` | Stopwatch must be running |

---

#### Samsung Clock Timer

- **Package:** `com.sec.android.app.clockpackage` · **App key:** `clocktimer`

| Action | Precondition |
|--------|-------------|
| `launch` | All alarms/timers cleared, stopwatch reset |
| `create` | None needed |
| `modify` | A timer must exist |
| `pause` | A timer must exist |
| `restart` | A timer must exist |
| `stop` | A timer must exist |
| `read` | A timer must exist |

---

#### Samsung Camera

- **Package:** `com.sec.android.app.camera` · **App key:** `samsungcamera`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `click` | None needed |
| `check` | None needed (screenshot captured via config) |
| `videostart` | None needed  (Not supported reliably) |
| `videostop` | None needed  (Not supported reliably) |
| `exit` | Camera app must be in foreground (automated) |


---

#### Samsung Voice Recorder

- **Package:** `com.sec.android.app.voicenote` · **App key:** `samsungvoicerecorder`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |


---


### Apps Without Automated Preconditions

These apps do not have a `precondition.py` module. The framework skips precondition setup for them — required state must be set up manually before evaluation. As this requires lot of manual effort, currently we rely on the sequential execution of query such that previously executed queries could setup the precondition for next query but this is unreliable if a query fails.


---

#### Samsung Call 

- **Package:** `com.samsung.android.dialer` · **App key:** `samsungcall`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `send` | A contact matching the name must exist (manual) |
| `videostart` | A contact matching the name must exist (manual) |
| `disambiguation` | Multiple contacts with similar names must exist (manual) |
| `notsend` | Contact must not exist in contacts (manual) |



**Manual setup:** Add the following contacts before evaluation:
- Add multiple contacts named "Anne" with different number — used for disambiguation tests.
- Add a single contact named "John" — used for call/send tests.
- Ensure no contact named "Lily" exists — used for notsend tests.


---

#### Samsung Message

- **Package:** `com.samsung.android.messaging` · **App key:** `samsungmessage`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `read` | An existing message thread must exist (manual) |
| `send` | A contact matching the recipient must exist (manual) |
| `visualsend` | None needed (manual — no precondition required) |
| `draft` | An existing draft message must exist (manual) |
| `disambiguation` | Multiple contacts with similar names must exist (manual) |
| `notsend` | Contact must not exist in contacts (manual) |

**Consent audio:** `send`, `messagesend`, `messagereply`, `callsend` → `Yes.wav` (pause 18s, wait 5s). `draft` → `edit_message.wav` (pause 18s, wait 5s) then `Yes.wav` (pause 17s, wait 5s).

**Manual setup:** Add the following contacts  and create a chat with these contacts:
- Add a single contact named 'Maria'
- Add multiple contacts named 'Anne'
- Make sure there is no chat/contact named 'Lily'


---

#### Thirdparty Spotify

- **Package:** `com.spotify.music` · **App key:** `spotify`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `play` | Spotify must be logged in (manual) |
| `playlistplay` | A playlist must exist; Spotify logged in (manual) |
| `podcastnext` | A podcast must be actively playing(Currently the evaluation asks to play a podcast rather than the next episode); Spotify logged in (manual) |

**Manual setup:** 
 - Spotify must be logged in and verified before any non-launch action. 
 - Add a playlist titled "Week End". 
 - Add some songs to your favourites. 
 - Premium subscription required to avoid automation break because of advertisements

---

#### Thirdparty WhatsApp

- **Package:** `com.whatsapp` · **App key:** `whatsapp`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `call` | A contact with WhatsApp calling must exist (manual) |
| `messagesend` | A contact and chat thread must exist (manual) |
| `messagereply` | An existing chat thread must exist (manual) |
| `disambiguation` | Multiple contacts with similar names must exist (manual) |
| `notsend` | Contact must not exist in contacts (manual) |
| `callsend` | A contact with WhatsApp calling must exist (manual) |
| `send` | A contact and chat thread must exist (manual) |

**Consent audio:** `messagesend`, `messagereply`, `send`, `callsend` → `Yes.wav` (pause 18s, wait 5s).

**Manual setup:** 

- WhatsApp must be logged in and verified with a phone number. 
- Before running any query, sync contacts: open WhatsApp → tap new chat → tap ellipsis (⋮) → tap Refresh. 
- For `messagesend`/`send`/`messagereply`, a contact and/or existing chat thread must be pre-seeded for contact named 'Max'. 
- For `call`/`callsend`, a contact with WhatsApp calling capability must exist. 
- For `disambiguation`, multiple contacts names 'Anne' must be pre-seeded.


---

#### Google Translate  

- **Package:** `com.google.android.apps.translate` · **App key:** `googletranslate`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `start` | None needed |


**Manual setup:** No manual precondition required.


---


#### Google YouTube Music  (Automation not Reliable)

- **Package:** `com.google.android.apps.youtube.music` · **App key:** `googleyoutubemusic`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `play` | None needed |
| `playlistcreate` | None needed |
| `playlistplay` | A playlist must exist (manual) |
| `podcastnext` | A podcast must be actively playing (manual) |
| `create` | None needed |
| `visualcreate` | None needed |
| `playlistvisualcreate` | None needed |
| `modify` | Matching playlist must exist (manual) |
| `delete` | Matching playlist must exist (manual) |



**Manual setup:** 
- App must be logged in. 
- Add a playlist titled "Week End". Add some songs to your favourites. 
- Premium subscription required to avoid automation break because of advertisements


---

#### Google Calendar  (Automation not reliable)

- **Package:** `com.google.android.calendar` · **App key:** `googlecalendar`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `create` | Clean calendar for that day (manual) |
| `modify` | Matching event must exist (manual) |
| `delete` | Matching event must exist (manual) |
| `read` | Matching event must exist (manual) |

**Consent audio:** `create`, `modify`, `delete` → `Yes.wav` (pause 18s, wait 5s).

**Manual setup:** 
- Remove all existing events on the particular day being tested before evaluation. 
- Add only a single event which is a meeting event, (eg. Meeting with Max) - [Without this automation might work because of the sequential nature of evaluation, if the previous query(_Meeing with Jane_) of event addition succeeds, context is already set] 

---


#### Google Keep (Automation not reliable)

- **Package:** `com.google.android.keep` · **App key:** `googlekeep`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `create` | Clean state (no duplicate note) |
| `visualcreate` | Clean state; image context provided |
| `modify` | Matching note must exist (manual) |
| `delete` | Matching note must exist (manual) |
| `read` | Matching note must exist (manual) |


**Manual setup:** 
- Create a note titled "Shopping List" beforehand.

---

#### Google Mail  (Not supported)

- **Package:** `com.google.android.gm` · **App key:** `googlemail`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `search` | Emails matching the search query must exist (manual) |
| `thread_read` | An email thread must exist (manual) |



**Manual setup:** For `search`, ensure emails matching the query exist in the inbox. For `thread_read`, an email thread must be present.

---

#### Google Maps (Not Supported)

- **Package:** `com.google.android.apps.maps` · **App key:** `googlemaps`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `query` | None needed |
| `eta` | None needed |
| `startnavigate` | None needed |
| `stopnavigate` | Navigation must be actively running (manual) |
| `addstop` | Navigation must be running with an active route (manual) |
| `querynavigate` | Navigation must be actively running (manual) |



**Manual setup:** For `stopnavigate`/`addstop`/`querynavigate`, navigation must be actively running before the query.

---

#### Google Tasks  (Automation not reliable)

- **Package:** `com.google.android.apps.tasks` · **App key:** `googletasks`

| Action | Required Precondition |
|--------|----------------------|
| `launch` | App force-stopped (automated) |
| `create` | Clean state (no duplicate task) |
| `modify` | Matching task must exist (dependent on previous query) |
| `delete` | Matching task must exist (dependent on previous query) |



**Manual setup:** 
 - No manual setup required



---
