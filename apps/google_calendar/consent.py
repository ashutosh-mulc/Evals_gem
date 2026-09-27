"""
Consent audio rules for Google Calendar.

Maps (feature, action) → list of (wav_file, pause_seconds, wait_seconds).
"""

CONSENT_RULES = {
    ("calendar", "create"): [("Yes.wav", 18, 5)],
    ("calendar", "modify"): [("Yes.wav", 18, 5)],
    ("calendar", "delete"): [("Yes.wav", 18, 5)],
}

