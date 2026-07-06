"""Delivery bookkeeping: schema migration + mark_email_sent / get_thread_refs."""
from __future__ import annotations

import sqlite3

from prospectus_agent import db

_DELIVERY_COLS = {"rfc_message_id", "gmail_message_id", "gmail_thread_id", "sent_at"}


def test_migration_adds_delivery_columns_to_preexisting_db():
    # Simulate a DB created before the delivery columns existed.
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """CREATE TABLE emails (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               company_id INTEGER NOT NULL,
               type TEXT NOT NULL, subject TEXT, body TEXT, created_at TEXT NOT NULL
           );"""
    )
    db.init_db(conn)  # must ALTER-add the missing columns
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(emails)")}
    assert _DELIVERY_COLS <= cols
    db.init_db(conn)  # idempotent — running again must not error


def test_fresh_db_has_delivery_columns(conn):
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(emails)")}
    assert _DELIVERY_COLS <= cols


def test_mark_email_sent_and_thread_refs(conn):
    cid = db.upsert_company(
        conn, name="Acme", domain="acme.com", hq_location="", industry="",
        fit_score=9, why_fit="x", suggested_applications=[], source_urls=[], status="drafted",
    )
    eid = db.add_email(conn, cid, type="initial", subject="Hi", body="Body")

    assert db.get_thread_refs(conn, cid) is None  # nothing sent yet

    db.mark_email_sent(
        conn, eid,
        rfc_message_id="<abc@opennumerics.com>",
        gmail_message_id="gm1", gmail_thread_id="th1",
        sent_at="2026-07-06T10:00:00",
    )

    refs = db.get_thread_refs(conn, cid)
    assert refs["rfc_message_id"] == "<abc@opennumerics.com>"
    assert refs["gmail_thread_id"] == "th1"
    assert refs["subject"] == "Hi"

    row = conn.execute("SELECT sent_at, gmail_message_id FROM emails WHERE id=?", (eid,)).fetchone()
    assert row["sent_at"] == "2026-07-06T10:00:00"
    assert row["gmail_message_id"] == "gm1"
