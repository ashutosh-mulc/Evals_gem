"""
Tests for agent_testers/apps/helpers.py — shared helper functions.

Tests keyword extraction, content extraction, overlap detection,
pre-state diffing, and result builders.
"""

import pytest

from apps.helpers import (
    extract_keyword,
    extract_content_from_gt,
    content_overlaps,
    pre_items_by_id,
    new_or_changed,
    result,
    unsupported_result,
    error_result,
)


# ── extract_keyword ────────────────────────────────────────────────

def test_extract_keyword_quoted():
    assert extract_keyword("A note titled 'Shopping List' with content") == "shopping list"


def test_extract_keyword_double_quoted():
    assert extract_keyword('A note titled "Shopping List"') == "shopping list"


def test_extract_keyword_title_pattern():
    assert extract_keyword("Title: Meeting Notes") == "meeting notes"


def test_extract_keyword_note_title_pattern():
    assert extract_keyword("Note Title: Shopping List, with content") == "shopping list"


def test_extract_keyword_time_pattern():
    result = extract_keyword("Set alarm for 7:30am")
    assert "7" in result and "30" in result


def test_extract_keyword_fallback_words():
    result = extract_keyword("create reminder about calling dentist")
    assert "calling" in result or "dentist" in result


def test_extract_keyword_empty():
    assert extract_keyword("") == ""


# ── extract_content_from_gt ────────────────────────────────────────

def test_extract_content_with_keyword():
    assert extract_content_from_gt("A note with content 'milk and eggs'") == "milk and eggs"


def test_extract_content_two_quotes():
    assert extract_content_from_gt("'Shopping List' with 'milk and eggs'") == "milk and eggs"


def test_extract_content_with_add():
    result = extract_content_from_gt("Add a banana to your shopping list")
    assert "banana" in result or "shopping" in result


def test_extract_content_empty():
    assert extract_content_from_gt("no content here") == ""


# ── content_overlaps ───────────────────────────────────────────────

def test_content_overlaps_true():
    assert content_overlaps("note with milk and eggs", "milk and eggs") is True


def test_content_overlaps_false():
    assert content_overlaps("note about books", "milk and eggs") is False


def test_content_overlaps_empty_content():
    assert content_overlaps("anything", "") is False


def test_content_overlaps_empty_gt():
    assert content_overlaps("", "some content") is False


# ── pre_items_by_id ───────────────────────────────────────────────

def test_pre_items_by_id_valid():
    pre = {"notes": [{"id": "1", "title": "Test"}]}
    result = pre_items_by_id(pre, "notes")
    assert result is not None
    assert "1" in result
    assert result["1"]["title"] == "Test"


def test_pre_items_by_id_empty():
    assert pre_items_by_id({}, "notes") is None


def test_pre_items_by_id_none():
    assert pre_items_by_id(None, "notes") is None


def test_pre_items_by_id_missing_key():
    assert pre_items_by_id({"reminders": []}, "notes") is None


# ── new_or_changed ─────────────────────────────────────────────────

class MockItem:
    """Simple mock item with to_dict()."""
    def __init__(self, id, title, content=""):
        self.id = id
        self.title = title
        self.content = content
    def to_dict(self):
        return {"id": self.id, "title": self.title, "content": self.content}


def test_new_or_changed_finds_new():
    items = [MockItem("1", "New Note", "content")]
    pre_by_id = {}
    result = new_or_changed(items, pre_by_id, ("title", "content"))
    assert len(result) == 1


def test_new_or_changed_finds_modified():
    items = [MockItem("1", "Modified Title", "content")]
    pre_by_id = {"1": {"id": "1", "title": "Old Title", "content": "content"}}
    result = new_or_changed(items, pre_by_id, ("title", "content"))
    assert len(result) == 1


def test_new_or_changed_skips_unchanged():
    items = [MockItem("1", "Same Title", "Same Content")]
    pre_by_id = {"1": {"id": "1", "title": "Same Title", "content": "Same Content"}}
    result = new_or_changed(items, pre_by_id, ("title", "content"))
    assert len(result) == 0


# ── result builders ───────────────────────────────────────────────

def test_result_builder():
    r = result("samsungnote", True, 5, "analysis text", {"a": 1}, "expected answer")
    assert r["method"] == "xrclaw"
    assert r["app_name"] == "samsungnote"
    assert r["verified"] is True
    assert r["rating"] == 5
    assert r["analysis"] == "analysis text"
    assert r["actual_state"] == {"a": 1}
    assert r["expected"] == "expected answer"


def test_unsupported_result_builder():
    r = unsupported_result("unknownapp", "expected")
    assert r["method"] == "xrclaw_unsupported"
    assert r["verified"] is False
    assert r["rating"] == 0
    assert r["expected"] == "expected"


def test_error_result_builder():
    r = error_result("samsungnote", "expected", "some error")
    assert r["method"] == "xrclaw_error"
    assert r["verified"] is False
    assert r["rating"] == 0
    assert "some error" in r["analysis"]
    assert r["expected"] == "expected"
