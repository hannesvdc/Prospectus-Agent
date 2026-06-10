"""Prompt for refreshing Open Numerics' own profile from its website."""
from __future__ import annotations

SYSTEM = (
    "You research a company's website and produce a tight factual brief of "
    "what they offer. No marketing fluff, no speculation — only what the site says."
)


def build_user(url: str) -> str:
    return (
        f"Use web search to open and read {url} (and obvious sub-pages like "
        "services/about if linked). Summarise, in under 250 words, what Open "
        "Numerics does: its core services, the technical methods it uses, and the "
        "kinds of problems and industries it serves. Write it as a brief another "
        "writer could use to explain ON to a prospect."
    )
