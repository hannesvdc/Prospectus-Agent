"""Em/en dashes must never reach a stored email (AI tell). Unit + storage tests."""
from __future__ import annotations

from prospectus_agent import db


def test_em_dash_becomes_comma():
    assert db.humanize_email_text("Reaction Studio — GPU compute") == "Reaction Studio, GPU compute"


def test_en_dash_stripped():
    assert "–" not in db.humanize_email_text("range 5 – 10 here")


def test_no_dash_char_survives_anywhere():
    for s in ["a—b", "a — b", "a–b", "we help you — faster — with X",
              "Subject line — with a tail"]:
        out = db.humanize_email_text(s)
        assert "—" not in out and "–" not in out


def test_doubled_punctuation_is_tidied():
    # dash right after a period shouldn't leave ". ,"
    assert db.humanize_email_text("We shipped it. — Next up, more.") == "We shipped it. Next up, more."


def test_plain_text_and_normal_commas_untouched():
    s = "We help you, and your team, move faster. It works."
    assert db.humanize_email_text(s) == s


def test_idempotent_and_empty_safe():
    once = db.humanize_email_text("A — B — C")
    assert db.humanize_email_text(once) == once
    assert db.humanize_email_text("") == ""


def test_add_and_update_email_strip_dashes(conn):
    cid = db.upsert_company(
        conn, name="Acme", domain="acme.com", hq_location="", industry="",
        fit_score=9, why_fit="x", suggested_applications=[], source_urls=[], status="new",
    )
    eid = db.add_email(conn, cid, type="initial",
                       subject="Acme — intro", body="Hi — we're Acme, and we'd love to help.")
    row = conn.execute("SELECT subject, body FROM emails WHERE id=?", (eid,)).fetchone()
    assert "—" not in row["subject"] and "—" not in row["body"]

    db.update_email(conn, eid, subject="New — subj", body="New — body.")
    row = conn.execute("SELECT subject, body FROM emails WHERE id=?", (eid,)).fetchone()
    assert "—" not in row["subject"] and "—" not in row["body"]
