"""Prompts for follow-up email drafting."""
from __future__ import annotations

from prospectus_agent import agent_profile as profile
from prospectus_agent import config


def system() -> str:
    return (
        f"You write brief, courteous B2B follow-up emails for {profile.NAME}. "
        "Follow-ups are short, add a little new value or a gentle nudge, and never "
        "guilt-trip. Never invent facts about the recipient's company."
    )


def _voice_notes() -> str:
    """The seller's voice dos/don'ts (profile.voice_notes) — same personal tone the
    initial emails use, applied to follow-ups too."""
    if not profile.VOICE_NOTES:
        return ""
    notes = "\n".join(f"- {n}" for n in profile.VOICE_NOTES)
    return f"\nVoice notes for {profile.NAME} (apply these to the follow-up):\n{notes}\n"


def build_user(company_row, prior_block: str, on_profile: str) -> str:
    """`company_row` is a sqlite3.Row (name/domain/last_contact_date)."""
    return f"""About {profile.NAME}:
{on_profile}

We emailed {company_row['name']} ({company_row['domain']}) on
{company_row['last_contact_date']} and have had no reply after
{config.FOLLOWUP_BUSINESS_DAYS} business days.

{prior_block}

Write a short follow-up (about 60-100 words): reference the earlier note briefly,
restate the single most relevant way {profile.NAME} could help {company_row['name']},
and make it easy to decline. You may end with a short closing like "Best,", but do
NOT add a signature, sender name, or contact details — the sender's email client
appends their own signature.
{_voice_notes()}
Then call `submit_followup`.
"""
