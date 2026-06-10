"""Configuration: loads environment variables and exposes shared constants.

All tunables live in .env (see .env.example). This module reads them once and
provides typed access plus a single OpenAI client factory.
"""
from __future__ import annotations

import os

from dotenv import load_dotenv

load_dotenv()


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

# --- Open Numerics profile -------------------------------------------------
ON_WEBSITE_URL = os.getenv("ON_WEBSITE_URL", "https://opennumerics.com").strip()
ON_PROFILE_CACHE = "on_profile_cache.json"

# --- Sender identity -------------------------------------------------------
SENDER = {
    "name": os.getenv("SENDER_NAME", "").strip(),
    "title": os.getenv("SENDER_TITLE", "").strip(),
    "company": os.getenv("SENDER_COMPANY", "Open Numerics").strip(),
    "email": os.getenv("SENDER_EMAIL", "").strip(),
    "physical_address": os.getenv("SENDER_PHYSICAL_ADDRESS", "").strip(),
}

# --- Pipeline tunables -----------------------------------------------------
# gpt-5.5 is OpenAI's recommended model for the hosted web search tool.
MODEL = os.getenv("OPENAI_MODEL", "gpt-5.5").strip()
TARGET_REGION = os.getenv("TARGET_REGION", "North America").strip()
FIT_SCORE_THRESHOLD = _int("FIT_SCORE_THRESHOLD", 7)
TARGET_COMPANY_COUNT = _int("TARGET_COMPANY_COUNT", 5)
# Max companies from any one sector among a day's picks (diversifier).
MAX_PER_SECTOR = _int("MAX_PER_SECTOR", 2)
# Sector bucket keys to exclude entirely (see sectors.py for valid keys), e.g.
# "aerospace_defense". Avoided-but-qualified companies are kept as backlog, so
# removing a sector here makes them eligible again.
AVOID_SECTORS = _list("AVOID_SECTORS")
MAX_DISCOVERY_CALLS = _int("MAX_DISCOVERY_CALLS", 3)
FOLLOWUP_BUSINESS_DAYS = _int("FOLLOWUP_BUSINESS_DAYS", 5)
DB_PATH = os.getenv("DB_PATH", "prospects.db").strip()

# What ON does — used to ground every prompt even before the live profile
# refresh succeeds. Kept short and factual.
ON_SERVICE_AREAS = [
    "numerical simulation (CFD, FEA, multiphysics, custom solvers)",
    "uncertainty quantification (UQ) and sensitivity analysis",
    "scientific machine learning (physics-informed / surrogate models)",
    "GPU acceleration of scientific and engineering compute",
    "high-performance and parallel computing for modelling workloads",
]


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
