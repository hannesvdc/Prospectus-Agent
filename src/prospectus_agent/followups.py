"""Follow-up logic: find companies you emailed that haven't replied within
FOLLOWUP_BUSINESS_DAYS business days, and draft a follow-up for each.

Business days = weekdays (Mon-Fri). No public-holiday calendar in v1.
"""
from __future__ import annotations

from datetime import date, timedelta

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import drafting


def business_days_since(start_iso: str, end: date | None = None) -> int:
    """Number of weekdays strictly after `start_iso`, up to and including `end`
    (default: today). Sending Monday => reaches 5 the following Monday."""
    end = end or date.today()
    start = date.fromisoformat(start_iso)
    count = 0
    d = start
    while d < end:
        d += timedelta(days=1)
        if d.weekday() < 5:  # 0-4 = Mon-Fri
            count += 1
    return count


def is_due(row) -> bool:
    """True if an awaiting company row is past the follow-up threshold."""
    return business_days_since(row["last_contact_date"]) >= config.FOLLOWUP_BUSINESS_DAYS


def is_final(row) -> bool:
    """True if the NEXT follow-up for this company is the second/final one — i.e. the
    first follow-up was already sent (status 'followed_up'). Status 'sent' means the
    first follow-up is next."""
    return row["status"] == "followed_up"


# Status after recording a sent follow-up: 'sent' -> 'followed_up' (1st done, await
# final), 'followed_up' -> 'no_reply' (both done; terminal).
_AFTER_SENT = {"sent": "followed_up", "followed_up": "no_reply"}


def due_followup_emails(conn) -> list:
    """Latest follow-up draft for every company currently past the threshold —
    used to (re)write a complete followups.md regardless of when each was drafted."""
    out = []
    for row in db.companies_awaiting_followup(conn):
        if not is_due(row):
            continue
        em = db.latest_email(conn, row["id"], "followup")
        if em:
            out.append(em)
    return out


def mark_followups_sent(conn) -> list[dict]:
    """Record that you've sent the due follow-ups, advancing each one stage: a 1st
    follow-up ('sent') -> 'followed_up' (clock restarts for the final one); a 2nd/final
    follow-up ('followed_up') -> 'no_reply' (terminal — never followed up again). Only
    touches companies that actually have a follow-up draft. Returns a summary list."""
    today = date.today().isoformat()
    marked = []
    for row in db.companies_awaiting_followup(conn):
        if not is_due(row):
            continue
        if not db.latest_email(conn, row["id"], "followup"):
            continue
        nxt = _AFTER_SENT.get(row["status"], "no_reply")
        db.set_status(conn, row["domain"], nxt, contact_date=today)
        marked.append({"name": row["name"], "domain": row["domain"],
                       "final": nxt == "no_reply"})
    return marked


def run_followups(client, conn, on_profile: str) -> list[dict]:
    """Sweep for stale outreach; draft follow-ups. Returns a list of summary
    dicts for the digest."""
    flagged: list[dict] = []
    for row in db.companies_awaiting_followup(conn):
        bdays = business_days_since(row["last_contact_date"])
        if bdays < config.FOLLOWUP_BUSINESS_DAYS:
            continue

        entry = {
            "name": row["name"],
            "domain": row["domain"],
            "business_days": bdays,
            "final": is_final(row),
            "drafted": False,
        }

        # Don't redraft if we already produced a follow-up since the last contact.
        if db.has_email_since(conn, row["id"], "followup", row["last_contact_date"]):
            entry["note"] = "follow-up already drafted"
            flagged.append(entry)
            continue

        result = drafting.draft_followup(client, conn, row, on_profile, final=is_final(row))
        if result:
            db.add_email(conn, row["id"], type="followup",
                         subject=result.email_subject, body=result.email_body)
            entry["drafted"] = True
            entry["subject"] = result.email_subject
        else:
            entry["note"] = "draft failed"
        flagged.append(entry)

    return flagged
