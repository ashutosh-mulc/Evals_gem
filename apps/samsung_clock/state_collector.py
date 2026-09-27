"""
State collector for Samsung Clock (generic launch).

This directory handles the generic "clock" feature (e.g. clock_launch).
The alarm/stopwatch/timer-specific state collectors live in their own
directories (samsung_clock_alarm, samsung_clock_stopwatch, samsung_clock_timer)
and register the real XRClaw-based collectors under the same app_key.

APP_KEYS is intentionally empty so this stub does NOT register in
STATE_COLLECTORS — the real collector from samsung_clock_alarm takes effect.
"""

APP_KEYS = ()
ACCESSOR = None

