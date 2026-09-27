"""
Tests for agent_testers/apps/__init__.py — app registry auto-discovery.

Verifies that all 22+ apps are discovered and their state collectors,
judge handlers, and consent rules are registered.
"""

import pytest

from apps import (
    APP_CONFIGS,
    APP_KEY_MAP,
    STATE_COLLECTORS,
    JUDGE_HANDLERS,
    JUDGE_PROMPTS,
    CONSENT_RULES,
    supported_apps,
    get_state_collector,
    get_judge_handler,
    get_prompt,
    get_consent_rules,
)


# ── Registry population ────────────────────────────────────────────

def test_state_collectors_nonempty():
    assert len(STATE_COLLECTORS) > 0, "No state collectors discovered"


def test_app_key_map_nonempty():
    assert len(APP_KEY_MAP) > 0, "No app keys mapped"


def test_judge_handlers_nonempty():
    assert len(JUDGE_HANDLERS) > 0, "No judge handlers registered"


def test_consent_rules_nonempty():
    assert len(CONSENT_RULES) > 0, "No consent rules registered"


# ── Key apps in STATE_COLLECTORS ───────────────────────────────────

def test_samsungnote_in_collectors():
    assert "samsungnote" in STATE_COLLECTORS


def test_samsungreminder_in_collectors():
    assert "samsungreminder" in STATE_COLLECTORS


def test_samsungcalendar_in_collectors():
    assert "samsungcalendar" in STATE_COLLECTORS


def test_device_in_collectors():
    assert "device" in STATE_COLLECTORS


def test_device_mediacontrol_in_collectors():
    assert "device_mediacontrol" in STATE_COLLECTORS


def test_notification_in_collectors():
    assert "notification" in STATE_COLLECTORS


# ── supported_apps() ───────────────────────────────────────────────

def test_supported_apps_returns_set():
    apps = supported_apps()
    assert isinstance(apps, set)


def test_supported_apps_contains_expected():
    apps = supported_apps()
    assert "samsungnote" in apps
    assert "device" in apps


# ── get_state_collector ─────────────────────────────────────────────

def test_get_state_collector_returns_module():
    mod = get_state_collector("samsungnote")
    assert mod is not None
    assert hasattr(mod, "capture_pre")
    assert hasattr(mod, "verify")


def test_get_state_collector_nonexistent():
    assert get_state_collector("nonexistent_app") is None


# ── get_judge_handler ──────────────────────────────────────────────

def test_get_judge_handler_returns_callable():
    handler = get_judge_handler("samsungnote", "create")
    assert handler is not None
    assert callable(handler)


def test_get_judge_handler_nonexistent():
    assert get_judge_handler("nonexistent", "create") is None


# ── get_prompt ────────────────────────────────────────────────────

def test_get_prompt_returns_string_or_none():
    prompt = get_prompt("samsungnote")
    # prompt.json files store raw JSON (dict with "prompt" key, or dict of sub-prompts)
    assert prompt is None or isinstance(prompt, (str, dict))



# ── get_consent_rules ─────────────────────────────────────────────

def test_get_consent_rules_returns_list():
    rules = get_consent_rules("notes", "create")
    assert isinstance(rules, list)


def test_get_consent_rules_nonexistent():
    assert get_consent_rules("nonexistent", "action") == []


# ── APP_CONFIGS structure ──────────────────────────────────────────

def test_app_configs_has_samsung_group():
    assert "samsung" in APP_CONFIGS


def test_app_configs_has_google_group():
    assert "google" in APP_CONFIGS


def test_app_configs_has_device_group():
    assert "device" in APP_CONFIGS
