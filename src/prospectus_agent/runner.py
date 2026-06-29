"""Shared plumbing for the run commands (daily run, refine, follow-up sweep).

Keeps the common entrypoint prologue in one place so the command modules stay
focused on what's unique to each. (Lives in its own module to avoid an import
cycle — config/db/llm all import config, which must not import them.)
"""
from __future__ import annotations

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import llm


class Clients:
    """Lazy registry of vendor SDK clients, keyed by vendor name. Built once per
    run and threaded through the pipeline; `get(vendor)` constructs + caches the
    client on first use (so we never build a client for an unused vendor)."""

    def __init__(self):
        self._cache = {}

    def get(self, vendor: str):
        vendor = vendor.lower()
        if vendor not in self._cache:
            self._cache[vendor] = config.get_client(vendor)
        return self._cache[vendor]


def open_session():
    """Validate API keys for the configured vendors, build the client registry,
    open + initialise the active profile's database, and reset token accounting.
    Returns (clients, conn). Raises RuntimeError if a needed key is missing."""
    for vendor in {config.SEARCH_VENDOR, config.WRITER_VENDOR}:
        config.require_api_key(vendor)
    clients = Clients()
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)
    llm.reset_usage()
    return clients, conn
