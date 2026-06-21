"""Tests for business-day math and the follow-up sweep (drafting stubbed)."""
from __future__ import annotations

from datetime import date, timedelta

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import followups
from prospectus_agent.schemas import FollowUpResult


def _next_weekday(d: date, weekday: int) -> date:
    while d.weekday() != weekday:
        d += timedelta(days=1)
    return d


def test_same_day_is_zero():
    d = date(2026, 6, 10)
    assert followups.business_days_since(d.isoformat(), d) == 0


def test_monday_to_next_monday_is_five():
    mon = _next_weekday(date(2026, 6, 1), 0)
    assert followups.business_days_since(mon.isoformat(), mon + timedelta(days=7)) == 5


def test_weekend_only_counts_zero():
    sat = _next_weekday(date(2026, 6, 1), 5)  # Saturday
    assert followups.business_days_since(sat.isoformat(), sat + timedelta(days=1)) == 0


def test_friday_to_monday_is_one():
    fri = _next_weekday(date(2026, 6, 1), 4)  # Friday
    # +3 days -> Monday; Sat/Sun skipped, Monday counts once.
    assert followups.business_days_since(fri.isoformat(), fri + timedelta(days=3)) == 1


# --- run_followups ---------------------------------------------------------

def _insert_sent(conn, domain, days_ago):
    db.upsert_company(
        conn, name=domain, domain=domain, hq_location="", industry="",
        fit_score=9, why_fit="", suggested_applications=[], source_urls=[],
        status="sent",
    )
    contact_date = (date.today() - timedelta(days=days_ago)).isoformat()
    conn.execute(
        "UPDATE companies SET last_contact_date=? WHERE domain=?", (contact_date, domain)
    )
    conn.commit()
    return db.get_company_by_domain(conn, domain)["id"]


def test_run_followups_drafts_due_company(conn, monkeypatch):
    calls = []

    def fake_draft(client, c, row, profile):
        calls.append(row["domain"])
        return FollowUpResult(email_subject="Following up", email_body="Just checking in.")

    monkeypatch.setattr(followups.drafting, "draft_followup", fake_draft)

    cid = _insert_sent(conn, "due.com", days_ago=14)        # well past threshold
    _insert_sent(conn, "fresh.com", days_ago=0)             # sent today, not due

    result = followups.run_followups(client=None, conn=conn, on_profile="ON")

    domains = {r["domain"]: r for r in result}
    assert "due.com" in domains and domains["due.com"]["drafted"] is True
    assert "fresh.com" not in domains
    assert calls == ["due.com"]
    # A follow-up email was stored.
    assert db.latest_email(conn, cid, "followup") is not None


def test_run_followups_skips_already_drafted(conn, monkeypatch):
    calls = []
    monkeypatch.setattr(
        followups.drafting, "draft_followup",
        lambda *a, **k: calls.append(1) or FollowUpResult(email_subject="x", email_body="y"),
    )

    cid = _insert_sent(conn, "due.com", days_ago=14)
    # Pre-existing follow-up dated today (>= last_contact_date) -> should skip.
    db.add_email(conn, cid, type="followup", subject="prev", body="prev")

    result = followups.run_followups(client=None, conn=conn, on_profile="ON")
    entry = next(r for r in result if r["domain"] == "due.com")
    assert entry["drafted"] is False
    assert entry["note"] == "follow-up already drafted"
    assert calls == []  # draft_followup never called


def test_threshold_respected(conn, monkeypatch):
    monkeypatch.setattr(config, "FOLLOWUP_BUSINESS_DAYS", 5)
    monkeypatch.setattr(
        followups.drafting, "draft_followup",
        lambda *a, **k: FollowUpResult(email_subject="x", email_body="y"),
    )
    # 2 calendar days ago -> at most 2 business days -> under threshold.
    _insert_sent(conn, "recent.com", days_ago=2)
    result = followups.run_followups(client=None, conn=conn, on_profile="ON")
    assert result == []


# --- one-and-done follow-up ------------------------------------------------

def test_mark_followups_sent_is_terminal(conn):
    cid = _insert_sent(conn, "due.com", days_ago=14)
    db.add_email(conn, cid, type="followup", subject="fu", body="fu")
    _insert_sent(conn, "nofu.com", days_ago=14)  # due but no follow-up draft

    marked = followups.mark_followups_sent(conn)
    assert [m["domain"] for m in marked] == ["due.com"]  # only the one with a draft

    # It moved to the terminal 'followed_up' status...
    assert db.get_company(conn, cid)["status"] == "followed_up"
    # ...so it no longer shows up as awaiting follow-up, EVER (not just for now).
    assert all(r["domain"] != "due.com" for r in db.companies_awaiting_followup(conn))
    assert followups.due_followup_emails(conn) == []  # nothing due anymore


def test_followed_up_company_never_redrafts(conn, monkeypatch):
    monkeypatch.setattr(
        followups.drafting, "draft_followup",
        lambda *a, **k: FollowUpResult(email_subject="x", email_body="y"),
    )
    cid = _insert_sent(conn, "due.com", days_ago=14)
    db.add_email(conn, cid, type="followup", subject="fu", body="fu")
    followups.mark_followups_sent(conn)
    # Even long after, a follow-up sweep ignores a followed_up company.
    assert followups.run_followups(client=None, conn=conn, on_profile="ON") == []
