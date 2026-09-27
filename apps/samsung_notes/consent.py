"""
Consent audio rules for Samsung Notes.

Maps (feature, action) → list of (wav_file, pause_seconds, wait_seconds).
Used by the consent player to play affirmation/confirmation audio after
the agent asks a follow-up question.
"""

# No consent audio needed for Samsung Notes
CONSENT_RULES = {}
