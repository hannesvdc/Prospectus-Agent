"""Keep a fresh, cached brief of the seller company's own positioning.

Fetched from the website (from profile.yaml) at most every PROFILE_REFRESH_DAYS
days so drafts reflect current services without a web-search call every run.
Falls back to the profile's offerings/description if the fetch fails.
"""
from __future__ import annotations

import json
import os
from datetime import date

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent.llm import WEB_SEARCH_TOOL, run_text
from prospectus_agent.prompts import on_profile as on_profile_prompts


def _cache_is_fresh(cached: dict) -> bool:
    if not cached.get("profile") or not cached.get("date"):
        return False
    try:
        age = (date.today() - date.fromisoformat(cached["date"])).days
    except ValueError:
        return False
    return 0 <= age < config.PROFILE_REFRESH_DAYS


def _fallback_profile() -> str:
    if agent_profile.DESCRIPTION:
        return agent_profile.DESCRIPTION
    offerings = "\n".join(f"- {a}" for a in agent_profile.OFFERINGS)
    return f"{agent_profile.NAME} offers:\n{offerings}"


def refresh_profile(client, *, force: bool = False) -> str:
    """Return a concise text brief of the seller company, refreshing from the
    website at most every PROFILE_REFRESH_DAYS days. Cached to BRIEF_CACHE."""
    today = date.today().isoformat()

    if not force and os.path.exists(config.BRIEF_CACHE):
        try:
            with open(config.BRIEF_CACHE) as f:
                cached = json.load(f)
            if _cache_is_fresh(cached):
                return cached["profile"]
        except (json.JSONDecodeError, OSError):
            pass

    try:
        profile = run_text(
            client,
            model=config.DISCOVERY_MODEL,
            system=on_profile_prompts.SYSTEM,
            user_text=on_profile_prompts.build_user(agent_profile.WEBSITE),
            tools=[WEB_SEARCH_TOOL],
            max_output_tokens=config.PROFILE_MAX_TOKENS,
            effort=config.DISCOVERY_EFFORT,
        )
    except Exception as e:  # network/API issue — degrade gracefully
        print(f"  ! company brief refresh failed ({e}); using profile fallback.")
        return _fallback_profile()

    if not profile.strip():
        return _fallback_profile()

    try:
        with open(config.BRIEF_CACHE, "w") as f:
            json.dump({"date": today, "profile": profile}, f, indent=2)
    except OSError:
        pass

    return profile
