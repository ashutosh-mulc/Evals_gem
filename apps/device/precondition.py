"""
Preconditions for device-level evaluations.

Handles all device features:
- dnd:          Set DND to opposite state (on→off, off→on) so agent can toggle it.
- volume:       Set volume to known starting level (up→low, down→high).
- mediacontrol: Start media playing or paused depending on the action.
- notification: Post (read/auto) or clear (notread) notifications.
- datetime/battery: Skip (no precondition needed).
"""

from __future__ import annotations

import logging
import subprocess
import time

logger = logging.getLogger(__name__)


def _get_companion_device(dm):
    """Extract the companion device ADB serial from the device manager."""
    return getattr(dm, "companion_device", None) or getattr(dm, "device", "")


def _adb_shell(device, command):
    """Run an ADB shell command on the given device."""
    return subprocess.run(
        f"adb -s {device} shell {command}",
        shell=True, capture_output=True, text=True, timeout=15
    )


# ── DND ──────────────────────────────────────────────────────────

def _setup_dnd(dm, action):
    """Set DND to the opposite of the desired action.

    For 'on' action: start with DND off (so agent can turn it on).
    For 'off' action: start with DND on (so agent can turn it off).
    """
    device = _get_companion_device(dm)
    statecollector_dm = getattr(dm, "_dm", None) or dm

    # Determine target state: opposite of what the agent should do
    if action == "on":
        dnd_cmd = "off"  # Start with DND off
    elif action == "off":
        dnd_cmd = "on"   # Start with DND on
    else:
        return {
            "passed": True,
            "set": [],
            "checked": [],
            "failed": [],
            "skipped": f"No DND precondition for action='{action}'",
        }

    try:
        # Try XRClaw/mock method first (works for both mock and real devices)
        expected_enabled = (dnd_cmd == "on")
        if hasattr(statecollector_dm.device_info, 'set_dnd_mode'):
            statecollector_dm.device_info.set_dnd_mode(expected_enabled)
        else:
            # Fallback to ADB for real devices
            _adb_shell(device, f"cmd notification set_dnd {dnd_cmd}")
        time.sleep(1)

        # Verify via XRClaw DeviceInfoApp
        dnd_state = statecollector_dm.device_info.get_dnd_mode()
        actual_enabled = dnd_state.enabled

        if actual_enabled == expected_enabled:
            return {
                "passed": True,
                "set": [f"Set DND {dnd_cmd} (enabled={actual_enabled})"],
                "checked": [f"DND enabled={actual_enabled} (expected {expected_enabled})"],
                "failed": [],
                "skipped": None,
            }
        else:
            return {
                "passed": False,
                "set": [f"Set DND {dnd_cmd}"],
                "checked": [],
                "failed": [f"DND verification failed: enabled={actual_enabled}, expected={expected_enabled}"],
                "skipped": None,
            }
    except Exception as e:
        logger.error("Precondition: failed to set DND: %s", e)
        return {
            "passed": False,
            "set": [],
            "checked": [],
            "failed": [f"Failed to set DND via XRClaw: {e}"],
            "skipped": None,
        }


# ── Volume ───────────────────────────────────────────────────────

# All Android audio stream IDs and names
_STREAM_IDS = {
    0: "VOICE_CALL",
    1: "SYSTEM",
    2: "RING",
    3: "MUSIC",
    4: "ALARM",
    5: "NOTIFICATION",
    6: "BLUETOOTH_SCO",
    7: "SYSTEM_ENFORCED",
    8: "DTMF",
    9: "TTS",
    10: "ACCESSIBILITY",
    11: "ASSISTANT",
    12: "ENFORCED_AUDIBLE",
}


def _set_volume_on_device(device, direction):
    """Set volume on ALL streams of a single device to a percentage-based target.

    Args:
        device: ADB serial of the target device.
        direction: "low" (~10%), "high" (~90%), "mid" (50%), or "zero" (0).

    Returns:
        List of human-readable action strings (one per stream set).
    """
    from agent_testers.device_managers.adb_device_info import DeviceInfo

    di = DeviceInfo(device=device)
    vol_state = di.get_volume()
    stream_maxes = vol_state.get("all_streams", {})

    set_actions = []

    for stream_id, stream_name in _STREAM_IDS.items():
        # Look up this stream's max from device data (fallback to 15)
        sinfo = stream_maxes.get(stream_name, {})
        smax = sinfo.get("max", 15)
        if smax is None or smax <= 0:
            smax = 15

        if direction == "low":
            target = max(1, int(0.1 * smax))
        elif direction == "high":
            target = int(0.9 * smax)
        elif direction == "mid":
            target = int(0.5 * smax)
        elif direction == "zero":
            target = 0
        else:
            continue

        _adb_shell(device, f"media volume --stream {stream_id} --set {target}")
        set_actions.append(f"Set {stream_name} to {target} (max={smax})")

    return set_actions


def _setup_volume(dm, action):
    """Set volume to a known starting level on both Jinju and companion devices.

    For 'up'/'uprelative': start low (so agent can increase).
    For 'down'/'downrelative': start high (so agent can decrease).
    For 'mute': start unmuted.
    For 'unmute': start muted.
    For 'set': skip (query, not a change).
    """
    jinju_device = getattr(dm, "jinju_device", None) or getattr(dm, "device", "")
    companion_device = getattr(dm, "companion_device", None)

    # Target level directions
    volume_targets = {
        "up":          "low",   # 1 (near min)
        "uprelative":  "low",
        "down":        "high",  # max - 1 (near max)
        "downrelative": "high",
        "mute":        "mid",   # mid level, unmuted
        "unmute":      "zero",  # volume 0 (muted)
    }

    if action not in volume_targets:
        return {
            "passed": True,
            "set": [],
            "checked": [],
            "failed": [],
            "skipped": f"No volume precondition for action='{action}'",
        }

    direction = volume_targets[action]
    set_actions = []

    try:
        # Set volume on the Jinju device (all streams)
        set_actions.append(f"[Jinju:{jinju_device}]")
        set_actions += _set_volume_on_device(jinju_device, direction)

        # Set volume on the companion device (all streams) if available and distinct
        if companion_device and companion_device != jinju_device:
            set_actions.append(f"[Companion:{companion_device}]")
            set_actions += _set_volume_on_device(companion_device, direction)

        time.sleep(1)

        # Verify via DeviceInfo on both devices
        from agent_testers.device_managers.adb_device_info import DeviceInfo
        checked = []

        jinju_di = DeviceInfo(device=jinju_device)
        jinju_vol = jinju_di.get_volume()
        if jinju_vol.get("all_streams"):
            checked.append(f"Jinju volume streams read: {len(jinju_vol['all_streams'])} streams")
        else:
            return {
                "passed": False,
                "set": set_actions,
                "checked": [],
                "failed": ["Could not read Jinju volume after setting"],
                "skipped": None,
            }

        if companion_device and companion_device != jinju_device:
            comp_di = DeviceInfo(device=companion_device)
            comp_vol = comp_di.get_volume()
            if comp_vol.get("all_streams"):
                checked.append(f"Companion volume streams read: {len(comp_vol['all_streams'])} streams")
            else:
                return {
                    "passed": False,
                    "set": set_actions,
                    "checked": checked,
                    "failed": ["Could not read Companion volume after setting"],
                    "skipped": None,
                }

        return {
            "passed": True,
            "set": set_actions,
            "checked": checked,
            "failed": [],
            "skipped": None,
        }
    except Exception as e:
        logger.error("Precondition: failed to set volume: %s", e)
        return {
            "passed": False,
            "set": [],
            "checked": [],
            "failed": [f"Failed to set volume: {e}"],
            "skipped": None,
        }


# ── MediaControl ─────────────────────────────────────────────────

def _setup_mediacontrol(dm, action):
    """Set up media playback state for mediacontrol queries.

    For 'pause'/'skip'/'previous'/'like'/'dislike'/'seek'/'seekrelative': start with media playing.
    For 'play'/'resume'/'replay': start with media paused.
    """
    device = _get_companion_device(dm)
    statecollector_dm = getattr(dm, "_dm", None) or dm

    # Actions that need media playing first (so agent can pause/skip/like/dislike/seek)
    needs_playing = {"pause", "skip", "previous", "like", "dislike", "seek", "seekrelative"}
    # Actions that need media paused first (so agent can play/resume)
    needs_paused = {"play", "resume", "replay"}

    if action not in needs_playing and action not in needs_paused:
        return {
            "passed": True,
            "set": [],
            "checked": [],
            "failed": [],
            "skipped": f"No mediacontrol precondition for action='{action}'",
        }

    try:
        if action in needs_playing:
            expected_playing = True
        else:
            expected_playing = False

        # Try XRClaw/mock method first (works for both mock and real devices)
        if hasattr(statecollector_dm.device_info, 'set_media_playing'):
            statecollector_dm.device_info.set_media_playing(expected_playing)
        else:
            # Fallback to ADB for real devices
            # Start YouTube Music playback
            _adb_shell(device, "am start -n com.google.android.apps.youtube.music/.activities.MusicActivity")
            time.sleep(3)

            if action in needs_playing:
                # Send PLAY (keycode 126) to ensure media is playing
                _adb_shell(device, "input keyevent 126")  # KEYCODE_MEDIA_PLAY
                time.sleep(1)
            else:
                # Send PAUSE (keycode 127) to ensure media is paused
                _adb_shell(device, "input keyevent 127")  # KEYCODE_MEDIA_PAUSE
                time.sleep(1)

        # Verify state
        media = statecollector_dm.device_info.get_media()
        is_playing = media.get("playing", media.get("is_playing", False))

        if is_playing == expected_playing:
            return {
                "passed": True,
                "set": [f"Set media playing={is_playing} for {action} action"],
                "checked": [f"Media playing={is_playing} (expected {expected_playing})"],
                "failed": [],
                "skipped": None,
            }
        else:
            return {
                "passed": False,
                "set": [f"Set media for {action} action"],
                "checked": [],
                "failed": [f"Media playing={is_playing}, expected={expected_playing}"],
                "skipped": None,
            }
    except Exception as e:
        logger.error("Precondition: failed to set up mediacontrol: %s", e)
        return {
            "passed": False,
            "set": [],
            "checked": [],
            "failed": [f"Failed to set up mediacontrol: {e}"],
            "skipped": None,
        }


# ── Notification ─────────────────────────────────────────────────

def _setup_notification(dm, action, gt_answer):
    """Set up notification preconditions.

    For read/auto: post a test notification derived from gt_answer.
    For notread: clear all notifications so the panel is empty.
    """
    statecollector_dm = getattr(dm, "_dm", None) or dm

    if action == "notread":
        try:
            cleared = statecollector_dm.notifications.clear_all()
            logger.info("Precondition: cleared %d notification(s) for notread query", cleared)
            return {
                "passed": True,
                "set": [f"Cleared {cleared} existing notification(s)"],
                "checked": ["Notification panel is empty"],
                "failed": [],
                "skipped": None,
            }
        except Exception as e:
            logger.error("Precondition: failed to clear notifications: %s", e)
            return {
                "passed": False,
                "set": [],
                "checked": [],
                "failed": [f"Failed to clear notifications: {e}"],
                "skipped": None,
            }

    elif action in ("read", "auto"):
        try:
            title, content = gt_answer, ""
            if ":" in gt_answer:
                title, content = gt_answer.split(":", 1)
            statecollector_dm.notifications.post_notification(title.strip(), content.strip())
            logger.info("Precondition: posted notification '%s' for %s query", title, action)
            return {
                "passed": True,
                "set": [f"Posted notification '{title}'"],
                "checked": [f"Notification '{title}' exists on device"],
                "failed": [],
                "skipped": None,
            }
        except Exception as e:
            logger.error("Precondition: failed to post notification: %s", e)
            return {
                "passed": False,
                "set": [],
                "checked": [],
                "failed": [f"Failed to post notification: {e}"],
                "skipped": None,
            }

    return {
        "passed": True,
        "set": [],
        "checked": [],
        "failed": [],
        "skipped": f"No notification precondition for action='{action}'",
    }


# ── Main entry points ────────────────────────────────────────────

def setup(dm, sc, qt, question, gt_answer):
    """Set up preconditions for device-level queries.

    Dispatches to feature-specific handlers based on qt.feature.
    """
    feature = qt.feature  # "volume", "datetime", "battery", "dnd", "mediacontrol", "notification"
    action = qt.action    # "on", "off", "up", "down", "read", "notread", "auto", etc.

    # Features that need no precondition
    if feature in ("datetime", "battery"):
        return {
            "passed": True,
            "set": [],
            "checked": [],
            "failed": [],
            "skipped": f"No precondition needed for {feature}",
        }

    # Get XRClaw device manager — prefer sc._dm, fall back to dm
    # Store it on dm so feature handlers can access it
    statecollector_dm = getattr(sc, "_dm", None) if sc else None
    if statecollector_dm is not None:
        dm._dm = statecollector_dm

    if feature == "dnd":
        return _setup_dnd(dm, action)
    elif feature == "volume":
        return _setup_volume(dm, action)
    elif feature == "mediacontrol":
        return _setup_mediacontrol(dm, action)
    elif feature == "notification":
        return _setup_notification(dm, action, gt_answer)
    else:
        return {
            "passed": True,
            "set": [],
            "checked": [],
            "failed": [],
            "skipped": f"No precondition for feature='{feature}'",
        }


