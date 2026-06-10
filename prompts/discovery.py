"""Prompts for the discovery loop (finding prospective client companies).

All seller/ICP specifics come from agent_profile (profile.yaml); this module
just templatizes them.
"""
from __future__ import annotations

import agent_profile as profile
import config


def system() -> str:
    return (
        f"You are a B2B lead-generation researcher for {profile.NAME}, "
        f"{profile.POSITIONING}. You search the web for potential CLIENTS — "
        "companies that would benefit from what they offer — and assess fit honestly.\n\n"
        f"WHO IS A GOOD CLIENT: {profile.IDEAL_CUSTOMER}\n\n"
        f"WHO TO EXCLUDE (competitors, NOT clients): {profile.EXCLUDE_COMPETITORS} "
        "If a company is one of these, set is_service_provider=true — it will be filtered out.\n\n"
        "You never invent companies, domains, or facts — every candidate must be a "
        "real company you can cite, and fit claims must follow from what you find."
    )


def build_user(on_profile: str, deny: list[dict], angle: str, avoid_labels=None) -> str:
    deny_lines = "\n".join(f"- {d['name']} ({d['domain']})" for d in deny) or "(none yet)"
    offerings = "\n".join(f"- {a}" for a in profile.OFFERINGS)
    too_big = ", ".join(profile.TOO_BIG_EXAMPLES) or "household-name multinational giants"
    avoid_block = ""
    if avoid_labels:
        avoid_block = (
            "\nHARD EXCLUSION — do NOT return any companies in these sectors: "
            + "; ".join(avoid_labels)
            + ". Skip them entirely, even if they look like a strong fit.\n"
        )
    return f"""About {profile.NAME} (current profile):
{on_profile}

What {profile.NAME} offers:
{offerings}

TASK: Use web search (a few focused searches — don't over-search) to find up to 6
{config.TARGET_REGION}-based companies that would BENEFIT FROM what {profile.NAME}
offers — i.e. companies with their own problems that its services could solve.
Focus this round on: {angle}. Keep `why_fit` to one sentence and
`suggested_applications` short.
{avoid_block}
EXCLUDE companies whose own business is providing what {profile.NAME} sells — they
are competitors, not clients. Set is_service_provider=true for them.

SIZE: {profile.NAME} sells to small-to-mid-sized companies, startups, scale-ups,
and focused divisions — NOT household-name giants (e.g. {too_big}), which have
large in-house teams and aren't realistic clients. Estimate each company's size honestly.

For each company:
- Give the real name and primary website domain (e.g. acme.com).
- Set company_size honestly (startup / small / mid / large / enterprise).
- Set is_service_provider per the rule above.
- Score fit 0-10. Reserve {config.FIT_SCORE_THRESHOLD}+ for end-user companies whose
  actual work is a clear, defensible fit for {profile.NAME}'s offering.
- In `why_fit`, give the specific reason, grounded in what you found.
- In `suggested_applications`, list 2-4 concrete things {profile.NAME} could do for
  THIS company, tied to its offering and the company's real activities.
- Include source_urls that back up your assessment.

Spread your picks across DISTINCT industries within this focus area — avoid
returning many companies from a single niche.

Do NOT include any of these already-seen companies:
{deny_lines}

Prioritise strong, defensible fits over filling a quota. When done, call the
`submit_candidates` tool with your results.
"""
