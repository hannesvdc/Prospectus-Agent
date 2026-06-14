"""Tests for per-winner research/drafting with run_with_submit stubbed.

Verifies contact expansion (public kept, guessed generated), email storage,
status transition to 'drafted', and graceful handling when the model returns
nothing.
"""
from __future__ import annotations

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import research
from prospectus_agent.schemas import Candidate


def _caps(monkeypatch, *, public=1, people=3, guesses=1):
    monkeypatch.setattr(config, "MAX_PUBLIC_EMAILS", public)
    monkeypatch.setattr(config, "MAX_PEOPLE", people)
    monkeypatch.setattr(config, "GUESSES_PER_PERSON", guesses)


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
    _caps(monkeypatch)  # 1 public inbox, 3 people, 1 guess each
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

    # 1 generic inbox + Bob's published address (public); Jane gets ONE guess.
    assert set(by_conf["public"]) == {"info@acme.com", "bob@acme.com"}
    assert by_conf["guessed"] == ["jane.doe@acme.com"]  # single best guess
    assert summary["contacts"] == 3

    # Email drafted and status advanced.
    em = db.latest_email(conn, cid, "initial")
    assert em["subject"] == "CFD for your turbines"
    assert db.get_company_by_domain(conn, "acme.com")["status"] == "drafted"


def test_research_caps_contacts(conn, monkeypatch):
    _caps(monkeypatch, public=1, people=3, guesses=1)
    cid, cand = _winner(conn)
    payload = {
        "refined_applications": ["x"],
        "public_emails": ["info@acme.com", "sales@acme.com", "hr@acme.com"],  # 3 -> 1
        "people": [  # 5 -> 3
            {"name": n, "title": "VP", "public_email": None}
            for n in ["Alice Smith", "Bob Jones", "Carol White", "Dan Brown", "Eve Black"]
        ],
        "email_subject": "S",
        "email_body": "B",
        "draft_notes": "",
    }
    monkeypatch.setattr(research, "run_with_submit", lambda *a, **k: payload)
    research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    contacts = db.get_contacts(conn, cid)
    public = [c for c in contacts if c["email_confidence"] == "public"]
    guessed = [c for c in contacts if c["email_confidence"] == "guessed"]
    assert len(public) == 1                  # only one generic inbox
    assert len(guessed) == 3                 # 3 people, one guess each
    assert len(contacts) == 4                # 1 + 3 total


def test_research_handles_no_result(conn, monkeypatch):
    cid, cand = _winner(conn)
    monkeypatch.setattr(research, "run_with_submit", lambda *a, **k: None)
    summary = research.research_and_draft(None, conn, cid, cand, on_profile="ON")
    assert summary["drafted"] is False
    assert db.get_contacts(conn, cid) == []
    # Status unchanged (still 'new'), no email stored.
    assert db.get_company_by_domain(conn, "acme.com")["status"] == "new"
    assert db.latest_email(conn, cid, "initial") is None
