"""Tests for the --sent backfill (mark drafted emails as sent)."""
from __future__ import annotations

from datetime import date

from prospectus_agent import db, mark_sent


def _drafted(conn, *, domain, draft_date):
    cid = db.upsert_company(
        conn, name=domain, domain=domain, hq_location="", industry="Biotech",
        fit_score=9, why_fit="x", suggested_applications=["y"], source_urls=[],
        status="drafted",
    )
    eid = db.add_email(conn, cid, type="initial", subject="s", body="b")
    conn.execute("UPDATE emails SET created_at=? WHERE id=?", (draft_date, eid))
    conn.commit()
    return cid


def test_marks_drafted_sent_with_draft_date(conn):
    _drafted(conn, domain="a.com", draft_date="2026-06-10")
    _drafted(conn, domain="b.com", draft_date="2026-06-12")

    marked = mark_sent.mark_drafted_sent(conn)
    assert len(marked) == 2

    rows = {r["domain"]: r for r in conn.execute(
        "SELECT domain, status, last_contact_date FROM companies").fetchall()}
    assert rows["a.com"]["status"] == "sent"
    assert rows["a.com"]["last_contact_date"] == "2026-06-10"   # draft date, not today
    assert rows["b.com"]["last_contact_date"] == "2026-06-12"


def test_idempotent(conn):
    _drafted(conn, domain="a.com", draft_date="2026-06-10")
    assert len(mark_sent.mark_drafted_sent(conn)) == 1
    assert mark_sent.mark_drafted_sent(conn) == []   # nothing left in 'drafted'


def test_only_touches_drafted(conn):
    _drafted(conn, domain="a.com", draft_date="2026-06-10")
    # A company already 'sent' or 'replied' must not be re-marked.
    cid = db.upsert_company(
        conn, name="r.com", domain="r.com", hq_location="", industry="Biotech",
        fit_score=9, why_fit="x", suggested_applications=[], source_urls=[], status="drafted",
    )
    db.set_status(conn, "r.com", "replied")

    marked = mark_sent.mark_drafted_sent(conn)
    assert [m["domain"] for m in marked] == ["a.com"]
    assert db.get_company(conn, cid)["status"] == "replied"


def test_no_initial_email_falls_back_to_today(conn):
    # Drafted company with no initial email row -> contact date defaults to today.
    db.upsert_company(
        conn, name="x.com", domain="x.com", hq_location="", industry="Biotech",
        fit_score=9, why_fit="x", suggested_applications=[], source_urls=[], status="drafted",
    )
    mark_sent.mark_drafted_sent(conn)
    row = conn.execute("SELECT last_contact_date FROM companies WHERE domain='x.com'").fetchone()
    assert row["last_contact_date"] == date.today().isoformat()
