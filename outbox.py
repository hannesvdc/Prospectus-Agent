"""Write ready-to-send outreach drafts after a run.

For every email drafted today it produces, under outbox/<date>/:
  - index.md  — one block per email (recipients + subject + body), for fast
                copy-paste.
  - <type>-<domain>.eml — an RFC822 draft you can double-click to open in your
                mail client (To/Subject/Body pre-filled; marked unsent).

Recipients: public addresses go in the To line; pattern-guessed addresses are
listed too (tagged) so you choose whether to include them.
"""
from __future__ import annotations

import os
import re
from datetime import date
from email.message import EmailMessage

import db


def _slug(domain: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (domain or "").lower()).strip("-") or "company"


def _split_contacts(contacts):
    public = [c for c in contacts if c["email_confidence"] == "public"]
    guessed = [c for c in contacts if c["email_confidence"] == "guessed"]
    return public, guessed


def _to_line(public, guessed) -> list[str]:
    """Addresses for the To: field — public if any, else the single best guess."""
    if public:
        return [c["email"] for c in public]
    return [guessed[0]["email"]] if guessed else []


def _build_eml(to_list: list[str], subject: str, body: str) -> bytes:
    # No From header — when you open the draft, your mail client fills in your
    # account and appends your signature on send.
    msg = EmailMessage()
    if to_list:
        msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg["X-Unsent"] = "1"  # opens as an editable draft in Outlook/compatible clients
    msg.set_content(body)
    return bytes(msg)


def _contact_label(c) -> str:
    who = ", ".join(p for p in (c["name"], c["role"]) if p)
    tag = c["email_confidence"] + (f" — {who}" if who else "")
    return f"- {c['email']}  ({tag})"


def generate(conn, *, out_root: str = "outbox", today: str | None = None):
    """Write today's drafts. Returns (out_dir, count) or None if nothing drafted."""
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
        to_list = _to_line(public, guessed)

        # .eml draft
        fname = f"{em['type']}-{_slug(company['domain'])}.eml"
        with open(os.path.join(out_dir, fname), "wb") as f:
            f.write(_build_eml(to_list, em["subject"], em["body"]))

        # markdown block
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
            md.append("> No published address found — the To: line uses the most likely guess; verify before sending.")
        md.append(f"\n**Subject:** {em['subject']}\n")
        md.append("**Body:**\n")
        md.append("```")
        md.append(em["body"])
        md.append("```")
        md.append("\n---\n")

    with open(os.path.join(out_dir, "index.md"), "w") as f:
        f.write("\n".join(md))

    return out_dir, len(emails)
