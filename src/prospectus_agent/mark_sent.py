"""Mark drafted emails as sent — you send manually, this records it so follow-ups fire.

Invoked by `prospectus-agent --profile <name> --sent`.

The follow-up sweep only acts on companies in 'sent' status, so unless you record
your sends nothing ever gets a nudge. This marks every company still in 'drafted'
status as 'sent', using its initial-email date as the contact date (a proxy for when
you sent it) — which starts the follow-up clock correctly, including for drafts you
sent days ago. Idempotent: once everything's marked, re-running does nothing.

Assumes the intended workflow: you send every draft the agent produces. If you skip
some, mark those individually instead with `prospectus-status mark DOMAIN <status>`.
"""
from __future__ import annotations

import sys
from datetime import date

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import runner


def mark_drafted_sent(conn) -> list[dict]:
    """Mark all 'drafted' companies as 'sent', contact date = their initial-email
    (draft) date. Returns a summary list of what was marked."""
    marked: list[dict] = []
    for row in db.companies_by_status(conn, "drafted"):
        em = db.latest_email(conn, row["id"], "initial")
        contact_date = em["created_at"] if em else date.today().isoformat()
        db.set_status(conn, row["domain"], "sent", contact_date=contact_date)
        marked.append({"name": row["name"], "domain": row["domain"], "date": contact_date})
    return marked


def main() -> int:
    conn = runner.open_db()
    marked = mark_drafted_sent(conn)

    if not marked:
        print(f"{agent_profile.NAME}: nothing in 'drafted' status — no sends to record.")
        conn.close()
        return 0

    print(f"{agent_profile.NAME}: marked {len(marked)} draft(s) as sent "
          "(contact date = draft date):")
    for m in sorted(marked, key=lambda x: x["date"]):
        print(f"   {m['date']}  {m['domain']}")
    print("\nThe follow-up clock now runs from those dates. Run `prospectus-agent` "
          f"(--profile {config.PROFILE or 'default'}) to draft follow-ups for any past "
          f"the {config.FOLLOWUP_BUSINESS_DAYS}-business-day threshold.")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
