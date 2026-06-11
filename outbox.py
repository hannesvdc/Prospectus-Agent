"""Write a ready-to-review markdown digest of the drafts after a run.

For every email drafted today it produces `outbox/<date>/index.md` — one block per
email (recipients + subject + body), ready to copy-paste into your mail client.

Recipients: public addresses are listed first, then pattern-guessed ones (tagged),
so you choose whom to include.
"""
from __future__ import annotations

import os
from datetime import date

import db


def _split_contacts(contacts):
    public = [c for c in contacts if c["email_confidence"] == "public"]
    guessed = [c for c in contacts if c["email_confidence"] == "guessed"]
    return public, guessed


def _contact_label(c) -> str:
    who = ", ".join(p for p in (c["name"], c["role"]) if p)
    tag = c["email_confidence"] + (f" — {who}" if who else "")
    return f"- {c['email']}  ({tag})"


def generate(conn, *, out_root: str = "outbox", today: str | None = None):
    """Write today's drafts to <out_root>/<date>/index.md.
    Returns (out_dir, count) or None if nothing was drafted today."""
    today = today or date.today().isoformat()
    emails = db.emails_on(conn, today)
    if not emails:
        return None

    out_dir = os.path.join(out_root, today)
    os.makedirs(out_dir, exist_ok=True)

    md: list[str] = [f"# Outreach drafts — {today}\n"]
    for em in emails:
        company = db.get_company(conn, em["company_id"])
        if company is None:
            continue
        contacts = db.get_contacts(conn, em["company_id"])
        public, guessed = _split_contacts(contacts)

        kind = " (follow-up)" if em["type"] == "followup" else ""
        md.append(f"## {company['name']} ({company['domain']}){kind}")
        meta = " · ".join(p for p in (company["industry"], company["hq_location"]) if p)
        if meta:
            md.append(f"_{meta}_")
        md.append("\n**Send to:**")
        if contacts:
            md.extend(_contact_label(c) for c in contacts)
        else:
            md.append("- (no contacts found)")
        if not public and guessed:
            md.append("> No published address found — these are best-guess addresses; verify before sending.")
        md.append(f"\n**Subject:** {em['subject']}\n")
        md.append("**Body:**\n")
        md.append("```")
        md.append(em["body"])
        md.append("```")
        md.append("\n---\n")

    with open(os.path.join(out_dir, "index.md"), "w") as f:
        f.write("\n".join(md))

    return out_dir, len(emails)
