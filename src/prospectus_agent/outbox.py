"""Write a ready-to-review digest of the drafts after a run.

Under `outbox/<date>/`, new prospect emails and follow-ups are written to separate
files, each as a markdown + HTML pair:
  * `new_prospects.md` / `new_prospects.html` — initial outreach drafts.
  * `followups.md`     / `followups.html`     — follow-up drafts.

The `.md` is easy to skim and copy as plain text; the `.html` renders the body as
rich HTML with the seller's name turned into a real <a href> link, so copying the
body from a browser and pasting into Gmail preserves the hyperlink (Gmail keeps links
only on rich-text paste, not markdown). Open the `.html` in a browser to copy from.

Running the agent again on the same day **appends** that run's new drafts rather than
overwriting them, so earlier drafts (and notes you added) survive.

Recipients: public addresses are listed first, then pattern-guessed ones (tagged),
so you choose whom to include.
"""
from __future__ import annotations

import html
import os
import re
from datetime import date

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent import db


def _split_contacts(contacts):
    public = [c for c in contacts if c["email_confidence"] == "public"]
    guessed = [c for c in contacts if c["email_confidence"] == "guessed"]
    return public, guessed


def _contact_label(c) -> str:
    who = ", ".join(p for p in (c["name"], c["role"]) if p)
    tag = c["email_confidence"] + (f" — {who}" if who else "")
    return f"- {c['email']}  ({tag})"


def _recipient_line(contacts) -> str:
    """Comma-separated address list to paste straight into Gmail's To: field. Includes
    all published addresses but only the TOP guess per person — so casting a wider net
    of format guesses (listed in full above) doesn't turn this into a 15-address line
    you'd accidentally send to. Verify the right format before sending."""
    seen, emails, guessed_people = set(), [], set()
    for c in contacts:
        e = (c["email"] or "").strip()
        if not e or e in seen:
            continue
        if c["email_confidence"] == "guessed":
            person = (c["name"] or "").lower()
            if person in guessed_people:
                continue  # keep only the first (most-likely) guess for this person
            guessed_people.add(person)
        seen.add(e)
        emails.append(e)
    return ", ".join(emails)


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
    recipients = _recipient_line(contacts)
    if recipients:
        lines.append(f"\n**To (copy):** `{recipients}`")
    lines.append(f"\n**Subject:** {em['subject']}\n")
    lines.append("**Body:**\n")
    lines.append("```")
    lines.append(em["body"])
    lines.append("```")
    lines.append("\n---\n")
    return "\n".join(lines)


def _linkify_body(body: str) -> str:
    """HTML-escape the body, turn newlines into <br>, and hyperlink EVERY mention
    of the seller's name to its website so Gmail keeps the links on paste. (The
    subject/title is rendered separately and is intentionally left unlinked.)"""
    esc = html.escape(body)
    name, site = agent_profile.NAME, agent_profile.WEBSITE
    if name and site:
        # Replace every occurrence of the escaped name with an anchor. The
        # replacement contains the name itself, but re.sub won't re-scan inserted
        # text, so already-linked mentions aren't double-wrapped.
        link = f'<a href="{html.escape(site)}">{html.escape(name)}</a>'
        esc = re.sub(re.escape(html.escape(name)), lambda _m: link, esc)
    return esc.replace("\n", "<br>\n")


def _email_block_html(conn, em) -> str | None:
    company = db.get_company(conn, em["company_id"])
    if company is None:
        return None
    contacts = db.get_contacts(conn, em["company_id"])
    public, guessed = _split_contacts(contacts)

    kind = " (follow-up)" if em["type"] == "followup" else ""
    parts = [f"<h2>{html.escape(company['name'])} "
             f"({html.escape(company['domain'])}){kind}</h2>"]
    meta = " · ".join(p for p in (company["industry"], company["hq_location"]) if p)
    if meta:
        parts.append(f"<p><em>{html.escape(meta)}</em></p>")

    parts.append("<p><strong>Send to:</strong></p><ul>")
    if contacts:
        for c in contacts:
            who = ", ".join(p for p in (c["name"], c["role"]) if p)
            tag = c["email_confidence"] + (f" — {who}" if who else "")
            parts.append(f"<li>{html.escape(c['email'])} "
                         f"({html.escape(tag)})</li>")
    else:
        parts.append("<li>(no contacts found)</li>")
    parts.append("</ul>")
    if not public and guessed:
        parts.append("<p><em>No published address found — these are best-guess "
                     "addresses; verify before sending.</em></p>")
    recipients = _recipient_line(contacts)
    if recipients:
        parts.append(f"<p><strong>To (copy):</strong> "
                     f"<code>{html.escape(recipients)}</code></p>")

    parts.append(f"<p><strong>Subject:</strong> {html.escape(em['subject'])}</p>")
    parts.append("<p><strong>Body</strong> (copy from here into Gmail):</p>")
    parts.append(f'<div style="border:1px solid #ccc;padding:12px;'
                 f'font-family:Arial,sans-serif">{_linkify_body(em["body"])}</div>')
    parts.append("<hr>")
    return "\n".join(parts)


# Which email type goes to which file pair: (basename, human title).
_GROUPS = [
    ("initial", "new_prospects", "New prospect drafts"),
    ("followup", "followups", "Follow-up drafts"),
]


def _write_group(conn, out_dir, today, basename, title, emails, overwrite) -> int:
    """Write one email-type's drafts to <basename>.md + <basename>.html (append by
    default, overwrite if asked). Returns the number of blocks written."""
    md_blocks = [b for b in (_email_block(conn, em) for em in emails) if b]
    if not md_blocks:
        return 0
    html_blocks = [b for b in (_email_block_html(conn, em) for em in emails) if b]

    md_path = os.path.join(out_dir, f"{basename}.md")
    md_fresh = overwrite or not os.path.exists(md_path)
    with open(md_path, "w" if md_fresh else "a") as f:
        if md_fresh:
            f.write(f"# {title} — {today}\n\n")
        f.write("\n".join(md_blocks) + "\n")

    html_path = os.path.join(out_dir, f"{basename}.html")
    html_fresh = overwrite or not os.path.exists(html_path)
    with open(html_path, "w" if html_fresh else "a") as f:
        if html_fresh:
            f.write(f'<!DOCTYPE html>\n<html><head><meta charset="utf-8">\n'
                    f"<title>{title} — {today}</title></head>\n<body>\n"
                    f"<h1>{title} — {today}</h1>\n")
        f.write("\n".join(html_blocks) + "\n")
    return len(md_blocks)


def generate(conn, *, out_root: str | None = None, today: str | None = None,
             since_email_id: int | None = None, overwrite: bool = False):
    """Write today's drafts under <out_root>/<date>/, splitting new prospect emails
    (new_prospects.md/.html) from follow-ups (followups.md/.html).

    By default APPENDS if the files already exist (so re-running the same day
    augments them); with `since_email_id`, only emails newer than that id are
    written. With `overwrite=True`, ALL of today's drafts are rewritten from
    scratch (used by the refine flow after drafts change in place).
    Returns (out_dir, count) or None if there's nothing to write."""
    out_root = out_root or config.OUTBOX_DIR
    today = today or date.today().isoformat()
    emails = db.emails_on(conn, today)
    if since_email_id is not None and not overwrite:
        emails = [e for e in emails if e["id"] > since_email_id]
    if not emails:
        return None

    out_dir = os.path.join(out_root, today)
    os.makedirs(out_dir, exist_ok=True)

    total = 0
    for email_type, basename, title in _GROUPS:
        group = [e for e in emails if e["type"] == email_type]
        total += _write_group(conn, out_dir, today, basename, title, group, overwrite)

    return (out_dir, total) if total else None


def write_file(conn, emails, *, basename: str, title: str,
               out_root: str | None = None, today: str | None = None):
    """Write an EXPLICIT list of email rows to <out_root>/<today>/<basename>.{md,html},
    overwriting that file. Unlike generate(), this ignores each email's date — it
    surfaces a curated set (e.g. ALL currently-due follow-ups) into today's folder,
    so `--followup` always produces a fresh file even when the drafts already existed.
    Returns (out_dir, count) or None if there's nothing to write."""
    out_root = out_root or config.OUTBOX_DIR
    today = today or date.today().isoformat()
    if not emails:
        return None
    out_dir = os.path.join(out_root, today)
    os.makedirs(out_dir, exist_ok=True)
    n = _write_group(conn, out_dir, today, basename, title, emails, overwrite=True)
    return (out_dir, n) if n else None
