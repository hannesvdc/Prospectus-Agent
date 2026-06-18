"""Discovery: the bounded web-search loop that surfaces new prospect companies.

At most MAX_DISCOVERY_CALLS rounds. Each round is ONE logical API call, rotates
the industry angle (with a per-day offset so the lead sector varies), and returns
a batch of scored candidates. We accumulate qualified, newly-seen companies as
"winners" until we have TARGET_COMPANY_COUNT or run out of rounds.

Diversifier: no more than MAX_PER_SECTOR winners may share a sector (classified
from the company's industry), so a single sector (e.g. aviation) can't dominate
a day's picks. Qualified companies that don't make the cut are still stored as
'new' — a backlog that future runs draft first (also subject to the cap), so good
leads aren't wasted.

Every candidate returned — fit or not — is written to the DB so it never
resurfaces. Qualified, newly-seen companies are returned as "winners".
"""
from __future__ import annotations

import json
from datetime import date

from prospectus_agent import agent_profile as profile
from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import sectors
from prospectus_agent.llm import WEB_SEARCH_TOOL, run_with_submit
from prospectus_agent.prompts import discovery as discovery_prompts
from prospectus_agent.schemas import Candidate, DiscoveryResult

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
                            "description": f"Why this company plausibly needs {profile.NAME}'s offerings",
                        },
                        "suggested_applications": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": f"Concrete ways {profile.NAME} could help, tied to this company's actual work",
                        },
                        "fit_score": {
                            "type": "integer",
                            "description": f"Fit for {profile.NAME}, 0 (none) to 10 (ideal)",
                        },
                        "company_size": {
                            "type": "string",
                            "enum": ["startup", "small", "mid", "large", "enterprise"],
                            "description": (
                                "Approximate headcount: startup (<50), small (50-200), "
                                "mid (200-1000), large (1000-10000), enterprise (10000+)."
                            ),
                        },
                        "is_service_provider": {
                            "type": "boolean",
                            "description": (
                                f"True if the company ITSELF sells the same kind of "
                                f"product or services as {profile.NAME} (a peer or "
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
                        "company_size",
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

def _row_to_candidate(row) -> Candidate:
    """Reconstruct a Candidate from a stored backlog row."""
    return Candidate(
        name=row["name"],
        domain=row["domain"],
        hq_location=row["hq_location"] or "",
        industry=row["industry"] or "",
        why_fit=row["why_fit"] or "",
        suggested_applications=json.loads(row["suggested_applications"] or "[]"),
        fit_score=row["fit_score"] or 0,
        source_urls=json.loads(row["source_urls"] or "[]"),
    )


def discover(client, conn, on_profile: str) -> list[tuple[int, Candidate]]:
    """Run the discovery loop. Returns a list of (company_id, Candidate) for the
    qualified winners (up to TARGET_COMPANY_COUNT), diversified across sectors."""
    seen = db.get_seen_domains(conn)
    deny = db.deny_list(conn, limit=config.DENY_LIST_LIMIT)
    winners: list[tuple[int, Candidate]] = []
    sector_counts: dict[str, int] = {}

    def try_select(cid: int, cand: Candidate) -> bool:
        """Add as a winner unless the target is met, its sector is avoided, or
        its sector is already at the per-sector cap."""
        if len(winners) >= config.TARGET_COMPANY_COUNT:
            return False
        bucket = sectors.classify(cand.industry, cand.why_fit)
        if bucket in config.AVOID_SECTORS:
            return False
        if sector_counts.get(bucket, 0) >= config.MAX_PER_SECTOR:
            return False
        winners.append((cid, cand))
        sector_counts[bucket] = sector_counts.get(bucket, 0) + 1
        return True

    # 1) Drain the backlog first: previously-found qualified companies that were
    #    never drafted (e.g. capped on an earlier day). Subject to the same cap.
    backlog = db.companies_by_status(conn, "new")
    seeded = 0
    for row in backlog:
        if len(winners) >= config.TARGET_COMPANY_COUNT:
            break
        if try_select(row["id"], _row_to_candidate(row)):
            seeded += 1
    if seeded:
        print(f"  Seeded {seeded} prospect(s) from the backlog (status=new).")

    # 2) Fresh discovery rounds, rotating the lead sector by day.
    avoid_labels = [sectors.label(b) for b in config.AVOID_SECTORS]
    angles = profile.INDUSTRY_ANGLES
    offset = date.today().toordinal() % len(angles)
    for round_idx in range(config.MAX_DISCOVERY_CALLS):
        if len(winners) >= config.TARGET_COMPANY_COUNT:
            break

        angle = angles[(offset + round_idx) % len(angles)]
        print(f"  Discovery round {round_idx + 1}/{config.MAX_DISCOVERY_CALLS} "
              f"({len(winners)}/{config.TARGET_COMPANY_COUNT} so far) — {angle.split('(')[0].strip()}")

        raw = run_with_submit(
            client,
            model=config.DISCOVERY_MODEL,
            system=discovery_prompts.system(),
            user_text=discovery_prompts.build_user(on_profile, deny, angle, avoid_labels),
            tools=[WEB_SEARCH_TOOL, SUBMIT_CANDIDATES_TOOL],
            submit_tool_name="submit_candidates",
            max_output_tokens=config.DISCOVERY_MAX_TOKENS,
            effort=config.DISCOVERY_EFFORT,
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

            # Exclude competitors (sell these services themselves) and companies
            # above the size ceiling — both regardless of score, stored as
            # not_a_fit so they don't recur.
            qualified = (
                cand.fit_score >= config.FIT_SCORE_THRESHOLD
                and not cand.is_service_provider
                and config.size_allowed(cand.company_size)
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
            # Qualified-but-not-selected stays 'new' (a backlog for a future run).
            if qualified:
                try_select(cid, cand)

        print(f"    +{new_this_round} new companies seen this round")

    return winners
