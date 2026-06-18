"""Prompt for refreshing the seller's own profile from its website."""
from __future__ import annotations

from prospectus_agent import agent_profile as profile

SYSTEM = (
    "You produce a tight factual brief of what a company offers, for a writer who "
    "will use it to explain the company to a prospect. The company's own stated "
    "positioning and offerings are authoritative; use its website to add concrete "
    "detail and current specifics. No marketing fluff, no speculation."
)


def build_user(url: str) -> str:
    offerings = "\n".join(f"- {o}" for o in profile.OFFERINGS)
    return (
        f"{profile.NAME} positions itself as {profile.POSITIONING}. Its stated "
        f"offerings are:\n{offerings}\n\n"
        f"Use web search to open and read {url} (homepage + one services/about "
        f"page if linked — don't crawl) to confirm and enrich the above with concrete "
        f"detail. Then summarise, in under 130 words, what {profile.NAME} does: its "
        "core services or product, the methods or technology it uses, and the kinds "
        "of problems and audiences it serves. Cover the full breadth of the stated "
        "offerings above (don't fixate on one) — if the website omits something the "
        "offerings list, still include it. Write it as a tight brief another writer "
        "could use to explain the company to a prospect."
    )
