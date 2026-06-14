"""Configuration: loads environment variables and exposes shared constants.

All tunables live in .env (see .env.example). This module reads them once and
provides typed access plus a single OpenAI client factory.

Filesystem paths (db, outbox, caches, profile) are resolved against a project
HOME directory rather than the current working directory, so the agent can be
run from anywhere once installed. See _resolve_home().
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _resolve_home() -> Path:
    """The project home directory — where .env, profile.yaml, the SQLite db and
    the outbox live. This is what lets the agent run from ANY working directory.

    Resolution order:
      1. $PROSPECTUS_AGENT_HOME, if set (point this at your project dir).
      2. The repo root inferred from this file's location (works for an editable
         `pip install -e .`, where this file stays at <home>/src/prospectus_agent/).
      3. The current working directory (last resort)."""
    env_home = os.getenv("PROSPECTUS_AGENT_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]  # <home>/src/prospectus_agent/config.py
    if (repo_root / ".env").exists() or (repo_root / "profile.yaml").exists() \
            or (repo_root / "profile.example.yaml").exists():
        return repo_root
    return Path.cwd()


HOME = _resolve_home()
# Load .env from the resolved home (not just the CWD) so running from elsewhere works.
load_dotenv(HOME / ".env")


def _path(env_name: str, default_name: str) -> str:
    """A configurable filesystem path. An absolute value in the env var is used
    as-is; a relative value (or the default) is resolved against HOME, so paths
    in .env stay portable and the agent still works from any directory."""
    raw = (os.getenv(env_name) or "").strip()
    p = Path(raw).expanduser() if raw else Path(default_name)
    return str(p if p.is_absolute() else HOME / p)


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    """Comma-separated env var -> lowercased list (empty if unset)."""
    return [s.strip().lower() for s in os.getenv(name, "").split(",") if s.strip()]


# --- Secrets ---------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()

# Cache file for the company brief fetched from the website (see on_profile.py).
# Company identity / offerings / targeting live in profile.yaml (agent_profile.py).
BRIEF_CACHE = _path("BRIEF_CACHE", "company_brief_cache.json")

# Where the copy-paste draft digests (index.md / index.html) are written. Set
# OUTBOX_DIR in .env to an absolute path to keep drafts in a fixed location
# regardless of where you run the agent from.
OUTBOX_DIR = _path("OUTBOX_DIR", "outbox")

# --- Pipeline tunables -----------------------------------------------------
# gpt-5.4-mini is ~6.6x cheaper than gpt-5.5 and plenty for scoring + short email
# drafting. Bump to gpt-5.4 or gpt-5.5 if you find draft quality lacking.
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini").strip()

# --- Token / cost controls -------------------------------------------------
# gpt-5.x reasoning effort: none|minimal|low|medium|high|xhigh. Lower = fewer
# (hidden) reasoning tokens. Discovery/profile are mechanical -> low. Bump
# DRAFTING_EFFORT to medium/high if email quality dips.
DISCOVERY_MODEL = os.getenv("DISCOVERY_MODEL", MODEL).strip()  # e.g. a cheaper gpt-5-mini
DISCOVERY_EFFORT = os.getenv("DISCOVERY_EFFORT", "low").strip()
DRAFTING_EFFORT = os.getenv("DRAFTING_EFFORT", "low").strip()
# How much web-search content the tool pulls into context: low|medium|high.
SEARCH_CONTEXT_SIZE = os.getenv("SEARCH_CONTEXT_SIZE", "low").strip()
DISCOVERY_MAX_TOKENS = _int("DISCOVERY_MAX_TOKENS", 8000)
DRAFT_MAX_TOKENS = _int("DRAFT_MAX_TOKENS", 4000)
PROFILE_MAX_TOKENS = _int("PROFILE_MAX_TOKENS", 2000)
TARGET_REGION = os.getenv("TARGET_REGION", "North America").strip()
FIT_SCORE_THRESHOLD = _int("FIT_SCORE_THRESHOLD", 7)
TARGET_COMPANY_COUNT = _int("TARGET_COMPANY_COUNT", 5)
# Max companies from any one sector among a day's picks (diversifier).
MAX_PER_SECTOR = _int("MAX_PER_SECTOR", 2)
# Sector bucket keys to exclude entirely (see sectors.py for valid keys), e.g.
# "aerospace_defense". Avoided-but-qualified companies are kept as backlog, so
# removing a sector here makes them eligible again.
AVOID_SECTORS = _list("AVOID_SECTORS")
# Company-size ceiling. Picks larger than MAX_COMPANY_SIZE are excluded (ON is a
# boutique consultancy; household-name giants aren't realistic prospects).
COMPANY_SIZE_ORDER = ["startup", "small", "mid", "large", "enterprise"]
MAX_COMPANY_SIZE = os.getenv("MAX_COMPANY_SIZE", "mid").strip().lower()
MAX_DISCOVERY_CALLS = _int("MAX_DISCOVERY_CALLS", 2)

# Cap how many already-seen companies are sent as a "don't repeat" hint. The DB
# filter still guarantees no duplicates; this keeps input from growing unbounded.
DENY_LIST_LIMIT = _int("DENY_LIST_LIMIT", 150)
# Re-fetch the ON profile from the web at most every N days (cached otherwise).
PROFILE_REFRESH_DAYS = _int("PROFILE_REFRESH_DAYS", 7)

# Contact list size per company: one generic inbox + a few senior people.
MAX_PUBLIC_EMAILS = _int("MAX_PUBLIC_EMAILS", 1)      # generic inboxes (info@/contact@)
MAX_PEOPLE = _int("MAX_PEOPLE", 3)                    # named senior people
GUESSES_PER_PERSON = _int("GUESSES_PER_PERSON", 1)    # guessed addresses per person
FOLLOWUP_BUSINESS_DAYS = _int("FOLLOWUP_BUSINESS_DAYS", 5)
DB_PATH = _path("DB_PATH", "prospects.db")


def size_rank(size: str) -> int:
    """Index of a size bucket in COMPANY_SIZE_ORDER; unknown -> 'mid' (lenient)."""
    try:
        return COMPANY_SIZE_ORDER.index((size or "").strip().lower())
    except ValueError:
        return COMPANY_SIZE_ORDER.index("mid")


def size_allowed(size: str) -> bool:
    """True if `size` is at or below the configured MAX_COMPANY_SIZE ceiling."""
    return size_rank(size) <= size_rank(MAX_COMPANY_SIZE)


def require_api_key() -> str:
    """Return the API key or raise a clear error if it is missing."""
    if not OPENAI_API_KEY:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to the .env file "
            "(see .env.example) before running steps that call the API."
        )
    return OPENAI_API_KEY


def get_client():
    """Construct an OpenAI client. Imported lazily so non-API code paths
    (e.g. the status CLI) work without the package configured."""
    from openai import OpenAI

    return OpenAI(api_key=require_api_key())
