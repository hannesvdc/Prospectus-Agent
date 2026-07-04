"""Prompt text for the prospecting agent, one module per prompt type.

Each module exposes a `SYSTEM` string and a `build_user(...)` function that
returns the user-message text. Keeping prompts here (separate from the
orchestration code) makes them easy to read, diff, and tune in one place.
"""

# Shared sign-off rule — every outreach and follow-up email ends the same way:
# an optional "Best," and NO signature (the sender's mail client appends their
# own on send). Kept here so the three prompt modules never drift.
SIGNOFF_RULE = (
    'You may end with "Best,", but do NOT add a signature, sender name, title, '
    "company, or contact details — the sender's email client appends their own on send."
)
