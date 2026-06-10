"""Deterministic email-address guessing from a person's name + company domain.

Public emails the model actually found are kept as-is (confidence 'public').
For named people without a published address we generate the common corporate
patterns and tag them 'guessed' so the sender knows they are unverified.
"""
from __future__ import annotations

import re
import unicodedata


def _slug(text: str) -> str:
    """Lowercase ASCII, letters only (strip accents, punctuation, spaces)."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", text.lower())


def _name_parts(full_name: str) -> tuple[str, str]:
    tokens = [t for t in re.split(r"\s+", full_name.strip()) if t]
    # Drop common honorifics.
    honorifics = {"dr", "dr.", "mr", "mr.", "ms", "ms.", "mrs", "mrs.", "prof", "prof."}
    tokens = [t for t in tokens if t.lower().strip(".") not in {h.strip('.') for h in honorifics}]
    if not tokens:
        return "", ""
    if len(tokens) == 1:
        return _slug(tokens[0]), ""
    return _slug(tokens[0]), _slug(tokens[-1])


def guess_emails(full_name: str, domain: str) -> list[str]:
    """Return likely email guesses for a person at a domain (most-likely first)."""
    first, last = _name_parts(full_name)
    domain = domain.strip().lower()
    if not domain or not first:
        return []

    patterns: list[str] = []
    if last:
        patterns.append(f"{first}.{last}@{domain}")   # jane.doe@
        patterns.append(f"{first[0]}{last}@{domain}")  # jdoe@
        patterns.append(f"{first}{last}@{domain}")     # janedoe@
    patterns.append(f"{first}@{domain}")               # jane@

    # De-dupe, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for p in patterns:
        if p not in seen:
            seen.add(p)
            out.append(p)
    return out
