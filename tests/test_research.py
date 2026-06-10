"""Tests for per-winner research/drafting with run_with_submit stubbed.

Verifies contact expansion (public kept, guessed generated), email storage,
status transition to 'drafted', and graceful handling when the model returns
nothing.
"""
from __future__ import annotations

import db
import research
from schemas import Candidate


def _winner(conn, domain="acme.com"):
    cid = db.upsert_company(
        conn, name="Acme", domain=domain, hq_location="Denver, CO", industry="Aero",
        fit_score=9, why_fit="CFD", suggested_applications=["x"], source_urls=[],
        status="new",
    )
    cand = Candidate(name="Acme", domain=domain, why_fit="CFD", fit_score=9,
                     suggested_applications=["x"])
    return cid, cand


def test_research_stores_contacts_and_draft(conn, monkeypatch):
    cid, cand = _winner(conn)

    payload = {
        "refined_applications": ["GPU-accelerate their CFD", "UQ on fatigue"],
        "public_emails": ["info@acme.com"],
        "people": [
            {"name": "Jane Doe", "title": "CTO", "public_email": None},
            {"name": "Bob Lee", "title": "VP Eng", "public_email": "bob@acme.com"},
        ],
        "email_subject": "CFD for your turbines",
        "email_body": "Hi there, ...",
        "draft_notes": "Address to Jane if possible.",
    }
    monkeypatch.setattr(research, "run_with_submit", lambda *a, **k: payload)

    summary = research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    assert summary["drafted"] is True
    contacts = db.get_contacts(conn, cid)
    by_conf = {}
    for c in contacts:
        by_conf.setdefault(c["email_confidence"], []).append(c["email"])

    # info@ (public) + bob@ (public) = 2 public; Jane has no public email -> guesses.
    assert set(by_conf["public"]) == {"info@acme.com", "bob@acme.com"}
    assert "jane.doe@acme.com" in by_conf["guessed"]
    assert len(by_conf["guessed"]) == 4  # the four name patterns for Jane
    assert summary["contacts"] == 6

    # Email drafted and status advanced.
    em = db.latest_email(conn, cid, "initial")
    assert em["subject"] == "CFD for your turbines"
    assert db.get_company_by_domain(conn, "acme.com")["status"] == "drafted"


def test_research_handles_no_result(conn, monkeypatch):
    cid, cand = _winner(conn)
    monkeypatch.setattr(research, "run_with_submit", lambda *a, **k: None)
    summary = research.research_and_draft(None, conn, cid, cand, on_profile="ON")
    assert summary["drafted"] is False
    assert db.get_contacts(conn, cid) == []
    # Status unchanged (still 'new'), no email stored.
    assert db.get_company_by_domain(conn, "acme.com")["status"] == "new"
    assert db.latest_email(conn, cid, "initial") is None
