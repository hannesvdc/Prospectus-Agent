"""Tests for per-winner research/drafting with run_searcher/run_writer stubbed.

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
    # Keep the suite offline + deterministic: the MX gate shells out to `dig`, so
    # stub it here (it's unit-tested on its own in test_verify.py). Verification is
    # OFF by default (real .env creds would otherwise trigger live API calls);
    # the tests that exercise it re-enable it explicitly.
    monkeypatch.setattr(research.verify, "domain_deliverable", lambda d: True)
    monkeypatch.setattr(research.profile, "VERIFY_EMAILS", False)


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
            {"name": "Bob Lee", "title": "VP Eng", "public_email": "bob.lee@acme.com"},
        ],
        "email_subject": "CFD for your turbines",
        "email_body": "Hi there, ...",
        "draft_notes": "Address to Jane if possible.",
    }
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: payload)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: payload)

    summary = research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    assert summary["drafted"] is True
    contacts = db.get_contacts(conn, cid)
    by_conf = {}
    for c in contacts:
        by_conf.setdefault(c["email_confidence"], []).append(c["email"])

    # Bob's published address is real (public). Its format (first.last) is used to
    # INFER Jane's address rather than blind-guessing. The generic info@ inbox is
    # dropped because we have reliable personal targets.
    assert set(by_conf["public"]) == {"bob.lee@acme.com"}
    assert by_conf["inferred"] == ["jane.doe@acme.com"]
    assert "guessed" not in by_conf
    assert "info@acme.com" not in [c["email"] for c in contacts]
    assert summary["contacts"] == 2

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
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: payload)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: payload)
    research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    contacts = db.get_contacts(conn, cid)
    public = [c for c in contacts if c["email_confidence"] == "public"]
    guessed = [c for c in contacts if c["email_confidence"] == "guessed"]
    assert len(public) == 1                  # only one generic inbox
    assert len(guessed) == 3                 # 3 people, one guess each
    assert len(contacts) == 4                # 1 + 3 total


def test_research_handles_no_result(conn, monkeypatch):
    cid, cand = _winner(conn)
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: None)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: None)
    summary = research.research_and_draft(None, conn, cid, cand, on_profile="ON")
    assert summary["drafted"] is False
    assert db.get_contacts(conn, cid) == []
    # Status unchanged (still 'new'), no email stored.
    assert db.get_company_by_domain(conn, "acme.com")["status"] == "new"
    assert db.latest_email(conn, cid, "initial") is None


def test_research_verifies_and_keeps_deliverable(conn, monkeypatch):
    _caps(monkeypatch)  # also stubs domain_deliverable -> True
    monkeypatch.setattr(research.profile, "VERIFY_EMAILS", True)
    monkeypatch.setattr(research.verify, "verification_available", lambda: True)
    # Jane's first candidate is deliverable; every Bob candidate is invalid.
    monkeypatch.setattr(
        research.verify, "verify_email",
        lambda e: "valid" if e == "jane.doe@acme.com" else "invalid",
    )
    cid, cand = _winner(conn)
    payload = {
        "refined_applications": ["x"],
        "public_emails": ["info@acme.com"],
        "people": [
            {"name": "Jane Doe", "title": "CTO", "public_email": None},
            {"name": "Bob Lee", "title": "VP", "public_email": None},
        ],
        "email_subject": "S", "email_body": "B", "draft_notes": "",
    }
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: payload)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: payload)
    research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    contacts = db.get_contacts(conn, cid)
    emails = {c["email"]: c["email_confidence"] for c in contacts}
    # Jane verifies -> kept as 'verified'. Bob's guesses all come back invalid, but we
    # DON'T drop him — we fall back to the best guess. Inbox dropped (reliable exists).
    assert emails == {"jane.doe@acme.com": "verified", "bob.lee@acme.com": "guessed"}


def test_research_never_zero_contacts_when_verification_fails(conn, monkeypatch):
    # Deliverable domain, but Verifalia rejects every guess -> we must still emit
    # guessed addresses, never "(no contacts found)".
    _caps(monkeypatch)
    monkeypatch.setattr(research.profile, "VERIFY_EMAILS", True)
    monkeypatch.setattr(research.verify, "verification_available", lambda: True)
    monkeypatch.setattr(research.verify, "verify_email", lambda e: "invalid")
    cid, cand = _winner(conn)
    payload = {
        "refined_applications": ["x"],
        "public_emails": [],
        "people": [{"name": "Jane Doe", "title": "CTO", "public_email": None}],
        "email_subject": "S", "email_body": "B", "draft_notes": "",
    }
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: payload)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: payload)
    research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    contacts = db.get_contacts(conn, cid)
    assert contacts, "must never leave a deliverable company with zero contacts"
    assert contacts[0]["email"] == "jane.doe@acme.com"
    assert contacts[0]["email_confidence"] == "guessed"


def test_research_catch_all_short_circuits_verification(conn, monkeypatch):
    _caps(monkeypatch)  # 3 people, stubs domain_deliverable -> True
    monkeypatch.setattr(research.profile, "VERIFY_EMAILS", True)
    monkeypatch.setattr(research.verify, "verification_available", lambda: True)
    calls = []
    monkeypatch.setattr(research.verify, "verify_email",
                        lambda e: (calls.append(e), "risky")[1])  # every address is catch-all
    cid, cand = _winner(conn)
    payload = {
        "refined_applications": ["x"],
        "public_emails": ["info@acme.com"],
        "people": [
            {"name": "Jane Doe", "title": "CTO", "public_email": None},
            {"name": "Bob Lee", "title": "VP", "public_email": None},
        ],
        "email_subject": "S", "email_body": "B", "draft_notes": "",
    }
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: payload)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: payload)
    research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    # ONE verification call for the whole company: Jane trips catch-all, Bob skips it.
    assert len(calls) == 1
    emails = {c["email"]: c["email_confidence"] for c in db.get_contacts(conn, cid)}
    assert emails["jane.doe@acme.com"] == "guessed"      # catch-all -> unconfirmed
    assert emails["bob.lee@acme.com"] == "guessed"
    assert "info@acme.com" in emails                     # inbox kept (no reliable personal)


def test_undeliverable_domain_warns_and_makes_no_contacts(conn, monkeypatch, capsys):
    _caps(monkeypatch)
    monkeypatch.setattr(research.verify, "domain_deliverable", lambda d: False)  # no MX/A
    cid, cand = _winner(conn)
    payload = {
        "refined_applications": ["x"], "public_emails": ["info@acme.com"],
        "people": [{"name": "Jane Doe", "title": "CTO", "public_email": None}],
        "email_subject": "S", "email_body": "B", "draft_notes": "",
    }
    monkeypatch.setattr(research, "run_searcher", lambda *a, **k: payload)
    monkeypatch.setattr(research, "run_writer", lambda *a, **k: payload)

    summary = research.research_and_draft(None, conn, cid, cand, on_profile="ON")

    assert summary["drafted"] is True and summary["contacts"] == 0
    assert "no MX/A record" in summary["warning"]
    assert db.get_contacts(conn, cid) == []
    assert "no MX/A record" in capsys.readouterr().out   # surfaced to the operator
