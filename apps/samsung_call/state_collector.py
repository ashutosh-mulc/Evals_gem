"""
State collector for Samsung Call.

Uses XRClaw's PhoneApp (dm.phone) to query call records for verification.
Supports modes: launch, send, videostart, disambiguation, notsend.
"""

from __future__ import annotations

from ..helpers import (
    result,
    verify_launch,
)

APP_KEYS = ("call",)
PACKAGE_NAME = "com.samsung.android.dialer"


def _find_call_records(dm) -> list:
    """Fetch call records via XRClaw PhoneApp."""
    try:
        return dm.phone.find_call_records()
    except Exception:
        return []


def _records_to_dicts(records: list) -> list:
    """Convert CallRecord objects to dicts."""
    return [r.to_dict() for r in records]


def _record_ids(records: list) -> set:
    """Extract a set of call record IDs."""
    return {r.id for r in records}


def _new_records(post_records: list, pre_ids: set) -> list:
    """Return records that are new (not in pre-state)."""
    return [r for r in post_records if r.id not in pre_ids]


def _extract_phone_number(text: str) -> str:
    """Extract a phone number from a question or gt_answer string."""
    import re
    match = re.search(r'(\+?\d[\d\s\-]{6,})', text)
    if match:
        return re.sub(r'[\s\-]', '', match.group(1))
    return ""


def capture_pre(dm) -> dict:
    """Snapshot current call record IDs before the agent acts.

    Only IDs are stored — used for diffing in verify().  Full record data
    is never sent to the judge; only the delta (new records) is.
    """
    records = _find_call_records(dm)
    return {
        "call_record_ids": list(_record_ids(records)),
        "count": len(records),
    }


def verify(dm, app_key, mode, question, gt_answer, pre_state=None) -> dict:
    """Verify Samsung Call state after the agent has acted.

    Modes:
      - launch: verify dialer is in foreground
      - send: verify a new outgoing call was made
      - videostart: verify a new outgoing video call was made
      - disambiguation: verify a new outgoing call was made
      - notsend: verify NO new call was made
    """
    app_name = app_key

    # ── Launch mode: verify dialer is in foreground ──
    if mode == "launch":
        return verify_launch(dm, app_name, PACKAGE_NAME, "Samsung Dialer", gt_answer)

    # ── Query post-state call records ──
    post_records = _find_call_records(dm)

    # Compute pre-state IDs for diffing
    pre_ids = set(pre_state.get("call_record_ids", [])) if pre_state else None
    new_records = _new_records(post_records, pre_ids) if pre_ids is not None else post_records

    # Only send the delta (newly added records) to avoid false positives
    actual_state = {
        "new_calls": _records_to_dicts(new_records),
        "new_call_count": len(new_records),
    }

    # ── Notsend mode: verify NO new call was made ──
    if mode == "notsend":
        verified = len(new_records) == 0
        rating = 5 if verified else 0
        analysis = (
            f"Notsend verification: {len(new_records)} new call(s) detected "
            f"(pre: {len(pre_ids) if pre_ids else 'N/A'}, post: {len(post_records)}). "
            f"{'No new calls — correct refusal.' if verified else 'New call(s) were made — should not have called.'}"
        )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # ── Send / videostart / disambiguation: verify new outgoing call ──
    expected_number = _extract_phone_number(question) or _extract_phone_number(gt_answer)

    outgoing_new = [r for r in new_records if r.call_type.upper() == "OUTGOING"]
    actual_state["new_outgoing_calls"] = _records_to_dicts(outgoing_new)

    if not outgoing_new:
        verified = False
        rating = 0
        analysis = (
            f"Call verification: no new outgoing call found. "
            f"Pre: {len(pre_ids) if pre_ids else 'N/A'} records, "
            f"Post: {len(post_records)} records, "
            f"New: {len(new_records)} (0 outgoing). "
            f"Expected a call to '{expected_number or 'unknown number'}'."
        )
        return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # For videostart: check if the call was a video call
    if mode == "videostart":
        video_calls = [r for r in outgoing_new if r.is_video_call]
        if not video_calls:
            verified = False
            rating = 2
            analysis = (
                f"Video call verification: {len(outgoing_new)} new outgoing call(s) found, "
                f"but none are video calls. "
                f"Call to '{outgoing_new[0].phone_number}'."
            )
            return result(app_name, verified, rating, analysis, actual_state, gt_answer)

    # Verify the phone number matches (if we extracted one)
    if expected_number:
        matching = [r for r in outgoing_new if expected_number in r.phone_number or r.phone_number in expected_number]
        if matching:
            verified = True
            rating = 5
            call = matching[0]
            analysis = (
                f"Call verification: new outgoing call to '{call.phone_number}' "
                f"(type={call.call_type}, video={call.is_video_call}). "
                f"Matches expected number '{expected_number}'."
            )
        else:
            verified = False
            rating = 2
            numbers = [r.phone_number for r in outgoing_new]
            analysis = (
                f"Call verification: new outgoing call(s) made to {numbers}, "
                f"but expected '{expected_number}'. Number mismatch."
            )
    else:
        # No number to compare — just verify a call was made
        verified = True
        rating = 4
        call = outgoing_new[0]
        analysis = (
            f"Call verification: new outgoing call to '{call.phone_number}' "
            f"(type={call.call_type}, video={call.is_video_call}). "
            f"Could not extract expected number from question — verifying call was made only."
        )

    return result(app_name, verified, rating, analysis, actual_state, gt_answer)
