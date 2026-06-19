"""Shared plumbing for the run commands (daily run, refine, follow-up sweep).

Keeps the common entrypoint prologue in one place so the command modules stay
focused on what's unique to each. (Lives in its own module to avoid an import
cycle — config/db/llm/on_profile all import config, which must not import them.)
"""
from __future__ import annotations

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import llm


def open_session():
    """Validate the API key, build the OpenAI client, open + initialise the active
    profile's database, and reset token accounting. Returns (client, conn).
    Raises RuntimeError (from require_api_key) if the key is missing."""
    config.require_api_key()
    client = config.get_client()
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)
    llm.reset_usage()
    return client, conn
