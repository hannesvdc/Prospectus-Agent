"""Prompt fragments shared across more than one prompt type."""
from __future__ import annotations

import config

# Injected into every outreach prompt. North America => CAN-SPAM applies.
CANSPAM_GUIDANCE = (
    "Compliance (CAN-SPAM): the subject line must be accurate and non-deceptive; "
    "clearly identify the sender and that this is outreach from Open Numerics; "
    "include the sender's name, company, and a physical postal address in the "
    "sign-off; and keep an easy, polite opt-out (e.g. 'reply and I won't follow up')."
)


def sender_block() -> str:
    """Sender identity, formatted for inclusion in an outreach prompt. Missing
    fields are flagged so the model (and you) notice the gap."""
    s = config.SENDER
    return (
        "Sender identity for the sign-off:\n"
        f"- Name: {s['name'] or '(missing — fill SENDER_NAME in .env)'}\n"
        f"- Title: {s['title'] or '(none)'}\n"
        f"- Company: {s['company']}\n"
        f"- Email: {s['email'] or '(missing — fill SENDER_EMAIL in .env)'}\n"
        f"- Physical address: {s['physical_address'] or '(missing — fill SENDER_PHYSICAL_ADDRESS in .env)'}"
    )
