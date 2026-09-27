"""
Device info filter — extracts only the relevant device state fields for a given
question_type and outputs them in compact XML format.

This reduces prompt noise by sending the VLM judge only the data it needs to
evaluate a specific query type (e.g., only volume pre/post for volume queries,
only media pre/post for mediacontrol queries).

Usage:
    from judge_worker.device_info_filter import filter_device_info

    filtered_xml = filter_device_info(device_info, question_type)
    # → "<device_state_pre><volume .../></device_state_pre>..."

Feature → Fields mapping:
    volume          → jinju.volume (pre + post)
    datetime_time   → jinju.time (post only)
    datetime_date   → jinju.date (post only)
    battery         → jinju.battery or companion.battery (post only)
    dnd             → companion.dnd_mode (pre + post)
    mediacontrol    → companion.media (pre + post)
    notification    → (empty — uses screenshot)
    camera / video  → (empty — uses image_captured flag)
    unknown         → full JSON (safe fallback)
"""

from __future__ import annotations

import json
from typing import Optional


# ── Feature detection ──────────────────────────────────────────────

def _get_feature(question_type: str) -> str:
    """Extract the feature category from a question_type string.

    Examples:
        "online_device_volume_up"          → "volume"
        "online_device_datetime_time"      → "datetime_time"
        "online_device_battery_glasses"     → "battery"
        "online_device_mediacontrol_play"  → "mediacontrol"
        "online_device_notification_read"  → "notification"
        "online_device_camera_click"       → "camera"
    """
    qt = (question_type or "").lower()
    parts = qt.split("_")
    if len(parts) < 4:
        return "unknown"

    group = parts[1]
    if group != "device":
        return "unknown"

    # Compound features: datetime_time, datetime_date, mediacontrol_*
    # parts[2] is the feature base, parts[3] may be a sub-feature or action
    feature_base = parts[2]

    if feature_base == "datetime":
        # datetime_time, datetime_date
        if len(parts) >= 4:
            return f"datetime_{parts[3]}"
        return "datetime"

    if feature_base == "mediacontrol":
        # For like/dislike, no device_info needed — app_state.log_analysis has the flags
        if len(parts) >= 4 and parts[3] in ("like", "dislike"):
            return "mediacontrol_like_dislike"
        return "mediacontrol"

    if feature_base == "notification":
        return "notification"

    if feature_base == "camera":
        return "camera"

    if feature_base == "video":
        return "video"

    # Simple features: volume, battery, dnd
    return feature_base


# ── XML formatting helpers ──────────────────────────────────────────

def _xml_attr(key: str, value) -> str:
    """Format a key=value pair as an XML attribute string."""
    if value is None:
        return ""
    # Convert Python bool to lowercase string for XML
    if isinstance(value, bool):
        val = "true" if value else "false"
    else:
        val = str(value)
    # Escape double quotes in value
    val = val.replace('"', '"')
    return f'{key}="{val}"'


def _xml_attrs(d: dict, keys: list[str]) -> str:
    """Build a string of XML attributes from a dict for the given keys."""
    parts = [_xml_attr(k, d.get(k)) for k in keys if d.get(k) is not None]
    return " ".join(parts)


def _format_volume(device_info: dict) -> str:
    """Format volume as XML elements for both jinju and companion devices."""
    parts = []

    for device_key, label in [("jinju", "volume"), ("companion", "companion_volume")]:
        dev = device_info.get(device_key, {})
        vol = dev.get("volume")
        if not vol:
            continue
        attrs = _xml_attrs(vol, ["muted", "min", "max", "current"])
        all_streams = vol.get("all_streams", {})

        if not all_streams:
            if attrs:
                parts.append(f"<{label} {attrs}/>")
            continue

        # Build child elements for each stream
        children = []
        for sname, sinfo in sorted(all_streams.items()):
            child_attrs = _xml_attrs(sinfo, ["streamVolume", "muted", "min", "max"])
            if child_attrs:
                children.append(f"  <stream name=\"{sname}\" {child_attrs}/>")
        if children:
            parts.append(f"<{label} {attrs}>\n" + "\n".join(children) + f"\n</{label}>")
        elif attrs:
            parts.append(f"<{label} {attrs}/>")

    return "\n".join(parts)


def format_volume_diff(device_info_pre: dict, device_info_post: dict) -> str:
    """Compare pre vs post volume and return XML showing only changed channels.

    Compares ``streamVolume`` and ``muted`` for every stream on both jinju and
    companion devices.  Returns an XML element with ``<changed_stream>`` children
    for each stream that differs, or a text element stating nothing changed.

    Args:
        device_info_pre: Full device_info snapshot from before the action.
        device_info_post: Full device_info snapshot from after the action.

    Returns:
        XML string wrapped in ``<volume_diff>`` tags.
    """
    if not device_info_pre or not device_info_post:
        return ""

    changed = []

    for device_key in ("jinju", "companion"):
        pre_vol = device_info_pre.get(device_key, {}).get("volume", {})
        post_vol = device_info_post.get(device_key, {}).get("volume", {})
        if not pre_vol or not post_vol:
            continue

        pre_streams = pre_vol.get("all_streams", {})
        post_streams = post_vol.get("all_streams", {})

        # Check top-level muted change
        pre_muted = pre_vol.get("muted")
        post_muted = post_vol.get("muted")
        if pre_muted != post_muted:
            changed.append(
                f'  <changed_stream device="{device_key}" name="master_muted" '
                f'pre="{pre_muted}" post="{post_muted}"/>'
            )

        # Check each stream
        all_names = sorted(set(pre_streams) | set(post_streams))
        for sname in all_names:
            pre_s = pre_streams.get(sname, {})
            post_s = post_streams.get(sname, {})
            pre_vol_val = pre_s.get("streamVolume")
            post_vol_val = post_s.get("streamVolume")
            pre_s_muted = pre_s.get("muted")
            post_s_muted = post_s.get("muted")

            if pre_vol_val != post_vol_val or pre_s_muted != post_s_muted:
                delta = ""
                if pre_vol_val is not None and post_vol_val is not None:
                    try:
                        d = int(post_vol_val) - int(pre_vol_val)
                        delta = f' delta="{"+" if d >= 0 else ""}{d}"'
                    except (ValueError, TypeError):
                        pass
                changed.append(
                    f'  <changed_stream device="{device_key}" name="{sname}" '
                    f'pre="{pre_vol_val}" post="{post_vol_val}"{delta}/>'
                )

    if not changed:
        return "<volume_diff>No volume channels changed!</volume_diff>"

    return "<volume_diff>\n" + "\n".join(changed) + "\n</volume_diff>"


def _format_time(device_info: dict) -> str:
    """Format jinju.time as an XML element."""
    jinju = device_info.get("jinju", {})
    t = jinju.get("time")
    if not t:
        return ""
    attrs = _xml_attrs(t, ["datetime_str", "timezone", "epoch_ms"])
    return f"<time {attrs}/>" if attrs else ""


def _format_date(device_info: dict) -> str:
    """Format jinju.date as an XML element."""
    jinju = device_info.get("jinju", {})
    d = jinju.get("date")
    if not d:
        return ""
    attrs = _xml_attrs(d, ["day", "month", "year", "day_of_week"])
    return f"<date {attrs}/>" if attrs else ""


def _format_battery(device_info: dict, target: str = "jinju") -> str:
    """Format battery info as an XML element.

    Args:
        device_info: Full device info dict
        target: "jinju" or "companion" — which device's battery to use
    """
    dev = device_info.get(target, {})
    bat = dev.get("battery")
    if not bat:
        return ""
    attrs = _xml_attrs(bat, ["level", "status", "charging"])
    return f"<battery {attrs}/>" if attrs else ""


def _format_dnd(device_info: dict) -> str:
    """Format companion.dnd_mode as an XML element."""
    companion = device_info.get("companion", {})
    dnd = companion.get("dnd_mode")
    if dnd is None:
        return ""
    return f"<dnd_mode>{dnd}</dnd_mode>"


def _format_media(device_info: dict) -> str:
    """Format companion.media as an XML element."""
    companion = device_info.get("companion", {})
    media = companion.get("media")
    if not media:
        return ""
    attrs = _xml_attrs(media, [
        "active", "playing", "state", "package",
        "title", "artist", "album", "position_ms", "speed",
    ])
    return f"<media {attrs}/>" if attrs else ""


# ── Feature → formatter dispatch ───────────────────────────────────

# Features that need pre + post comparison
_PRE_POST_FEATURES = {"volume", "dnd", "mediacontrol"}

# Features that only need post state
_POST_ONLY_FEATURES = {"datetime_time", "datetime_date"}

# Features that need no device info (use app_state.log_analysis or screenshots instead)
_NO_INFO_FEATURES = {"notification", "camera", "video", "mediacontrol_like_dislike"}


def _format_feature(device_info: dict, feature: str) -> str:
    """Format a single device_info snapshot for the given feature.

    Returns an XML element string, or empty string if no data.
    """
    if feature == "volume":
        return _format_volume(device_info)
    elif feature == "datetime_time":
        return _format_time(device_info)
    elif feature == "datetime_date":
        return _format_date(device_info)
    elif feature == "battery":
        return _format_battery(device_info, "jinju")
    elif feature == "dnd":
        return _format_dnd(device_info)
    elif feature == "mediacontrol":
        return _format_media(device_info)
    return ""


def _resolve_battery_target(question_type: str) -> str:
    """Determine which device's battery to use based on the question_type action.

    'glasses' → jinju, 'companion'/'phone' → companion
    """
    qt = (question_type or "").lower()
    if "glasses" in qt:
        return "jinju"
    if "companion" in qt or "phone" in qt:
        return "companion"
    return "jinju"  # default


# ── Main entry point ───────────────────────────────────────────────

def filter_device_info(device_info: Optional[dict], question_type: str) -> str:
    """Filter device_info to only the relevant fields for the given question_type.

    Args:
        device_info: Full device info dict (with 'jinju' and 'companion' keys),
                     or None/empty.
        question_type: The question type string (e.g., "online_device_volume_up").

    Returns:
        XML string with only the relevant device state fields, or empty string
        if no device info is needed. For unknown features, returns the full JSON
        as a safe fallback.
    """
    if not device_info:
        return ""

    feature = _get_feature(question_type)

    # No device info needed for these features
    if feature in _NO_INFO_FEATURES:
        return ""

    # Unknown feature — return full JSON as safe fallback
    if feature == "unknown":
        return json.dumps(device_info, indent=2)

    # Battery needs special handling — target depends on action (glasses vs companion)
    if feature == "battery":
        target = _resolve_battery_target(question_type)
        element = _format_battery(device_info, target)
        if not element:
            return ""
        return f"<device_state>\n  {element}\n</device_state>"

    # Pre + post features
    if feature in _PRE_POST_FEATURES:
        element = _format_feature(device_info, feature)
        if not element:
            return ""
        return f"<device_state>\n  {element}\n</device_state>"

    # Post-only features
    if feature in _POST_ONLY_FEATURES:
        element = _format_feature(device_info, feature)
        if not element:
            return ""
        return f"<device_state>\n  {element}\n</device_state>"

    # Fallback: full JSON
    return json.dumps(device_info, indent=2)
