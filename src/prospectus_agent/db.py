"""SQLite persistence layer.

Tracks every company ever seen (fits and non-fits) so none resurface, plus
contacts and drafted emails. Plain, deterministic Python — no LLM here.

Status lifecycle for a company:
    new          -> qualified (score >= threshold), not yet drafted
    drafted      -> an initial email draft exists, ready for you to send
    sent         -> you sent it (sets last_contact_date); follow-up clock starts
    followed_up  -> you sent the one follow-up; done — never followed up again
    replied      -> they responded; no follow-up needed
    not_interested -> closed
    not_a_fit    -> seen during discovery but below the fit threshold
"""
from __future__ import annotations

import json
import sqlite3
from datetime import date
from typing import Iterable, Optional

VALID_STATUSES = {
    "new",
    "drafted",
    "sent",
    "followed_up",
    "replied",
    "not_interested",
    "not_a_fit",
}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS companies (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    name                   TEXT NOT NULL,
    domain                 TEXT NOT NULL UNIQUE,
    hq_location            TEXT,
    industry               TEXT,
    fit_score              INTEGER,
    why_fit                TEXT,
    suggested_applications TEXT,   -- JSON list
    source_urls            TEXT,   -- JSON list
    status                 TEXT NOT NULL DEFAULT 'new',
    first_seen             TEXT NOT NULL,
    last_contact_date      TEXT,
    updated_at             TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS contacts (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id       INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name             TEXT,
    role             TEXT,
    email            TEXT,
    email_confidence TEXT,          -- 'public' | 'guessed'
    UNIQUE(company_id, email)
);

CREATE TABLE IF NOT EXISTS emails (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    company_id INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    type       TEXT NOT NULL,       -- 'initial' | 'followup'
    subject    TEXT,
    body       TEXT,
    created_at TEXT NOT NULL
);
"""


def normalize_domain(raw: str) -> str:
    """Reduce a URL or domain to a bare lowercase host without scheme/www/path."""
    d = (raw or "").strip().lower()
    for prefix in ("https://", "http://"):
        if d.startswith(prefix):
            d = d[len(prefix):]
    if d.startswith("www."):
        d = d[4:]
    d = d.split("/")[0].split("?")[0].strip()
    return d


def connect(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


# --- companies -------------------------------------------------------------

def get_seen_domains(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT domain FROM companies").fetchall()
    return {r["domain"] for r in rows}


def deny_list(conn: sqlite3.Connection, limit: int | None = None) -> list[dict]:
    """Compact (name, domain) list to steer the model away from repeats. With a
    limit, returns the most-recently-seen `limit` companies (the DB filter still
    catches any duplicate the hint misses, so this only trades hint coverage for
    fewer prompt tokens)."""
    if limit:
        rows = conn.execute(
            "SELECT name, domain FROM companies ORDER BY first_seen DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT name, domain FROM companies ORDER BY first_seen").fetchall()
    return [{"name": r["name"], "domain": r["domain"]} for r in rows]


def get_company_by_domain(conn: sqlite3.Connection, domain: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM companies WHERE domain = ?", (normalize_domain(domain),)
    ).fetchone()


def upsert_company(
    conn: sqlite3.Connection,
    *,
    name: str,
    domain: str,
    hq_location: str,
    industry: str,
    fit_score: int,
    why_fit: str,
    suggested_applications: Iterable[str],
    source_urls: Iterable[str],
    status: str,
) -> int:
    """Insert a newly-seen company. If the domain already exists, leave its
    status untouched (so we never overwrite outreach progress) and return its id.
    Returns the company id.
    """
    domain = normalize_domain(domain)
    today = date.today().isoformat()
    existing = get_company_by_domain(conn, domain)
    if existing:
        return existing["id"]

    cur = conn.execute(
        """
        INSERT INTO companies
            (name, domain, hq_location, industry, fit_score, why_fit,
             suggested_applications, source_urls, status, first_seen, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            domain,
            hq_location,
            industry,
            fit_score,
            why_fit,
            json.dumps(list(suggested_applications)),
            json.dumps(list(source_urls)),
            status,
            today,
            today,
        ),
    )
    conn.commit()
    return cur.lastrowid


def set_status(
    conn: sqlite3.Connection,
    domain: str,
    status: str,
    *,
    set_contact_date: bool = False,
    contact_date: str | None = None,
) -> bool:
    """Update a company's status. Optionally set its last_contact_date: pass an
    explicit `contact_date` (ISO string — e.g. the real send date), or
    set_contact_date=True to use today. `contact_date` takes precedence."""
    if status not in VALID_STATUSES:
        raise ValueError(f"Invalid status '{status}'. Valid: {sorted(VALID_STATUSES)}")
    domain = normalize_domain(domain)
    today = date.today().isoformat()
    cd = contact_date or (today if set_contact_date else None)
    if cd is not None:
        cur = conn.execute(
            "UPDATE companies SET status=?, last_contact_date=?, updated_at=? WHERE domain=?",
            (status, cd, today, domain),
        )
    else:
        cur = conn.execute(
            "UPDATE companies SET status=?, updated_at=? WHERE domain=?",
            (status, today, domain),
        )
    conn.commit()
    return cur.rowcount > 0


def companies_by_status(conn: sqlite3.Connection, status: str) -> list[sqlite3.Row]:
    """All companies in a given status, highest fit_score first."""
    return conn.execute(
        "SELECT * FROM companies WHERE status=? ORDER BY fit_score DESC, first_seen",
        (status,),
    ).fetchall()


def companies_awaiting_followup(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """Companies marked 'sent' with a contact date set (business-day math is
    done by the caller, which knows the threshold)."""
    return conn.execute(
        "SELECT * FROM companies WHERE status='sent' AND last_contact_date IS NOT NULL"
    ).fetchall()


# --- contacts --------------------------------------------------------------

def add_contact(
    conn: sqlite3.Connection,
    company_id: int,
    *,
    name: str,
    role: str,
    email: str,
    email_confidence: str,
) -> None:
    try:
        conn.execute(
            """INSERT INTO contacts (company_id, name, role, email, email_confidence)
               VALUES (?, ?, ?, ?, ?)""",
            (company_id, name, role, email, email_confidence),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        pass  # duplicate (company_id, email) — ignore


def get_contacts(conn: sqlite3.Connection, company_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM contacts WHERE company_id=? ORDER BY email_confidence DESC",
        (company_id,),
    ).fetchall()


# --- emails ----------------------------------------------------------------

def add_email(
    conn: sqlite3.Connection,
    company_id: int,
    *,
    type: str,
    subject: str,
    body: str,
) -> int:
    cur = conn.execute(
        "INSERT INTO emails (company_id, type, subject, body, created_at) VALUES (?, ?, ?, ?, ?)",
        (company_id, type, subject, body, date.today().isoformat()),
    )
    conn.commit()
    return cur.lastrowid


def update_email(
    conn: sqlite3.Connection, email_id: int, *, subject: str, body: str
) -> bool:
    """Overwrite an existing draft's subject/body in place (used by refine).
    Returns True if a row was updated."""
    cur = conn.execute(
        "UPDATE emails SET subject=?, body=? WHERE id=?",
        (subject, body, email_id),
    )
    conn.commit()
    return cur.rowcount > 0


def has_email_since(
    conn: sqlite3.Connection, company_id: int, type: str, since_date: str
) -> bool:
    row = conn.execute(
        "SELECT 1 FROM emails WHERE company_id=? AND type=? AND created_at >= ? LIMIT 1",
        (company_id, type, since_date),
    ).fetchone()
    return row is not None


def max_email_id(conn: sqlite3.Connection) -> int:
    """Highest email id so far (0 if none) — used to detect a run's new drafts."""
    return conn.execute("SELECT COALESCE(MAX(id), 0) FROM emails").fetchone()[0]


def emails_on(conn: sqlite3.Connection, date_iso: str) -> list[sqlite3.Row]:
    """All emails drafted on a given date (initial first, then follow-ups)."""
    return conn.execute(
        "SELECT * FROM emails WHERE created_at=? ORDER BY CASE type WHEN 'initial' THEN 0 ELSE 1 END, id",
        (date_iso,),
    ).fetchall()


def get_company(conn: sqlite3.Connection, company_id: int) -> Optional[sqlite3.Row]:
    return conn.execute("SELECT * FROM companies WHERE id=?", (company_id,)).fetchone()


def latest_email(conn: sqlite3.Connection, company_id: int, type: str) -> Optional[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM emails WHERE company_id=? AND type=? ORDER BY created_at DESC, id DESC LIMIT 1",
        (company_id, type),
    ).fetchone()
