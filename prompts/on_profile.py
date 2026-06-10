"""Prompt for refreshing the seller's own profile from its website."""
from __future__ import annotations

import agent_profile as profile

SYSTEM = (
    "You research a company's website and produce a tight factual brief of "
    "what they offer. No marketing fluff, no speculation — only what the site says."
)


def build_user(url: str) -> str:
    return (
        f"Use web search to open and read {url} (homepage + one services/about "
        f"page if linked — don't crawl). Summarise, in under 120 words, what "
        f"{profile.NAME} does: its core services, the technical methods it uses, and "
        "the kinds of problems and industries it serves. Write it as a tight brief "
        "another writer could use to explain the company to a prospect."
    )
