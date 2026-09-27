# Dataset Analysis: dataset-app-eval-heirarchical-v1.2.jsonl

## 1. Dataset Overview

| Property | Value |
|----------|-------|
| **File** | `data/datasets/dataset-app-eval-heirarchical-v1.2.jsonl` |
| **Schema version** | 2.0.1 |
| **Total lines** | 174 (1 schema header + 173 test cases) |
| **Config range** | `dataset_start_index: 0`, `dataset_end_index: 170` |
| **Eval type** | `APP_EVAL_TASK` (all 173 cases) |

## 2. Schema (Line 0 — Header)

```json
{
  "version": "2.0.1",
  "fields": {
    "eval_id": "Unique identifier for the QA pair",
    "image": "Base64-encoded image (e.g. PNG or JPEG)",
    "audio": "Base64-encoded audio (e.g. WAV)",
    "image_path": "name of the image file",
    "audio_path": "name of the audio file",
    "audio_duration": "Duration in seconds (float)",
    "question": "Text transcription of the question",
    "gt_answer": "Ground-truth answer",
    "question_type": "Type/category of question (e.g., Object Recognition, Spatial Understanding)",
    "eval_type": "Evaluation type/category for the record"
  }
}
```

## 3. Fields Per Test Case

Every test case has these 10 fields:

| Field | Type | Description |
|-------|------|-------------|
| `eval_id` | string | Unique ID (e.g., `q00001`) |
| `image` | base64 string | Base64-encoded image (PNG/JPEG) |
| `audio` | base64 string | Base64-encoded audio (WAV) |
| `image_path` | string | Original image filename |
| `audio_path` | string | Original audio file path |
| `audio_duration` | float | Audio duration in seconds |
| `question` | string | Text transcription of the spoken question |
| `gt_answer` | string | Ground-truth answer (empty for 161/173 cases) |
| `question_type` | string | Hierarchical category (e.g., `online_samsung_notes_create`) |
| `eval_type` | string | Always `APP_EVAL_TASK` |

## 4. Question Type Hierarchy

The `question_type` field follows a hierarchical naming convention:

```
<connectivity>_<app>_<feature>_<action>
```

### 4.1 Connectivity Levels

| Connectivity | Cases | Description |
|-------------|-------|-------------|
| `online_` | 143 | Device is connected to internet |
| `offline_` | 19 | Device is offline (no internet) |
| `disconnected_` | 11 | Device is disconnected from companion |

### 4.2 App Groups

| App Group | Cases | Subtypes |
|-----------|-------|----------|
| `samsung` | 67 | camera, call, message, calendar, reminder, notes, voicerecorder, clock (timer/alarm/stopwatch) |
| `device` | 54 | volume, battery, datetime, dnd, notification, mediacontrol |
| `google` | 40 | translate, calendar, tasks, keep, mail, maps, youtubemusic |
| `thirdparty` | 12 | whatsapp, spotify |

### 4.3 Full Question Type Distribution (137 unique types)

#### Samsung Apps (61 online + 3 offline + 3 disconnected = 67 cases)

| Question Type | Count | Sample Question |
|---------------|-------|-----------------|
| `online_samsung_camera_click` | 4 | "Take a photo", "Click a pic" |
| `online_samsung_camera_videostart` | 1 | "Record a video" |
| `online_samsung_camera_videostop` | 1 | "Stop recording" |
| `online_samsung_camera_check` | 1 | "Check the last photo taken" |
| `online_samsung_camera_open` | 1 | "Open camera" |
| `online_samsung_camera_close` | 1 | "Close camera" |
| `online_samsung_call_send` | 2 | "Call John" |
| `online_samsung_call_launch` | 1 | "Open phone app" |
| `online_samsung_call_disambiguation` | 1 | "Call Anne" (multiple contacts) |
| `online_samsung_call_notsend` | 1 | "Call unknown person" |
| `online_samsung_call_videostart` | 1 | "Video call John" |
| `online_samsung_message_launch` | 1 | "Open messages" |
| `online_samsung_message_read` | 1 | "Read my messages" |
| `online_samsung_message_send` | 1 | "Send a message to Maria" |
| `online_samsung_message_draft` | 1 | "Draft a message to John" |
| `online_samsung_message_disambiguation` | 1 | "Send message to Anne" |
| `online_samsung_message_notsend` | 1 | "Send message to Lily" (not in contacts) |
| `online_samsung_message_visualsend` | 1 | "Send message with image" |
| `online_samsung_calendar_launch` | 1 | "Open calendar" |
| `online_samsung_calendar_create` | 1 | "Create an event" |
| `online_samsung_calendar_read` | 1 | "What's on my calendar today?" |
| `online_samsung_calendar_modify` | 1 | "Move my meeting to 3pm" |
| `online_samsung_calendar_delete` | 1 | "Delete tomorrow's event" |
| `online_samsung_reminder_create` | 2 | "Remind me to buy milk" |
| `online_samsung_reminder_modify` | 2 | "Change reminder to 5pm" |
| `online_samsung_reminder_launch` | 1 | "Open reminders" |
| `online_samsung_reminder_delete` | 1 | "Delete reminder" |
| `online_samsung_reminder_read` | 1 | "What are my reminders?" |
| `online_samsung_reminder_noread` | 1 | "Do I have a reminder to take out trash?" |
| `online_samsung_notes_create` | 2 | "Create a note titled Shopping List" |
| `online_samsung_notes_modify` | 2 | "Add to my Shopping List note" |
| `online_samsung_notes_launch` | 1 | "Open Samsung Notes" |
| `online_samsung_notes_delete` | 1 | "Delete my Shopping List note" |
| `online_samsung_notes_read` | 1 | "Read my Shopping List note" |
| `online_samsung_voicerecorder_launch` | 1 | "Open voice recorder" |
| `online_samsung_clock_launch` | 1 | "Open clock app" |
| `online_samsung_clock_timer_create` | 1 | "Set a timer for 5 minutes" |
| `online_samsung_clock_timer_read` | 1 | "How much time is left on the timer?" |
| `online_samsung_clock_timer_modify` | 1 | "Change timer to 10 minutes" |
| `online_samsung_clock_timer_pause` | 1 | "Pause the timer" |
| `online_samsung_clock_timer_restart` | 1 | "Restart the timer" |
| `online_samsung_clock_timer_stop` | 1 | "Stop the timer" |
| `online_samsung_clock_alarm_create` | 1 | "Set an alarm for 7am" |
| `online_samsung_clock_alarm_read` | 2 | "What alarms do I have set?" |
| `online_samsung_clock_alarm_modify` | 1 | "Change alarm to 8am" |
| `online_samsung_clock_alarm_stop` | 1 | "Stop the alarm" |
| `online_samsung_clock_alarm_disable` | 1 | "Disable the alarm" |
| `online_samsung_clock_alarm_delete` | 1 | "Delete the alarm" |
| `online_samsung_clock_stopwatch_start` | 1 | "Start Stopwatch" |
| `online_samsung_clock_stopwatch_lap` | 1 | "Record a lap" |
| `online_samsung_clock_stopwatch_stop` | 1 | "Stop the stopwatch" |
| `online_samsung_clock_stopwatch_reset` | 1 | "Reset the stopwatch" |
| `offline_samsung_camera_click` | 1 | "Take a picture" |
| `offline_samsung_camera_videostart` | 1 | "Record a video" |
| `offline_samsung_camera_videostop` | 1 | "Stop recording" |
| `disconnected_samsung_camera_click` | 1 | "Take a picture" |
| `disconnected_samsung_camera_videostart` | 1 | "Record a video" |
| `disconnected_samsung_camera_videostop` | 1 | "Stop recording" |

#### Device Controls (30 online + 16 offline + 8 disconnected = 54 cases)

| Question Type | Count | Sample Question |
|---------------|-------|-----------------|
| `online_device_volume_up` | 4 | "Turn it up", "Turn the volume up" |
| `online_device_volume_down` | 2 | "Turn it down" |
| `online_device_volume_set` | 1 | "Set volume to 50%" |
| `online_device_volume_uprelative` | 1 | "Increase volume" |
| `online_device_volume_downrelative` | 1 | "Decrease volume" |
| `online_device_battery_glasses` | 2 | "What's my battery level?" |
| `online_device_battery_companion` | 1 | "What's the phone battery?" |
| `online_device_datetime_time` | 1 | "What is the current time?" |
| `online_device_datetime_date` | 1 | "What is the current date?" |
| `online_device_dnd_on` | 1 | "Turn on Do Not Disturb" |
| `online_device_dnd_off` | 1 | "Turn off Do Not Disturb" |
| `online_device_notification_read` | 1 | "Read my notifications" |
| `online_device_notification_notread` | 1 | "Do I have notifications from WhatsApp?" |
| `online_device_notification_auto` | 1 | "Check notifications" |
| `online_device_mediacontrol_play` | 1 | "Play" |
| `online_device_mediacontrol_pause` | — | (offline only) |
| `online_device_mediacontrol_resume` | 2 | "Resume" |
| `online_device_mediacontrol_replay` | 1 | "Replay" |
| `online_device_mediacontrol_previous` | 1 | "Previous track" |
| `online_device_mediacontrol_skip` | 2 | "Next track" |
| `online_device_mediacontrol_seekrelative` | 1 | "Skip 30 seconds" |
| `online_device_mediacontrol_seek` | 1 | "Go to 2:30" |
| `online_device_mediacontrol_like` | 1 | "Like this song" |
| `online_device_mediacontrol_dislike` | 1 | "Dislike this song" |
| `offline_device_volume_set` | 2 | "Set volume to 5" |
| `offline_device_volume_up` | 1 | "Turn it up" |
| `offline_device_volume_down` | 1 | "Turn it down" |
| `offline_device_battery_glasses` | 2 | "What's my battery level?" |
| `offline_device_datetime_time` | 1 | "What is the current time?" |
| `offline_device_datetime_date` | 1 | "What is the current date?" |
| `offline_device_mediacontrol_*` | 6 | play, pause, resume, replay, previous, skip |
| `offline_device_dnd_on/off` | 2 | "Turn on/off Do Not Disturb" |
| `disconnected_device_battery_glasses` | 2 | "What's my battery level?" |
| `disconnected_device_volume_up` | 2 | "Turn it up" |
| `disconnected_device_volume_set` | 2 | "Set volume to 5" |
| `disconnected_device_datetime_time` | 1 | "What is the current time?" |
| `disconnected_device_datetime_date` | 1 | "What is the current date?" |

#### Google Apps (40 cases, all online)

| Question Type | Count | Sample Question |
|---------------|-------|-----------------|
| `online_google_translate_launch` | 1 | "Launch google translate" |
| `online_google_translate_start` | 2 | "Start translating. -- मैं हमेशा..." |
| `online_google_calendar_create` | 2 | "Create an event" |
| `online_google_calendar_modify` | 1 | "Modify event" |
| `online_google_calendar_delete` | 1 | "Delete event" |
| `online_google_tasks_launch` | 1 | "Open Google Tasks" |
| `online_google_tasks_create` | 1 | "Create a task" |
| `online_google_tasks_modify` | 2 | "Modify a task" |
| `online_google_tasks_delete` | 1 | "Delete a task" |
| `online_google_keep_launch` | 1 | "Open Google Keep" |
| `online_google_keep_create` | 2 | "Create a note" |
| `online_google_keep_modify` | 2 | "Modify a note" |
| `online_google_keep_visualcreate` | 1 | "Create note from image" |
| `online_google_keep_read` | 1 | "Read my notes" |
| `online_google_mail_launch` | 1 | "Open Gmail" |
| `online_google_mail_search` | 1 | "Search for emails from John" |
| `online_google_mail_thread_read` | 1 | "Read email thread" |
| `online_google_maps_launch` | 1 | "Open Google Maps" |
| `online_google_maps_startnavigate` | 1 | "Navigate to home" |
| `online_google_maps_querynavigate` | 1 | "How do I get to work?" |
| `online_google_maps_query` | 2 | "Where is the nearest coffee shop?" |
| `online_google_maps_eta` | 1 | "How long to get home?" |
| `online_google_maps_addstop` | 1 | "Add a stop" |
| `online_google_maps_stopnavigate` | 1 | "Stop navigation" |
| `online_google_youtubemusic_play` | 5 | "Play music" |
| `online_google_youtubemusic_playlistcreate` | 2 | "Create a playlist" |
| `online_google_youtubemusic_playlistplay` | 2 | "Play my playlist" |
| `online_google_youtubemusic_podcastnext` | 1 | "Next podcast" |

#### Third-Party Apps (12 cases, all online)

| Question Type | Count | Sample Question |
|---------------|-------|-----------------|
| `online_thirdparty_whatsapp_launch` | 1 | "Open whatsapp app" |
| `online_thirdparty_whatsapp_messagesend` | 1 | "Send a message to Max on WhatsApp" |
| `online_thirdparty_whatsapp_messagereply` | 1 | "Reply to Max on WhatsApp" |
| `online_thirdparty_whatsapp_call` | 1 | "Call Max on WhatsApp" |
| `online_thirdparty_whatsapp_disambiguation` | 1 | "Call Anne on whatsapp" |
| `online_thirdparty_spotify_launch` | 1 | "Open Spotify" |
| `online_thirdparty_spotify_play` | 3 | "Play music on Spotify" |
| `online_thirdparty_spotify_playlistplay` | 2 | "Play my playlist on Spotify" |
| `online_thirdparty_spotify_podcastnext` | 1 | "Next podcast on Spotify" |

## 5. Ground-Truth Answer Analysis

| Status | Count | Notes |
|--------|-------|-------|
| **Empty** `gt_answer` | 161/173 | Most cases rely on state collector verification, not gt_answer |
| **Non-empty** `gt_answer` | 12/173 | Used for specific edge cases |

### 5.1 Cases with Non-Empty gt_answer

These 12 cases have explicit ground-truth answers that the judge should compare against:

| eval_id | question_type | Question (truncated) | gt_answer (truncated) |
|---------|---------------|----------------------|----------------------|
| q00050 | `online_samsung_message_notsend` | Send a message to Lily... | Lily is not in contact list, the message can't be send |
| q00063 | `online_samsung_reminder_noread` | Do I have a reminder to take out trash... | No, there is no reminder to take out trash on Tuesday's |
| q00072 | `online_samsung_voicerecorder_launch` | Open voice recorder | The message should be sent to Maria |
| q00087 | `online_samsung_clock_stopwatch_start` | Start Stopwatch | Alarm created successfully! |
| q00092 | `online_google_translate_start` | Start translating. -- मैं हमेशा... | "I always wish for your future" |
| q00093 | `online_google_translate_start` | Start translating from korean -- 항상... | "I always wish for your future" |
| q00114 | `online_google_maps_query` | How long will it take to get to home by walking? | 20-30 mins |
| q00115 | `online_google_maps_query` | Where is the nearest coffee shop? | Starbuck's bagmane tech part is nearest about 150 meters... |
| q00116 | `online_device_volume_up` | What do the reviews say about Meghana Foods... | Reviews are generally popular for its signature spicy Andhra... |
| q00134 | `online_thirdparty_whatsapp_messagereply` | Can you reply to Max on WhatsApp that 1PM sounds good... | reply to Max on WhatsApp that 1PM sounds good for lunch |
| q00135 | `online_thirdparty_whatsapp_call` | Can you call Max on WhatsApp | Call should be done to Max over whatsapp |
| q00136 | `online_thirdparty_whatsapp_disambiguation` | Can you call Anne on whatsapp? | There are several Anne in contact list... |

> **Note:** Some gt_answer values appear to be mismatched with their question_type (e.g., q00072's gt_answer mentions "message" but the question is about voice recorder; q00087's gt_answer says "Alarm created" but the question is about stopwatch). This may indicate data labeling errors or that gt_answer is used for a different purpose than expected.

## 6. Audio Analysis

| Property | Value |
|----------|-------|
| Has base64 audio | 173/173 (100%) |
| Duration range | 0.035s – 11.559s |
| Average duration | 2.727s |
| Format | WAV (base64-encoded) |
| Unique audio paths | 145 |

### 6.1 Audio Duration by Category

- **Short (< 1s)**: Simple commands like "Turn it up" (0.882s), "Click a pic" (0.998s)
- **Medium (1-5s)**: Most app interactions like "Send a message to Max on WhatsApp" (3.971s)
- **Long (> 5s)**: Translation tasks with multi-language content (8.6s – 11.6s)

### 6.2 Audio Transcription

The `question` field contains the text transcription of the audio. The audio is the TTS-generated speech that gets sent to the AI assistant on the device. For integration testing, we can:

1. **Decode the base64 audio** to WAV files for playback
2. **Use the transcription service** to verify the audio matches the `question` field
3. **Use the `question` text directly** for mock testing without audio playback

## 7. Image Analysis

| Property | Value |
|----------|-------|
| Has base64 image | 173/173 (100%) |
| Unique images | 6 |

### 7.1 Image Inventory

| Image Path | Description | Used For |
|------------|-------------|----------|
| `image_60.png` | Default/placeholder image | Most test cases |
| `data/QADB_Preparation/Image_Set/image_60.png` | Same as above (different path) | Some device/camera cases |
| `image_61.png` | Second placeholder | Some cases |
| `hotel_room_number.jpeg` | Hotel room number photo | Visual question answering |
| `rock_poster.jpeg` | Rock poster photo | Visual question answering |
| `images.jpeg` | Generic image | Some cases |

> Most test cases use `image_60.png` as a placeholder. The actual visual content is only relevant for VQA (Visual Question Answering) tasks, which are a minority.

## 8. What's Needed vs. What We Have

### 8.1 For Each Test Case, We Need:

| Component | Available? | Source |
|-----------|-----------|--------|
| **Question text** | ✅ | `question` field |
| **Question audio** | ✅ | `audio` field (base64 WAV) |
| **Question type** | ✅ | `question_type` field |
| **Ground-truth answer** | ⚠️ Partial | Only 12/173 cases have non-empty `gt_answer` |
| **Image context** | ✅ | `image` field (base64) |
| **App key mapping** | ✅ | Derived from `question_type` (e.g., `online_samsung_notes_create` → `samsungnote`) |
| **Mode (create/read/modify/delete/launch)** | ✅ | Derived from `question_type` suffix |
| **Connectivity state** | ✅ | Derived from `question_type` prefix (online/offline/disconnected) |
| **State collector** | ✅ | Mapped via `STATE_COLLECTORS` registry |
| **Deterministic judge** | ✅ | For device queries (battery, volume, datetime) |
| **LLM judge** | ✅ | For complex app interactions |
| **Transcription service** | ✅ | Available at `transcription_url` |
| **Device manager** | ✅ | Jinju-Gemini (config) or MockXRClaw (testing) |

### 8.2 Evaluation Flow Per Test Case

```
1. Load test case from dataset
2. Decode audio (base64 → WAV)
3. Send audio to device manager (invoke)
4. Capture agent's spoken response (via ARAP recording)
5. Transcribe response (via transcription service)
6. Capture pre-state (via XRClaw state collector)
7. Capture post-state (via XRClaw state collector)
8. Verify state change (via state collector's verify())
9. Judge the response (via deterministic judge or LLM judge)
10. Generate score and analysis
```

### 8.3 What's Missing / Needs Attention

1. **gt_answer is empty for 93% of cases** — For these, evaluation relies entirely on state collector verification (did the device state change as expected?) and LLM judge (was the spoken response appropriate?)

2. **Some gt_answer values appear mismatched** — q00072 (voice recorder) has gt_answer about "message to Maria"; q00087 (stopwatch) has gt_answer "Alarm created successfully!" — these may be data errors.

3. **Audio paths reference external machine** — Paths like `/home/biplab_das/Shouvik/...` won't resolve on this machine. The base64 `audio` field is self-contained, so this is not a blocker.

4. **No expected state change specification** — The dataset doesn't explicitly say what state change is expected. This is inferred from the `question_type` and the state collector's logic.

5. **Connectivity variants** — The same question (e.g., "Take a picture") appears in online, offline, and disconnected variants. The expected behavior differs: online should work, offline should work for local apps, disconnected should fail for cloud-dependent features.

## 9. Test Case Categories for Integration Testing

### 9.1 Category A: Device Control (Deterministic Judge)

These can be evaluated with the `DeterministicJudge` without an LLM:

| question_type | Expected Behavior | Judge Method |
|---------------|-----------------|--------------|
| `*_device_volume_up` | Volume increases | DeterministicJudge (volume comparison) |
| `*_device_volume_down` | Volume decreases | DeterministicJudge (volume comparison) |
| `*_device_volume_set` | Volume matches target | DeterministicJudge (volume comparison) |
| `*_device_battery_glasses` | Battery level reported | DeterministicJudge (battery comparison) |
| `*_device_datetime_time` | Current time reported | DeterministicJudge (time comparison) |
| `*_device_datetime_date` | Current date reported | DeterministicJudge (date comparison) |

### 9.2 Category B: App State Change (State Collector + LLM Judge)

These require state collector verification + LLM judge for response quality:

| App | Actions | State Collector |
|-----|---------|-----------------|
| Samsung Notes | create, modify, delete, read, launch | `samsungnote` |
| Samsung Reminders | create, modify, delete, read, launch | `samsungreminder` |
| Samsung Calendar | create, read, modify, delete, launch | `samsungcalendar` |
| Samsung Clock Timer | create, read, modify, pause, restart, stop | `clocktimer` |
| Samsung Clock Alarm | create, read, modify, stop, disable, delete | `clockalarm` |
| Samsung Clock Stopwatch | start, lap, stop, reset | `clockstopwatch` |
| Samsung Camera | click, videostart, videostop, check, open, close | `samsungcamera` |
| Samsung Call | send, launch, videostart, disambiguation, notsend | `samsungcall` |
| Samsung Message | send, read, draft, launch, disambiguation, notsend, visualsend | `samsungmessage` |
| Google Keep | create, modify, launch, visualcreate, read | `googlekeep` |
| Google Calendar | create, modify, delete | `googlecalendar` |
| Google Tasks | create, modify, delete, launch | `googletasks` |
| Google Translate | launch, start | `googletranslate` |
| Google Maps | launch, startnavigate, query, eta, addstop, stopnavigate | `googlemaps` |
| Google Mail | launch, search, thread_read | `googlemail` |
| Google YouTube Music | play, playlistcreate, playlistplay, podcastnext | `googleyoutubemusic` |
| Spotify | launch, play, playlistplay, podcastnext | `thirdpartyspotify` |
| WhatsApp | launch, messagesend, messagereply, call, disambiguation | `thirdpartywhatsapp` |

### 9.3 Category C: Edge Cases

| question_type | Edge Case | Expected Behavior |
|---------------|-----------|-------------------|
| `*_notsend` | Contact not in list | Agent should refuse or explain |
| `*_noread` | Item doesn't exist | Agent should say "no reminder found" |
| `*_disambiguation` | Multiple matches | Agent should ask for clarification |
| `disconnected_*` | No companion connection | Cloud features should fail gracefully |
| `offline_*` | No internet | Cloud-dependent features should fail |

## 10. Recommended Testing Strategy

### Phase 1: Mock Testing (No Device Required)

Test each test case using `MockXRClawDeviceManager`:

1. **Decode audio** from base64 to verify it's valid WAV
2. **Verify question text** matches audio transcription
3. **Simulate the expected state change** on the mock device
4. **Run state collector verify()** to confirm it detects the change
5. **Run deterministic judge** for device control cases
6. **Verify app key routing** — each question_type maps to the correct state collector

### Phase 2: Transcription Verification

For each test case:
1. Decode base64 audio to WAV file in `scratch_pad/audio/`
2. Send to transcription service
3. Compare transcription output to `question` field
4. Flag any mismatches

### Phase 3: Integration Testing (Device Required)

For each test case:
1. Send audio to device via device manager
2. Capture agent response via ARAP
3. Transcribe response
4. Capture pre/post state via XRClaw
5. Run state collector verify()
6. Run judge
7. Store results in `scratch_pad/results/`

### Phase 4: Image Analysis (VQA Cases)

For cases with non-placeholder images:
1. Decode base64 image to file in `scratch_pad/images/`
2. Use multimodal LLM to analyze image content
3. Verify the question is answerable from the image
4. Test the VQA judge pipeline

## 11. Summary

The dataset contains **173 test cases** across **137 unique question types** covering:
- **8 app groups** (Samsung, Device, Google, Third-party)
- **3 connectivity levels** (online, offline, disconnected)
- **~20 apps** with create/read/modify/delete/launch actions
- **100% have audio** (base64 WAV, avg 2.7s)
- **100% have images** (6 unique images, mostly placeholder)
- **7% have gt_answer** (12 cases with explicit expected answers)

The evaluation pipeline needs:
1. **State collectors** (✅ implemented, 22 apps registered)
2. **Deterministic judge** (✅ implemented for device controls)
3. **LLM judge** (✅ available via judge_url)
4. **Transcription service** (✅ available via transcription_url)
5. **Device manager** (✅ Jinju-Gemini config, MockXRClaw for testing)
6. **ARAP** (✅ for audio recording)
