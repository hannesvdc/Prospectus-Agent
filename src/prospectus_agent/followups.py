"""Follow-up logic: find companies you emailed that haven't replied within
FOLLOWUP_DAYS calendar days, and draft a follow-up for each.

Calendar days (not weekdays) so due-dates spread evenly across the week — a company
comes due exactly N days after contact, weekends included, instead of the whole
weekend's worth bunching onto Monday.
"""
from __future__ import annotations

from datetime import date

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import drafting


def days_since(start_iso: str, end: date | None = None) -> int:
    """Calendar days from `start_iso` up to `end` (default: today)."""
    end = end or date.today()
    return (end - date.fromisoformat(start_iso)).days


def is_due(row) -> bool:
    """True if an awaiting company row is past the follow-up threshold."""
    return days_since(row["last_contact_date"]) >= config.FOLLOWUP_DAYS


def is_final(row) -> bool:
    """True if the NEXT follow-up for this company is the second/final one — i.e. the
    first follow-up was already sent (status 'followed_up'). Status 'sent' means the
    first follow-up is next."""
    return row["status"] == "followed_up"


# Status after recording a sent follow-up: 'sent' -> 'followed_up' (1st done, await
# final), 'followed_up' -> 'no_reply' (both done; terminal).
_AFTER_SENT = {"sent": "followed_up", "followed_up": "no_reply"}


def advance_after_followup_send(conn, row, today: str) -> str:
    """Advance a company one follow-up stage after its follow-up is sent
    (sent -> followed_up -> no_reply) and stamp the contact date. Returns the new
    status. The single home of the follow-up state machine (used by both the manual
    `--sent` path and the auto-send path)."""
    nxt = _AFTER_SENT.get(row["status"], "no_reply")
    db.set_status(conn, row["domain"], nxt, contact_date=today)
    return nxt


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
        nxt = advance_after_followup_send(conn, row, today)
        marked.append({"name": row["name"], "domain": row["domain"],
                       "final": nxt == "no_reply"})
    return marked


def run_followups(client, conn, on_profile: str) -> list[dict]:
    """Sweep for stale outreach; draft follow-ups. Returns a list of summary
    dicts for the digest."""
    flagged: list[dict] = []
    for row in db.companies_awaiting_followup(conn):
        days = days_since(row["last_contact_date"])
        if days < config.FOLLOWUP_DAYS:
            continue

        final = is_final(row)
        entry = {
            "name": row["name"],
            "domain": row["domain"],
            "days": days,
            "final": final,
            "drafted": False,
        }

        # Don't redraft if we already produced a follow-up since the last contact.
        if db.has_email_since(conn, row["id"], "followup", row["last_contact_date"]):
            entry["note"] = "follow-up already drafted"
            flagged.append(entry)
            continue

        result = drafting.draft_followup(client, conn, row, on_profile, final=final)
        if result:
            db.add_email(conn, row["id"], type="followup",
                         subject=result.email_subject, body=result.email_body)
            entry["drafted"] = True
            entry["subject"] = result.email_subject
        else:
            entry["note"] = "draft failed"
        flagged.append(entry)

    return flagged
