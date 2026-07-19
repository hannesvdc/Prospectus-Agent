"""Dry-run delivery orchestration (no network, nothing sent)."""
from __future__ import annotations

from prospectus_agent import db
from prospectus_agent import deliver_run


class _KeepOpen:
    """Proxy the fixture connection but no-op close(), so deliver_run.main (which
    closes the DB it opens) doesn't tear down the in-memory test DB before asserts.
    (sqlite3.Connection.close is read-only, so we can't monkeypatch it directly.)"""

    def __init__(self, conn):
        self._conn = conn

    def __getattr__(self, name):
        return getattr(self._conn, name)

    def close(self):
        pass


def _use_conn(monkeypatch, conn):
    monkeypatch.setattr(deliver_run.runner, "open_db", lambda **k: _KeepOpen(conn))


def _drafted_with_contact(conn, domain, *, confidence="verified", sent=False):
    cid = db.upsert_company(
        conn, name=domain.split(".")[0].title(), domain=domain, hq_location="", industry="",
        fit_score=9, why_fit="x", suggested_applications=[], source_urls=[], status="drafted",
    )
    db.add_contact(conn, cid, name="Jane Doe", role="CTO",
                   email=f"jane.doe@{domain}", email_confidence=confidence)
    eid = db.add_email(conn, cid, type="initial", subject=f"Hi {domain}", body="Hello there.")
    if sent:
        db.mark_email_sent(conn, eid, rfc_message_id="<x@opennumerics.com>",
                           gmail_message_id="g", gmail_thread_id="t", sent_at="2026-07-06")
    return cid


def test_dry_run_reports_and_sends_nothing(conn, monkeypatch, capsys):
    _use_conn(monkeypatch, conn)
    _drafted_with_contact(conn, "acme.com")
    _drafted_with_contact(conn, "beta.com")

    rc = deliver_run.main(followup=False, live=False)
    out = capsys.readouterr().out

    assert rc == 0
    assert "DRY RUN" in out and "Would send: 2" in out
    assert "jane.doe@acme.com" in out
    # Nothing marked sent by a dry run.
    cid = db.get_company_by_domain(conn, "acme.com")["id"]
    assert db.latest_email(conn, cid, "initial")["sent_at"] is None


def test_already_sent_is_skipped(conn, monkeypatch, capsys):
    _use_conn(monkeypatch, conn)
    _drafted_with_contact(conn, "acme.com", sent=True)   # already delivered
    _drafted_with_contact(conn, "beta.com")              # not yet

    deliver_run.main(followup=False, live=False)
    out = capsys.readouterr().out
    assert "Would send: 1" in out          # only beta
    assert "beta.com" in out and "acme.com" not in out


def test_daily_cap_stops_early(conn, monkeypatch, capsys):
    _use_conn(monkeypatch, conn)
    monkeypatch.setattr(deliver_run.config, "AUTOSEND_DAILY_MAX", 1)
    _drafted_with_contact(conn, "acme.com")
    _drafted_with_contact(conn, "beta.com")

    deliver_run.main(followup=False, live=False)
    out = capsys.readouterr().out
    assert "Would send: 1" in out and "daily cap" in out


def _due_followup(conn, domain):
    """A company that's overdue for a follow-up, with a follow-up draft ready to send."""
    cid = db.upsert_company(
        conn, name=domain.split(".")[0].title(), domain=domain, hq_location="", industry="",
        fit_score=9, why_fit="x", suggested_applications=[], source_urls=[], status="drafted",
    )
    db.add_contact(conn, cid, name="Jane Doe", role="CTO",
                   email=f"jane.doe@{domain}", email_confidence="verified")
    db.set_status(conn, domain, "sent", contact_date="2020-01-01")   # long past -> due
    db.add_email(conn, cid, type="followup", subject=f"Re: Hi {domain}", body="Following up.")
    return cid


def test_followups_ignore_the_daily_cap(conn, monkeypatch, capsys):
    """The cap is a cold-outreach guardrail; follow-ups (warm contacts) are uncapped."""
    _use_conn(monkeypatch, conn)
    monkeypatch.setattr(deliver_run.config, "AUTOSEND_DAILY_MAX", 1)
    for d in ("acme.com", "beta.com", "gamma.com"):
        _due_followup(conn, d)

    deliver_run.main(followup=True, live=False)
    out = capsys.readouterr().out
    assert "Would send: 3" in out          # all three, despite cap=1
    assert "no cap (follow-ups)" in out
    assert "daily cap" not in out


def test_live_send_records_and_advances_status(conn, monkeypatch, capsys):
    _use_conn(monkeypatch, conn)
    # Enable the live path with the Gmail API fully stubbed (no libs / no network).
    monkeypatch.setattr(deliver_run.config, "GMAIL_CLIENT_ID", "x")
    monkeypatch.setattr(deliver_run.config, "GMAIL_CLIENT_SECRET", "y")
    monkeypatch.setattr(deliver_run.config, "GMAIL_REFRESH_TOKEN", "z")
    monkeypatch.setattr(deliver_run.config, "autosend_allowed", lambda: True)
    monkeypatch.setattr(deliver_run.config, "AUTOSEND_PACING_SECONDS", 0)
    monkeypatch.setattr(deliver_run.send, "gmail_service", lambda: object())
    monkeypatch.setattr(deliver_run.send, "fetch_signature", lambda service=None: "<b>Open Numerics</b>")
    sent_to = []

    def fake_send(msg, *, thread_id=None, service=None):
        sent_to.append(msg["To"])
        return {"id": "gmid", "threadId": "thid"}

    monkeypatch.setattr(deliver_run.send, "send_via_gmail", fake_send)

    _drafted_with_contact(conn, "acme.com")
    rc = deliver_run.main(followup=False, live=True)
    out = capsys.readouterr().out

    assert rc == 0 and "SENDING" in out and "Sent: 1" in out
    assert sent_to == ["jane.doe@acme.com"]
    cid = db.get_company_by_domain(conn, "acme.com")["id"]
    row = db.latest_email(conn, cid, "initial")
    assert row["sent_at"] and row["gmail_message_id"] == "gmid" and row["gmail_thread_id"] == "thid"
    # status advanced -> 'sent' (follow-up clock started)
    assert db.get_company_by_domain(conn, "acme.com")["status"] == "sent"


def test_live_without_creds_downgrades_to_dry_run(conn, monkeypatch, capsys):
    _use_conn(monkeypatch, conn)
    monkeypatch.setattr(deliver_run.config, "GMAIL_CLIENT_ID", "")
    monkeypatch.setattr(deliver_run.config, "GMAIL_CLIENT_SECRET", "")
    monkeypatch.setattr(deliver_run.config, "GMAIL_REFRESH_TOKEN", "")
    monkeypatch.setattr(deliver_run.config, "autosend_allowed", lambda: True)
    _drafted_with_contact(conn, "acme.com")

    deliver_run.main(followup=False, live=True)
    out = capsys.readouterr().out
    assert "DRY RUN" in out and "no Gmail credentials" in out
    # nothing sent
    cid = db.get_company_by_domain(conn, "acme.com")["id"]
    assert db.latest_email(conn, cid, "initial")["sent_at"] is None
