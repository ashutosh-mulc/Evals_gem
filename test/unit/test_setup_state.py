"""Declarative precondition setup (apps/setup_state.py) and its PreconditionManager hook."""

from agent_testers.preconditions import PreconditionManager
from apps.setup_state import apply_setup
from test.mocks.mock_xrclaw import MockXRClawDeviceManager


def test_setup_is_exact_so_reruns_never_duplicate():
    dm = MockXRClawDeviceManager()
    dm.alarms.create_alarm("18:00", label="left over from an earlier query")
    for _ in range(2):
        rep = apply_setup(dm, {"alarms": [{"time": "18:00"}]})
        assert rep["passed"], rep
    assert [a.time for a in dm.alarms.find_alarms()] == ["18:00"]


def test_multiple_kinds():
    dm = MockXRClawDeviceManager()
    rep = apply_setup(dm, {
        "notes": [{"title": "Shopping List", "content": "milk"}],
        "timers": [{"duration_seconds": 600}],
    })
    assert rep["passed"], rep
    assert [n.title for n in dm.notes.find_notes()] == ["Shopping List"]
    assert len(dm.timers.find_timers()) == 1


def test_failures_are_reported_not_raised(monkeypatch):
    dm = MockXRClawDeviceManager()
    monkeypatch.setattr("apps.setup_state.VERIFY_WAIT_S", 0)
    monkeypatch.setattr(dm.alarms.__class__, "create_alarm", lambda self, **kw: True)  # create silently fails
    rep = apply_setup(dm, {"alarms": [{"time": "18:00"}], "bogus": [{}]})
    assert not rep["passed"]
    assert any("expected 1" in f for f in rep["failed"])
    assert any("unknown setup kind" in f for f in rep["failed"])


def test_manager_uses_setup_block_instead_of_regex_module():
    dm = MockXRClawDeviceManager()
    mgr = PreconditionManager(device_manager=dm)
    rep = mgr.setup({"question_type": "online_samsung_clock_alarm_delete",
                     "question": "Delete my wake-up alarm",  # regex would guess 07:00
                     "setup": {"alarms": [{"time": "06:30", "label": "wake up"}]}})
    assert rep["passed"], rep
    assert [a.time for a in dm.alarms.find_alarms()] == ["06:30"]
