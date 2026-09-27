"""
Consent audio rules for Thirdparty Whatsapp.

Maps (feature, action) → list of (wav_file, pause_seconds, wait_seconds).
"""

CONSENT_RULES = {
    ("whatsapp", "messagesend"): [("Yes.wav", 18, 5)],
    ("whatsapp", "messagereply"): [("Yes.wav", 18, 5)],
    ("whatsapp", "send"): [("Yes.wav", 18, 5)],
    ("whatsapp", "callsend"): [("Yes.wav", 18, 5)],
}

