"""Write a ready-to-review markdown digest of the drafts after a run.

Produces `outbox/<date>/index.md` — one block per email (recipients + subject +
body), ready to copy-paste into your mail client. Running the agent again on the
same day **appends** that run's new drafts to the existing file rather than
overwriting it, so earlier drafts (and any notes you added) are preserved.

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


def _email_block(conn, em) -> str | None:
    company = db.get_company(conn, em["company_id"])
    if company is None:
        return None
    contacts = db.get_contacts(conn, em["company_id"])
    public, guessed = _split_contacts(contacts)

    lines = []
    kind = " (follow-up)" if em["type"] == "followup" else ""
    lines.append(f"## {company['name']} ({company['domain']}){kind}")
    meta = " · ".join(p for p in (company["industry"], company["hq_location"]) if p)
    if meta:
        lines.append(f"_{meta}_")
    lines.append("\n**Send to:**")
    if contacts:
        lines.extend(_contact_label(c) for c in contacts)
    else:
        lines.append("- (no contacts found)")
    if not public and guessed:
        lines.append("> No published address found — these are best-guess addresses; verify before sending.")
    lines.append(f"\n**Subject:** {em['subject']}\n")
    lines.append("**Body:**\n")
    lines.append("```")
    lines.append(em["body"])
    lines.append("```")
    lines.append("\n---\n")
    return "\n".join(lines)


def generate(conn, *, out_root: str = "outbox", today: str | None = None,
             since_email_id: int | None = None):
    """Write today's drafts to <out_root>/<date>/index.md, appending if the file
    already exists. With `since_email_id`, only emails newer than that id (i.e.
    this run's drafts) are written — so re-running the same day augments the file.
    Returns (out_dir, count) or None if there's nothing new to write."""
    today = today or date.today().isoformat()
    emails = db.emails_on(conn, today)
    if since_email_id is not None:
        emails = [e for e in emails if e["id"] > since_email_id]
    blocks = [b for b in (_email_block(conn, em) for em in emails) if b]
    if not blocks:
        return None

    out_dir = os.path.join(out_root, today)
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "index.md")

    file_exists = os.path.exists(path)
    with open(path, "a" if file_exists else "w") as f:
        if not file_exists:
            f.write(f"# Outreach drafts — {today}\n\n")
        f.write("\n".join(blocks) + "\n")

    return out_dir, len(blocks)
