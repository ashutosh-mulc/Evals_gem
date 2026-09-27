"""
Consent audio rules for Samsung Message.

Maps (feature, action) → list of (wav_file, pause_seconds, wait_seconds).
"""

CONSENT_RULES = {
    ("message", "send"): [("Yes.wav", 18, 5)],
    ("message", "messagesend"): [("Yes.wav", 18, 5)],
    ("message", "messagereply"): [("Yes.wav", 18, 5)],
    ("message", "callsend"): [("Yes.wav", 18, 5)],
    ("message", "draft"): [("edit_message.wav", 18, 5), ("Yes.wav", 17, 5)],
}

