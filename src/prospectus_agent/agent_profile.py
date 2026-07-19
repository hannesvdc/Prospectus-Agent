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

from prospectus_agent import config

# config resolves the active profile path (honoring $PROFILE_PATH, the --profile
# flag via $PROSPECTUS_PROFILE, and $DEFAULT_PROFILE). Falls back to the committed
# example so a fresh clone still runs.
_PATH = config.PROFILE_PATH
_FALLBACK = str(config.HOME / "profile.example.yaml")


def _load() -> tuple[dict, str]:
    path = _PATH if os.path.exists(_PATH) else _FALLBACK
    with open(path) as f:
        return (yaml.safe_load(f) or {}), path


_DATA, SOURCE = _load()
_company = _DATA.get("company") or {}
_targeting = _DATA.get("targeting") or {}
_settings = _DATA.get("settings") or {}


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

# Optional capability/feature areas named in the email SUBJECT line (kept generic;
# the prospect's own use cases are never guessed). List of short phrases.
CAPABILITY_AREAS = [str(a).strip() for a in (_company.get("capability_areas") or []) if str(a).strip()]

# Optional business-specific voice notes — framing dos/don'ts injected into the
# email-body prompt (how to describe what you do, words to avoid, etc.). This is
# where seller-specific messaging lives so the engine itself stays generic.
VOICE_NOTES = [_clean(n) for n in (_company.get("voice_notes") or []) if str(n).strip()]

# Optional opening style for the email body. "problem" leads with a challenge
# common to teams doing the prospect's kind of work (framed as a pattern, not a
# diagnosis), then introduces the seller; anything else (default "intro") opens
# with a plain seller introduction. Per-profile, so one business can lead with the
# client's problem while another stays product/intro-led.
OPENING_STYLE = _clean(_company.get("opening_style", "")).lower() or "intro"

# Optional closing style for the email body. "feedback" makes a low-commitment
# demonstration offer (invite one workflow they'd want or a bottleneck they face, and
# offer to run it through the product and show the result) instead of a call; anything
# else (default "call") asks for a short intro call. Per-profile, so a product-led
# business can invite a demo while a services one asks for a meeting.
CLOSING_STYLE = _clean(_company.get("closing_style", "")).lower() or "call"

# Optional recent product/research innovations to surface in FOLLOW-UP emails as a
# "here's what's new since we first wrote" beat. List of short phrases; each is
# collapsed to a tidy block. Empty list if unset (follow-ups then omit the beat).
RECENT_INNOVATIONS = [_clean(n) for n in (_company.get("recent_innovations") or []) if str(n).strip()]

# --- targeting -------------------------------------------------------------
IDEAL_CUSTOMER = _clean(_req(_targeting, "targeting", "ideal_customer"))
EXCLUDE_COMPETITORS = _clean(_req(_targeting, "targeting", "exclude_competitors"))
INDUSTRY_ANGLES = _req(_targeting, "targeting", "industry_angles")
TOO_BIG_EXAMPLES = _targeting.get("too_big_examples") or []
# Geographic focus for discovery — per-profile; falls back to $TARGET_REGION (.env)
# then the built-in default. Use "Global" (or "worldwide") for no geographic limit.
REGION = _clean(_targeting.get("region", "")) or config.TARGET_REGION

# --- optional sector taxonomy override -------------------------------------
SECTORS = _DATA.get("sectors")  # dict[bucket -> list[keyword]] or None (use default)

# --- settings --------------------------------------------------------------
# Opt in to real mailbox verification (Verifalia) for this profile. Needs
# VERIFALIA_* credentials in .env to actually run; otherwise silently no-ops.
VERIFY_EMAILS = bool(_settings.get("verify_emails", False))
