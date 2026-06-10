"""Keep a fresh, cached profile of Open Numerics' own positioning.

Fetched from the live website at most every PROFILE_REFRESH_DAYS days (it rarely
changes) so drafts reflect ON's services without paying a web-search call every
run. Falls back to the static ON_SERVICE_AREAS list in config if the fetch fails.
"""
from __future__ import annotations

import json
import os
from datetime import date

import config
from llm import WEB_SEARCH_TOOL, run_text
from prompts import on_profile as on_profile_prompts


def _cache_is_fresh(cached: dict) -> bool:
    if not cached.get("profile") or not cached.get("date"):
        return False
    try:
        age = (date.today() - date.fromisoformat(cached["date"])).days
    except ValueError:
        return False
    return 0 <= age < config.PROFILE_REFRESH_DAYS


def _fallback_profile() -> str:
    areas = "\n".join(f"- {a}" for a in config.ON_SERVICE_AREAS)
    return (
        f"{config.COMPANY_NAME} provides specialist scientific-computing "
        f"services, including:\n{areas}"
    )


def refresh_profile(client, *, force: bool = False) -> str:
    """Return a concise text profile of ON, refreshing from the website at most
    every PROFILE_REFRESH_DAYS days. Cached to on_profile_cache.json."""
    today = date.today().isoformat()

    if not force and os.path.exists(config.ON_PROFILE_CACHE):
        try:
            with open(config.ON_PROFILE_CACHE) as f:
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
            user_text=on_profile_prompts.build_user(config.ON_WEBSITE_URL),
            tools=[WEB_SEARCH_TOOL],
            max_output_tokens=config.PROFILE_MAX_TOKENS,
            effort=config.DISCOVERY_EFFORT,
        )
    except Exception as e:  # network/API issue — degrade gracefully
        print(f"  ! ON profile refresh failed ({e}); using static fallback.")
        return _fallback_profile()

    if not profile.strip():
        return _fallback_profile()

    try:
        with open(config.ON_PROFILE_CACHE, "w") as f:
            json.dump({"date": today, "profile": profile}, f, indent=2)
    except OSError:
        pass

    return profile
