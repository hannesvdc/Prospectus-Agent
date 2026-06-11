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


# Leading titles and trailing credentials to drop so we pick the real surname,
# e.g. "Jeremy Schrooten, PhD" -> jeremy.schrooten (not jeremy.phd).
_HONORIFICS = {"dr", "mr", "ms", "mrs", "mx", "prof", "sir", "madam"}
_SUFFIXES = {"phd", "md", "mba", "msc", "dvm", "dds", "jd", "cpa", "esq",
             "jr", "sr", "ii", "iii", "iv"}


def _name_parts(full_name: str) -> tuple[str, str]:
    tokens = []
    for raw in re.split(r"\s+", full_name.strip()):
        t = raw.strip(".,")  # drop surrounding punctuation (e.g. "Schrooten,")
        low = t.lower()
        if not t or low in _HONORIFICS or low in _SUFFIXES:
            continue
        tokens.append(t)
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
