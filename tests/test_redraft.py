"""Tests for the refine/redraft flow (run_writer stubbed)."""
from __future__ import annotations

from datetime import date

from prospectus_agent import db
from prospectus_agent import redraft
from prospectus_agent.prompts import redraft as redraft_prompts


def _drafted(conn, *, domain="acme.com", subject="Old subj", body="Old body"):
    cid = db.upsert_company(
        conn, name="Acme", domain=domain, hq_location="Denver, CO", industry="Aero",
        fit_score=9, why_fit="CFD", suggested_applications=["x"], source_urls=[],
        status="drafted",
    )
    db.add_contact(conn, cid, name="", role="generic inbox",
                   email="info@acme.com", email_confidence="public")
    eid = db.add_email(conn, cid, type="initial", subject=subject, body=body)
    return cid, eid


def test_update_email_overwrites_in_place(conn):
    _, eid = _drafted(conn)
    assert db.update_email(conn, eid, subject="New subj", body="New body") is True
    row = conn.execute("SELECT subject, body FROM emails WHERE id=?", (eid,)).fetchone()
    assert row["subject"] == "New subj"
    assert row["body"] == "New body"


def test_refine_email_rewrites_draft(conn, monkeypatch):
    cid, eid = _drafted(conn)
    payload = {
        "email_subject": "Refined subject",
        "email_body": "Refined, prose-only body.",
        "draft_notes": "",
    }
    monkeypatch.setattr(redraft, "run_writer", lambda *a, **k: payload)

    em = conn.execute("SELECT * FROM emails WHERE id=?", (eid,)).fetchone()
    summary = redraft.refine_email(None, conn, em, on_profile="ON")

    assert summary["refined"] is True
    row = conn.execute("SELECT subject, body FROM emails WHERE id=?", (eid,)).fetchone()
    assert row["subject"] == "Refined subject"
    assert row["body"] == "Refined, prose-only body."
    # Contacts untouched by a refine.
    assert len(db.get_contacts(conn, cid)) == 1


def test_refine_email_keeps_draft_when_model_returns_nothing(conn, monkeypatch):
    _, eid = _drafted(conn, subject="Keep me", body="Keep body")
    monkeypatch.setattr(redraft, "run_writer", lambda *a, **k: None)

    em = conn.execute("SELECT * FROM emails WHERE id=?", (eid,)).fetchone()
    summary = redraft.refine_email(None, conn, em, on_profile="ON")

    assert summary["refined"] is False
    row = conn.execute("SELECT subject, body FROM emails WHERE id=?", (eid,)).fetchone()
    assert row["subject"] == "Keep me"  # unchanged


def test_refine_today_only_touches_initials(conn, monkeypatch):
    cid, _ = _drafted(conn)
    db.add_email(conn, cid, type="followup", subject="FU", body="follow up")
    calls = []

    def fake(*a, **k):
        calls.append(k.get("user_text", ""))
        return {"email_subject": "R", "email_body": "R body", "draft_notes": ""}

    monkeypatch.setattr(redraft, "run_writer", fake)
    summaries = redraft.refine_today(None, conn, "ON", today=date.today().isoformat())

    # Only the single initial email was refined, not the follow-up.
    assert len(summaries) == 1
    assert summaries[0]["refined"] is True
    assert len(calls) == 1


def test_redraft_prompt_includes_draft_and_rules(conn):
    company = {"name": "Acme", "domain": "acme.com", "industry": "Aero", "why_fit": "CFD"}
    out = redraft_prompts.build_user(company, "BRIEF", "Subj X", "Body Y")
    assert "Subj X" in out and "Body Y" in out
    assert "email_subject" in out and "email_body" in out  # shared rules present
    assert "submit_refined_email" in out
