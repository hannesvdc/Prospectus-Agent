"""Tests for the outbox generator (markdown digest)."""
from __future__ import annotations

from datetime import date

from prospectus_agent import db
from prospectus_agent import outbox


def _seed(conn, *, domain="acme.com", with_public=True, etype="initial"):
    cid = db.upsert_company(
        conn, name="Acme", domain=domain, hq_location="Denver, CO", industry="Automotive",
        fit_score=9, why_fit="crash sim", suggested_applications=["x"], source_urls=[],
        status="drafted",
    )
    if with_public:
        db.add_contact(conn, cid, name="", role="generic inbox",
                       email="info@acme.com", email_confidence="public")
    db.add_contact(conn, cid, name="Jane Doe", role="CTO",
                   email="jane.doe@acme.com", email_confidence="guessed")
    db.add_email(conn, cid, type=etype, subject="Crash sim for your EVs",
                 body="Hi there,\nWe can help.\n\nBest")
    return cid


def test_generate_writes_index(conn, tmp_path):
    _seed(conn)
    today = date.today().isoformat()
    result = outbox.generate(conn, out_root=str(tmp_path), today=today)
    assert result is not None
    out_dir, count = result
    assert count == 1

    index = (tmp_path / today / "index.md").read_text()
    assert "Acme (acme.com)" in index
    assert "Crash sim for your EVs" in index
    assert "We can help." in index
    assert "info@acme.com  (public" in index
    assert "jane.doe@acme.com  (guessed — Jane Doe, CTO)" in index

    # No .eml files are produced anymore.
    assert not list((tmp_path / today).glob("*.eml"))


def test_generate_writes_html_with_hyperlink(conn, tmp_path):
    from prospectus_agent import agent_profile
    cid = db.upsert_company(
        conn, name="Acme", domain="acme.com", hq_location="Denver, CO",
        industry="Automotive", fit_score=9, why_fit="crash sim",
        suggested_applications=["x"], source_urls=[], status="drafted",
    )
    db.add_contact(conn, cid, name="", role="generic inbox",
                   email="info@acme.com", email_confidence="public")
    # Two mentions of the seller name in the body; both should be linked.
    db.add_email(conn, cid, type="initial", subject="Sim for your EVs",
                 body=f"Hi there,\nI'm reaching out to introduce {agent_profile.NAME}.\n"
                      f"{agent_profile.NAME} helps R&D teams.\n\nBest")
    today = date.today().isoformat()
    outbox.generate(conn, out_root=str(tmp_path), today=today)

    html = (tmp_path / today / "index.html").read_text()
    # EVERY body mention of the seller's name is hyperlinked for Gmail paste.
    anchor = f'<a href="{agent_profile.WEBSITE}">{agent_profile.NAME}</a>'
    assert html.count(anchor) == 2
    assert "Sim for your EVs" in html
    assert "info@acme.com" in html


def test_guessed_only_warns(conn, tmp_path):
    _seed(conn, with_public=False)
    today = date.today().isoformat()
    outbox.generate(conn, out_root=str(tmp_path), today=today)
    index = (tmp_path / today / "index.md").read_text()
    assert "jane.doe@acme.com" in index
    assert "verify before sending" in index


def test_followups_labelled(conn, tmp_path):
    _seed(conn, etype="followup")
    today = date.today().isoformat()
    outbox.generate(conn, out_root=str(tmp_path), today=today)
    index = (tmp_path / today / "index.md").read_text()
    assert "(follow-up)" in index


def test_second_run_same_day_appends(conn, tmp_path):
    today = date.today().isoformat()

    # Run 1: company A.
    before1 = db.max_email_id(conn)
    _seed(conn, domain="a.com")
    outbox.generate(conn, out_root=str(tmp_path), today=today, since_email_id=before1)

    # Run 2: company B (only B is new this run).
    before2 = db.max_email_id(conn)
    _seed(conn, domain="b.com")
    result = outbox.generate(conn, out_root=str(tmp_path), today=today, since_email_id=before2)
    assert result == (str(tmp_path / today), 1)  # only B written this run

    index = (tmp_path / today / "index.md").read_text()
    assert "a.com" in index and "b.com" in index          # augmented, not replaced
    assert index.count("# Outreach drafts") == 1           # header not duplicated


def test_overwrite_regenerates_fresh(conn, tmp_path):
    today = date.today().isoformat()
    _seed(conn, domain="a.com")
    outbox.generate(conn, out_root=str(tmp_path), today=today)

    # A draft is refined in place, then the outbox is regenerated with overwrite.
    eid = conn.execute("SELECT id FROM emails LIMIT 1").fetchone()["id"]
    db.update_email(conn, eid, subject="Refined subject", body="Refined body text")
    outbox.generate(conn, out_root=str(tmp_path), today=today, overwrite=True)

    index = (tmp_path / today / "index.md").read_text()
    assert "Refined subject" in index
    assert "Crash sim for your EVs" not in index        # old content gone
    assert index.count("# Outreach drafts") == 1        # single fresh header


def test_nothing_drafted_returns_none(conn, tmp_path):
    assert outbox.generate(conn, out_root=str(tmp_path), today="2026-06-10") is None


def test_only_todays_emails_included(conn, tmp_path):
    cid = _seed(conn)
    conn.execute("UPDATE emails SET created_at='2000-01-01' WHERE company_id=?", (cid,))
    conn.commit()
    today = date.today().isoformat()
    assert outbox.generate(conn, out_root=str(tmp_path), today=today) is None
