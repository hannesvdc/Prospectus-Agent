"""Keep a fresh, cached profile of Open Numerics' own positioning.

Fetched from the live website once per day so every drafted email reflects
ON's current services. Falls back to the static ON_SERVICE_AREAS list in
config if the fetch fails.
"""
from __future__ import annotations

import json
import os
from datetime import date

import config
from llm import WEB_SEARCH_TOOL, run_text
from prompts import on_profile as on_profile_prompts


def _fallback_profile() -> str:
    areas = "\n".join(f"- {a}" for a in config.ON_SERVICE_AREAS)
    return (
        f"{config.COMPANY_NAME} provides specialist scientific-computing "
        f"services, including:\n{areas}"
    )


def refresh_profile(client, *, force: bool = False) -> str:
    """Return a concise text profile of ON, refreshing from the website at most
    once per day. Cached to on_profile_cache.json."""
    today = date.today().isoformat()

    if not force and os.path.exists(config.ON_PROFILE_CACHE):
        try:
            with open(config.ON_PROFILE_CACHE) as f:
                cached = json.load(f)
            if cached.get("date") == today and cached.get("profile"):
                return cached["profile"]
        except (json.JSONDecodeError, OSError):
            pass

    try:
        profile = run_text(
            client,
            model=config.MODEL,
            system=on_profile_prompts.SYSTEM,
            user_text=on_profile_prompts.build_user(config.ON_WEBSITE_URL),
            tools=[WEB_SEARCH_TOOL],
            max_output_tokens=4000,
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
