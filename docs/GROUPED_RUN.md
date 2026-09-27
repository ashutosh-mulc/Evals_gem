# Grouped Evaluation Runs

Run targeted subsets of the dataset by app function (volume, camera, notes, etc.)
instead of the full dataset at once. Useful for TDD with a real device — test one
app function group, fix issues, then move to the next.

## Quick Start

Add a `"test_groups"` field to your config JSON:

```json
{
    "test_groups": "volume,camera",
    ...
}
```

Then run the automator as usual:

```bash
python -m automator.automator configs/jinju_gemini_config.json
```

The automator will filter the dataset to only entries matching the selected groups
before evaluation. A per-group breakdown is printed at startup:

```
============================================================
Test group filtering enabled: volume, camera
Available groups: battery, calendar, call, camera, clock, datetime, dnd, keep, mail, maps, messages, music, notes, notifications, reminders, spotify, tasks, translate, voicerecorder, volume, whatsapp, youtube_music
Dataset before filtering: 171 entries
Dataset after filtering:  12 entries
  camera: 4 entries
  volume: 8 entries
============================================================
```

## Configuration

The `"test_groups"` field accepts multiple formats:

| Format | Example | Result |
|--------|---------|--------|
| Single group (string) | `"volume"` | Only volume tests |
| Comma-separated string | `"volume,camera,music"` | Volume + camera + music |
| List of strings | `["volume", "camera"]` | Volume + camera |
| `"all"` | `"all"` | All tests (no filtering) |
| Omitted | *(key absent)* | All tests (no filtering, backward compatible) |
| Empty string | `""` | All tests (no filtering) |

When the key is omitted or set to `"all"`, the automator runs the full dataset
exactly as before — **no regressions**.

## Available Test Groups

| Group | Description | Question Type Patterns |
|-------|-------------|----------------------|
| `volume` | Volume up/down/set/mute/unmute | `volume` |
| `camera` | Camera photo/video capture | `camera` |
| `music` | Media control: play/pause/skip/replay/like/dislike/seek | `mediacontrol` |
| `notifications` | Read/not-read/auto notifications | `notification` |
| `datetime` | Time and date queries | `datetime_time`, `datetime_date` |
| `battery` | Battery level queries (glasses/companion) | `battery` |
| `dnd` | Do Not Disturb on/off | `dnd` |
| `notes` | Samsung Notes create/read/edit/delete | `samsung_notes` |
| `reminders` | Samsung Reminders create/list/delete | `samsung_reminder` |
| `maps` | Google Maps navigation/search | `google_maps` |
| `calendar` | Samsung/Google Calendar create/view | `samsung_calendar`, `google_calendar` |
| `clock` | Clock alarm/timer/stopwatch | `clock_alarm`, `clock_timer`, `clock_stopwatch` |
| `messages` | Samsung Messages send/read | `samsung_message` |
| `spotify` | Spotify play/search/control | `spotify` |
| `whatsapp` | WhatsApp send/read messages | `whatsapp` |
| `translate` | Google Translate | `google_translate` |
| `youtube_music` | YouTube Music play/search | `youtube_music` |
| `voicerecorder` | Samsung Voice Recorder | `samsung_voicerecorder` |
| `call` | Samsung Call dial/end | `samsung_call` |
| `keep` | Google Keep notes | `google_keep` |
| `mail` | Google Mail read/send | `google_mail` |
| `tasks` | Google Tasks | `google_tasks` |

## TDD Workflow with Real Device

The intended workflow is to test one group at a time, fix issues, then move on:

```bash
# 1. Set the group in config
#    "test_groups": "volume"

# 2. Run the evaluation
python -m automator.automator configs/jinju_gemini_config.json

# 3. Review failures
cat {root_folder}/eval_set_1/bad_responses.txt

# 4. Fix the issue in code

# 5. Re-run to verify the fix
python -m automator.automator configs/jinju_gemini_config.json

# 6. Once all pass, move to the next group
#    "test_groups": "camera"
```

## How It Works

1. **Round 1**: The automator copies the full dataset to `eval_set_1/`, then
   filters it in-place to only entries matching the selected test groups. The
   filtered dataset overwrites the eval folder's copy.

2. **Round 2+** (if `num_evaluations > 1`): Failure retry works on the already-filtered
   dataset — only failed entries from the previous round are re-evaluated.

3. **Post-processing**: Reports, charts, and summaries are generated for the filtered
   subset only.

## Adding a New Test Group

Edit `common/test_groups.py` and add an entry to the `TEST_GROUPS` dict:

```python
"my_new_group": TestGroup(
    name="my_new_group",
    description="Description of the group",
    patterns=["my_pattern"],          # Substrings to match in question_type
    app_keys=["my_app_key"],          # App key from the registry
),
```

The group is immediately available for use in config `"test_groups"`.

## Validation

If you specify an unknown group name, the automator will raise a clear error:

```
ValueError: Unknown test group 'nonexistent'. Available groups: battery, calendar, ...
```

## Testing

Unit tests are in `test/unit/test_test_groups.py`:

```bash
# Run test group tests
python -m pytest test/unit/test_test_groups.py -v

# Run all tests
python -m pytest test/ --tb=short --ignore=test/legacy -q
```

## Key Files

| File | Purpose |
|------|---------|
| `common/test_groups.py` | TestGroup dataclass + TEST_GROUPS registry + filtering functions |
| `automator/automator.py` | Integration — filters dataset in `prepare_iter_dataset()` round 1 |
| `test/unit/test_test_groups.py` | Unit tests for registry, resolution, filtering, config parsing |
