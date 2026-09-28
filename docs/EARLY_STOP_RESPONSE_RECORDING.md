# Early-Stop Response Recording — Design Plan

## Context

Every evaluation question currently records the agent's spoken reply for a **fixed 30 s** (`configs/jinju_gemini_config.json:25`, `devices.arap.record_duration`), regardless of how long the agent actually took to respond. Across a large eval batch this wastes 15-25 s per question in dead air after the agent has finished speaking, inflating total run time substantially with no benefit to result quality.

The goal is to detect, live, when the agent has actually finished speaking and stop the recording then — while still falling back safely to the current fixed-duration behavior whenever the detection signal is unavailable or inconclusive, so this change can only make things **faster**, never **worse**, than today.

This document is a plan only. No code has been changed as part of it. It is intended to be handed to an implementation agent/session.

---

## System topology (confirmed by live device inspection)

- **Jinju glasses** (serial e.g. `4103d783bb2a9c00`): a Bluetooth **A2DP sink** only — plays whatever audio is streamed to it, no local app logic. Confirmed via `dumpsys bluetooth_manager`: `Profile: A2dpSinkService ... state:Connected`.
- **Companion Galaxy S25 phone** (serial e.g. `R3CX80PJ7KY`): runs the actual Gemini Live app + Google TTS engine (`com.google.android.googlequicksearchbox`, `com.google.android.apps.bard`, `com.google.android.tts` all confirmed installed here). This is the A2DP **source** — it generates the TTS audio and streams it to the glasses over Bluetooth. **The real, meaningful `MediaSession`/player object lives on this phone, not the glasses.**
- **ARAP recorder phone** (third device, e.g. `R3CXB0A3JZK` in the current config): acoustically records whatever the glasses' speaker plays, via an ADB-broadcast-controlled recorder app. No live audio stream reaches the host during recording — the file only exists once pulled after `stop_recording()`.

This is why the detection signal must be polled from the **companion phone**, not the glasses: the glasses have no app-level playback state to query at all.

---

## Current code (what's being replaced)

`agent_testers/agent_tester.py:427-451`:
```python
self.arap_recorder.start_recording(response_filename)
qt = QuestionType.parse(question_info.get("question_type", ""))
...
play_consent(self.device_manager, qt, assets_dir)
time.sleep(self.arap_record_duration)     # ← fixed 30s wait, replace this
self.arap_recorder.stop_recording(response_path)
```
`self.arap_record_duration` is set once from config at `agent_tester.py:153`.

An identical, independently-maintained copy of this whole sequence exists in `scripts/run_test_case.py::_record_response` (lines ~442-480): `start_recording` → `play_consent` → `time.sleep(config["devices"]["arap"]["record_duration"])` → `stop_recording`. Both call sites duplicate the entire recording sequence today, not just the sleep line.

---

## Proposed design

### 1. Signal source: companion phone's `dumpsys media_session`, via the existing `DeviceInfo` class

`agent_testers/device_managers/adb_device_info.py::DeviceInfo.get_media()` (renamed from `device_config.py`; the class itself is unchanged) already does exactly the needed parsing — no new adb/dumpsys code needed:
```python
{"active": bool, "playing": bool, "package": str|None, "state": str|None,
 "state_code": int|None, ..., "error": str|None}
```
`playing = (state_code == 3)` i.e. Android's `PlaybackState.STATE_PLAYING`. It's fully device-agnostic (just shells `adb -s <serial> shell dumpsys media_session` against whatever serial you construct it with) and already tolerates adb errors internally (returns the dict with `error` set, never raises out of `get_media()` itself).

**Important caveat, confirmed by reading `_select_active_session()` (lines 448-519):** if Gemini's session is torn down entirely at end-of-speech (rather than transitioning to Paused/Stopped), `get_media()` reports `active=False` with no state at all. Any consumer must treat **both** `active=False` and `active=True, playing=False` as "not currently speaking."

### 2. Two-phase polling loop — this is the core of the design

A single new function, one shared elapsed-time clock, one ceiling for both phases (critical — see "Bug caught in review" below):

**Phase 1 — wait for speech to start.** The agent has real "thinking" latency (ASR → LLM → TTS) before any audio plays. Poll `get_media()` until `playing == True` is observed for the first time. This directly answers the original ask — *"is the agent processing or has it started responding"* — using the phone's own player state instead of guessing a wait time.
  - If the ceiling is reached with `playing` never having been `True`: abort early-stop entirely for this turn and treat it as if the mechanism weren't available — the recording keeps running until the ceiling (same as today), because we cannot distinguish "agent genuinely never responded" from "the signal missed a quiet response."

**Phase 2 — confirm speech has ended.** Once `playing == True` has been seen at least once, keep polling:
  - Every time `playing == True`: reset a consecutive-not-playing counter to 0.
  - Every time `playing == False` (or `active == False`): increment the counter.
  - Once the counter reaches **3** consecutive not-playing polls: declare the response finished, stop recording early.
  - The same overall ceiling still applies throughout — if reached first, stop regardless of phase/counter state (exact parity with today's worst case).

**Why "3 consecutive polls" and not a wall-clock grace period:** a fixed number of seconds (e.g. "wait 2s of silence") was explicitly rejected because response latency is network-quality-dependent. A **sample-count** debounce sidesteps this: it's a small, fixed, *structural* integer whose job is only to reject a single flaky/stale adb read — not to model network latency at all. Network/latency variability is absorbed entirely by Phase 1 being unbounded-until-ceiling; by the time Phase 2 starts, audio has already reached the phone's player, so remaining uncertainty is "did it actually stop or is this a momentary flicker between sentences," which is a sample-count question, not a network-speed question. This matches the existing house style for debounce in this codebase — `agent_testers/device_managers/mixins/app_tasks.py::_tap_by_resource_id` already uses a fixed `max_retries=3` for the same class of problem (reject a transient bad read, don't wait an arbitrary duration).

**Poll cadence:** time each `get_media()` call; sleep only long enough afterward to avoid hammering `adb` (a small fixed floor, e.g. 0.3s) — this is adb-hygiene, not a latency-absorbing mechanism (that's Phase 1's job — don't let an implementer conflate the two).

### 3. Bug caught during design review — must be called out explicitly to whoever implements this

If Phase 1's ceiling-timeout fallback is implemented as "just fall back to the old `time.sleep(record_duration)`," and Phase 1 already spent time polling before timing out, total wait doubles (~60s instead of 30s) — a regression. **There must be exactly one elapsed-time clock, started once at function entry, shared by both phases; every wait is `ceiling - elapsed_so_far`, never a fresh full-duration sleep tacked on after already having waited.**

### 4. Consent turns: excluded, unconditionally, using an existing static lookup

Consent turns (message/send, calendar/create, etc. — where a canned `Yes.wav` plays mid-recording) must keep today's exact fixed-duration behavior. This is knowable before recording even starts, with no new detection needed:
```python
from apps import get_consent_rules
is_consent = bool(get_consent_rules(qt.feature, qt.action))
```
`qt` is already parsed before the recording sleep at both call sites today. If `is_consent`, skip the new polling entirely and keep `time.sleep(record_duration)` as-is. (A smarter, dynamic "does this turn need consent" detector is explicitly future work — noted as a TODO already in `agent_testers/consent_player.py:8-9` — not part of this change.)

### 5. Defensive filtering: prefer known Gemini/TTS packages, don't be brittle if wrong

`_select_active_session()` currently picks any `PLAYING` session regardless of package. Add an optional `prefer_packages` parameter to `get_media()`/`_select_active_session()` (default `None`, fully backward-compatible with the one existing call site in `mixins/device_info.py`, which must keep its current unfiltered behavior for unrelated DND/media queries). The new polling code passes `prefer_packages=("com.google.android.googlequicksearchbox", "com.google.android.apps.bard", "com.google.android.tts")` — filter to matches first, fall back to "any session" only if none match, so a same-model Gemini update that changes the owning package doesn't silently break detection.

### 6. Graceful degradation when there's no companion device at all

Not every `DeviceManager` subclass implements `_get_companion_device()` — `AppTasksMixin` (`agent_testers/device_managers/mixins/app_tasks.py`, not `DeviceManagerTemplate`) raises `NotImplementedError` by default for managers that don't mix it in. As of 2026-09-28 that's only `dummy-device-manager` (`s25_claude_live`, `s25_gpt_live`, `s25_gemini_upload`, and `meta_live` were removed as unused device_manager_types). Catch this (and any other resolution failure) and fall back to the old fixed sleep unconditionally — this scopes the feature to configs that actually have a real companion media session without crashing on the dummy one.

---

## Where the code should live (avoids duplicating the *new*, more complex logic twice)

Both `agent_tester.py` and `run_test_case.py::_record_response` duplicate the entire recording sequence today. Since this change touches both anyway, extract a single shared implementation rather than let two copies of the new polling logic drift apart:

- **New module `agent_testers/response_wait.py`** — pure polling logic (`wait_for_response_end(companion_device, ceiling_s, ...)`), no recording side effects, so it's unit-testable against a fake `get_media()`.
- **New module `agent_testers/response_recorder.py`** — the shared `record_agent_response(device_manager, arap_recorder, qt, response_filename, response_path, record_duration, assets_dir)` function: does `start_recording` → consent branch (§4) → `wait_for_response_end` or fixed sleep → `stop_recording`, returning a telemetry dict. Both call sites shrink to constructing their existing objects and calling this once.

`ARAPManager` and `RobopodManager` already expose matching `start_recording(file)` / `stop_recording(path)` signatures, so the shared function works transparently with either recorder backend.

---

## Telemetry (no new plumbing required)

`question_info["metadata"]` already flows unmodified into `create_payload()` and on to the coordinator/judge. Attach the polling result as a nested dict, same pattern as existing `precondition_report`/`global_reset_report` entries:
```python
question_info["metadata"]["response_wait"] = {
  "is_consent": bool, "early_stop_fired": bool, "speech_started_detected": bool,
  "elapsed_s": float, "poll_count": int, "package_seen": str|None,
  "fallback_reason": "speech_never_started" | "adb_error" | None,
}
```
For `run_test_case.py`, the same dict threads into the existing `tracer.step("record_response", outputs={...})` call — `ExecutionTracer.step()` already accepts arbitrary `outputs`. Also log one line per question (matching existing `print(...)`/`logging.info(...)` pairs elsewhere in `agent_tester.py`) so behavior is greppable across a batch run without parsing per-question JSON.

---

## Open risk requiring validation before full trust (flagged, not resolved by this plan)

**Unverified assumption:** Gemini Live's TTS session stays continuously `PLAYING` in `dumpsys media_session` for the full spoken reply, without dipping to Buffering/Paused between sentences on longer, multi-sentence answers. If this assumption is wrong, a natural pause mid-reply could satisfy the 3-consecutive-not-playing debounce and truncate a real, still-in-progress response — this is a genuine regression (cut-off audio), not merely a missed optimization, so it's the one thing in this design that fails unsafely rather than safely.

**Recommendation for whoever implements this:** validate empirically before trusting it to gate real recordings — e.g. one batch where `wait_for_response_end` computes and logs its decision, but the *old* fixed sleep still actually controls `stop_recording()`. Confirm from the logs that early-stop would never have fired before a known-long response finished speaking. Only then let it actually gate recording. This is a one-time validation step, not a permanent feature flag — it does not conflict with the requirement that early-stop be the unconditional default once trusted.

Everything else in this design (Phase 1 never-started fallback, ceiling safety net, consent exclusion, companion-device-unavailable fallback) fails **safely** — i.e., in every other error/edge case, the worst outcome is "no time saved," never "truncated audio."

---

## Critical files

| File | Change |
|---|---|
| `agent_testers/response_wait.py` | **New.** `wait_for_response_end()` — two-phase polling/debounce logic described above. |
| `agent_testers/response_recorder.py` | **New.** `record_agent_response()` — shared start/consent-branch/wait/stop sequence used by both call sites. |
| `agent_testers/device_managers/adb_device_info.py` (renamed from `device_config.py`) | Add optional `prefer_packages` param to `get_media()` / `_select_active_session()`, default `None`, backward-compatible. |
| `agent_testers/agent_tester.py` | Lines 427-451: replace inline sequence with a call to `record_agent_response(...)`. |
| `scripts/run_test_case.py` | `_record_response` (lines ~442-480): replace inline sequence with the same shared call. |
| `apps/registry.py`, `agent_testers/consent_player.py` | Reference only — `get_consent_rules` / `play_consent` already provide everything needed for the consent branch; no changes. |
| `agent_testers/device_managers/mixins/app_tasks.py` | Reference only — confirms `_get_companion_device()`'s `NotImplementedError` stub pattern to catch for graceful degradation. |

## Constants (documented, not configurable — same tier as existing `max_retries=3` in `app_tasks.py`)

- `CONSECUTIVE_SILENCE_SAMPLES_TO_CONFIRM_END = 3`
- `MIN_POLL_INTERVAL_S = 0.3` (adb-hygiene floor, not a latency-absorbing mechanism)
- Recommend a slightly reduced per-poll adb timeout (e.g. 5s vs. `DeviceInfo`'s own default of 10s) so one hung adb call can't eat a third of the ceiling.

## Verification plan (for the implementer)

1. Unit-test `wait_for_response_end()` against a fake `get_media()` sequence generator covering: normal speech-then-silence, speech-never-starts (ceiling fallback), and a single transient not-playing blip mid-speech (must NOT trigger early stop — counter should reset).
2. Confirm total elapsed time in the "speech never starts" path exactly equals the ceiling, not double (the bug flagged above).
3. Run the shadow-mode validation batch described in "Open risk" before flipping early-stop to actually gate `stop_recording()`.
4. After going live, compare a full batch's total wall-clock run time against a prior fixed-duration run on the same question set, and spot-check several `cleaned_response_*.mp3` outputs for truncation versus the judge's transcript/rating to confirm no content was cut off.
