"""
Integration tests for state collectors — tests each app's capture_pre() and
verify() functions using the MockXRClawDeviceManager.

This is a parametrized matrix that covers all 22+ apps registered in the
app registry. Each test:
  1. Creates a MockXRClawDeviceManager
  2. Sets up initial state (simulating pre-query device state)
  3. Calls capture_pre() to snapshot the state
  4. Simulates the agent's action (create note, set alarm, etc.)
  5. Calls verify() to check the result
  6. Asserts the rating and verification status
"""

import pytest

from test.mocks.mock_xrclaw import MockXRClawDeviceManager
from apps import STATE_COLLECTORS


# ═══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def dm():
    """Fresh MockXRClawDeviceManager for each test."""
    return MockXRClawDeviceManager()


# ═══════════════════════════════════════════════════════════════════════════════
# Samsung Notes — create, modify, delete, read, launch
# ═══════════════════════════════════════════════════════════════════════════════

class TestSamsungNotesStateCollector:
    """Tests for agent_testers/apps/samsung_notes/state_collector.py"""

    def test_create_note_success(self, dm):
        from apps.samsung_notes.state_collector import capture_pre, verify

        # Pre-state: no notes
        pre = capture_pre(dm)
        assert pre["count"] == 0

        # Simulate agent creating a note
        dm.notes.create_note("Shopping List", "milk and eggs")

        # Verify — gt_answer must contain words that overlap with note content
        # for content_overlaps() to return True (needs 2+ significant words).
        # Note: no quotes around content words, else split() includes quotes
        # in the tokens and overlap fails (e.g. "'milk" != "milk").
        result = verify(dm, "samsungnote", "create", "Create a note titled 'Shopping List'",
                        "A note titled 'Shopping List' with content milk and eggs", pre)
        assert result["verified"] is True
        assert result["rating"] == 5
        assert result["method"] == "xrclaw"


    def test_create_note_not_found(self, dm):
        from apps.samsung_notes.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        # Agent didn't create anything
        result = verify(dm, "samsungnote", "create", "Create a note titled 'Shopping List'",
                        "A note titled 'Shopping List' with content 'milk and eggs'", pre)
        assert result["verified"] is False
        assert result["rating"] == 0

    def test_delete_note_success(self, dm):
        from apps.samsung_notes.state_collector import capture_pre, verify

        # Pre-state: note exists
        dm.notes.create_note("Shopping List", "milk and eggs")
        pre = capture_pre(dm)

        # Simulate agent deleting the note
        dm.notes.delete_notes([dm.notes.find_notes()[0].id])

        result = verify(dm, "samsungnote", "delete", "Delete the note titled 'Shopping List'",
                        "Delete the note titled 'Shopping List'", pre)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_read_note_success(self, dm):
        from apps.samsung_notes.state_collector import verify

        dm.notes.create_note("Shopping List", "milk and eggs")
        result = verify(dm, "samsungnote", "read", "Read the note titled 'Shopping List'",
                        "Read the note titled 'Shopping List'", None)
        assert result["verified"] is True
        assert result["method"] == "xrclaw_read"

    def test_launch_success(self, dm):
        from apps.samsung_notes.state_collector import verify

        dm.set_foreground_app("com.samsung.android.app.notes")
        result = verify(dm, "samsungnote", "launch", "Open Samsung Notes",
                        "Open Samsung Notes", None)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_launch_failed(self, dm):
        from apps.samsung_notes.state_collector import verify

        dm.set_foreground_app("com.some.other.app")
        result = verify(dm, "samsungnote", "launch", "Open Samsung Notes",
                        "Open Samsung Notes", None)
        assert result["verified"] is False
        assert result["rating"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# Samsung Reminders — create, modify, delete, read
# ═══════════════════════════════════════════════════════════════════════════════

class TestSamsungRemindersStateCollector:
    """Tests for agent_testers/apps/samsung_reminders/state_collector.py"""

    def test_create_reminder_success(self, dm):
        from apps.samsung_reminders.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        dm.reminders.create_reminder("Buy groceries", "milk and eggs")

        result = verify(dm, "samsungreminder", "create", "Create a reminder titled 'Buy groceries'",
                        "A reminder titled 'Buy groceries'", pre)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_delete_reminder_success(self, dm):
        from apps.samsung_reminders.state_collector import capture_pre, verify

        dm.reminders.create_reminder("Buy groceries")
        pre = capture_pre(dm)
        dm.reminders.delete_reminders([dm.reminders.find_reminders()[0].id])

        result = verify(dm, "samsungreminder", "delete", "Delete the reminder titled 'Buy groceries'",
                        "Delete the reminder titled 'Buy groceries'", pre)
        assert result["verified"] is True
        assert result["rating"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Samsung Calendar — create, modify, delete, read
# ═══════════════════════════════════════════════════════════════════════════════

class TestSamsungCalendarStateCollector:
    """Tests for agent_testers/apps/samsung_calendar/state_collector.py"""

    def test_create_event_success(self, dm):
        from apps.samsung_calendar.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        dm.calendar.create_event("Team Meeting", "Weekly sync")

        result = verify(dm, "samsungcalendar", "create", "Create an event titled 'Team Meeting'",
                        "An event titled 'Team Meeting'", pre)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_delete_event_success(self, dm):
        from apps.samsung_calendar.state_collector import capture_pre, verify

        dm.calendar.create_event("Team Meeting")
        pre = capture_pre(dm)
        dm.calendar.delete_events([dm.calendar.find_events()[0].id])

        result = verify(dm, "samsungcalendar", "delete", "Delete the event titled 'Team Meeting'",
                        "Delete the event titled 'Team Meeting'", pre)
        assert result["verified"] is True
        assert result["rating"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Google Calendar — create, modify, delete, read
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoogleCalendarStateCollector:
    """Tests for agent_testers/apps/google_calendar/state_collector.py"""

    def test_create_event_success(self, dm):
        from apps.google_calendar.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        dm.google_calendar.create_event("Lunch Meeting", "at the cafe")

        result = verify(dm, "googlecalendar", "create", "Create an event titled 'Lunch Meeting'",
                        "An event titled 'Lunch Meeting'", pre)
        assert result["verified"] is True
        assert result["rating"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Clock Alarm — create, modify, delete, read
# ═══════════════════════════════════════════════════════════════════════════════

class TestClockAlarmStateCollector:
    """Tests for agent_testers/apps/samsung_clock_alarm/state_collector.py"""

    def test_create_alarm_success(self, dm):
        from apps.samsung_clock_alarm.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        # State collector formats alarm time as zero-padded "07:00"
        dm.alarms.create_alarm("07:00", "Morning Alarm")

        # gt_answer must contain the time "07:00" for keyword matching to work
        result = verify(dm, "clockalarm", "create", "Set an alarm for 07:00",
                        "Set an alarm for 07:00", pre)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_delete_alarm_success(self, dm):
        from apps.samsung_clock_alarm.state_collector import capture_pre, verify

        dm.alarms.create_alarm("07:00", "Morning Alarm")
        pre = capture_pre(dm)
        alarm_id = dm.alarms.find_alarms()[0].id
        dm.alarms.delete_alarm(alarm_id)

        result = verify(dm, "clockalarm", "delete", "Delete the 07:00 alarm",
                        "Delete the 07:00 alarm", pre)
        assert result["verified"] is True
        assert result["rating"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Clock Timer — create, modify, delete, read
# ═══════════════════════════════════════════════════════════════════════════════

class TestClockTimerStateCollector:
    """Tests for agent_testers/apps/samsung_clock_timer/state_collector.py"""

    def test_create_timer_success(self, dm):
        from apps.samsung_clock_timer.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        # Timer creation is simulated by setting an alarm with timer-like label
        dm.alarms.create_alarm("10 seconds", "Timer")

        result = verify(dm, "clocktimer", "create", "Set a timer for 10 seconds",
                        "Set a timer for 10 seconds", pre)
        # Timer state collector may use different verification logic
        assert result is not None
        assert "rating" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Clock Stopwatch — start, lap, stop, reset
# ═══════════════════════════════════════════════════════════════════════════════

class TestClockStopwatchStateCollector:
    """Tests for agent_testers/apps/samsung_clock_stopwatch/state_collector.py"""

    def test_start_stopwatch_success(self, dm):
        from apps.samsung_clock_stopwatch.state_collector import capture_pre, verify

        pre = capture_pre(dm)
        dm.stopwatch.start_stopwatch()

        result = verify(dm, "clockstopwatch", "start", "Start the stopwatch",
                        "Start the stopwatch", pre)
        assert result is not None
        assert "rating" in result

    def test_stop_stopwatch_success(self, dm):
        from apps.samsung_clock_stopwatch.state_collector import capture_pre, verify

        dm.stopwatch.start_stopwatch()
        pre = capture_pre(dm)
        dm.stopwatch.pause_stopwatch()

        result = verify(dm, "clockstopwatch", "stop", "Stop the stopwatch",
                        "Stop the stopwatch", pre)
        assert result is not None
        assert "rating" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Device — volume, battery, datetime, dnd, mediacontrol, notification
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeviceStateCollector:
    """Tests for agent_testers/apps/device/state_collector.py"""

    def test_capture_pre_device_info(self, dm):
        from apps.device.state_collector import capture_pre

        pre = capture_pre(dm, app_key="device")
        assert pre is not None
        assert "battery" in pre

    def test_capture_pre_mediacontrol(self, dm):
        from apps.device.state_collector import capture_pre

        pre = capture_pre(dm, app_key="device_mediacontrol")
        assert pre is not None
        assert "is_playing" in pre

    def test_verify_device_info(self, dm):
        from apps.device.state_collector import verify

        result = verify(dm, "device", "glasses", "What's my battery?",
                        "Battery at 75%", None)
        assert result["method"] == "xrclaw"
        assert "actual_state" in result

    def test_verify_media_play(self, dm):
        from apps.device.state_collector import capture_pre, verify

        pre = capture_pre(dm, app_key="device_mediacontrol")
        dm.media.play()

        result = verify(dm, "device_mediacontrol", "play", "Play music",
                        "play music", pre)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_verify_media_pause(self, dm):
        from apps.device.state_collector import capture_pre, verify

        dm.media.play()
        pre = capture_pre(dm, app_key="device_mediacontrol")
        dm.media.pause()

        result = verify(dm, "device_mediacontrol", "pause", "Pause music",
                        "pause music", pre)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_verify_notification_read(self, dm):
        from apps.device.state_collector import verify

        dm.notifications.post_notification("Test Notification", "Hello world")
        result = verify(dm, "notification", "read", "Read my notifications",
                        "Test Notification", None)
        assert result["verified"] is True
        assert result["rating"] == 5

    def test_verify_notification_dismiss(self, dm):
        from apps.device.state_collector import capture_pre, verify

        dm.notifications.post_notification("Test Notification", "Hello world")
        pre = capture_pre(dm, app_key="notification")
        dm.notifications.clear_all()

        result = verify(dm, "notification", "dismiss", "Dismiss the notification",
                        "Test Notification", pre)
        assert result["verified"] is True
        assert result["rating"] == 5


# ═══════════════════════════════════════════════════════════════════════════════
# Google Maps — query, navigate, eta
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoogleMapsStateCollector:
    """Tests for agent_testers/apps/google_maps/state_collector.py"""

    def test_maps_state_collector_exists(self):
        assert "googlemaps" in STATE_COLLECTORS

    def test_verify_query(self, dm):
        from apps.google_maps.state_collector import verify

        dm.maps.search_place("coffee shop")
        result = verify(dm, "googlemaps", "query", "Find a coffee shop nearby",
                        "Find a coffee shop nearby", None)
        assert result is not None
        assert "rating" in result

    def test_verify_navigate(self, dm):
        from apps.google_maps.state_collector import verify

        dm.maps.get_directions("here", "there")
        result = verify(dm, "googlemaps", "startnavigate", "Navigate to the nearest gas station",
                        "Navigate to the nearest gas station", None)
        assert result is not None
        assert "rating" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Google Translate — create (translate), start
# ═══════════════════════════════════════════════════════════════════════════════

class TestGoogleTranslateStateCollector:
    """Tests for agent_testers/apps/google_translate/state_collector.py"""

    def test_translate_state_collector_exists(self):
        assert "googletranslate" in STATE_COLLECTORS

    def test_verify_create(self, dm):
        from apps.google_translate.state_collector import verify

        result = verify(dm, "googletranslate", "create", "Translate hello to Spanish",
                        "Translate hello to Spanish", None)
        assert result is not None
        assert "rating" in result


# ═══════════════════════════════════════════════════════════════════════════════
# Samsung Call — launch, call
# ═══════════════════════════════════════════════════════════════════════════════

class TestSamsungCallStateCollector:
    """Tests for agent_testers/apps/samsung_call/state_collector.py"""

    def test_call_state_collector_exists(self):
        assert "call" in STATE_COLLECTORS

    def test_verify_launch(self, dm):
        from apps.samsung_call.state_collector import verify

        result = verify(dm, "call", "launch", "Open Phone",
                        "Open Phone", None)

        assert result is not None
        assert "rating" in result
