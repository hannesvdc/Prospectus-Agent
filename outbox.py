"""Write a ready-to-review digest of the drafts after a run.

Produces two files per run under `outbox/<date>/`:
  * `index.md`   — markdown digest (recipients + subject + body in a code block),
                   easy to skim and copy as plain text.
  * `index.html` — the same drafts as rich HTML. The body has the seller's name
                   turned into a real <a href> link to its website, so when you
                   copy the body from a browser and paste into Gmail the hyperlink
                   is preserved (Gmail keeps links only on rich-text paste, not on
                   markdown). Open this file in a browser to copy from.

Running the agent again on the same day **appends** that run's new drafts to both
files rather than overwriting them, so earlier drafts (and notes you added) survive.

Recipients: public addresses are listed first, then pattern-guessed ones (tagged),
so you choose whom to include.
"""
from __future__ import annotations

import html
import os
import re
from datetime import date

import agent_profile
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

    parts.append(f"<p><strong>Subject:</strong> {html.escape(em['subject'])}</p>")
    parts.append("<p><strong>Body</strong> (copy from here into Gmail):</p>")
    parts.append(f'<div style="border:1px solid #ccc;padding:12px;'
                 f'font-family:Arial,sans-serif">{_linkify_body(em["body"])}</div>')
    parts.append("<hr>")
    return "\n".join(parts)


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
    html_blocks = [b for b in (_email_block_html(conn, em) for em in emails) if b]

    out_dir = os.path.join(out_root, today)
    os.makedirs(out_dir, exist_ok=True)

    md_path = os.path.join(out_dir, "index.md")
    md_exists = os.path.exists(md_path)
    with open(md_path, "a" if md_exists else "w") as f:
        if not md_exists:
            f.write(f"# Outreach drafts — {today}\n\n")
        f.write("\n".join(blocks) + "\n")

    html_path = os.path.join(out_dir, "index.html")
    html_exists = os.path.exists(html_path)
    with open(html_path, "a" if html_exists else "w") as f:
        if not html_exists:
            f.write(f'<!DOCTYPE html>\n<html><head><meta charset="utf-8">\n'
                    f"<title>Outreach drafts — {today}</title></head>\n<body>\n"
                    f"<h1>Outreach drafts — {today}</h1>\n")
        f.write("\n".join(html_blocks) + "\n")

    return out_dir, len(blocks)
