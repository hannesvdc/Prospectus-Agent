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


# Cloudflare (and similar) hide addresses behind a placeholder like
# "[email protected]" that only decodes via on-page JavaScript — the scraper/model
# sees the placeholder, never the real address. Never store it.
_OBFUSCATED_RE = re.compile(
    r"\[email[\s ]*protected\]|/cdn-cgi/l/email-protection|__cf_email__", re.I)


def is_real_email(email: str) -> bool:
    """True if `email` is a genuine, storable address: exactly one '@', a non-empty
    local part, a domain with a dot, not a credential-built local part
    (jeremy.phd@), and not an obfuscation placeholder ([email protected])."""
    e = (email or "").strip()
    if not e or _OBFUSCATED_RE.search(e) or e.count("@") != 1:
        return False
    local, _, domain = e.partition("@")
    if not local or "." not in domain:
        return False
    return not is_credentialed_local_part(e)


def is_credentialed_local_part(email: str) -> bool:
    """True if the email's local-part contains an academic/professional credential
    as a dotted/dashed segment (e.g. "jeremy.phd@", "phd@", "dr.smith@"). Such an
    address was almost certainly built from a title rather than genuinely published,
    so callers should discard it and fall back to clean pattern guessing."""
    local = email.split("@", 1)[0].lower()
    segments = re.split(r"[._\-+]", local)
    return any(seg in _SUFFIXES or seg in _HONORIFICS for seg in segments)


def _local_candidates(first: str, last: str) -> list[tuple[str, str]]:
    """(pattern_id, local_part) pairs for a name, most-likely first.

    This ONE canonical list drives all three operations — blind guessing,
    pattern *inference* from a known real address, and pattern *application* to
    another name — so an inferred pattern always maps back to a format we can
    build, and guessing/inference never drift apart.
    """
    if not first:
        return []
    fi = first[0]
    if not last:
        return [("first", first)]                 # jane
    li = last[0]
    return [
        ("first.last", f"{first}.{last}"),         # jane.doe
        ("filast",     f"{fi}{last}"),             # jdoe
        ("firstlast",  f"{first}{last}"),          # janedoe
        ("first",      first),                     # jane
        ("fi.last",    f"{fi}.{last}"),            # j.doe
        ("first_last", f"{first}_{last}"),         # jane_doe
        ("firstli",    f"{first}{li}"),            # janed
        ("last.first", f"{last}.{first}"),         # doe.jane
        ("last",       last),                      # doe
    ]


def guess_emails(full_name: str, domain: str) -> list[str]:
    """Return likely email guesses for a person at a domain (most-likely first)."""
    first, last = _name_parts(full_name)
    domain = domain.strip().lower()
    if not domain or not first:
        return []
    # De-dupe, preserve order.
    seen: set[str] = set()
    out: list[str] = []
    for _pid, local in _local_candidates(first, last):
        addr = f"{local}@{domain}"
        if addr not in seen:
            seen.add(addr)
            out.append(addr)
    return out


def infer_pattern(known: list[tuple[str, str]], domain: str) -> str | None:
    """Learn a domain's email format from REAL addresses it actually uses.

    `known` is a list of (full_name, email) pairs that were genuinely published.
    Returns the local-part `pattern_id` they follow (majority vote; ties break
    toward the more common corporate format), or None if none match — e.g. the
    only address is a generic inbox, or the formats disagree unrecognisably.
    """
    domain = domain.strip().lower()
    priority = [pid for pid, _ in _local_candidates("first", "last")]
    votes: dict[str, int] = {}
    for name, email in known:
        if not email or "@" not in email:
            continue
        local, _, dom = email.strip().lower().partition("@")
        if dom != domain:
            continue                       # a personal gmail etc. tells us nothing
        first, last = _name_parts(name)
        if not first:
            continue
        for pid, cand in _local_candidates(first, last):
            if cand == local:
                votes[pid] = votes.get(pid, 0) + 1
                break                      # count the most-likely matching format
    if not votes:
        return None
    # Most votes wins; tie -> earlier (more common) canonical format.
    return max(votes, key=lambda p: (votes[p], -priority.index(p)))


def apply_pattern(full_name: str, domain: str, pattern_id: str) -> str:
    """Build the single address for a name using an inferred `pattern_id`.
    Returns "" if the pattern can't be built for this name (e.g. it needs a
    surname the person doesn't have)."""
    first, last = _name_parts(full_name)
    domain = domain.strip().lower()
    if not domain or not first:
        return ""
    for pid, local in _local_candidates(first, last):
        if pid == pattern_id:
            return f"{local}@{domain}"
    return ""
