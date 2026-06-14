"""Loads the seller profile (profile.yaml) that templatizes the agent.

This is the single file a self-hosting user edits to describe their own business
and who they want to prospect — see profile.example.yaml. All domain-specific
content lives here; the rest of the codebase is generic.

PROFILE_PATH env var overrides the path. If the chosen file is absent, falls back
to profile.example.yaml so a fresh clone still runs.
"""
from __future__ import annotations

import os
from pathlib import Path

import yaml

from prospectus_agent import config

# PROFILE_PATH (absolute or relative) overrides the default; relative values and
# the defaults resolve against the project HOME, so the agent runs from anywhere.
_raw = (os.getenv("PROFILE_PATH") or "").strip()
_p = Path(_raw).expanduser() if _raw else Path("profile.yaml")
_PATH = str(_p if _p.is_absolute() else config.HOME / _p)
_FALLBACK = str(config.HOME / "profile.example.yaml")


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

# Optional gold-standard opener exemplars — endorsed sample opening lines the
# drafter adapts (not copies) to anchor tone/structure. List of strings; each is
# collapsed to a single tidy block. Empty list if unset.
EXAMPLE_OPENERS = [_clean(o) for o in (_company.get("example_openers") or []) if str(o).strip()]

# --- targeting -------------------------------------------------------------
IDEAL_CUSTOMER = _clean(_req(_targeting, "targeting", "ideal_customer"))
EXCLUDE_COMPETITORS = _clean(_req(_targeting, "targeting", "exclude_competitors"))
INDUSTRY_ANGLES = _req(_targeting, "targeting", "industry_angles")
TOO_BIG_EXAMPLES = _targeting.get("too_big_examples") or []

# --- optional sector taxonomy override -------------------------------------
SECTORS = _DATA.get("sectors")  # dict[bucket -> list[keyword]] or None (use default)
