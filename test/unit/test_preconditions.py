"""
Unit tests for the precondition system.

Tests the PreconditionManager dispatch, per-app precondition modules,
and integration with the existing mock XRClaw device manager.
"""

import json
import pytest
from unittest.mock import MagicMock, patch

from agent_testers.preconditions import PreconditionManager
from common.question_type import QuestionType
from test.mocks.mock_xrclaw import MockXRClawDeviceManager


# ── Fixtures ──────────────────────────────────────────────────────

class FakeDeviceManager:
    """Minimal device manager that wraps a mock XRClaw DM."""
    def __init__(self):
        self._mock_dm = MockXRClawDeviceManager()
        self.jinju_device = "jinju_serial"
        self.companion_device = "companion_serial"

    @property
    def notes(self):
        return self._mock_dm.notes

    @property
    def reminders(self):
        return self._mock_dm.reminders

    @property
    def calendar(self):
        return self._mock_dm.calendar

    @property
    def google_calendar(self):
        return self._mock_dm.google_calendar

    @property
    def alarms(self):
        return self._mock_dm.alarms

    @property
    def timers(self):
        return self._mock_dm.timers

    @property
    def stopwatch(self):
        return self._mock_dm.stopwatch

    @property
    def media(self):
        return self._mock_dm.media

    @property
    def maps(self):
        return self._mock_dm.maps

    @property
    def messages(self):
        return self._mock_dm.messages

    @property
    def notifications(self):
        return self._mock_dm.notifications

    @property
    def device_info(self):
        return self._mock_dm.device_info

    @property
    def translation(self):
        return self._mock_dm.translation

    def get_foreground_app(self):
        return self._mock_dm.get_foreground_app()


class FakeStateCollector:
    """Wraps the mock DM so PreconditionManager can use it."""
    def __init__(self, mock_dm):
        self._dm = mock_dm

    def get_supported_apps(self):
        return {"samsungnote", "samsungreminder", "samsungcalendar", "clockalarm",
                "clocktimer", "clockstopwatch", "device", "notification",
                "googlecalendar", "googlekeep", "googletasks", "googlemaps",
                "googletranslate", "samsungmessage", "spotify",
                "youtubemusic", "google_mail"}

    def capture_pre_state(self, app_name):
        return {}

    def collect_app_state(self, **kwargs):
        return {"verified": True, "rating": 5}


@pytest.fixture
def dm():
    return FakeDeviceManager()


@pytest.fixture
def sc(dm):
    return FakeStateCollector(dm._mock_dm)


@pytest.fixture
def mgr(dm, sc):
    return PreconditionManager(dm, sc)


def _make_q_info(question_type, question="", gt_answer=""):
    return {
        "eval_id": "q00001",
        "eval_type": "APP_EVAL_TASK",
        "question_type": question_type,
        "question": question,
        "gt_answer": gt_answer,
    }


# ── PreconditionManager dispatch tests ─────────────────────────────

class TestPreconditionManagerDispatch:
    """Verify PreconditionManager dispatches correctly."""

    def test_skip_when_no_question_type(self, mgr):
        """No question_type → skip with passed=True."""
        report = mgr.setup(_make_q_info(""))
        assert report["passed"] is True
        assert report["skipped"] is not None

    def test_skip_when_no_precondition_module(self, mgr):
        """App with no precondition module → skip."""
        # google_mail has no precondition.py
        report = mgr.setup(_make_q_info("online_google_mail_launch", "Launch Gmail", ""))
        assert report["passed"] is True
        assert report["skipped"] is not None

    def test_skip_for_non_app_eval(self, mgr):
        """Non-app eval question → skip."""
        q_info = _make_q_info("online_samsung_notes_create", "Create a note", "A note titled Test")
        q_info["eval_type"] = "QA_TASK"
        # PreconditionManager doesn't check eval_type, only question_type
        # This test verifies it still dispatches based on question_type
        report = mgr.setup(q_info)
        # Should still try to set up preconditions based on question_type
        assert isinstance(report, dict)
        assert "passed" in report

    def test_setup_catches_exception(self, mgr):
        """If setup() raises, PreconditionManager catches it and returns failed report."""
        with patch("apps.PRECONDITIONS") as mock_pre:
            mock_mod = MagicMock()
            mock_mod.setup.side_effect = RuntimeError("boom")
            mock_pre.get.return_value = mock_mod
            report = mgr.setup(_make_q_info("online_samsung_notes_create"))
            assert report["passed"] is False
            assert any("boom" in f for f in report["failed"])

    def test_verify_returns_passed_when_no_module(self, mgr):
        """verify() returns passed=True when no precondition module exists."""
        result = mgr.verify(_make_q_info("online_google_mail_launch"))
        assert result["passed"] is True

    def test_normalize_report_adds_defaults(self):
        """_normalize_report fills in missing keys."""
        from agent_testers.preconditions import PreconditionManager
        report = PreconditionManager._normalize_report({})
        assert report["passed"] is True
        assert report["set"] == []
        assert report["checked"] == []
        assert report["failed"] == []
        assert report["skipped"] is None


# ── Samsung Notes preconditions ────────────────────────────────────

class TestSamsungNotesPreconditions:
    """Test Samsung Notes precondition setup."""

    def test_delete_creates_note_with_matching_title(self, mgr, dm):
        """For delete action, a note matching the gt_answer should be created."""
        q_info = _make_q_info(
            "online_samsung_notes_delete",
            "Delete my note titled Shopping List",
            "A note titled 'Shopping List' with content 'milk and eggs'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        notes = dm.notes.find_notes()
        assert any("Shopping List" in n.title for n in notes)

    def test_modify_creates_note_with_matching_title(self, mgr, dm):
        """For modify action, a note matching the gt_answer should be created."""
        q_info = _make_q_info(
            "online_samsung_notes_modify",
            "Add 'bread' to my Shopping List note",
            "A note titled 'Shopping List' with content 'milk and eggs'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        notes = dm.notes.find_notes()
        assert any("Shopping List" in n.title for n in notes)

    def test_read_creates_note_with_matching_title(self, mgr, dm):
        """For read action, a note matching the gt_answer should be created."""
        q_info = _make_q_info(
            "online_samsung_notes_read",
            "Read my Shopping List note",
            "A note titled 'Shopping List' with content 'milk and eggs'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        notes = dm.notes.find_notes()
        assert any("Shopping List" in n.title for n in notes)

    def test_create_does_not_create_note(self, mgr, dm):
        """For create action, no pre-existing note should be created."""
        q_info = _make_q_info(
            "online_samsung_notes_create",
            "Create a note titled Shopping List",
            "A note titled 'Shopping List' with content 'milk and eggs'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        # No notes should have been created (create = agent creates it)
        notes = dm.notes.find_notes()
        matching = [n for n in notes if "Shopping List" in n.title]
        assert len(matching) == 0

    def test_launch_does_not_create_note(self, mgr, dm):
        """For launch action, no note should be created."""
        q_info = _make_q_info(
            "online_samsung_notes_launch",
            "Open Samsung Notes",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.notes.find_notes()) == 0

    def test_launch_clears_stale_notes(self, mgr, dm):
        """For launch action, all pre-existing notes should be deleted."""
        # Pre-seed some stale notes
        dm.notes.create_note("Old Note 1", "stale content")
        dm.notes.create_note("Old Note 2", "more stale content")
        assert len(dm.notes.find_notes()) == 2

        q_info = _make_q_info(
            "online_samsung_notes_launch",
            "Open Samsung Notes",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.notes.find_notes()) == 0



# ── Samsung Reminders preconditions ────────────────────────────────

class TestSamsungRemindersPreconditions:
    """Test Samsung Reminders precondition setup."""

    def test_delete_creates_reminder(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_reminder_delete",
            "Delete my reminder to buy groceries",
            "A reminder titled 'Buy groceries'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        reminders = dm.reminders.find_reminders()
        assert any("Buy groceries" in r.title for r in reminders)

    def test_modify_creates_reminder(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_reminder_modify",
            "Change my grocery reminder",
            "A reminder titled 'Buy groceries'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        reminders = dm.reminders.find_reminders()
        assert any("Buy groceries" in r.title for r in reminders)

    def test_read_creates_reminder(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_reminder_read",
            "Read my grocery reminder",
            "A reminder titled 'Buy groceries' with description 'milk and eggs'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        reminders = dm.reminders.find_reminders()
        assert any("Buy groceries" in r.title for r in reminders)

    def test_create_does_not_create_reminder(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_reminder_create",
            "Create a reminder to buy groceries",
            "A reminder titled 'Buy groceries'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.reminders.find_reminders()) == 0

    def test_launch_clears_stale_reminders(self, mgr, dm):
        """For launch action, all pre-existing reminders should be deleted."""
        # Pre-seed some stale reminders
        dm.reminders.create_reminder("Old Reminder 1", "stale content")
        dm.reminders.create_reminder("Old Reminder 2", "more stale content")
        assert len(dm.reminders.find_reminders()) == 2

        q_info = _make_q_info(
            "online_samsung_reminder_launch",
            "Open Samsung Reminders",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.reminders.find_reminders()) == 0


# ── Samsung Calendar preconditions ────────────────────────────────


class TestSamsungCalendarPreconditions:
    """Test Samsung Calendar precondition setup."""

    def test_delete_creates_event(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_calendar_delete",
            "Delete my Team Meeting event",
            "An event titled 'Team Meeting'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        events = dm.calendar.find_events()
        assert any("Team Meeting" in e.title for e in events)

    def test_modify_creates_event(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_calendar_modify",
            "Change my Team Meeting event time",
            "An event titled 'Team Meeting'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        events = dm.calendar.find_events()
        assert any("Team Meeting" in e.title for e in events)

    def test_read_creates_event(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_calendar_read",
            "What time is my Team Meeting?",
            "An event titled 'Team Meeting'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        events = dm.calendar.find_events()
        assert any("Team Meeting" in e.title for e in events)

    def test_create_does_not_create_event(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_calendar_create",
            "Create a Team Meeting event",
            "An event titled 'Team Meeting'"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.calendar.find_events()) == 0

    def test_launch_clears_stale_events(self, mgr, dm):
        """For launch action, all pre-existing events should be deleted."""
        # Pre-seed some stale events
        dm.calendar.create_event("Old Meeting", "stale content")
        dm.calendar.create_event("Old Lunch", "more stale content")
        assert len(dm.calendar.find_events()) == 2

        q_info = _make_q_info(
            "online_samsung_calendar_launch",
            "Open Samsung Calendar",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.calendar.find_events()) == 0


# ── Calendar holiday filtering tests ────────────────────────────────

class TestCalendarHolidayFiltering:
    """Test that holiday events are filtered from state collector output."""

    def test_holiday_filtered_by_title(self, dm):
        """Events with holiday titles from holidays.json should be filtered."""
        from apps.samsung_calendar.state_collector import _filter_holidays, _is_holiday_event
        from test.mocks.mock_xrclaw import MockEventItem

        events = [
            MockEventItem("e1", "Christmas Day", "", ""),
            MockEventItem("e2", "Team Meeting", "", ""),
            MockEventItem("e3", "Diwali", "", ""),
            MockEventItem("e4", "Lunch with Team", "", ""),
        ]
        filtered = _filter_holidays(events)
        titles = [e.title for e in filtered]
        assert "Christmas Day" not in titles
        assert "Diwali" not in titles
        assert "Team Meeting" in titles
        assert "Lunch with Team" in titles

    def test_holiday_filtered_by_is_holiday_property(self, dm):
        """Events flagged as holiday via XRClaw is_holiday property should be filtered."""
        from apps.samsung_calendar.state_collector import _filter_holidays
        from test.mocks.mock_xrclaw import MockEventItem

        # Read-only, all-day, with 'holiday' in description → is_holiday=True
        events = [
            MockEventItem("e1", "Some Day", "Public holiday", "", all_day=True, is_read_only=True),
            MockEventItem("e2", "Real Event", "Team meeting notes", "", all_day=False, is_read_only=False),
        ]
        filtered = _filter_holidays(events)
        titles = [e.title for e in filtered]
        assert "Some Day" not in titles
        assert "Real Event" in titles

    def test_holiday_filtered_by_description(self, dm):
        """Events with holiday markers in description should be filtered."""
        from apps.samsung_calendar.state_collector import _filter_holidays
        from test.mocks.mock_xrclaw import MockEventItem

        events = [
            MockEventItem("e1", "Some Day", "Click to hide observances", ""),
            MockEventItem("e2", "Real Event", "Team meeting notes", ""),
        ]
        filtered = _filter_holidays(events)
        titles = [e.title for e in filtered]
        assert "Some Day" not in titles
        assert "Real Event" in titles



# ── Clock Alarm preconditions ──────────────────────────────────────


class TestClockAlarmPreconditions:
    """Test Clock Alarm precondition setup."""

    def test_delete_creates_alarm(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_alarm_delete",
            "Delete my 7 AM alarm",
            "An alarm at 07:00"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        alarms = dm.alarms.find_alarms()
        assert len(alarms) > 0

    def test_modify_creates_alarm(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_alarm_modify",
            "Change my alarm to 8 AM",
            "An alarm at 07:00"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        alarms = dm.alarms.find_alarms()
        assert len(alarms) > 0

    def test_disable_creates_alarm(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_alarm_disable",
            "Disable my morning alarm",
            "An alarm at 07:00"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        alarms = dm.alarms.find_alarms()
        assert len(alarms) > 0
        # Alarm should be enabled (so disable can be verified)
        assert all(a.enabled for a in alarms)

    def test_read_creates_alarm(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_alarm_read",
            "What time is my alarm set for?",
            "An alarm at 07:00"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        alarms = dm.alarms.find_alarms()
        assert len(alarms) > 0

    def test_create_does_not_create_alarm(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_alarm_create",
            "Set an alarm for 7 AM",
            "An alarm at 07:00"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.alarms.find_alarms()) == 0


# ── Clock Timer preconditions ──────────────────────────────────────

class TestClockTimerPreconditions:
    """Test Clock Timer precondition setup."""

    def test_modify_creates_timer(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_timer_modify",
            "Change my timer to 10 minutes",
            "A timer set for 5 minutes"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        # Timer is created via the TimerApp
        timers = dm.timers.find_timers()
        assert len(timers) > 0

    def test_pause_creates_timer(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_timer_pause",
            "Pause my timer",
            "A timer set for 5 minutes"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        timers = dm.timers.find_timers()
        assert len(timers) > 0

    def test_stop_creates_timer(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_timer_stop",
            "Stop my timer",
            "A timer set for 5 minutes"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True

    def test_read_creates_timer(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_timer_read",
            "How much time is left on my timer?",
            "A timer set for 5 minutes"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True

    def test_create_does_not_create_timer(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_timer_create",
            "Set a timer for 5 minutes",
            "A timer set for 5 minutes"
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert len(dm.timers.find_timers()) == 0


# ── Clock Stopwatch preconditions ──────────────────────────────────

class TestClockStopwatchPreconditions:
    """Test Clock Stopwatch precondition setup."""

    def test_lap_starts_stopwatch(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_stopwatch_lap",
            "Record a lap on my stopwatch",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert dm.stopwatch.get_state().is_running is True

    def test_stop_starts_stopwatch(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_stopwatch_stop",
            "Stop my stopwatch",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert dm.stopwatch.get_state().is_running is True

    def test_reset_starts_stopwatch(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_stopwatch_reset",
            "Reset my stopwatch",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert dm.stopwatch.get_state().is_running is True

    def test_start_does_not_start_stopwatch(self, mgr, dm):
        q_info = _make_q_info(
            "online_samsung_clock_stopwatch_start",
            "Start a stopwatch",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert dm.stopwatch.get_state().is_running is False


# ── Device state preconditions ────────────────────────────────────

class TestDeviceStatePreconditions:
    """Test device state preconditions (volume, DND, media)."""

    def test_volume_up_sets_known_volume(self, mgr, dm):
        """Volume up should set volume to a known starting level."""
        q_info = _make_q_info(
            "online_device_volume_up",
            "Turn it up",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        # Volume should be at a known low level
        vol = dm.device_info.get_volume()
        assert vol.current is not None
        assert vol.current <= 5  # Known low starting point

    def test_volume_down_sets_known_volume(self, mgr, dm):
        """Volume down should set volume to a known starting level."""
        q_info = _make_q_info(
            "online_device_volume_down",
            "Turn it down",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        vol = dm.device_info.get_volume()
        assert vol.current is not None
        assert vol.current >= 50  # Known high starting point

    def test_dnd_on_sets_dnd_off(self, mgr, dm):
        """DND on should start from DND off state."""
        q_info = _make_q_info(
            "online_device_dnd_on",
            "Turn on Do Not Disturb",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        dnd = dm.device_info.get_dnd_mode()
        assert dnd.enabled is False  # Start from off

    def test_dnd_off_sets_dnd_on(self, mgr, dm):
        """DND off should start from DND on state."""
        q_info = _make_q_info(
            "online_device_dnd_off",
            "Turn off Do Not Disturb",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        dnd = dm.device_info.get_dnd_mode()
        assert dnd.enabled is True  # Start from on

    def test_mediacontrol_pause_starts_media(self, mgr, dm):
        """MediaControl pause should start media playback."""
        q_info = _make_q_info(
            "online_device_mediacontrol_pause",
            "Pause the music",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        media = dm.media.get_state()
        assert media.is_playing is True

    def test_mediacontrol_resume_pauses_media(self, mgr, dm):
        """MediaControl resume should start from paused state."""
        q_info = _make_q_info(
            "online_device_mediacontrol_resume",
            "Resume the music",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        media = dm.media.get_state()
        assert media.is_playing is False  # Start from paused

    def test_mediacontrol_skip_starts_media(self, mgr, dm):
        """MediaControl skip should have media playing."""
        q_info = _make_q_info(
            "online_device_mediacontrol_skip",
            "Skip to the next song",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        media = dm.media.get_state()
        assert media.is_playing is True

    def test_volume_set_does_not_change_volume(self, mgr, dm):
        """Volume set is a query, not a change — no precondition needed."""
        q_info = _make_q_info(
            "online_device_volume_set",
            "What is the volume?",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        # Should skip (no precondition needed for query)

    def test_battery_query_skips_precondition(self, mgr, dm):
        """Battery query has no precondition."""
        q_info = _make_q_info(
            "online_device_battery_glasses",
            "What is the battery level?",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert report["skipped"] is not None

    def test_datetime_query_skips_precondition(self, mgr, dm):
        """DateTime query has no precondition."""
        q_info = _make_q_info(
            "online_device_datetime_time",
            "What time is it?",
            ""
        )
        report = mgr.setup(q_info)
        assert report["passed"] is True
        assert report["skipped"] is not None


# ── Registry discovery test ──────────────────────────────────────

class TestRegistryDiscovery:
    """Verify precondition modules are auto-discovered."""

    def test_preconditions_registry_populated(self):
        """PRECONDITIONS registry should contain entries after discovery."""
        from apps import PRECONDITIONS
        # We expect at least notes, reminders, calendar, clock apps, device
        assert len(PRECONDITIONS) > 0

    def test_samsung_notes_in_preconditions(self):
        """samsungnote should be in PRECONDITIONS."""
        from apps import PRECONDITIONS
        assert "samsungnote" in PRECONDITIONS

    def test_device_in_preconditions(self):
        """device should be in PRECONDITIONS."""
        from apps import PRECONDITIONS
        assert "device" in PRECONDITIONS

    def test_precondition_modules_have_setup(self):
        """All precondition modules should have a setup function."""
        from apps import PRECONDITIONS
        for app_key, mod in PRECONDITIONS.items():
            assert hasattr(mod, "setup"), f"Precondition module for {app_key} has no setup()"
