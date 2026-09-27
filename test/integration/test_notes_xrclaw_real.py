"""
Real XRClaw integration tests for Samsung Notes interface.

These tests connect to the real XRClaw DeviceManager on the companion device
(S25) and verify that the notes CRUD interface works correctly. They exercise
the same API that the state collector and precondition system use at
evaluation time.

Tests are skipped (not failed) if:
    - The XRClaw python_automation path doesn't exist
    - The companion device is not connected via ADB

Run with:
    pytest test/integration/test_notes_xrclaw_real.py -v
"""

from __future__ import annotations

import json
import os
import uuid

import pytest

# ── Config loading ─────────────────────────────────────────────────

CONFIG_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "configs", "jinju_gemini_config.json"
)


def _load_config() -> dict:
    with open(CONFIG_PATH) as f:
        return json.load(f)


def _xrclaw_available() -> bool:
    try:
        config = _load_config()
        path = config.get("xrclaw", {}).get("python_automation_path", "")
        if not path or not os.path.isdir(path):
            return False
        parent = os.path.dirname(path)
        return os.path.isfile(os.path.join(parent, "python_automation", "__init__.py"))
    except Exception:
        return False


# ── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def real_dm():
    if not _xrclaw_available():
        pytest.skip("XRClaw not available")
    config = _load_config()
    xrclaw_path = config["xrclaw"]["python_automation_path"]
    device_id = config["devices"]["s25_device_id"]
    parent_dir = os.path.dirname(xrclaw_path)
    if parent_dir not in os.sys.path:
        os.sys.path.insert(0, parent_dir)
    from python_automation import DeviceManager
    dm = DeviceManager(adb_path="adb", device=device_id)
    yield dm


@pytest.fixture(autouse=True)
def cleanup_notes(real_dm):
    TEST_PREFIX = "XRCLAW_TEST_"
    yield
    try:
        notes = real_dm.notes.find_notes()
        ids = [n.id for n in notes if TEST_PREFIX in (n.title or "")]
        if ids:
            real_dm.notes.delete_notes(ids)
    except Exception:
        pass


def _make_title(base="Note"):
    return f"XRCLAW_TEST_{base}_{uuid.uuid4().hex[:8]}"


def _find_by_title(dm, title):
    """Find notes by exact title — client-side filter.

    XRClaw's find_notes(query) does NOT filter by title on the real device.
    It returns ALL notes regardless of the query parameter.
    """
    return [n for n in dm.notes.find_notes() if n.title == title]


# ═══════════════════════════════════════════════════════════════════
# XRClaw Notes CRUD Interface Tests
# ═══════════════════════════════════════════════════════════════════

class TestNotesCRUD:
    """Test basic CRUD operations on Samsung Notes via XRClaw."""

    def test_create_note(self, real_dm):
        title = _make_title("Shopping")
        note_id = real_dm.notes.create_note(title, "milk and eggs")
        assert note_id is not None
        assert len(_find_by_title(real_dm, title)) == 1

    def test_create_note_empty_content(self, real_dm):
        title = _make_title("Empty")
        note_id = real_dm.notes.create_note(title, "")
        assert note_id is not None
        assert len(_find_by_title(real_dm, title)) == 1

    def test_find_notes_query_does_not_filter(self, real_dm):
        """Document XRClaw behavior: find_notes(query) returns ALL notes."""
        title_a = _make_title("Alpha")
        title_b = _make_title("Beta")
        real_dm.notes.create_note(title_a, "a")
        real_dm.notes.create_note(title_b, "b")
        results = real_dm.notes.find_notes("Alpha")
        all_titles = [n.title for n in results]
        assert title_a in all_titles
        # Documents quirk: find_notes doesn't filter
        assert title_b in all_titles, (
            "find_notes('Alpha') also returns Beta — query param is ignored"
        )

    def test_get_notes_by_id(self, real_dm):
        """get_notes([id]) returns note with correct title and ID.

        Content may be empty — see test_get_notes_content_behavior.
        """
        title = _make_title("GetById")
        note_id = real_dm.notes.create_note(title, "full content")
        notes = real_dm.notes.get_notes([note_id])
        assert len(notes) == 1
        assert notes[0].title == title
        assert notes[0].id == note_id

    def test_get_notes_content_behavior(self, real_dm):
        """Document XRClaw behavior: get_notes() may return empty content.

        XRClaw may also append trailing garbage bytes to content.
        """
        title = _make_title("ContentCheck")
        content = "the actual content"
        real_dm.notes.create_note(title, content)
        all_notes = real_dm.notes.find_notes()
        matching = [n for n in all_notes if n.title == title]
        assert len(matching) == 1
        full = real_dm.notes.get_notes([matching[0].id])
        assert len(full) == 1
        if not full[0].content:
            pytest.skip("XRClaw get_notes() returns empty content — known limitation")
        # XRClaw may append trailing garbage bytes — strip non-printable chars
        actual = full[0].content.encode("utf-8", errors="ignore").decode("utf-8").strip()
        actual = "".join(c for c in actual if c.isprintable() or c in "\n\r\t")
        assert content in actual, f"Expected '{content}' in '{actual}'"

    def test_update_note(self, real_dm):
        title = _make_title("Update")
        note_id = real_dm.notes.create_note(title, "original")
        success = real_dm.notes.update_note(note_id, content="updated")
        assert success
        notes = real_dm.notes.get_notes([note_id])
        assert len(notes) == 1
        if not notes[0].content:
            pytest.skip("XRClaw get_notes() returns empty content")
        assert notes[0].content == "updated"

    def test_delete_note(self, real_dm):
        title = _make_title("Delete")
        note_id = real_dm.notes.create_note(title, "to be deleted")
        assert real_dm.notes.delete_notes([note_id])
        assert len(_find_by_title(real_dm, title)) == 0

    def test_delete_multiple_notes(self, real_dm):
        t1, t2, t3 = _make_title("M1"), _make_title("M2"), _make_title("M3")
        id1 = real_dm.notes.create_note(t1, "c1")
        id2 = real_dm.notes.create_note(t2, "c2")
        id3 = real_dm.notes.create_note(t3, "c3")
        real_dm.notes.delete_notes([id1, id2])
        assert len(_find_by_title(real_dm, t1)) == 0
        assert len(_find_by_title(real_dm, t2)) == 0
        assert len(_find_by_title(real_dm, t3)) == 1


# ═══════════════════════════════════════════════════════════════════
# State Collector Integration Tests
# ═══════════════════════════════════════════════════════════════════

class TestNotesStateCollector:
    """Test the notes state collector with real XRClaw."""

    def test_capture_pre_empty(self, real_dm):
        from apps.samsung_notes.state_collector import capture_pre
        pre = capture_pre(real_dm)
        assert "notes" in pre and "count" in pre
        test_notes = [n for n in pre["notes"] if "XRCLAW_TEST_" in n.get("title", "")]
        assert len(test_notes) == 0

    def test_capture_pre_with_notes(self, real_dm):
        from apps.samsung_notes.state_collector import capture_pre
        title = _make_title("PreCapture")
        real_dm.notes.create_note(title, "pre content")
        pre = capture_pre(real_dm)
        matching = [n for n in pre["notes"] if n.get("title") == title]
        assert len(matching) == 1

    def test_verify_create(self, real_dm):
        from apps.samsung_notes.state_collector import capture_pre, verify
        pre = capture_pre(real_dm)
        title = _make_title("VerifyCreate")
        real_dm.notes.create_note(title, "milk and eggs")
        # Use quotes around title so extract_keyword picks it up
        gt = f"A note titled '{title}' with content 'milk and eggs'"
        result = verify(real_dm, "samsungnote", "create", f"Create {title}", gt, pre)
        assert result["verified"] is True, result.get("analysis")
        assert result["rating"] == 5

    def test_verify_delete(self, real_dm):
        from apps.samsung_notes.state_collector import capture_pre, verify
        title = _make_title("VerifyDelete")
        real_dm.notes.create_note(title, "to be deleted")
        pre = capture_pre(real_dm)
        matching = _find_by_title(real_dm, title)
        assert len(matching) == 1
        real_dm.notes.delete_notes([matching[0].id])
        gt = f"Delete the note titled '{title}'"
        result = verify(real_dm, "samsungnote", "delete", f"Delete {title}", gt, pre)
        assert result["verified"] is True, result.get("analysis")
        assert result["rating"] == 5

    def test_verify_read(self, real_dm):
        from apps.samsung_notes.state_collector import verify
        title = _make_title("VerifyRead")
        real_dm.notes.create_note(title, "the note content")
        gt = f"Read the note titled '{title}'"
        result = verify(real_dm, "samsungnote", "read", f"Read {title}", gt, None)
        assert result["verified"] is True, result.get("analysis")
        assert result["method"] == "xrclaw_read"

    def test_verify_modify(self, real_dm):
        from apps.samsung_notes.state_collector import capture_pre, verify
        title = _make_title("VerifyModify")
        real_dm.notes.create_note(title, "original content")
        pre = capture_pre(real_dm)
        matching = _find_by_title(real_dm, title)
        assert len(matching) == 1
        real_dm.notes.update_note(matching[0].id, content="appended text")
        gt = f"Modify the note titled '{title}' with content 'appended text'"
        result = verify(real_dm, "samsungnote", "modify", f"Modify {title}", gt, pre)
        assert result["rating"] >= 3, result.get("analysis")


# ═══════════════════════════════════════════════════════════════════
# Precondition System Tests
# ═══════════════════════════════════════════════════════════════════

class TestNotesPreconditions:
    """Test the precondition system with real XRClaw."""

    def test_precondition_creates_note_for_delete(self, real_dm):
        from apps.samsung_notes.precondition import setup
        title = _make_title("PrecondDelete")
        gt = f"Delete the note titled {title}"
        class MockQT:
            action = "delete"
        result = setup(real_dm, real_dm, MockQT(), f"Delete {title}", gt)
        assert result["passed"], result.get("failed")
        assert len(_find_by_title(real_dm, title)) == 1

    def test_precondition_creates_note_for_modify(self, real_dm):
        from apps.samsung_notes.precondition import setup
        title = _make_title("PrecondModify")
        gt = f"Modify the note titled {title} with content new text"
        class MockQT:
            action = "modify"
        result = setup(real_dm, real_dm, MockQT(), f"Modify {title}", gt)
        assert result["passed"], result.get("failed")
        assert len(_find_by_title(real_dm, title)) == 1

    def test_precondition_creates_note_for_read(self, real_dm):
        from apps.samsung_notes.precondition import setup
        title = _make_title("PrecondRead")
        gt = f"Read the note titled {title}"
        class MockQT:
            action = "read"
        result = setup(real_dm, real_dm, MockQT(), f"Read {title}", gt)
        assert result["passed"], result.get("failed")
        assert len(_find_by_title(real_dm, title)) == 1

    def test_precondition_skipped_for_create(self, real_dm):
        from apps.samsung_notes.precondition import setup
        class MockQT:
            action = "create"
        result = setup(real_dm, real_dm, MockQT(), "Create a note", "A note")
        assert result["passed"] is True
        assert result.get("skipped") is not None
