"""
Declarative precondition setup from a dataset row's ``setup`` block.

    "setup": {"alarms": [{"time": "18:00"}], "notes": [{"title": "Shopping List", "content": "milk"}]}

Each kind is made to match *exactly* (clear, then create each item), so re-running
never creates duplicates and a query never depends on what the previous query left
behind. Item dicts are passed straight to the XRClaw create_* call as kwargs.
"""

from __future__ import annotations

import time

from .precondition_helpers import report

# kind -> (clear, create, list). XRClaw accessors; same names exist in test/mocks/mock_xrclaw.py.
ENTITIES = {
    "alarms":    (lambda dm: dm.alarms.clear_state(),            lambda dm, i: dm.alarms.create_alarm(**i),       lambda dm: dm.alarms.find_alarms()),
    "notes":     (lambda dm: dm.notes.clear_all_notes(),         lambda dm, i: dm.notes.create_note(**i),         lambda dm: dm.notes.find_notes()),
    "reminders": (lambda dm: dm.reminders.clear_all_reminders(), lambda dm, i: dm.reminders.create_reminder(**i), lambda dm: dm.reminders.find_reminders()),
    "timers":    (lambda dm: dm.timers.delete_all_timers(),      lambda dm, i: dm.timers.create_timer(**i),       lambda dm: dm.timers.find_timers()),
    # Holidays can't be deleted, so they don't count towards the expected number.
    "events":    (lambda dm: dm.calendar.clear_all_events(),     lambda dm, i: dm.calendar.create_event(**i),
                  lambda dm: [e for e in dm.calendar.find_events() if not getattr(e, "is_holiday", False)]),
}

# XRClaw creates via broadcasts, so a fresh item can take a moment to show up in a listing.
VERIFY_TRIES = 3
VERIFY_WAIT_S = 0.5


def apply_setup(dm, setup: dict) -> dict:
    """Make the device hold exactly the items in ``setup``. Returns a precondition report."""
    set_items, failed = [], []
    for kind, items in setup.items():
        if kind not in ENTITIES:
            failed.append(f"unknown setup kind '{kind}' (known: {', '.join(ENTITIES)})")
            continue
        clear, create, listing = ENTITIES[kind]
        try:
            clear(dm)
            for item in items:
                create(dm, item)
            for attempt in range(VERIFY_TRIES):
                found = len(listing(dm))
                if found == len(items) or attempt == VERIFY_TRIES - 1:
                    break
                time.sleep(VERIFY_WAIT_S)
        except Exception as e:
            failed.append(f"{kind}: {e}")
            continue
        if found == len(items):
            set_items.append(f"{kind}: exactly {found} item(s) {items}")
        else:
            failed.append(f"{kind}: expected {len(items)} item(s), found {found}")
    return report(passed=not failed, set_items=set_items, failed=failed)
