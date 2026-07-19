"""Shared plumbing for the run commands (daily run, refine, follow-up sweep).

Keeps the common entrypoint prologue in one place so the command modules stay
focused on what's unique to each. (Lives in its own module to avoid an import
cycle — config/db/llm all import config, which must not import them.)
"""
from __future__ import annotations

import os
import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import llm


def _backup_db(db_path: str) -> None:
    """Roll a fresh backup of the profile DB before a run — a one-file recovery
    point for the last mutating command. Overwrites `<db_path>.bak`. Best-effort:
    a backup failure (or no DB yet) never blocks the run. Gitignored (*.db.bak*)."""
    if not db_path or db_path == ":memory:" or not os.path.exists(db_path):
        return
    try:
        shutil.copy2(db_path, db_path + ".bak")
    except OSError:
        pass


class Clients:
    """Lazy registry of vendor SDK clients, keyed by vendor name. Built once per
    run and threaded through the pipeline; `get(vendor)` constructs + caches the
    client on first use (so we never build a client for an unused vendor)."""

    def __init__(self) -> None:
        self._cache: dict = {}

    def get(self, vendor: str):
        vendor = vendor.lower()
        if vendor not in self._cache:
            self._cache[vendor] = config.get_client(vendor)
        return self._cache[vendor]


def open_db(*, backup: bool = False) -> sqlite3.Connection:
    """Open + initialise the active profile's database, returning the connection.
    Shared by open_session() and the key-less commands (mark-sent, status CLI).
    With backup=True, roll a `<db>.bak` snapshot first — the mutating commands pass
    this; the read-only status CLI leaves it False so viewing never clobbers the
    recovery point."""
    if backup:
        _backup_db(config.DB_PATH)
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)
    return conn


def open_session() -> tuple[Clients, sqlite3.Connection]:
    """Validate API keys for the configured vendors, build the client registry,
    open + initialise the active profile's database (rolling a fresh backup first),
    and reset token accounting. Returns (clients, conn). Raises RuntimeError if a
    needed key is missing."""
    for vendor in {config.SEARCH_VENDOR, config.WRITER_VENDOR}:
        config.require_api_key(vendor)
    clients = Clients()
    conn = open_db(backup=True)
    llm.reset_usage()
    return clients, conn


@contextmanager
def session(banner: str) -> Iterator[tuple[Clients, sqlite3.Connection]]:
    """Entrypoint context manager for the run commands. Prints `banner`, opens the
    session (raising RuntimeError if a required API key is missing), yields
    (clients, conn), and on exit prints the token-usage summary and closes the DB.
    Wrap the body and catch RuntimeError to print an ERROR line and return 1:

        try:
            with runner.session(banner) as (clients, conn):
                ...
        except RuntimeError as e:
            print(f"ERROR: {e}"); return 1
        return 0
    """
    print(banner)
    clients, conn = open_session()
    try:
        yield clients, conn
    finally:
        usage = llm.usage_summary()
        if usage:
            print(f"\n{usage}")
        conn.close()
