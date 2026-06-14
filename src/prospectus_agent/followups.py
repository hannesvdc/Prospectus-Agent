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
            "drafted": False,
        }

        # Don't redraft if we already produced a follow-up since the last contact.
        if db.has_email_since(conn, row["id"], "followup", row["last_contact_date"]):
            entry["note"] = "follow-up already drafted"
            flagged.append(entry)
            continue

        result = drafting.draft_followup(client, conn, row, on_profile)
        if result:
            db.add_email(conn, row["id"], type="followup",
                         subject=result.email_subject, body=result.email_body)
            entry["drafted"] = True
            entry["subject"] = result.email_subject
        else:
            entry["note"] = "draft failed"
        flagged.append(entry)

    return flagged
