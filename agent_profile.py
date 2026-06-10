"""Loads the seller profile (profile.yaml) that templatizes the agent.

This is the single file a self-hosting user edits to describe their own business
and who they want to prospect — see profile.example.yaml. All domain-specific
content lives here; the rest of the codebase is generic.

PROFILE_PATH env var overrides the path. If the chosen file is absent, falls back
to profile.example.yaml so a fresh clone still runs.
"""
from __future__ import annotations

import os

import yaml

_PATH = os.getenv("PROFILE_PATH", "profile.yaml")
_FALLBACK = "profile.example.yaml"


def _load() -> tuple[dict, str]:
    path = _PATH if os.path.exists(_PATH) else _FALLBACK
    with open(path) as f:
        return (yaml.safe_load(f) or {}), path


_DATA, SOURCE = _load()
_company = _DATA.get("company") or {}
_targeting = _DATA.get("targeting") or {}


def _req(section: dict, section_name: str, key: str):
    value = section.get(key)
    if value in (None, "", []):
        raise RuntimeError(
            f"{SOURCE}: required field '{section_name}.{key}' is missing or empty "
            "(see profile.example.yaml)."
        )
    return value


def _clean(text: str) -> str:
    # YAML block scalars keep trailing newlines; collapse to a tidy single block.
    return " ".join(str(text).split())


# --- company ---------------------------------------------------------------
NAME = _req(_company, "company", "name")
WEBSITE = _req(_company, "company", "website")
POSITIONING = _req(_company, "company", "positioning")
OFFERINGS = _req(_company, "company", "offerings")
DESCRIPTION = _clean(_company.get("description", ""))
CREDIBILITY = _clean(_company.get("credibility", ""))  # optional trust line for emails

# --- targeting -------------------------------------------------------------
IDEAL_CUSTOMER = _clean(_req(_targeting, "targeting", "ideal_customer"))
EXCLUDE_COMPETITORS = _clean(_req(_targeting, "targeting", "exclude_competitors"))
INDUSTRY_ANGLES = _req(_targeting, "targeting", "industry_angles")
TOO_BIG_EXAMPLES = _targeting.get("too_big_examples") or []

# --- optional sector taxonomy override -------------------------------------
SECTORS = _DATA.get("sectors")  # dict[bucket -> list[keyword]] or None (use default)
