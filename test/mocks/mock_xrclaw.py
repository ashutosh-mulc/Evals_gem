"""
MockXRClawDeviceManager — drop-in replacement for XRClaw's DeviceManager.

Mirrors the exact API surface of `python_automation.device_manager.DeviceManager`
so that MAIRE's state collectors (agent_testers/apps/*/state_collector.py) can be
tested without a physical device.

All state is in-memory and mutable. Tests can:
    1. Load fixture state (pre_state)
    2. Call capture_pre() on the state collector
    3. Simulate agent action (create_note, delete_reminder, etc.)
    4. Call verify() on the state collector
    5. Assert the result matches expected

Usage:
    from test.mocks.mock_xrclaw import MockXRClawDeviceManager

    dm = MockXRClawDeviceManager()
    dm.notes.create_note("Shopping List", "milk and eggs")
    notes = dm.notes.find_notes()
    assert any(n.title == "Shopping List" for n in notes)
"""

from __future__ import annotations

import json
import os
from typing import Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# Data model classes — mirror XRClaw's data classes exactly (fields + to_dict)
# ═══════════════════════════════════════════════════════════════════════════════


class MockNoteItem:
    """Mirrors XRClaw's NoteItem."""

    def __init__(self, id: str, title: str, content: str = ""):
        self.id = id
        self.title = title
        self.content = content

    def __repr__(self) -> str:
        return f"MockNoteItem(id={self.id!r}, title={self.title!r}, content={self.content!r})"

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "content": self.content}


import re as _re

class MockReminderItem:
    """Mirrors XRClaw's ReminderItem."""

    def __init__(
        self,
        id: str,
        title: str,
        description: str = "",
        completed: bool = False,
        date_time: str = "",
        all_day: bool = False,
        recurrence: str = "",
        task_category_id: str = "",
    ):
        self.id = id
        self.title = title
        self.description = description
        self.completed = completed
        self.date_time = date_time
        self.all_day = all_day
        self.recurrence = recurrence
        self.task_category_id = task_category_id

    @property
    def date(self) -> str:
        if not self.date_time:
            return ""
        return self.date_time.split("T")[0]

    @property
    def time(self) -> str:
        if self.all_day or not self.date_time:
            return ""
        parts = self.date_time.split("T")
        return parts[1] if len(parts) > 1 else ""

    @property
    def frequency(self) -> str:
        if not self.recurrence:
            return ""
        match = _re.search(r'FREQ=(\w+)', self.recurrence)
        return match.group(1).lower() if match else ""

    @property
    def recurrence_days(self) -> str:
        if not self.recurrence:
            return ""
        match = _re.search(r'BYDAY=([\w,]+)', self.recurrence)
        return match.group(1) if match else ""

    def __repr__(self) -> str:
        parts = [f"id={self.id!r}", f"title={self.title!r}"]
        if self.date_time:
            parts.append(f"date_time={self.date_time!r}")
        if self.recurrence:
            parts.append(f"recurrence={self.recurrence!r}")
        if self.completed:
            parts.append("completed=True")
        return f"MockReminderItem({', '.join(parts)})"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "completed": self.completed,
            "date_time": self.date_time,
            "date": self.date,
            "time": self.time,
            "all_day": self.all_day,
            "recurrence": self.recurrence,
            "frequency": self.frequency,
            "recurrence_days": self.recurrence_days,
            "task_category_id": self.task_category_id,
        }



class MockEventItem:
    """Mirrors XRClaw's EventItem.

    Fields: id, title, description, location, all_day, is_read_only,
    start_date, end_date, recurrence_schedule.
    Has an is_holiday property that checks read-only + all-day + description.
    """

    def __init__(
        self,
        id: str,
        title: str,
        description: str = "",
        location: str = "",
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        all_day: bool = False,
        is_read_only: bool = False,
        start_date: str = "",
        end_date: str = "",
        recurrence_schedule: str = "",
    ):
        self.id = id
        self.title = title
        self.description = description
        self.location = location
        self.start_time = start_time
        self.end_time = end_time
        self.all_day = all_day
        self.is_read_only = is_read_only
        self.start_date = start_date
        self.end_date = end_date
        self.recurrence_schedule = recurrence_schedule

    @property
    def is_holiday(self) -> bool:
        """True if this is a pre-filled holiday/observance (read-only, all-day)."""
        if not self.is_read_only or not self.all_day:
            return False
        desc_lower = self.description.lower()
        return (
            "holiday" in desc_lower
            or "observance" in desc_lower
            or self.description == ""
        )

    def __repr__(self) -> str:
        return f"MockEventItem(id={self.id!r}, title={self.title!r}, start={self.start_date!r}, all_day={self.all_day}, read_only={self.is_read_only})"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "location": self.location,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "all_day": self.all_day,
            "is_read_only": self.is_read_only,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "recurrence_schedule": self.recurrence_schedule,
        }





class MockAlarmItem:
    """Mirrors XRClaw's AlarmItem."""

    def __init__(
        self,
        id: str = "",
        time: str = "",
        label: str = "",
        enabled: bool = True,
        days: str = "",
        vibrate: bool = True,
        sound: str = "",
    ):
        self.id = id
        self.time = time
        self.label = label
        self.enabled = enabled
        self.days = days
        self.vibrate = vibrate
        self.sound = sound

    def __repr__(self) -> str:
        return f"MockAlarmItem(id={self.id!r}, time={self.time!r}, label={self.label!r}, enabled={self.enabled})"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "time": self.time,
            "label": self.label,
            "enabled": self.enabled,
            "days": self.days,
            "vibrate": self.vibrate,
            "sound": self.sound,
        }


class MockAlarmState:
    """Mirrors XRClaw's AlarmState."""

    def __init__(self, alarms=None, error: str = ""):
        self.alarms = alarms or []
        self.error = error

    @property
    def count(self) -> int:
        return len(self.alarms)

    @property
    def enabled_count(self) -> int:
        return sum(1 for a in self.alarms if a.enabled)

    def to_dict(self) -> dict:
        return {
            "alarms": [a.to_dict() for a in self.alarms],
            "count": self.count,
            "enabled_count": self.enabled_count,
            "error": self.error,
        }


class MockTimerItem:
    """Mirrors XRClaw's TimerItem."""

    def __init__(
        self,
        id: str = "",
        label: str = "",
        timer_state: str = "",
        is_firing: bool = False,
        original_duration_millis: int = 0,
        duration_millis: int = 0,
        remaining_duration_millis: int = 0,
        expire_time_epoch_millis: int = 0,
    ):
        self.id = id
        self.label = label
        self.timer_state = timer_state
        self.is_firing = is_firing
        self.original_duration_millis = original_duration_millis
        self.duration_millis = duration_millis
        self.remaining_duration_millis = remaining_duration_millis
        self.expire_time_epoch_millis = expire_time_epoch_millis

    @property
    def is_running(self) -> bool:
        return self.timer_state.upper() == "STARTED"

    @property
    def is_paused(self) -> bool:
        return self.timer_state.upper() == "PAUSED"

    def __repr__(self) -> str:
        return (
            f"MockTimerItem(id={self.id!r}, label={self.label!r}, "
            f"timer_state={self.timer_state!r}, "
            f"original_duration_millis={self.original_duration_millis}, "
            f"remaining_duration_millis={self.remaining_duration_millis})"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "timer_state": self.timer_state,
            "is_firing": self.is_firing,
            "original_duration_millis": self.original_duration_millis,
            "duration_millis": self.duration_millis,
            "remaining_duration_millis": self.remaining_duration_millis,
            "expire_time_epoch_millis": self.expire_time_epoch_millis,
        }


class MockTimerState:
    """Mirrors XRClaw's TimerState."""

    def __init__(self, timers=None, error: str = ""):
        self.timers = timers or []
        self.error = error

    @property
    def count(self) -> int:
        return len(self.timers)

    @property
    def running_count(self) -> int:
        return sum(1 for t in self.timers if t.is_running)

    def to_dict(self) -> dict:
        return {
            "timers": [t.to_dict() for t in self.timers],
            "count": self.count,
            "running_count": self.running_count,
            "error": self.error,
        }


class MockStopwatchState:
    """Mirrors XRClaw's StopwatchState."""

    def __init__(self, is_running: bool = False, elapsed_ms: int = 0):
        self.is_running = is_running
        self.elapsed_ms = elapsed_ms

    def __repr__(self) -> str:
        return f"MockStopwatchState(running={self.is_running}, elapsed_ms={self.elapsed_ms})"

    def to_dict(self) -> dict:
        return {"is_running": self.is_running, "elapsed_ms": self.elapsed_ms}


class MockMediaState:
    """Mirrors XRClaw's MediaState."""

    def __init__(
        self,
        package: str = "",
        app_name: str = "",
        title: str = "",
        artist: str = "",
        album: str = "",
        playback_state: str = "",
        is_playing: bool = False,
        position_ms: int = 0,
        active: bool = False,
        state: str = "",
        state_code: int = 0,
        speed: float = 1.0,
        last_audio_package: str = "",
    ):
        self.package = package
        self.app_name = app_name
        self.title = title
        self.artist = artist
        self.album = album
        self.playback_state = playback_state
        self.is_playing = is_playing
        self.position_ms = position_ms
        self.active = active
        self.state = state
        self.state_code = state_code
        self.speed = speed
        self.last_audio_package = last_audio_package

    def __repr__(self) -> str:
        return f"MockMediaState(package={self.package!r}, title={self.title!r}, is_playing={self.is_playing})"

    def to_dict(self) -> dict:
        return {
            "package": self.package,
            "app_name": self.app_name,
            "title": self.title,
            "artist": self.artist,
            "album": self.album,
            "playback_state": self.playback_state,
            "is_playing": self.is_playing,
            "position_ms": self.position_ms,
            "active": self.active,
            "state": self.state,
            "state_code": self.state_code,
            "speed": self.speed,
            "last_audio_package": self.last_audio_package,
        }


class MockMapsNavigationState:
    """Mirrors XRClaw's MapsNavigationState."""

    def __init__(
        self,
        is_running: bool = False,
        is_navigating: bool = False,
        direction: str = "",
        eta: str = "",
        arrival_time: str = "",
        next_direction: str = "",
    ):
        self.is_running = is_running
        self.is_navigating = is_navigating
        self.direction = direction
        self.eta = eta
        self.arrival_time = arrival_time
        self.next_direction = next_direction

    def __repr__(self) -> str:
        return f"MockMapsNavigationState(running={self.is_running}, navigating={self.is_navigating})"

    def to_dict(self) -> dict:
        return {
            "is_running": self.is_running,
            "is_navigating": self.is_navigating,
            "direction": self.direction,
            "eta": self.eta,
            "arrival_time": self.arrival_time,
            "next_direction": self.next_direction,
        }


class MockMessageItem:
    """Mirrors XRClaw's MessageItem."""

    def __init__(self, id: str, message: str = "", sender: str = ""):
        self.id = id
        self.message = message
        self.sender = sender

    def __repr__(self) -> str:
        return f"MockMessageItem(id={self.id!r}, sender={self.sender!r})"

    def to_dict(self) -> dict:
        return {"id": self.id, "message": self.message, "sender": self.sender}


class MockCallRecord:
    """Mirrors XRClaw's CallRecord."""

    def __init__(
        self,
        id: str,
        phoneNumber: str = "",
        callType: str = "",
        isVideoCall: bool = False,
        startTime: str = "",
        contactId: str = "",
        durationMillis: int = 0,
    ):
        self.id = id
        self.phone_number = phoneNumber
        self.call_type = callType
        self.is_video_call = isVideoCall
        self.start_time = startTime
        self.contact_id = contactId
        self.duration_millis = durationMillis

    def __repr__(self) -> str:
        return (
            f"MockCallRecord(id={self.id!r}, phoneNumber={self.phone_number!r}, "
            f"callType={self.call_type!r}, isVideoCall={self.is_video_call})"
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "phoneNumber": self.phone_number,
            "callType": self.call_type,
            "isVideoCall": self.is_video_call,
            "startTime": self.start_time,
            "contactId": self.contact_id,
            "durationMillis": self.duration_millis,
        }


class MockNotificationItem:
    """Mirrors XRClaw's notification items."""

    def __init__(self, id: str = "", title: str = "", content: str = "", package: str = ""):
        self.id = id
        self.title = title
        self.content = content
        self.text = content  # Alias: state collector uses .text
        self.package = package

    def to_dict(self) -> dict:
        return {"id": self.id, "title": self.title, "content": self.content, "text": self.text, "package": self.package}



# ── Device info state classes ──────────────────────────────────────────────────


class MockBatteryState:
    """Mirrors XRClaw's BatteryState."""

    def __init__(self, level=None, status="", charging=False, temperature=None,
                 voltage=None, health="", technology="", error=""):
        self.level = level
        self.status = status
        self.charging = charging
        self.temperature = temperature
        self.voltage = voltage
        self.health = health
        self.technology = technology
        self.error = error

    def to_dict(self) -> dict:
        return {
            "level": self.level,
            "status": self.status,
            "charging": self.charging,
            "temperature": self.temperature,
            "voltage": self.voltage,
            "health": self.health,
            "technology": self.technology,
            "error": self.error,
        }


class MockTimeState:
    """Mirrors XRClaw's TimeState."""

    def __init__(self, datetime_str="", timezone="", epoch_ms=None, error=""):
        self.datetime_str = datetime_str
        self.timezone = timezone
        self.epoch_ms = epoch_ms
        self.error = error

    def to_dict(self) -> dict:
        return {
            "datetime_str": self.datetime_str,
            "timezone": self.timezone,
            "epoch_ms": self.epoch_ms,
            "error": self.error,
        }


class MockDateState:
    """Mirrors XRClaw's DateState."""

    def __init__(self, day=None, month="", year=None, day_of_week="", error=""):
        self.day = day
        self.month = month
        self.year = year
        self.day_of_week = day_of_week
        self.error = error

    def to_dict(self) -> dict:
        return {
            "day": self.day,
            "month": self.month,
            "year": self.year,
            "day_of_week": self.day_of_week,
            "error": self.error,
        }


class MockVolumeState:
    """Mirrors XRClaw's VolumeState."""

    def __init__(self, muted=None, min=None, max=None, current=None, all_streams=None, error=""):
        self.muted = muted
        self.min = min
        self.max = max
        self.current = current
        self.all_streams = all_streams or {}
        self.error = error

    def to_dict(self) -> dict:
        return {
            "muted": self.muted,
            "min": self.min,
            "max": self.max,
            "current": self.current,
            "all_streams": self.all_streams,
            "error": self.error,
        }


class MockDndState:
    """Mirrors XRClaw's DndState."""

    def __init__(self, enabled=False, zen_mode="0", error=""):
        self.enabled = enabled
        self.zen_mode = zen_mode
        self.error = error

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "zen_mode": self.zen_mode,
            "error": self.error,
        }


class MockDeviceInfoState:
    """Mirrors XRClaw's DeviceInfoState — combined device info."""

    def __init__(self, battery=None, time=None, date=None, volume=None, dnd=None, media=None):
        self.battery = battery or MockBatteryState()
        self.time = time or MockTimeState()
        self.date = date or MockDateState()
        self.volume = volume or MockVolumeState()
        self.dnd = dnd or MockDndState()
        self.media = media or MockMediaState()

    def to_dict(self) -> dict:
        return {
            "battery": self.battery.to_dict(),
            "time": self.time.to_dict(),
            "date": self.date.to_dict(),
            "volume": self.volume.to_dict(),
            "dnd_mode": "true" if self.dnd.enabled else "false",
            "media": self.media if isinstance(self.media, dict) else self.media.to_dict(),
        }


@dataclass
class MockTranslationState:
    """Mirrors XRClaw's TranslationState."""

    translation_triggered: bool = False
    target_language_name: Optional[str] = None
    target_language_code: Optional[str] = None
    translate_app_launched: bool = False
    language_pair_changed: bool = False
    translation_service_connected: bool = False
    gemini_client_states: list = field(default_factory=list)
    conversation_stop_reason: Optional[str] = None
    cm_controller_stop_reason: Optional[str] = None
    is_gemini_app_invocation: Optional[bool] = None
    agent_states: list = field(default_factory=list)
    tinygemma_output: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "translation_triggered": self.translation_triggered,
            "target_language_name": self.target_language_name,
            "target_language_code": self.target_language_code,
            "translate_app_launched": self.translate_app_launched,
            "language_pair_changed": self.language_pair_changed,
            "translation_service_connected": self.translation_service_connected,
            "gemini_client_states": self.gemini_client_states,
            "conversation_stop_reason": self.conversation_stop_reason,
            "cm_controller_stop_reason": self.cm_controller_stop_reason,
            "is_gemini_app_invocation": self.is_gemini_app_invocation,
            "agent_states": self.agent_states,
            "tinygemma_output": self.tinygemma_output,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# Accessor classes — mirror XRClaw's app accessors (NotesApp, RemindersApp, etc.)
# ═══════════════════════════════════════════════════════════════════════════════


class MockNotesAccessor:
    """Mirrors XRClaw's NotesApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def find_notes(self, query: str = "") -> list:
        if query:
            return [n for n in self._dm._notes if query.lower() in n.title.lower()]
        return list(self._dm._notes)

    def get_notes(self, note_ids: list) -> list:
        return [n for n in self._dm._notes if n.id in note_ids]

    def create_note(self, title: str, content: str = "") -> Optional[str]:
        note = MockNoteItem(f"note_{len(self._dm._notes)}", title, content)
        self._dm._notes.append(note)
        return note.id

    def update_note(self, note_id: str, title: str = "", content: str = "") -> bool:
        for n in self._dm._notes:
            if n.id == note_id:
                if title:
                    n.title = title
                if content:
                    n.content = content
                return True
        return False

    def delete_notes(self, note_ids: list) -> bool:
        self._dm._notes = [n for n in self._dm._notes if n.id not in note_ids]
        return True

    def show_note(self, note_id: str) -> bool:
        return any(n.id == note_id for n in self._dm._notes)

    def clear_all_notes(self) -> int:
        count = len(self._dm._notes)
        self._dm._notes = []
        return count


class MockRemindersAccessor:
    """Mirrors XRClaw's RemindersApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def find_reminders(self, query: str = "") -> list:
        if query:
            return [r for r in self._dm._reminders if query.lower() in r.title.lower()]
        return list(self._dm._reminders)

    def get_reminders(self, task_ids: list) -> list:
        return [r for r in self._dm._reminders if r.id in task_ids]

    def create_reminder(self, title: str, description: str = "") -> Optional[str]:
        reminder = MockReminderItem(f"task_{len(self._dm._reminders)}", title, description)
        self._dm._reminders.append(reminder)
        return reminder.id

    def update_reminder(self, task_id: str, title: str = "", description: str = "") -> bool:
        for r in self._dm._reminders:
            if r.id == task_id:
                if title:
                    r.title = title
                if description:
                    r.description = description
                return True
        return False

    def delete_reminders(self, task_ids: list) -> bool:
        self._dm._reminders = [r for r in self._dm._reminders if r.id not in task_ids]
        return True

    def show_reminder(self, task_id: str) -> bool:
        return any(r.id == task_id for r in self._dm._reminders)

    def clear_all_reminders(self) -> int:
        count = len(self._dm._reminders)
        self._dm._reminders = []
        return count


class MockCalendarAccessor:
    """Mirrors XRClaw's CalendarApp (Samsung Calendar)."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def find_events(self, query: str = "", start_datetime: str = "", end_datetime: str = "") -> list:
        if query:
            return [e for e in self._dm._events if query.lower() in e.title.lower()]
        return list(self._dm._events)

    def get_events(self, event_ids: list) -> list:
        return [e for e in self._dm._events if e.id in event_ids]

    def create_event(self, title: str, description: str = "",
                     start_datetime: str = "", end_datetime: str = "") -> Optional[str]:
        event = MockEventItem(f"event_{len(self._dm._events)}", title, description)
        self._dm._events.append(event)
        return event.id

    def update_event(self, event_id: str, title: str = "", description: str = "") -> bool:
        for e in self._dm._events:
            if e.id == event_id:
                if title:
                    e.title = title
                if description:
                    e.description = description
                return True
        return False

    def delete_events(self, event_ids: list) -> bool:
        self._dm._events = [e for e in self._dm._events if e.id not in event_ids]
        return True

    def show_event(self, event_id: str) -> bool:
        return any(e.id == event_id for e in self._dm._events)

    def clear_all_events(self) -> int:
        count = len(self._dm._events)
        self._dm._events = []
        return count


class MockGoogleCalendarAccessor(MockCalendarAccessor):
    """Mirrors XRClaw's GoogleCalendarApp — same interface as CalendarApp."""
    pass


class MockAlarmAccessor:
    """Mirrors XRClaw's AlarmApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def find_alarms(self, query: str = "") -> list:
        if query:
            return [a for a in self._dm._alarms
                    if query.lower() in a.time.lower() or query.lower() in a.label.lower()]
        return list(self._dm._alarms)

    def get_state(self) -> MockAlarmState:
        return MockAlarmState(alarms=list(self._dm._alarms))

    def create_alarm(self, time: str, label: str = "", days: str = "") -> bool:
        alarm = MockAlarmItem(f"alarm_{len(self._dm._alarms)}", time, label, enabled=True, days=days)
        self._dm._alarms.append(alarm)
        return True

    def delete_alarm(self, alarm_id: str) -> bool:
        self._dm._alarms = [a for a in self._dm._alarms if a.id != alarm_id]
        return True

    def is_clock_running(self) -> bool:
        return self._dm.is_app_running("com.sec.android.app.clockpackage")

    def clear_state(self) -> None:
        self._dm._alarms = []
        self._dm.force_stop_app("com.sec.android.app.clockpackage")


class MockTimerAccessor:
    """Mirrors XRClaw's TimerApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def create_timer(self, duration_seconds: int, label: str = "") -> bool:
        timer = MockTimerItem(
            id=f"timer_{len(self._dm._timers)}",
            label=label,
            timer_state="STARTED",
            original_duration_millis=duration_seconds * 1000,
            duration_millis=duration_seconds * 1000,
            remaining_duration_millis=duration_seconds * 1000,
        )
        self._dm._timers.append(timer)
        return True

    def find_timers(self) -> list:
        return list(self._dm._timers)

    def delete_timer(self, timer_id: str) -> bool:
        self._dm._timers = [t for t in self._dm._timers if t.id != timer_id]
        return True

    def delete_all_timers(self) -> int:
        count = len(self._dm._timers)
        self._dm._timers = []
        return count

    def show_timer(self, timer_id: str) -> bool:
        return True

    def get_state(self) -> MockTimerState:
        return MockTimerState(timers=list(self._dm._timers))

    def is_clock_running(self) -> bool:
        return self._dm.is_app_running("com.sec.android.app.clockpackage")

    def clear_state(self) -> None:
        self._dm._timers = []
        self._dm.force_stop_app("com.sec.android.app.clockpackage")


class MockStopwatchAccessor:
    """Mirrors XRClaw's StopwatchApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def start_stopwatch(self) -> bool:
        self._dm._stopwatch.is_running = True
        return True

    def pause_stopwatch(self) -> bool:
        self._dm._stopwatch.is_running = False
        return True

    def reset_stopwatch(self) -> bool:
        self._dm._stopwatch.is_running = False
        self._dm._stopwatch.elapsed_ms = 0
        return True

    def get_state(self) -> MockStopwatchState:
        return self._dm._stopwatch

    def is_clock_running(self) -> bool:
        return self._dm.is_app_running("com.sec.android.app.clockpackage")

    def clear_state(self) -> None:
        self._dm._stopwatch = MockStopwatchState(False, 0)
        self._dm.force_stop_app("com.sec.android.app.clockpackage")


class MockMediaAccessor:
    """Mirrors XRClaw's MediaApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def get_state(self) -> MockMediaState:
        return self._dm._media_state

    def is_spotify_playing(self) -> bool:
        return self._dm._media_state.is_playing and "spotify" in (self._dm._media_state.package or "")

    def is_youtube_music_playing(self) -> bool:
        return self._dm._media_state.is_playing and "youtube.music" in (self._dm._media_state.package or "")

    def is_any_media_playing(self) -> bool:
        return self._dm._media_state.is_playing

    def play(self) -> bool:
        self._dm._media_state.is_playing = True
        self._dm._media_state.state_code = 3
        return True

    def pause(self) -> bool:
        self._dm._media_state.is_playing = False
        self._dm._media_state.state_code = 2
        return True

    def next_track(self) -> bool:
        self._dm._media_state.position_ms = 0
        return True

    def previous_track(self) -> bool:
        self._dm._media_state.position_ms = max(0, self._dm._media_state.position_ms - 30000)
        return True

    def launch_spotify(self) -> None:
        self._dm._media_state.package = "com.spotify.music"
        self._dm._media_state.app_name = "Spotify"

    def launch_youtube_music(self) -> None:
        self._dm._media_state.package = "com.google.android.apps.youtube.music"
        self._dm._media_state.app_name = "YouTube Music"

    def stop_spotify(self) -> None:
        if "spotify" in (self._dm._media_state.package or ""):
            self._dm._media_state.is_playing = False

    def stop_youtube_music(self) -> None:
        if "youtube.music" in (self._dm._media_state.package or ""):
            self._dm._media_state.is_playing = False

    def clear_state(self) -> None:
        self._dm._media_state = MockMediaState()


class MockMapsAccessor:
    """Mirrors XRClaw's MapsApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def get_state(self) -> MockMapsNavigationState:
        return self._dm._maps_state

    def is_maps_running(self) -> bool:
        return self._dm._maps_state.is_running

    def is_navigating(self) -> bool:
        return self._dm._maps_state.is_navigating

    def search_place(self, query: str) -> bool:
        self._dm._maps_state.is_running = True
        return True

    def get_directions(self, from_addr: str, to_addr: str, travel_mode: str = "driving") -> bool:
        self._dm._maps_state.is_running = True
        self._dm._maps_state.is_navigating = True
        return True

    def show_location(self, lat: str, lng: str, zoom: int = 15) -> bool:
        self._dm._maps_state.is_running = True
        return True

    def show_street_view(self, lat: str, lng: str) -> bool:
        self._dm._maps_state.is_running = True
        return True

    def clear_state(self) -> None:
        self._dm._maps_state = MockMapsNavigationState()
        self._dm.force_stop_app("com.google.android.apps.maps")


class MockMessagesAccessor:
    """Mirrors XRClaw's MessagesApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def send_sms(self, phone_number: str, message: str) -> bool:
        msg = MockMessageItem(f"msg_{len(self._dm._messages)}", message, phone_number)
        self._dm._messages.append(msg)
        return True

    def find_messages(self, query: str = "") -> list:
        if query:
            return [m for m in self._dm._messages if query.lower() in m.message.lower()]
        return list(self._dm._messages)

    def get_messages(self, message_ids: list) -> list:
        return [m for m in self._dm._messages if m.id in message_ids]

    def delete_messages(self, message_ids: list) -> bool:
        self._dm._messages = [m for m in self._dm._messages if m.id not in message_ids]
        return True

    def show_message(self, message_id: str) -> bool:
        return any(m.id == message_id for m in self._dm._messages)

    def is_messages_app_running(self) -> bool:
        return self._dm.is_app_running("com.samsung.android.messaging")

    def clear_state(self) -> None:
        self._dm.force_stop_app("com.samsung.android.messaging")


class MockPhoneAccessor:
    """Mirrors XRClaw's PhoneApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def find_call_records(self, query: str = "", call_type: str = "") -> list:
        records = list(self._dm._call_records)
        if query:
            records = [r for r in records if query in r.phone_number]
        if call_type:
            records = [r for r in records if r.call_type.upper() == call_type.upper()]
        return records

    def make_call(self, phone_number: str, contact_id: str = "") -> bool:
        record = MockCallRecord(
            id=f"call_{len(self._dm._call_records)}",
            phoneNumber=phone_number,
            callType="OUTGOING",
            isVideoCall=False,
        )
        self._dm._call_records.append(record)
        return True

    def delete_call_records(self, call_ids: list) -> bool:
        self._dm._call_records = [r for r in self._dm._call_records if r.id not in call_ids]
        return True

    def clear_state(self) -> None:
        self._dm._call_records = []


class MockDeviceInfoAccessor:
    """Mirrors XRClaw's DeviceInfoApp."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def get_battery(self) -> MockBatteryState:
        return self._dm._device_info.battery

    def get_time(self) -> MockTimeState:
        return self._dm._device_info.time

    def get_date(self) -> MockDateState:
        return self._dm._device_info.date

    def get_volume(self) -> MockVolumeState:
        return self._dm._device_info.volume

    def set_volume(self, level: int) -> bool:
        self._dm._device_info.volume.current = level
        self._dm._device_info.volume.muted = level == 0
        # Also update all_streams if present
        for sname, sinfo in self._dm._device_info.volume.all_streams.items():
            sinfo["streamVolume"] = level
            sinfo["muted"] = level == 0
        return True

    def get_dnd_mode(self) -> MockDndState:
        return self._dm._device_info.dnd

    def set_dnd_mode(self, enabled: bool) -> bool:
        self._dm._device_info.dnd.enabled = enabled
        return True

    def get_media(self) -> dict:
        media = self._dm._device_info.media
        if isinstance(media, MockMediaState):
            return media.to_dict()
        return media if isinstance(media, dict) else {}

    def set_media_playing(self, playing: bool) -> bool:
        if isinstance(self._dm._device_info.media, MockMediaState):
            self._dm._device_info.media.is_playing = playing
            self._dm._device_info.media.state_code = 3 if playing else 2
        # Also update the shared media state so dm.media.get_state() reflects the change
        self._dm._media_state.is_playing = playing
        self._dm._media_state.state_code = 3 if playing else 2
        return True

    def get_all(self) -> MockDeviceInfoState:
        return self._dm._device_info


class MockTranslationAccessor:
    """Mirrors XRClaw's TranslationApp."""

    # Common language code map (subset of XRClaw's full map)
    LANGUAGE_CODE_MAP = {
        "spanish": "es",
        "french": "fr",
        "german": "de",
        "japanese": "ja",
        "korean": "ko",
        "chinese": "zh",
        "italian": "it",
        "portuguese": "pt",
        "russian": "ru",
        "arabic": "ar",
        "hindi": "hi",
        "english": "en",
    }

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def clear_log(self) -> None:
        self._dm._translation_log = ""

    def get_state(self, lines: int = 2000) -> MockTranslationState:
        return self._dm._translation_state



class MockNotificationsAccessor:
    """Mirrors XRClaw's notification access."""

    def __init__(self, dm: "MockXRClawDeviceManager"):
        self._dm = dm

    def get_notifications(self) -> list:
        return list(self._dm._notifications)

    def post_notification(self, title: str, content: str) -> bool:
        notif = MockNotificationItem(
            id=f"notif_{len(self._dm._notifications)}",
            title=title,
            content=content,
        )
        self._dm._notifications.append(notif)
        return True

    def clear_all(self) -> int:
        count = len(self._dm._notifications)
        self._dm._notifications = []
        return count


# ═══════════════════════════════════════════════════════════════════════════════
# MockXRClawDeviceManager — the main mock
# ═══════════════════════════════════════════════════════════════════════════════


class MockXRClawDeviceManager:
    """Drop-in replacement for XRClaw's DeviceManager.

    All state is in-memory and mutable. The mock provides the same property
    accessors (dm.notes, dm.reminders, etc.) and methods (get_foreground_app,
    is_app_running, etc.) as the real DeviceManager.

    State can be loaded from JSON fixtures and mutated via the accessor methods
    to simulate agent actions.
    """

    def __init__(self, fixture_dir: str = None):
        # In-memory state stores
        self._notes: list[MockNoteItem] = []
        self._reminders: list[MockReminderItem] = []
        self._events: list[MockEventItem] = []
        self._alarms: list[MockAlarmItem] = []
        self._timers: list[MockTimerItem] = []
        self._messages: list[MockMessageItem] = []
        self._call_records: list[MockCallRecord] = []
        self._notifications: list[MockNotificationItem] = []
        self._stopwatch = MockStopwatchState(False, 0)
        self._media_state = MockMediaState()
        self._maps_state = MockMapsNavigationState()
        self._device_info = MockDeviceInfoState()
        self._translation_state = MockTranslationState()
        self._translation_log = ""

        # Foreground app tracking
        self._foreground_app: Optional[str] = None

        # Auto-incrementing ID counters
        self._id_counter = 0

        # Load fixtures if provided
        if fixture_dir:
            self.load_fixtures(fixture_dir)

    # ── Property accessors (mirror XRClaw DeviceManager) ─────────────

    @property
    def notes(self) -> MockNotesAccessor:
        return MockNotesAccessor(self)

    @property
    def reminders(self) -> MockRemindersAccessor:
        return MockRemindersAccessor(self)

    @property
    def calendar(self) -> MockCalendarAccessor:
        return MockCalendarAccessor(self)

    @property
    def google_calendar(self) -> MockGoogleCalendarAccessor:
        return MockGoogleCalendarAccessor(self)

    @property
    def alarms(self) -> MockAlarmAccessor:
        return MockAlarmAccessor(self)

    @property
    def timers(self) -> MockTimerAccessor:
        return MockTimerAccessor(self)

    @property
    def stopwatch(self) -> MockStopwatchAccessor:
        return MockStopwatchAccessor(self)

    @property
    def media(self) -> MockMediaAccessor:
        return MockMediaAccessor(self)

    @property
    def maps(self) -> MockMapsAccessor:
        return MockMapsAccessor(self)

    @property
    def messages(self) -> MockMessagesAccessor:
        return MockMessagesAccessor(self)

    @property
    def phone(self) -> MockPhoneAccessor:
        return MockPhoneAccessor(self)

    @property
    def device_info(self) -> MockDeviceInfoAccessor:
        return MockDeviceInfoAccessor(self)

    @property
    def translation(self) -> MockTranslationAccessor:
        return MockTranslationAccessor(self)

    @property
    def notifications(self) -> MockNotificationsAccessor:
        return MockNotificationsAccessor(self)

    # ── Device-level methods (mirror XRClaw DeviceManager) ──────────

    def get_foreground_app(self) -> Optional[str]:
        return self._foreground_app

    def set_foreground_app(self, pkg: str) -> None:
        self._foreground_app = pkg

    def is_app_running(self, package: str) -> bool:
        return package == self._foreground_app

    def force_stop_app(self, package: str) -> None:
        if package == self._foreground_app:
            self._foreground_app = None

    def launch_app(self, package: str) -> None:
        self._foreground_app = package

    def get_device_info(self) -> dict:
        return {
            "model": "MockDevice",
            "android_version": "15",
            "sdk_level": "35",
        }

    def clear_all_state(self) -> dict:
        results = {}
        results["notes_cleared"] = len(self._notes)
        self._notes = []
        results["reminders_cleared"] = len(self._reminders)
        self._reminders = []
        results["events_cleared"] = len(self._events)
        self._events = []
        results["alarms_cleared"] = len(self._alarms)
        self._alarms = []
        results["timers_cleared"] = len(self._timers)
        self._timers = []
        self._media_state = MockMediaState()
        self._maps_state = MockMapsNavigationState()
        self._stopwatch = MockStopwatchState()
        results["media_stopped"] = 1
        results["maps_stopped"] = 1
        return results

    def get_all_state(self) -> dict:
        state = {}
        state["notes"] = [n.to_dict() for n in self._notes]
        state["reminders"] = [r.to_dict() for r in self._reminders]
        state["calendar"] = [e.to_dict() for e in self._events]
        state["media"] = self._media_state.to_dict()
        state["maps"] = self._maps_state.to_dict()
        state["stopwatch"] = self._stopwatch.to_dict()
        state["alarms"] = [a.to_dict() for a in self._alarms]
        state["timers"] = [t.to_dict() for t in self._timers]
        return state

    # ── Fixture loading ──────────────────────────────────────────────

    def load_fixtures(self, fixture_dir: str) -> None:
        """Load state from JSON fixture files in the given directory.

        Expected files (all optional):
            notes.json, reminders.json, events.json, alarms.json,
            device_info.json, media.json, maps.json, stopwatch.json,
            translation.json, messages.json, notifications.json
        """
        def _load(name):
            path = os.path.join(fixture_dir, name)
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
            return None

        notes_data = _load("notes.json")
        if notes_data:
            self._notes = [MockNoteItem(n["id"], n["title"], n.get("content", ""))
                           for n in notes_data]

        reminders_data = _load("reminders.json")
        if reminders_data:
            self._reminders = [MockReminderItem(
                r["id"], r["title"],
                r.get("description", ""),
                r.get("completed", False),
                r.get("date_time", ""),
                r.get("all_day", False),
                r.get("recurrence", ""),
                r.get("task_category_id", ""),
            ) for r in reminders_data]


        events_data = _load("events.json")
        if events_data:
            self._events = [MockEventItem(
                e["id"], e["title"],
                e.get("description", ""),
                e.get("location", ""),
                e.get("all_day", False),
                e.get("is_read_only", False),
                e.get("start_date", ""),
                e.get("end_date", ""),
                e.get("recurrence_schedule", ""),
            ) for e in events_data]


        alarms_data = _load("alarms.json")
        if alarms_data:
            self._alarms = [MockAlarmItem(
                a["id"], a["time"], a.get("label", ""), a.get("enabled", True),
                a.get("days", ""), a.get("vibrate", True), a.get("sound", "")
            ) for a in alarms_data]

        device_info_data = _load("device_info.json")
        if device_info_data:
            self._device_info = self._build_device_info(device_info_data)

        media_data = _load("media.json")
        if media_data:
            self._media_state = MockMediaState(**media_data)

        maps_data = _load("maps.json")
        if maps_data:
            self._maps_state = MockMapsNavigationState(**maps_data)

        stopwatch_data = _load("stopwatch.json")
        if stopwatch_data:
            self._stopwatch = MockStopwatchState(**stopwatch_data)

        messages_data = _load("messages.json")
        if messages_data:
            self._messages = [MockMessageItem(
                m["id"], m.get("message", ""), m.get("sender", "")
            ) for m in messages_data]

        notifications_data = _load("notifications.json")
        if notifications_data:
            self._notifications = [MockNotificationItem(
                n["id"], n.get("title", ""), n.get("content", ""), n.get("package", "")
            ) for n in notifications_data]

    def _build_device_info(self, data: dict) -> MockDeviceInfoState:
        """Build MockDeviceInfoState from a dict."""
        battery = MockBatteryState(**data.get("battery", {})) if "battery" in data else MockBatteryState()
        time = MockTimeState(**data.get("time", {})) if "time" in data else MockTimeState()
        date = MockDateState(**data.get("date", {})) if "date" in data else MockDateState()
        volume = MockVolumeState(**data.get("volume", {})) if "volume" in data else MockVolumeState()
        dnd = MockDndState(**data.get("dnd", {})) if "dnd" in data else MockDndState()
        media = data.get("media", {})
        return MockDeviceInfoState(battery, time, date, volume, dnd, media)

    # ── State mutation helpers (for test setup) ──────────────────────

    def set_device_info(self, battery=None, time=None, date=None, volume=None, dnd=None, media=None):
        """Set device info fields. Only provided fields are updated."""
        if battery:
            self._device_info.battery = MockBatteryState(**battery) if isinstance(battery, dict) else battery
        if time:
            self._device_info.time = MockTimeState(**time) if isinstance(time, dict) else time
        if date:
            self._device_info.date = MockDateState(**date) if isinstance(date, dict) else date
        if volume:
            self._device_info.volume = MockVolumeState(**volume) if isinstance(volume, dict) else volume
        if dnd:
            self._device_info.dnd = MockDndState(**dnd) if isinstance(dnd, dict) else dnd
        if media:
            self._device_info.media = media

    def set_media_state(self, **kwargs):
        """Update media state fields."""
        for k, v in kwargs.items():
            setattr(self._media_state, k, v)

    def set_maps_state(self, **kwargs):
        """Update maps state fields."""
        for k, v in kwargs.items():
            setattr(self._maps_state, k, v)

    def set_stopwatch_state(self, **kwargs):
        """Update stopwatch state fields."""
        for k, v in kwargs.items():
            setattr(self._stopwatch, k, v)

    def set_translation_state(self, **kwargs):
        """Update translation state fields."""
        for k, v in kwargs.items():
            setattr(self._translation_state, k, v)

    def _next_id(self) -> str:
        self._id_counter += 1
        return f"mock_{self._id_counter}"
