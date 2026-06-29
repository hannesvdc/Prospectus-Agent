"""Configuration: loads environment variables and exposes shared constants.

All tunables live in .env (see .env.example). This module reads them once and
provides typed access plus a single OpenAI client factory.

Filesystem paths (db, outbox, caches, profile) are resolved against a project
HOME directory rather than the current working directory, so the agent can be
run from anywhere once installed (see paths.HOME).

Multi-business: the active PROFILE (from $PROSPECTUS_PROFILE, set by `--profile`,
else $DEFAULT_PROFILE in .env) drives per-business path defaults — profile.<p>.yaml,
<p>.db, outbox/<p>/, <p>_brief_cache.json — so every entry point (daily run, refine,
status) stays consistent. With no profile set, the legacy single-business defaults
apply (profile.yaml, prospects.db, outbox/).

Per-business tunables: a profile may include a `settings:` block (e.g.
target_company_count: 5) that OVERRIDES the corresponding .env value for that
business. Precedence is: profile settings > environment (.env / shell) > default.
"""
from __future__ import annotations

import os
from pathlib import Path

from prospectus_agent.paths import HOME  # resolves home + loads .env on import

# Active business profile name (empty = legacy single-profile mode).
PROFILE = (os.getenv("PROSPECTUS_PROFILE") or os.getenv("DEFAULT_PROFILE") or "").strip()


def _profiled(legacy: str, template: str) -> str:
    """Per-business default filename when a PROFILE is active, else the legacy name."""
    return template.format(p=PROFILE) if PROFILE else legacy


def _path(env_name: str, default_name: str) -> str:
    """A configurable filesystem path. An absolute value in the env var is used
    as-is; a relative value (or the default) is resolved against HOME, so paths
    in .env stay portable and the agent still works from any directory."""
    raw = (os.getenv(env_name) or "").strip()
    p = Path(raw).expanduser() if raw else Path(default_name)
    return str(p if p.is_absolute() else HOME / p)


# Path to the active profile YAML (loaded by agent_profile).
PROFILE_PATH = _path("PROFILE_PATH", _profiled("profile.yaml", "profile.{p}.yaml"))


def _load_settings() -> dict:
    """The active profile's optional `settings:` block — per-business overrides of
    the .env tunables (e.g. target_company_count). Keys are upper-cased to match the
    env var names. Falls back to the example profile if the active one is missing."""
    import yaml
    path = PROFILE_PATH if os.path.exists(PROFILE_PATH) else str(HOME / "profile.example.yaml")
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except (OSError, yaml.YAMLError):
        return {}
    block = data.get("settings") or {}
    return {str(k).upper(): v for k, v in block.items()} if isinstance(block, dict) else {}


_SETTINGS = _load_settings()


def _raw(name: str):
    """Effective raw value for a tunable, as a string or None. Precedence:
    profile `settings:` (per-business) > environment (.env / shell) > None.
    (Secrets like the API key are read straight from the env, not via this.)"""
    if name in _SETTINGS:
        v = _SETTINGS[name]
        return None if v is None else str(v)
    return os.getenv(name)


def _int(name: str, default: int) -> int:
    raw = _raw(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _list(name: str) -> list[str]:
    """Comma-separated tunable -> lowercased list (empty if unset)."""
    return [s.strip().lower() for s in (_raw(name) or "").split(",") if s.strip()]


# --- Secrets ---------------------------------------------------------------
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# Cache file for the company brief fetched from the website (see on_profile.py).
# Company identity / offerings / targeting live in profile.yaml (agent_profile.py).
BRIEF_CACHE = _path("BRIEF_CACHE", _profiled("company_brief_cache.json", "{p}_brief_cache.json"))

# Where the copy-paste draft digests (index.md / index.html) are written. Set
# OUTBOX_DIR in .env to an absolute path to keep drafts in a fixed location
# regardless of where you run the agent from.
OUTBOX_DIR = _path("OUTBOX_DIR", _profiled("outbox", "outbox/{p}"))

# --- Models: vendor + model per task ---------------------------------------
# The pipeline splits work into two roles, each with its own vendor + model:
#   SEARCH  — the "searcher": discovery, per-company research, and profile refresh,
#             all with the hosted web_search tool. A cheap model is plenty.
#   WRITER  — the "writer": drafts the actual emails (no web search). Prose quality
#             matters here; the output is short so the cost stays tiny.
# Vendor is "anthropic" or "openai"; mix and match freely (e.g. OpenAI search +
# Claude writing). Set the matching API key(s) for the vendors you choose.
SEARCH_VENDOR = (_raw("SEARCH_VENDOR") or "anthropic").strip().lower()
SEARCH_MODEL = (_raw("SEARCH_MODEL") or _raw("ANTHROPIC_MODEL") or "claude-haiku-4-5").strip()
WRITER_VENDOR = (_raw("WRITER_VENDOR") or "anthropic").strip().lower()
WRITER_MODEL = (_raw("WRITER_MODEL") or "claude-sonnet-4-6").strip()

# Back-compat aliases: MODEL == the search model; DISCOVERY_MODEL may override it.
MODEL = SEARCH_MODEL
DISCOVERY_MODEL = (_raw("DISCOVERY_MODEL") or SEARCH_MODEL).strip()

# --- Token / cost controls -------------------------------------------------
# Reasoning effort + search_context_size apply only to the OpenAI (Responses API)
# backend. They are ignored by the Anthropic backend (Haiku 4.5 rejects effort).
DISCOVERY_EFFORT = (_raw("DISCOVERY_EFFORT") or "low").strip()
DRAFTING_EFFORT = (_raw("DRAFTING_EFFORT") or "low").strip()
SEARCH_CONTEXT_SIZE = (_raw("SEARCH_CONTEXT_SIZE") or "low").strip()
DISCOVERY_MAX_TOKENS = _int("DISCOVERY_MAX_TOKENS", 8000)
DRAFT_MAX_TOKENS = _int("DRAFT_MAX_TOKENS", 4000)
PROFILE_MAX_TOKENS = _int("PROFILE_MAX_TOKENS", 2000)
TARGET_REGION = (_raw("TARGET_REGION") or "North America").strip()
FIT_SCORE_THRESHOLD = _int("FIT_SCORE_THRESHOLD", 7)
TARGET_COMPANY_COUNT = _int("TARGET_COMPANY_COUNT", 5)
# Max companies from any one sector among a day's picks (diversifier).
MAX_PER_SECTOR = _int("MAX_PER_SECTOR", 2)
# Sector bucket keys to exclude entirely (see sectors.py for valid keys), e.g.
# "aerospace_defense". Avoided-but-qualified companies are kept as backlog, so
# removing a sector here makes them eligible again.
AVOID_SECTORS = _list("AVOID_SECTORS")
# Company-size ceiling. Picks larger than MAX_COMPANY_SIZE are excluded (a boutique
# seller's realistic prospects aren't household-name giants).
COMPANY_SIZE_ORDER = ["startup", "small", "mid", "large", "enterprise"]
MAX_COMPANY_SIZE = (_raw("MAX_COMPANY_SIZE") or "mid").strip().lower()
MAX_DISCOVERY_CALLS = _int("MAX_DISCOVERY_CALLS", 2)

# Cap how many already-seen companies are sent as a "don't repeat" hint. The DB
# filter still guarantees no duplicates; this keeps input from growing unbounded.
DENY_LIST_LIMIT = _int("DENY_LIST_LIMIT", 150)
# Re-fetch the seller's profile from the web at most every N days (cached otherwise).
PROFILE_REFRESH_DAYS = _int("PROFILE_REFRESH_DAYS", 7)

# Contact list size per company: one generic inbox + a few senior people.
MAX_PUBLIC_EMAILS = _int("MAX_PUBLIC_EMAILS", 1)      # generic inboxes (info@/contact@)
MAX_PEOPLE = _int("MAX_PEOPLE", 3)                    # named senior people
GUESSES_PER_PERSON = _int("GUESSES_PER_PERSON", 1)    # guessed addresses per person
FOLLOWUP_BUSINESS_DAYS = _int("FOLLOWUP_BUSINESS_DAYS", 5)
DB_PATH = _path("DB_PATH", _profiled("prospects.db", "{p}.db"))


def size_rank(size: str) -> int:
    """Index of a size bucket in COMPANY_SIZE_ORDER; unknown -> 'mid' (lenient)."""
    try:
        return COMPANY_SIZE_ORDER.index((size or "").strip().lower())
    except ValueError:
        return COMPANY_SIZE_ORDER.index("mid")


def size_allowed(size: str) -> bool:
    """True if `size` is at or below the configured MAX_COMPANY_SIZE ceiling."""
    return size_rank(size) <= size_rank(MAX_COMPANY_SIZE)


_VENDOR_KEYS = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}


def require_api_key(vendor: str) -> str:
    """Return the API key for `vendor` or raise a clear error if it is missing."""
    vendor = vendor.lower()
    key = {"anthropic": ANTHROPIC_API_KEY, "openai": OPENAI_API_KEY}.get(vendor)
    if key is None:
        raise RuntimeError(f"Unknown vendor '{vendor}' (expected 'anthropic' or 'openai').")
    if not key:
        env = _VENDOR_KEYS[vendor]
        raise RuntimeError(
            f"{env} is not set. Add it to the .env file (see .env.example) before "
            f"running steps that use the '{vendor}' vendor."
        )
    return key


def get_client(vendor: str):
    """Construct the SDK client for `vendor`. Imported lazily so non-API code
    paths (e.g. the status CLI) work without the package configured."""
    vendor = vendor.lower()
    if vendor == "anthropic":
        from anthropic import Anthropic
        return Anthropic(api_key=require_api_key("anthropic"))
    if vendor == "openai":
        from openai import OpenAI
        return OpenAI(api_key=require_api_key("openai"))
    raise RuntimeError(f"Unknown vendor '{vendor}' (expected 'anthropic' or 'openai').")
