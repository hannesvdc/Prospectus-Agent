"""Tests for the SQLite layer: dedup, status lifecycle, contacts, emails."""
from __future__ import annotations

from datetime import date

import pytest

from prospectus_agent import db


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("https://www.Acme-Corp.com/about?x=1", "acme-corp.com"),
        ("http://acme-corp.com", "acme-corp.com"),
        ("WWW.Acme-Corp.COM", "acme-corp.com"),
        ("acme-corp.com/team", "acme-corp.com"),
        ("  acme-corp.com  ", "acme-corp.com"),
    ],
)
def test_normalize_domain(raw, expected):
    assert db.normalize_domain(raw) == expected


def _insert(conn, **over):
    base = dict(
        name="Acme", domain="acme.com", hq_location="Denver, CO", industry="Aero",
        fit_score=9, why_fit="CFD", suggested_applications=["a", "b"],
        source_urls=["http://x"], status="new",
    )
    base.update(over)
    return db.upsert_company(conn, **base)


def test_upsert_and_normalize(conn):
    cid = _insert(conn, domain="https://www.acme.com/about")
    row = db.get_company_by_domain(conn, "acme.com")
    assert row["id"] == cid
    assert row["domain"] == "acme.com"
    assert row["first_seen"] == date.today().isoformat()


def test_upsert_dedup_keeps_first_status(conn):
    cid = _insert(conn, status="new")
    # Same domain (different URL form), different status — must NOT overwrite.
    cid2 = _insert(conn, domain="acme.com", status="not_a_fit", name="dup")
    assert cid == cid2
    row = db.get_company_by_domain(conn, "acme.com")
    assert row["status"] == "new"
    assert row["name"] == "Acme"  # original preserved


def test_seen_domains_and_deny_list(conn):
    _insert(conn, domain="acme.com", name="Acme")
    _insert(conn, domain="beta.io", name="Beta")
    assert db.get_seen_domains(conn) == {"acme.com", "beta.io"}
    deny = db.deny_list(conn)
    assert {d["domain"] for d in deny} == {"acme.com", "beta.io"}
    assert {d["name"] for d in deny} == {"Acme", "Beta"}


def test_deny_list_limit(conn):
    for i in range(5):
        _insert(conn, domain=f"c{i}.com", name=f"C{i}")
    assert len(db.deny_list(conn, limit=2)) == 2   # capped
    assert len(db.deny_list(conn)) == 5            # full when no limit


def test_set_status_sent_sets_contact_date(conn):
    _insert(conn)
    assert db.set_status(conn, "acme.com", "sent", set_contact_date=True)
    row = db.get_company_by_domain(conn, "acme.com")
    assert row["status"] == "sent"
    assert row["last_contact_date"] == date.today().isoformat()


def test_set_status_without_contact_date(conn):
    _insert(conn)
    db.set_status(conn, "acme.com", "replied")
    row = db.get_company_by_domain(conn, "acme.com")
    assert row["status"] == "replied"
    assert row["last_contact_date"] is None


def test_set_status_invalid_raises(conn):
    _insert(conn)
    with pytest.raises(ValueError):
        db.set_status(conn, "acme.com", "bogus")


def test_set_status_unknown_domain_returns_false(conn):
    assert db.set_status(conn, "nope.com", "sent", set_contact_date=True) is False


def test_contacts_dedup_and_fetch(conn):
    cid = _insert(conn)
    db.add_contact(conn, cid, name="Jane", role="CTO",
                   email="jane@acme.com", email_confidence="public")
    # Duplicate (company_id, email) is silently ignored.
    db.add_contact(conn, cid, name="Jane2", role="CTO",
                   email="jane@acme.com", email_confidence="guessed")
    db.add_contact(conn, cid, name="Bob", role="VP",
                   email="bob@acme.com", email_confidence="guessed")
    contacts = db.get_contacts(conn, cid)
    assert len(contacts) == 2
    emails = {c["email"] for c in contacts}
    assert emails == {"jane@acme.com", "bob@acme.com"}


def test_emails_and_helpers(conn):
    cid = _insert(conn)
    db.add_email(conn, cid, type="initial", subject="Hi", body="Body")
    latest = db.latest_email(conn, cid, "initial")
    assert latest["subject"] == "Hi"
    assert db.latest_email(conn, cid, "followup") is None
    # has_email_since
    today = date.today().isoformat()
    assert db.has_email_since(conn, cid, "initial", today) is True
    assert db.has_email_since(conn, cid, "followup", today) is False


def test_companies_awaiting_followup(conn):
    _insert(conn, domain="sent.com")
    db.set_status(conn, "sent.com", "sent", set_contact_date=True)
    _insert(conn, domain="new.com")  # status new, no contact date
    _insert(conn, domain="replied.com")
    db.set_status(conn, "replied.com", "replied")
    awaiting = db.companies_awaiting_followup(conn)
    assert {r["domain"] for r in awaiting} == {"sent.com"}
