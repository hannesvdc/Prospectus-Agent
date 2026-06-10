"""Prompts for follow-up email drafting."""
from __future__ import annotations

import config

SYSTEM = (
    "You write brief, courteous B2B follow-up emails for Open Numerics. "
    "Follow-ups are short, add a little new value or a gentle nudge, and never "
    "guilt-trip. Never invent facts about the recipient's company."
)


def build_user(company_row, prior_block: str, on_profile: str) -> str:
    """`company_row` is a sqlite3.Row (name/domain/last_contact_date)."""
    return f"""About Open Numerics:
{on_profile}

We emailed {company_row['name']} ({company_row['domain']}) on
{company_row['last_contact_date']} and have had no reply after
{config.FOLLOWUP_BUSINESS_DAYS} business days.

{prior_block}

Write a short follow-up (about 60-100 words): reference the earlier note briefly,
restate the single most relevant way ON could help {company_row['name']}, and make
it easy to decline. You may end with a short closing like "Best,", but do NOT add
a signature, sender name, or contact details — the sender's email client appends
their own signature. Then call `submit_followup`.
"""
