"""Discovery: the bounded web-search loop that surfaces new prospect companies.

At most MAX_DISCOVERY_CALLS rounds. Each round is ONE logical API call (the
server-side web_search loop and any pause_turn resumes count as part of it).
Each round rotates the industry angle, asks for a batch of scored candidates,
filters to score >= threshold and not-already-seen, and accumulates until we
have TARGET_COMPANY_COUNT qualified companies or run out of rounds.

Every candidate returned — fit or not — is written to the DB so it never
resurfaces. Qualified, newly-seen companies are returned as "winners".
"""
from __future__ import annotations

import config
import db
from llm import WEB_SEARCH_TOOL, run_with_submit
from prompts import discovery as discovery_prompts
from schemas import Candidate, DiscoveryResult

SUBMIT_CANDIDATES_TOOL = {
    "type": "function",
    "name": "submit_candidates",
    "description": "Submit the prospect companies you found, with fit scores.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "domain": {
                            "type": "string",
                            "description": "Primary website domain, e.g. acme.com",
                        },
                        "hq_location": {"type": "string"},
                        "industry": {"type": "string"},
                        "why_fit": {
                            "type": "string",
                            "description": "Why this company plausibly needs ON's services",
                        },
                        "suggested_applications": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Concrete ON applications tied to this company's actual work",
                        },
                        "fit_score": {
                            "type": "integer",
                            "description": "Fit for Open Numerics, 0 (none) to 10 (ideal)",
                        },
                        "is_service_provider": {
                            "type": "boolean",
                            "description": (
                                "True if the company ITSELF sells simulation / UQ / "
                                "scientific-ML / HPC services or software (a peer or "
                                "competitor, NOT a potential client)."
                            ),
                        },
                        "source_urls": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "URLs that back up your assessment",
                        },
                    },
                    "required": [
                        "name",
                        "domain",
                        "hq_location",
                        "industry",
                        "why_fit",
                        "suggested_applications",
                        "fit_score",
                        "is_service_provider",
                        "source_urls",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["candidates"],
        "additionalProperties": False,
    },
}

def discover(client, conn, on_profile: str) -> list[tuple[int, Candidate]]:
    """Run the discovery loop. Returns a list of (company_id, Candidate) for the
    qualified, newly-seen winners (up to TARGET_COMPANY_COUNT)."""
    seen = db.get_seen_domains(conn)
    deny = db.deny_list(conn)
    winners: list[tuple[int, Candidate]] = []

    for round_idx in range(config.MAX_DISCOVERY_CALLS):
        if len(winners) >= config.TARGET_COMPANY_COUNT:
            break

        angle = discovery_prompts.INDUSTRY_ANGLES[round_idx % len(discovery_prompts.INDUSTRY_ANGLES)]
        print(f"  Discovery round {round_idx + 1}/{config.MAX_DISCOVERY_CALLS} "
              f"({len(winners)}/{config.TARGET_COMPANY_COUNT} so far) — {angle.split('(')[0].strip()}")

        raw = run_with_submit(
            client,
            model=config.MODEL,
            system=discovery_prompts.SYSTEM,
            user_text=discovery_prompts.build_user(on_profile, deny, angle),
            tools=[WEB_SEARCH_TOOL, SUBMIT_CANDIDATES_TOOL],
            submit_tool_name="submit_candidates",
        )
        if not raw:
            print("    (no candidates returned this round)")
            continue

        try:
            result = DiscoveryResult.model_validate(raw)
        except Exception as e:
            print(f"    ! could not validate model output: {e}")
            continue

        new_this_round = 0
        for cand in result.candidates:
            dom = db.normalize_domain(cand.domain)
            if not dom or dom in seen:
                continue
            seen.add(dom)
            deny.append({"name": cand.name, "domain": dom})

            # A company that sells these services itself is a competitor, not a
            # client — exclude it regardless of score (stored so it won't recur).
            qualified = (
                cand.fit_score >= config.FIT_SCORE_THRESHOLD
                and not cand.is_service_provider
            )
            status = "new" if qualified else "not_a_fit"
            cid = db.upsert_company(
                conn,
                name=cand.name,
                domain=dom,
                hq_location=cand.hq_location,
                industry=cand.industry,
                fit_score=cand.fit_score,
                why_fit=cand.why_fit,
                suggested_applications=cand.suggested_applications,
                source_urls=cand.source_urls,
                status=status,
            )
            new_this_round += 1
            if qualified and len(winners) < config.TARGET_COMPANY_COUNT:
                winners.append((cid, cand))

        print(f"    +{new_this_round} new companies seen this round")

    return winners
