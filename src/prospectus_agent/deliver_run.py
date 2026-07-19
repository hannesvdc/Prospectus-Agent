"""Auto-send drafts / due follow-ups (`prospectus-agent --deliver`).

DRY-RUN by default: computes recipients (To/Bcc per §6) and threading, and logs exactly
what WOULD send — changing nothing. `--live` actually sends via the Gmail API, but only
when the profile is allowed AND Gmail creds are configured; otherwise it downgrades to a
dry run with a notice. Delivery uses no LLM — it reads drafts/contacts and (when live)
sends, records the send, and advances the follow-up clock.
"""
from __future__ import annotations

import sqlite3
import sys
import time
from datetime import date, datetime

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import followups
from prospectus_agent import runner
from prospectus_agent import send


def _initial_candidates(
    conn: sqlite3.Connection,
) -> list[tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row | None]]:
    """(company, email, thread_refs=None) for drafted companies whose initial email
    hasn't been delivered yet."""
    out = []
    for company in db.companies_by_status(conn, "drafted"):
        em = db.latest_email(conn, company["id"], "initial")
        if em and em["sent_at"] is None:
            out.append((company, em, None))
    return out


def _followup_candidates(
    conn: sqlite3.Connection,
) -> list[tuple[sqlite3.Row, sqlite3.Row, sqlite3.Row | None]]:
    """(company, email, thread_refs) for due follow-ups not yet delivered — threaded
    under the initial send when we have its refs."""
    out = []
    for em in followups.due_followup_emails(conn):
        if em["sent_at"] is not None:
            continue
        out.append((db.get_company(conn, em["company_id"]), em,
                    db.get_thread_refs(conn, em["company_id"])))
    return out


def _record_send(conn: sqlite3.Connection, company: sqlite3.Row, em: sqlite3.Row,
                 message_id: str, resp: dict, *, followup: bool) -> None:
    """Persist a live send: store the ids on the email and advance the company's status
    (initial -> 'sent'; follow-up -> followed_up -> no_reply), starting/resetting the clock."""
    db.mark_email_sent(
        conn, em["id"],
        rfc_message_id=message_id,
        gmail_message_id=resp.get("id", ""),
        gmail_thread_id=resp.get("threadId", ""),
        sent_at=datetime.now().isoformat(timespec="seconds"),
    )
    today = date.today().isoformat()
    if followup:
        followups.advance_after_followup_send(conn, company, today)
    else:
        db.set_status(conn, company["domain"], "sent", contact_date=today)


def main(followup: bool = False, live: bool = False) -> int:
    scope = "follow-ups" if followup else "new prospects"
    print(f"{agent_profile.NAME} — deliver {scope} ({date.today().isoformat()})\n")

    if live and not config.autosend_allowed():
        print(f"  Profile '{config.PROFILE or 'default'}' isn't enabled for delivery "
              f"(AUTOSEND_PROFILES={config.AUTOSEND_PROFILES}) — dry run only.\n")
        live = False
    if live and not config.gmail_configured():
        print("  NOTE: no Gmail credentials set (GMAIL_CLIENT_ID/SECRET/REFRESH_TOKEN) — "
              "running as a dry run. Run `python -m prospectus_agent.gmail_auth` to set up.\n")
        live = False

    conn = runner.open_db(backup=live)

    service = None
    footer = ""
    if live:
        try:
            service = send.gmail_service()
            footer = send.fetch_signature(service)   # append the Gmail signature
        except RuntimeError as e:
            print(f"  NOTE: {e}\n  Running as a dry run.\n")
            live = False

    candidates = _followup_candidates(conn) if followup else _initial_candidates(conn)
    mode = "SENDING" if live else "DRY RUN — nothing is sent"
    # The daily cap is a spam-ramp guardrail for COLD initials only; follow-ups go to
    # people we've already contacted, so they're uncapped.
    cap_note = "no cap (follow-ups)" if followup else f"cap {config.AUTOSEND_DAILY_MAX}/run"
    print(f"[{mode}]  from {config.AUTOSEND_FROM}  ·  {cap_note}, "
          f"{config.AUTOSEND_MAX_RECIPIENTS} recipients/email\n")

    done = skipped = 0
    for company, em, refs in candidates:
        if not followup and done >= config.AUTOSEND_DAILY_MAX:
            print(f"  · daily cap ({config.AUTOSEND_DAILY_MAX}) reached — stopping.")
            break
        to, bcc = send.select_recipients(
            db.get_contacts(conn, company["id"]),
            max_recipients=config.AUTOSEND_MAX_RECIPIENTS,
        )
        if not to:
            print(f"  ✗ {company['domain']} — no deliverable recipients, skipped.")
            skipped += 1
            continue

        msg, message_id = send.build_message(em, to, bcc, thread_refs=refs, footer_html=footer)
        threaded = (f"  ↳ threaded under {refs['gmail_thread_id']}"
                    if refs and refs["gmail_thread_id"] else "")
        arrow = "✓ sent" if live else "→ would send"
        print(f"  {arrow}: {company['name']} ({company['domain']}){threaded}")
        print(f"      To:  {', '.join(to)}")
        if bcc:
            print(f"      Bcc: {', '.join(bcc)}")
        print(f"      Subject: {msg['Subject']}")

        if live:
            resp = send.send_via_gmail(
                msg, thread_id=(refs["gmail_thread_id"] if refs else None), service=service)
            _record_send(conn, company, em, message_id, resp, followup=followup)
            if config.AUTOSEND_PACING_SECONDS:
                time.sleep(config.AUTOSEND_PACING_SECONDS)
        done += 1

    verb = "Sent" if live else "Would send"
    print(f"\n{verb}: {done}   ·   skipped: {skipped}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
