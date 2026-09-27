# MAIRE Project - TODO List

This document tracks all pending, planned, and in-progress tasks for the MAIRE evaluation framework.

---

## �� High Priority Tasks


### 1. Early Stop Response Recording (SUPERSEDED)
**Status:** `SUPERSEDED` by `agent_testers/conversation.py`: Gemini Live agents now stop on the app's own
`#CM#` turn events (`agent_end` / `idle`) instead of polling `media_session`. Non-Gemini agents still use the
fixed `record_duration`. The design below is kept for reference only.  
**Priority:** High  
**Related Files:** See `EARLY_STOP_RESPONSE_RECORDING.md`

**Problem:**
Current evaluation records agent responses for fixed 30s regardless of actual response length. This wastes 15-25s per question in dead air after agent finishes speaking.

**Goal:**
Detect when agent finishes speaking live and stop recording early, while falling back safely to fixed-duration when detection signal is unavailable.

**System Topology:**
- **Jinju glasses**: Bluetooth A2DP sink only (no app-level state)
- **Companion S25 phone**: Runs Gemini Live app + TTS, has `MediaSession` state
- **ARAP recorder phone**: Acoustically records via ADB-controlled app

**Design Summary:**

```
Phase 1: Wait for speech to start
  └─ Poll get_media() until playing=True observed
  └─ If ceiling reached without playing=True → fallback to fixed duration

Phase 2: Confirm speech has ended  
  └─ Once playing=True seen, poll for 3 consecutive not-playing readings
  └─ When counter reaches 3 → stop recording early
  └─ Same ceiling applies throughout (safety net)
```

**Key Design Decisions:**
- **Signal source**: Companion phone's `dumpsys media_session` via `DeviceInfo.get_media()`
- **Debounce**: 3 consecutive not-playing polls (sample-count, not wall-clock)
- **Consent turns**: Excluded unconditionally via `get_consent_rules()`
- **Package filtering**: Prefer Gemini/TTS packages, fall back to any session
- **Single elapsed clock**: Shared by both phases (prevents double-wait bug)

**Files to Create/Modify:**

| File | Change Type | Description |
|------|-------------|-------------|
| `agent_testers/response_wait.py` | NEW | `wait_for_response_end()` - two-phase polling/debounce logic |
| `agent_testers/response_recorder.py` | NEW | `record_agent_response()` - shared start/consent/wait/stop sequence |
| `agent_testers/device_managers/device_config.py` | MODIFY | Add `prefer_packages` param to `get_media()` / `_select_active_session()` |
| `agent_testers/agent_tester.py` | MODIFY | Lines 427-451: replace inline sequence with shared call |
| `scripts/run_test_case.py` | MODIFY | `_record_response`: replace inline sequence with shared call |

**Constants (non-configurable):**
- `CONSECUTIVE_SILENCE_SAMPLES_TO_CONFIRM_END = 3`
- `MIN_POLL_INTERVAL_S = 0.3` (adb-hygiene floor)

**Implementation Checklist:**
- [ ] Create `response_wait.py` with `wait_for_response_end()` function
- [ ] Create `response_recorder.py` with `record_agent_response()` function
- [ ] Add `prefer_packages` parameter to `DeviceInfo.get_media()`
- [ ] Update `agent_tester.py` to use shared recorder
- [ ] Add telemetry to `question_info["metadata"]["response_wait"]`
- [ ] Unit test `wait_for_response_end()` with fake `get_media()` sequences
- [ ] Validate total elapsed time in "speech never starts" path equals ceiling (not double)
- [ ] Run shadow-mode validation batch before enabling early-stop gating
- [ ] Compare batch wall-clock time vs prior fixed-duration run
- [ ] Spot-check `cleaned_response_*.mp3` outputs for truncation

**Open Risk (requires validation):**
Gemini Live's TTS session might dip to Buffering/Paused between sentences on multi-sentence answers. If so, natural pause could trigger 3-consecutive-not-playing debounce and truncate real response.

**Mitigation:** Run shadow-mode batch where `wait_for_response_end()` logs decisions but old fixed sleep controls `stop_recording()`. Confirm early-stop would never fire before known-long responses finish.

**Related Documentation:**
- Full design: `EARLY_STOP_RESPONSE_RECORDING.md`

---

### 2. Media Control Like/Dislike Evaluation Automation (IN PROGRESS)
**Status:** `IN_PROGRESS`  
**Priority:** High  

**Scope:**
- **YouTube Music**: Log-based verification (via XRClaw `dm.media` or logcat parsing)
- **Spotify**: VLM-based verification (screenshot analysis)
- **Samsung Music**: Only this support like/dislike songs and playlists

**Implementation Plan:**

#### YouTube Music (Log-Based)
- [X] Add `media_like` and `media_dislike` to `apps/google_youtube_music/config.py::ACTIONS`
- [ ] Implement `capture_pre()` in `apps/google_youtube_music/state_collector.py`
  - Snapshot current like/dislike state via XRClaw `dm.media.get_like_status()` (or equivalent)
- [ ] Implement `verify()` in `apps/google_youtube_music/state_collector.py`
  - Compare pre vs post state
  - Return `result()` with rating based on state change
- [ ] Add handler to `apps/google_youtube_music/judge.py`
  - `_handle_like()` and `_handle_dislike()` methods
- [ ] Register handlers in `judge_worker/deterministic_judge.py::HANDLER_REGISTRY`

#### Spotify (VLM-Based)
- [ ] Add `media_like` and `media_dislike` to `apps/thirdparty_spotify/config.py::ACTIONS`
- [ ] Implement screenshot capture after like/dislike action
- [ ] Add judge prompt to `apps/thirdparty_spotify/prompt.py`
  - Prompt should analyze screenshot for like/dislike indicator (heart icon, etc.)
- [ ] Implement `capture_pre()` and `verify()` in `apps/thirdparty_spotify/state_collector.py`
  - May return `unsupported_result()` if no XRClaw support → falls back to VLM

**Related Files:**
- `apps/google_youtube_music/` - config.py, state_collector.py, judge.py, prompt.py
- `apps/thirdparty_spotify/` - config.py, state_collector.py, judge.py, prompt.py
- `judge_worker/deterministic_judge.py` - HANDLER_REGISTRY

---

### 4. Report Utilities - Pre-state Screenshots (PLANNED)
**Status:** `PLANNED`  
**Priority:** Medium  

**Goal:**
Add pre-state screenshots to reports for all queries, including deterministic judge-based queries that currently skip screenshot capture.

**Current Behavior:**
- Screenshots captured only for VLM-judged queries
- Deterministic judge queries (device queries, some app queries) skip screenshot capture
- Reports lack visual context for many evaluations

**Implementation Plan:**

#### Phase 1: Capture Pre-state Screenshots
- [ ] Add `app_screenshot_pre_path` to metadata for all APP_EVAL_TASK queries
- [ ] Capture screenshot BEFORE agent invokes (in `capture_pre_state()` or `setup()`)
- [ ] Store screenshot in assets folder with eval_id naming

#### Phase 2: Include in Reports
- [ ] Update `automator/report_generator/` to include pre-state screenshots
- [ ] Update HTML report template to show before/after comparison
- [ ] Add toggle to show/hide pre-state images in visual reports

#### Phase 3: Deterministic Judge Integration
- [ ] Ensure deterministic judge queries also capture screenshots
- [ ] Add screenshot to `metadata["app_state_pre"]` structure
- [ ] Update `generate_output_csv()` to reference screenshots if needed

**Related Files:**
- `agent_testers/device_managers/mixins/state_collect.py` - `capture_pre_state()`
- `automator/report_generator/` - Report generation logic
- `automator/templates/` - HTML report templates

---

### 5. Report Generator Code Review Fixes (PENDING)
**Status:** `PLANNED`  
**Priority:** Medium  
**Source:** Code review of report generation utils (2026-09-15) — 13 findings; 3 already fixed, 8 pending below

**Already Fixed (no action needed):**
- ✅ Pre/post-state screenshots read from `meta_info` (paths) instead of top-level base64 lists — template fixed
- ✅ `${preStateScreenshotsHtml}` / `${postStateScreenshotsHtml}` never inserted into final modal HTML — inserted
- ✅ Trailing comma made `screen_bytes` a tuple in `report_writer.py` — fixed; also added `os.path.exists` guards and `app_screenshot` field to `to_dict()`

**Pending Fixes:**

| # | Severity | File | Issue | Fix |
|---|----------|------|-------|-----|
| 1 | �� CRITICAL | `automator/templates/response_visualizer.html` (~line 408) | `loadModalSample()` references `maxRatingFilter` which is only defined inside the `DOMContentLoaded` closure → `ReferenceError` when clicking a sample card | Use the global `maxRating.value` instead, or hoist `maxRatingFilter` to global scope |
| 2 | �� MAJOR | `automator/report_generator/utils/render_summary.py:99` | `error_type == "non_unicode"` is a no-op comparison, not assignment — `not_english` errors counted under wrong key | Change `==` to `=` |
| 3 | �� MAJOR | `automator/report_generator/report_generator.py:87` | `result_json.split("<meta_start>")[1]` raises `IndexError` if tag missing (judge error/malformed response) — crashes entire report generation | Guard: if `len(parts) < 2`, warn, set `error_type = "judge_response_decode_error"`, skip entry |
| 4 | �� MAJOR | `automator/report_generator/report_writer.py:43` | `fetch_all` LIMIT appends `order` string instead of `limit` integer | `params.append(limit)` |
| 5 | �� MAJOR | `automator/report_generator/report_writer.py:160` | Header docs don't match actual fields (`app_screenshot` vs `screen`; missing `pre_state_screenshots`/`post_state_screenshots` docs) | Update header field descriptions to match `to_dict()` output |
| 6 | �� MINOR | `automator/report_generator/report_generator.py:140` | Bare `except:` catches `SystemExit`/`KeyboardInterrupt` | Change to `except Exception:` |
| 7 | �� MINOR | `automator/report_generator/utils/render_summary.py:91` | Debug `print(type(self.records))` left in production | Remove line |
| 8 | �� MINOR | `automator/templates/response_visualizer.html:213` | `errorTypeColors` keys `json_decode_error`/`compute_error` don't match actual error types (`judge_response_decode_error`) | Fix keys to match `error_codes` in `report_generator.py` |

**Deliberately NOT changing:**
- �� `samples[::-1]` reversal in `VQADatasetWriter.write()` — may be intentional ordering; confirm before changing

**Validation after fixes:**
- [ ] Run `py_compile` on modified Python files
- [ ] Regenerate report HTML and verify modal opens without console errors
- [ ] Verify error summary counts group `not_english` under `non_unicode` correctly

---

### 6. Foreground Detection Enriched Dict (COMPLETE)
**Status:** `COMPLETE`  
**Priority:** High  
**Related Files:** `XRClaw/python_automation/adb_helper.py`, `maire/apps/helpers.py`, `maire/apps/*/state_collector.py`

**Problem:**
`AdbHelper.get_current_package()` relied solely on `dumpsys activity activities | grep mResumedActivity`, a field that does not exist on Android 14+ / One UI 7. This caused `get_foreground_app()` to return `None` even when the app was visibly in the foreground, leading to false-negative launch verifications and unnecessary VLM fallback calls.

**Solution:**
1. **Fix 1 — XRClaw `AdbHelper.get_current_package()`**: Removed absent fields (`mResumedActivity`, `mFocusedActivity`). Now tries 4 fields that exist on the target device: `topResumedActivity`, `ResumedActivity`, `mCurrentFocus`, `mFocusedApp`.
2. **Fix 2 — Shared helper in `maire/apps/helpers.py`**: Replaced `get_foreground_package_with_fallback(dm)` (previously returned `Optional[str]`) with an enriched dict returning all 4 fields individually plus a `resolved` key (best-effort single answer, prioritizing activity-level over window-level) and a `source` key (which field was used).
3. **Fix 3 — Dead code removal**: Deleted broken local `_get_foreground_package_with_fallback()` from `google_maps/state_collector.py` (used wrong serial attribute) and dead `_get_foreground_package_with_fallback()` from `xrclaw_state_collector.py` (never called).
4. **State collectors updated**: All 8 collectors (samsung_calendar, samsung_notes, samsung_reminders, samsung_clock_alarm, samsung_clock_timer, samsung_clock_stopwatch, google_calendar, google_maps) now use `fg_info["resolved"]` and pass `{"foreground_info": fg_info}` in `actual_state` for judge transparency.

**Implementation Checklist:**
- [x] Fix `AdbHelper.get_current_package()` — remove absent fields, keep 4 working fields
- [x] Rewrite `get_foreground_package_with_fallback()` in `helpers.py` to return enriched dict
- [x] Update all 8 state collectors to use dict + `fg_info["resolved"]`
- [x] Delete dead `_get_foreground_package_with_fallback()` from `xrclaw_state_collector.py`
- [x] Delete broken local `_get_foreground_package_with_fallback()` from `google_maps/state_collector.py`
- [x] Verify parsing logic with 8 test cases (topResumedActivity, ResumedActivity line filtering, mCurrentFocus with nulls, mFocusedApp with system UI, mFocusedApp with real app, empty output, resolved priority, BinderProxy non-match)
- [x] All 10 files pass Python syntax check

---

## �� Code Structure Refactoring (LONG TERM)

**Status:** `PLANNED` (pending time availability)  
**Priority:** Medium  

**Identified Duplications:**

### 1. Logcat Parsing - DUPLICATED
| Location | Issue |
|----------|-------|
| `utils/log_analyzer.py` | Generalized pluggable analyzer (preferred) |
| `agent_testers/device_managers/mixins/logcat.py` | Duplicates camera detection logic |
| `XRClaw/python_automation/` | XRClaw's own logcat parsing (third-party) |

**Refactoring Plan:**
- [ ] Consolidate all logcat parsing into `utils/log_analyzer.py`
- [ ] Remove duplicate patterns from `logcat.py` mixin
- [ ] Update `logcat.py` to use `LogcatAnalyzer` exclusively

### 2. ADB Operations - SCATTERED
| Location | Issue |
|----------|-------|
| `utils/adb_client.py` | Central ADB client (should be single source) |
| `agent_testers/arap_manager.py` | Direct `subprocess.run(["adb", ...])` |
| `agent_testers/device_managers/mixins/*.py` | Direct ADB calls in each mixin |
| `agent_testers/power_monitor.py` | Direct ADB calls |
| `XRClaw/python_automation/adb_helper.py` | XRClaw's own ADB wrapper |

**Refactoring Plan:**
- [ ] Audit all direct ADB calls across codebase
- [ ] Add missing methods to `AdbClient` class
- [ ] Replace direct `subprocess.run(["adb", ...])` with `AdbClient` methods
- [ ] Document ADB wrapper pattern for future additions

### 3. Screenshot/Image Handling - NEEDS CONSOLIDATION
**Locations:**
- `logcat.py` has `_pull_jinju_query_image()`
- Device managers have their own screenshot capture
- Judge prompts reference screenshots extensively

**Refactoring Plan:**
- [ ] Audit all screenshot capture logic
- [ ] Create centralized `ScreenshotManager` utility
- [ ] Standardize screenshot naming and storage
- [ ] Add screenshot capture to deterministic judge queries

### 4. Media State Analysis - NEEDS CONSOLIDATION
**Locations:**
- `apps/google_youtube_music/` - Media playback state detection
- `agent_testers/device_managers/mixins/device_info.py` - May duplicate

**Refactoring Plan:**
- [ ] Audit media state detection across all apps
- [ ] Create shared `MediaStateAnalyzer` utility
- [ ] Standardize media state result format

### 5. Notification Handling - NEEDS CONSOLIDATION
**Locations:**
- `apps/device/precondition.py` - Notification setup
- XRClaw `dm.notifications` - Notification posting/reading

**Refactoring Plan:**
- [ ] Audit notification handling across all modules
- [ ] Consolidate notification logic into `apps/device/`
- [ ] Remove duplicate notification setup code

### 6. Merge `prompt_notifications.json` into `prompt.json` (PLANNED)
**Status:** `PLANNED`  
**Priority:** Low  

**Problem:**
`apps/device/prompt_notifications.json` is a separate file loaded via a special-case code path in `judge_prompts.py` (lines 109-119). It bypasses the normal app registry-based loading mechanism used by all other prompts. There is no functional reason for it to be separate — it's a legacy artifact.

**Proposed Fix:**
1. Merge the `"prompt"` content from `prompt_notifications.json` into `prompt.json` as a `"notifications"` key
2. Update `judge_prompts.py` to extract the notifications prompt from the already-loaded `_RAW_APP_PROMPTS["device"]` dict instead of loading a separate file
3. Delete `prompt_notifications.json`

**Files to Modify:**
| File | Change |
|------|--------|
| `apps/device/prompt.json` | Add `"notifications"` key with the prompt string |
| `judge_worker/judge_prompts.py` | Replace special-case file loading (lines 109-119) with extraction from `_RAW_APP_PROMPTS["device"]` |
| `apps/device/prompt_notifications.json` | Delete |

**Implementation Checklist:**
- [ ] Add `"notifications"` key to `apps/device/prompt.json`
- [ ] Update `judge_prompts.py` to extract notifications from loaded device prompt data
- [ ] Remove special-case file loading block
- [ ] Delete `apps/device/prompt_notifications.json`
- [ ] Verify notifications prompt still resolves correctly in judge


### 4. Compose UI Debug Screens for Gmail and Google Tasks (PLANNED)
**Status:** `PLANNED`  
**Priority:** High  
**Related Files:** `GoogleCalendarDebugScreen.kt`, `GoogleMailProvider.kt`, `GoogleTasksProvider.kt`, `AppFunctionExecutor.kt`

**Problem:**
Gmail and Google Tasks providers are fully implemented and ADB test receivers are registered, but there are no Compose UI debug screens to exercise them interactively. CLI testing via ADB broadcast receivers is cumbersome. We need debug screens following the existing `GoogleCalendarDebugScreen` pattern.

**Context:**
- Google sign-in is working (`GoogleAuthManager`, `GoogleSignInScreen`)
- `GoogleMailProvider` (423 lines) and `GoogleTasksProvider` (407 lines) are fully implemented
- ADB test receivers registered in manifest and tested
- OAuth scope is `gmail.readonly` only — write operations (send, delete, mark as read) will fail until scope is updated to `gmail.modify`. Tasks scope is full read/write.
- Shared composables available: `AppFunctionCard`, `LabeledTextField`, `ExecuteButton`, `ResultCard`, `DebugScreenContent` in `AppFunctionExecutor.kt`
- `GoogleCalendarDebugScreen.kt` is the reference pattern — uses `rememberCoroutineScope`, `withContext(Dispatchers.IO)`, plain `Column` with `verticalScroll` (not `DebugScreenContent` wrapper)
- `AppFunctionDomain` enum in `AppFunctionCenterScreen.kt` needs 2 new entries; `DomainDebugScreens.kt` needs 2 facade wrappers; `MainActivity.kt` needs 2 `when` branches

**Files to Create:**

| File | Description |
|------|-------------|
| `claw-client/src/main/java/com/samsung/xr/claw/client/ui/appfunctions/domains/GoogleMailDebugScreen.kt` | NEW — Compose debug screen for Gmail provider (list messages, get message detail, search, send, delete, mark as read/unread) |
| `claw-client/src/main/java/com/samsung/xr/claw/client/ui/appfunctions/domains/GoogleTasksDebugScreen.kt` | NEW — Compose debug screen for Google Tasks provider (list task lists, list tasks, get task, create/update/delete task, mark complete) |

**Files to Modify:**

| File | Change |
|------|--------|
| `AppFunctionCenterScreen.kt` | Add `GOOGLE_MAIL` and `GOOGLE_TASKS` entries to `AppFunctionDomain` enum |
| `DomainDebugScreens.kt` | Add 2 facade composable wrappers (`GoogleMailDebugScreen()` and `GoogleTasksDebugScreen()`) that delegate to the real screens |
| `MainActivity.kt` | Add 2 navigation `when` branches for `GOOGLE_MAIL` and `GOOGLE_TASKS` domains |

**Implementation Pattern (from `GoogleCalendarDebugScreen.kt`):**
- Use `rememberCoroutineScope()` for launching coroutines
- Wrap provider calls in `withContext(Dispatchers.IO)`
- Use plain `Column` with `verticalScroll(rememberScrollState())` — NOT `DebugScreenContent` wrapper
- Each provider function gets an `AppFunctionCard` with `LabeledTextField` inputs and `ExecuteButton`
- Results displayed in `ResultCard`
- State: `var result by remember { mutableStateOf("") }` per function

**Implementation Checklist:**
- [ ] Create `GoogleMailDebugScreen.kt` following `GoogleCalendarDebugScreen` pattern
  - [ ] List messages (maxResults input)
  - [ ] Get message detail (messageId input)
  - [ ] Search messages (query input)
  - [ ] Send email (to, subject, body inputs) — **will fail with current `gmail.readonly` scope**
  - [ ] Delete email (messageId input) — **will fail with current scope**
  - [ ] Mark as read (messageId input) — **will fail with current scope**
  - [ ] Mark as unread (messageId input) — **will fail with current scope**
- [ ] Create `GoogleTasksDebugScreen.kt` following `GoogleCalendarDebugScreen` pattern
  - [ ] List task lists (maxResults input)
  - [ ] List tasks (taskListId input, optional showCompleted toggle)
  - [ ] Get task (taskListId, taskId inputs)
  - [ ] Create task (taskListId, title, notes inputs)
  - [ ] Update task (taskListId, taskId, title, notes inputs)
  - [ ] Delete task (taskListId, taskId inputs)
  - [ ] Mark task complete (taskListId, taskId inputs)
- [ ] Add `GOOGLE_MAIL` and `GOOGLE_TASKS` to `AppFunctionDomain` enum in `AppFunctionCenterScreen.kt`
- [ ] Add facade wrappers in `DomainDebugScreens.kt`
- [ ] Add navigation `when` branches in `MainActivity.kt`
- [ ] Build and verify compilation
- [ ] Manually test read operations on device
- [ ] (Optional) Update OAuth scope to `gmail.modify` to enable write operations

**Open Risk:**
Gmail write operations (send, delete, mark as read/unread) will fail at runtime because the current OAuth scope is `gmail.readonly`. To enable these, the scope must be updated to `gmail.modify` in `GoogleAuthManager.kt` and users must re-authenticate. Read operations (list, get, search) will work with the current scope.

---

### 5. Google Keep API Integration — Boilerplate Complete, Testing Pending (IN_PROGRESS)
**Status:** `IN_PROGRESS`
**Priority:** Medium
**Related Files:** `GoogleKeepProvider.kt`, `GoogleKeepTestReceiver.kt`, `GoogleKeepDebugScreen.kt`, `GoogleAuthManager.kt`, `DomainDebugScreens.kt`, `AppFunctionCenterScreen.kt`, `MainActivity.kt`, `AndroidManifest.xml`, `GoogleSignInScreen.kt`

**Problem:**
Google Keep was the next Google integration to add after Gmail, Calendar, and Tasks. Unlike those services, **no `google-api-services-keep` Maven artifact exists** — the Keep API must be accessed via direct REST calls using `google-http-client-gson` (already a project dependency). The boilerplate (provider, test receiver, debug screen, navigation wiring) has been created and the project compiles and builds an APK successfully, but the integration has **not been tested on a device**.

**Context:**
- Google Keep API is **enterprise-only** (Google Workspace accounts); scope: `https://www.googleapis.com/auth/keep`
- OAuth scope added to `GoogleAuthManager.kt`
- Provider uses `GoogleAccountCredential` as `HttpRequestInitializer` with `HttpRequestFactory` for authenticated REST calls to `keep.googleapis.com`
- JSON parsing uses Gson's `JsonParser` / `JsonObject` directly (not google-http-client's `GsonFactory`)
- Pattern followed: Provider → TestReceiver → DebugScreen → enum entry → manifest registration → navigation wiring (same as Gmail/Calendar/Tasks)
- `AppFunctionDomain.GOOGLE_KEEP` enum entry uses `Icons.Filled.StickyNote2`
- Build verified: `./gradlew :claw-client:compileDebugKotlin` and `./gradlew :claw-client:assembleDebug` both succeed

**Files Created:**

| File | Description |
|------|-------------|
| `claw-client/.../google/GoogleKeepProvider.kt` | NEW — REST client with data classes (`NoteInfo`, `AttachmentInfo`, `PermissionInfo`) and CRUD methods (create/list/get/delete notes, download attachments, create/delete permissions) |
| `claw-client/.../google/GoogleKeepTestReceiver.kt` | NEW — ADB BroadcastReceiver for CLI testing (`com.samsung.xr.claw.client.TEST_GOOGLE_KEEP`) |
| `claw-client/.../ui/appfunctions/domains/GoogleKeepDebugScreen.kt` | NEW — Compose debug screen with cards for all operations (create, list, get, delete, permissions) |

**Files Modified:**

| File | Change |
|------|--------|
| `GoogleAuthManager.kt` | Added `https://www.googleapis.com/auth/keep` OAuth scope; updated comments |
| `DomainDebugScreens.kt` | Added import alias + facade wrapper for `GoogleKeepDebugScreen` |
| `AppFunctionCenterScreen.kt` | Added `GOOGLE_KEEP` enum entry with `Icons.Filled.StickyNote2` |
| `MainActivity.kt` | Added import + navigation `when` branch for `GOOGLE_KEEP` |
| `AndroidManifest.xml` | Registered `GoogleKeepTestReceiver` with intent filter |
| `GoogleSignInScreen.kt` | Updated info text to mention Keep |

**Implementation Checklist:**
- [x] Create `GoogleKeepProvider.kt` — REST client with data classes and CRUD methods
- [x] Create `GoogleKeepTestReceiver.kt` — ADB broadcast receiver for testing
- [x] Create `GoogleKeepDebugScreen.kt` — Compose UI debug screen
- [x] Add `https://www.googleapis.com/auth/keep` OAuth scope to `GoogleAuthManager.kt`
- [x] Add facade wrapper in `DomainDebugScreens.kt`
- [x] Add `GOOGLE_KEEP` enum entry in `AppFunctionCenterScreen.kt`
- [x] Add navigation `when` branch in `MainActivity.kt`
- [x] Register `GoogleKeepTestReceiver` in `AndroidManifest.xml`
- [x] Update `GoogleSignInScreen.kt` info text
- [x] Build and verify compilation (`compileDebugKotlin` passes)
- [x] Build and verify APK assembly (`assembleDebug` passes)
- [ ] Manually test read operations on device (list notes, get note)
- [ ] Manually test write operations on device (create note, delete note)
- [ ] Test ADB broadcast receiver: `adb shell am broadcast -a com.samsung.xr.claw.client.TEST_GOOGLE_KEEP --es action listNotes`
- [ ] Test attachment download
- [ ] Test permission create/delete
- [ ] Verify behavior with non-Workspace Google account (expect auth failure — Keep API is enterprise-only)

**Open Risks:**
1. **Enterprise-only API**: Google Keep API requires a Google Workspace (enterprise) account. Personal `@gmail.com` accounts will get a 403/error at runtime. Testing requires a Workspace account.
2. **No official client library**: Since Google hasn't published a Maven client library for Keep, the provider makes raw REST calls. Response parsing is manual via Gson — if the API response shape changes, parsing could break silently.
3. **Untested on device**: All code compiles and the APK builds, but no runtime testing has been done. Potential issues with OAuth token refresh, HTTP error handling, or JSON field mapping may surface during device testing.

---

## �� Backlog / Future Considerations

### 1. Consent Player Enhancement
**File:** `agent_testers/consent_player.py:8-9`  
**TODO:** Design a smart voice agent for affirmation/consent (currently uses pre-recorded WAV files)

**Current Behavior:**
- Plays pre-recorded `Yes.wav` / `No.wav` for consent turns
- Rules looked up from `CONSENT_RULES` by `(feature, action)`

**Future Enhancement:**
- [ ] Implement dynamic consent response generation
- [ ] Add more consent audio variations
- [ ] Support multi-language consent responses

### 2. State Collector Plugin Expansion
**Current:** 10 of 22 apps have XRClaw state collection support  
**Apps without XRClaw support:** google_keep, google_mail, spotify, whatsapp, etc.

**Enhancement Plan:**
- [ ] Add XRClaw support for remaining apps where feasible
- [ ] For apps without XRClaw support, improve VLM judge prompts
- [ ] Consider UI-automation-based collector as alternative plugin

### 3. Device Manager Unification
**Current:** Multiple device managers with overlapping logic:
- `jinju_gemini_manager.py`
- `s25_gemini_live_manager.py`
- `s25_gpt_live_manager.py`
- `s25_claude_live_manager.py`
- `meta_live_manager.py`
- `dummy_device_manager.py`

**Refactoring Plan:**
- [ ] Extract common logic into base class
- [ ] Use mixins for device-specific behavior
- [ ] Reduce code duplication across managers

---

---

## Rename "xrclaw" → "state_collector" in State Collector Code (PLANNED)

**Status:** `PLANNED`
**Priority:** Medium
**Last analyzed:** 2026-09-18

### Problem

The state collector subsystem was originally built on top of Samsung's **XRClaw** Python Automation framework. Over time the code has been refactored into generic `state_collector.py` files per app, but hundreds of internal references to "xrclaw" remain — in variable names, comments, user-visible HTML report labels, `method` field string values, backward-compat aliases, and function names. These are confusing because they imply XRClaw-specific logic where there is now only generic state-collector logic.

### Scope boundary — what NOT to rename

The following refer to the **actual XRClaw product/framework** and must stay as-is:

| Item | Location | Reason |
|------|----------|--------|
| Config key `"xrclaw"` | All JSON configs, `common/schema.py:XRClawConfig` | Configures the real XRClaw framework (`claw_package`, `python_automation_path`) |
| Metadata key `"xrclaw_state"` / `"xrclaw_state_pre"` | `common/evaluation_metadata.py`, `state_collect.py:151`, `judge_helpers.py:163`, `response_scorer.py:264`, `report_generator.py:191` | Backward-compat key for old JSONL data |
| `start_xrclaw()` | `automator/automator.py:96` | Launches actual XRClaw companion app (`com.samsung.xr.claw.client`) |
| `XRClawStateCollector` class + `xrclaw_state_collector.py` file | `agent_testers/device_managers/` | Wraps the actual XRClaw Python Automation framework's DeviceManager |
| `MockXRClawDeviceManager` class + `mock_xrclaw.py` file | `test/mocks/` | Mocks the actual XRClaw DeviceManager |
| `check_xrclaw_app_running()` / `--skip-xrclaw` | `scripts/pre_run_checks.py` | Checks the actual XRClaw app |
| `xrclaw_config` variables | `automator.py`, `agent_tester.py`, `run_test_case.py` | Read from `config.get("xrclaw", {})` — match config key |
| `_capture_device_info_xrclaw()` | `device_info.py:75` | Uses actual XRClaw DeviceInfoApp |
| Docstrings mentioning `XRClawStateCollector._collect_*_state()` | 7 `state_collector.py` files, `helpers.py:4` | Refer to actual class extraction history |

### Approach: Hard restructuring (no backward compat)

No soft backward-compat fallbacks. When we rename a producer value, we update all consumers to match. Old JSONL data with `"xrclaw"` method values will need re-processing or a one-time migration script if old reports must be re-opened.

---

### Part 1 — User-Visible Labels & Comments

**Files:** 3

#### `automator/templates/response_visualizer.html`
| Line | Current | New |
|------|---------|-----|
| 528 | `// App State section (XRClaw verification)` | `// App State section (state collector verification)` |
| 536 | `App State (XRClaw Verification):` | `App State (State Collector Verification):` |

#### `automator/report_generator/report_generator.py`
| Line | Current | New |
|------|---------|-----|
| 174 | `only XRClaw app_state` | `only state collector app_state` |
| 176 | `XRClaw app_state (notifications list)` | `state collector app_state (notifications list)` |
| 187 | `# ── XRClaw app state ──` | `# ── State collector app state ──` |
| 189-192 | `xrclaw = meta_info.get("app_state")` / `if xrclaw is None:` / `xrclaw = meta_info.get("xrclaw_state", {})` / `if xrclaw:` | `app_state = meta_info.get("app_state", {})` / `if app_state:` |
| 194-198 | `xrclaw.get(...)` ×5 | `app_state.get(...)` ×5 |
| 233 | `XRClaw app_state + screenshot` | `state collector app_state + screenshot` |

#### `automator/report_generator/report_writer.py`
| Line | Current | New |
|------|---------|-----|
| 167 | `XRClaw state, device state, camera flags` | `state collector state, device state, camera flags` |

---

### Part 2 — `method` Field String Values

**Files:** ~12 producers + 2 consumers + 5 test files

#### Producers (change emitted string values)

| File | Line | Current | New |
|------|------|---------|-----|
| `apps/helpers.py` | 192 | `"method": "xrclaw"` | `"method": "state_collector"` |
| `apps/helpers.py` | 205 | `"method": "xrclaw_unsupported"` | `"method": "state_collector_unsupported"` |
| `apps/helpers.py` | 218 | `"method": "xrclaw_error"` | `"method": "state_collector_error"` |
| `apps/helpers.py` | 228 | `def xrclaw_unavailable_result(...)` | `def state_collector_unavailable_result(...)` |
| `apps/helpers.py` | 231 | `"method": "xrclaw_unavailable"` | `"method": "state_collector_unavailable"` |
| `apps/device/state_collector.py` | 279 | `"method": "xrclaw_error"` | `"method": "state_collector_error"` |
| `apps/device/state_collector.py` | 289 | `"method": "xrclaw"` | `"method": "state_collector"` |
| `apps/samsung_notes/state_collector.py` | 83 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/samsung_reminders/state_collector.py` | 101 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/samsung_calendar/state_collector.py` | 111, 143 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/samsung_clock_alarm/state_collector.py` | 96 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/samsung_clock_timer/state_collector.py` | 67 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/samsung_clock_stopwatch/state_collector.py` | 67 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/google_calendar/state_collector.py` | 88, 118 | `"xrclaw_read"` | `"state_collector_read"` |
| `apps/google_maps/state_collector.py` | 20 | `from ..helpers import result, xrclaw_unavailable_result` | `from ..helpers import result, state_collector_unavailable_result` |
| `apps/google_maps/state_collector.py` | 120, 130, 211 | `xrclaw_unavailable_result(...)` | `state_collector_unavailable_result(...)` |

#### Consumers (hard restructuring — new values only)

| File | Line | Current | New |
|------|------|---------|-----|
| `apps/judge_helpers.py` | 33 | `"method": "xrclaw" or "state_collector"` (docstring) | `"method": "state_collector"` |
| `apps/judge_helpers.py` | 169 | `if method not in ("xrclaw", "xrclaw_read", "state_collector", "state_collector_read"):` | `if method not in ("state_collector", "state_collector_read"):` |
| `apps/judge_helpers.py` | 170 | `if method == "xrclaw_unavailable":` | `if method == "state_collector_unavailable":` |
| `apps/judge_helpers.py` | 172 | `Criteria: method must be 'xrclaw' or 'state_collector'.` | `Criteria: method must be 'state_collector'.` |
| `agent_testers/.../state_collect.py` | 156 | `in ("xrclaw", "xrclaw_read", "state_collector", "state_collector_read")` | `in ("state_collector", "state_collector_read")` |

#### Tests (update assertions)

| File | Line | Current | New |
|------|------|---------|-----|
| `test/unit/test_helpers.py` | 150 | `"xrclaw"` | `"state_collector"` |
| `test/unit/test_helpers.py` | 161 | `"xrclaw_unsupported"` | `"state_collector_unsupported"` |
| `test/unit/test_helpers.py` | 169 | `"xrclaw_error"` | `"state_collector_error"` |
| `test/unit/test_deterministic_judge.py` | 232 | `"xrclaw"` | `"state_collector"` |
| `test/unit/test_deterministic_judge.py` | 253 | `"xrclaw_error"` | `"state_collector_error"` |
| `test/integration/test_state_collectors.py` | 76 | `"xrclaw"` | `"state_collector"` |
| `test/integration/test_state_collectors.py` | 112 | `"xrclaw_read"` | `"state_collector_read"` |
| `test/integration/test_state_collectors.py` | 215 | `in ("xrclaw", "xrclaw_unsupported")` | `in ("state_collector", "state_collector_unsupported")` |
| `test/integration/test_state_collectors.py` | 352 | `"xrclaw"` | `"state_collector"` |
| `test/integration/test_notes_xrclaw_real.py` | 238 | `"xrclaw_read"` | `"state_collector_read"` |

---

### Part 3 — Function / Variable / Alias Names

**Files:** ~15

#### Remove backward-compat aliases

| File | Line | Change |
|------|------|--------|
| `agent_testers/.../device_manager.py` | 124 | Remove `_init_xrclaw_collector = _init_state_collector` |
| `agent_testers/.../device_manager.py` | 131 | Remove `capture_xrclaw_pre_state = capture_pre_state` |
| `agent_testers/.../device_manager.py` | 138 | Remove `_xrclaw_collect_state = _collect_state` |
| `agent_testers/.../state_collect.py` | 56 | Remove `_init_xrclaw_collector = _init_state_collector` |
| `agent_testers/.../state_collect.py` | 95 | Remove `capture_xrclaw_pre_state = capture_pre_state` |
| `agent_testers/.../state_collect.py` | 159 | Remove `_xrclaw_collect_state = _collect_state` |

#### Remove `XRCLAW_APP_KEY_MAP` / `get_xrclaw_app_key` aliases

| File | Line | Change |
|------|------|--------|
| `apps/registry.py` | 294-296 | Remove entire backward-compatible aliases block |
| `apps/__init__.py` | 26 | Remove `XRCLAW_APP_KEY_MAP,` from import |
| `apps/__init__.py` | 27 | Remove `get_xrclaw_app_key,` from import |
| `apps/__init__.py` | 47 | Remove `"XRCLAW_APP_KEY_MAP",` from `__all__` |
| `apps/__init__.py` | 48 | Remove `"get_xrclaw_app_key",` from `__all__` |

#### Remove `xrclaw_collector` attribute alias

| File | Line | Change |
|------|------|--------|
| `agent_testers/agent_tester.py` | 143-144 | Remove `# Backward compat: keep xrclaw_collector as an alias` + `self.device_manager.xrclaw_collector = ...` |
| `agent_testers/.../s25_gemini_live_manager.py` | 16 | Remove `self.xrclaw_collector = None  # backward-compat alias` |
| `agent_testers/.../jinju_gemini_manager.py` | 32 | Remove `self.xrclaw_collector = None  # backward-compat alias` |

#### Update `getattr` fallbacks (remove `xrclaw_collector` lookups)

| File | Line | Current | New |
|------|------|---------|-----|
| `agent_testers/.../app_meta_info.py` | 163 | `getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)` | `getattr(self, "state_collector", None)` |
| `agent_testers/.../app_meta_info.py` | 185 | (same pattern) | (same fix) |
| `agent_testers/.../device_info.py` | 56 | `getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)` | `getattr(self, "state_collector", None)` |
| `agent_testers/.../state_collect.py` | 65 | `collector = getattr(self, "xrclaw_collector", None)` | Remove line (line 63 already checks `state_collector`) |
| `agent_testers/.../s25_gemini_live_manager.py` | 65 | `getattr(self, "_collect_state", None) or getattr(self, "_xrclaw_collect_state", None)` | `getattr(self, "_collect_state", None)` |
| `agent_testers/.../s25_gemini_live_manager.py` | 66 | `getattr(self, "xrclaw_collector", None) or getattr(self, "state_collector", None)` | `getattr(self, "state_collector", None)` |

#### Update docstrings referencing `xrclaw_collector`

| File | Line | Current | New |
|------|------|---------|-----|
| `agent_testers/.../app_meta_info.py` | 5 | `(device vs app, camera, XRClaw, screenshot fallback)` | `(device vs app, camera, state collector, screenshot fallback)` |
| `agent_testers/.../app_meta_info.py` | 11 | `self.xrclaw_collector (or self.state_collector): StateCollector or None` | `self.state_collector: StateCollector or None` |
| `agent_testers/.../app_meta_info.py` | 12 | `self._xrclaw_collect_state() / _collect_state()` | `self._collect_state()` |
| `agent_testers/.../app_meta_info.py` | 34 | `self.xrclaw_collector (or self.state_collector)` | `self.state_collector` |
| `agent_testers/.../device_info.py` | 11 | `self.xrclaw_collector: StateCollector instance or None (backward-compat alias)` | `self.state_collector: StateCollector instance or None` |
| `agent_testers/.../device_info.py` | 32 | `self.xrclaw_collector (or self.state_collector)` | `self.state_collector` |
| `agent_testers/.../state_collect.py` | 7 | `state_collector (or xrclaw_collector)` | `state_collector` |
| `agent_testers/.../state_collect.py` | 23 | `self.xrclaw_collector: backward-compat alias (optional)` | Remove line |

#### Rename `xrclaw_dm` → `statecollector_dm` in precondition files

Pattern: `xrclaw_dm = getattr(sc, "_dm", None) or dm` (or `getattr(dm, "_dm", None) or dm`)

| File | Approx occurrences |
|------|-------------------|
| `apps/device/precondition.py` | ~15 |
| `apps/samsung_clock_stopwatch/precondition.py` | ~5 |
| `apps/samsung_calendar/precondition.py` | ~5 |
| `apps/samsung_clock_alarm/precondition.py` | ~3 |
| `apps/precondition_helpers.py` | `clear_clock_state(xrclaw_dm)` parameter + body |

#### Update `agent_tester.py` call sites

| File | Line | Current | New |
|------|------|---------|-----|
| `agent_testers/agent_tester.py` | 132 | `# Initialize XRClaw verifier if configured` | `# Initialize state collector if configured` |
| `agent_testers/agent_tester.py` | 147 | `Warning: XRClaw enabled but no s25_device_id...` | `Warning: State collector enabled but no s25_device_id...` |
| `agent_testers/agent_tester.py` | 423 | `See DeviceManagerTemplate.capture_xrclaw_pre_state.` | `See DeviceManagerTemplate.capture_pre_state.` |
| `agent_testers/agent_tester.py` | 425 | `self.device_manager.capture_xrclaw_pre_state(question_info)` | `self.device_manager.capture_pre_state(question_info)` |

#### Update `scripts/run_test_case.py` call sites

| File | Line | Current | New |
|------|------|---------|-----|
| `scripts/run_test_case.py` | 387 | `resources.dm.capture_xrclaw_pre_state(q_info)` | `resources.dm.capture_pre_state(q_info)` |
| `scripts/run_test_case.py` | 388 | `tracer.step("capture_xrclaw_pre_state", ...)` | `tracer.step("capture_pre_state", ...)` |
| `scripts/run_test_case.py` | 390 | `capture_xrclaw_pre_state failed` | `capture_pre_state failed` |
| `scripts/run_test_case.py` | 392 | `tracer.step("capture_xrclaw_pre_state", ...)` | `tracer.step("capture_pre_state", ...)` |

#### Update remaining comments

| File | Line | Current | New |
|------|------|---------|-----|
| `apps/device/state_collector.py` | 293 | `Device state fetched via XRClaw — evaluation deferred` | `Device state fetched via state collector — evaluation deferred` |
| `apps/google_maps/state_collector.py` | 6 | `Migrated from xrclaw_state_collector.py` | `Migrated from state_collector.py` |
| `apps/google_maps/state_collector.py` | 76 | `returns method="xrclaw_unavailable"` | `returns method="state_collector_unavailable"` |

---

### Implementation Order

1. **Part 1** — Labels & comments (3 files, zero risk)
2. **Part 2** — `method` field values (producers → consumers → tests, run tests after)
3. **Part 3** — Function/variable/alias names (remove aliases last, after all call sites updated)

### Validation

- Run `pytest test/unit/test_helpers.py test/unit/test_deterministic_judge.py -v` after Part 2
- Run `pytest test/integration/test_state_collectors.py -v` after Part 2
- Grep for remaining `xrclaw` references (excluding config keys, metadata keys, XRClaw product references, and test mock files) after Part 3
- Full test suite run after all parts

### Estimated total: ~30 files

---

## �� Notes

### Task Status Legend
- `PLANNED` - Task defined, not yet started
- `IN_PROGRESS` - Actively being worked on
- `BLOCKED` - Waiting on external dependency
- `COMPLETE` - Task finished, code merged

### Priority Levels
- **High** - Blocks other work or critical for evaluation correctness
- **Medium** - Important but not blocking
- **Low** - Nice to have, can be deferred

### Adding New Tasks
When adding new tasks to this list, include:
1. Clear problem statement
2. Proposed solution/approach
3. Files to create/modify
4. Implementation checklist
5. Any open risks or validation requirements

---

*Last updated: 2026-09-18*
