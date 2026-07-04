"""Best-effort domain deliverability check (MX lookup) — free, no API keys.

Client-side SMTP *mailbox* verification isn't possible from most machines:
outbound port 25 is commonly blocked, and Google/Microsoft-hosted domains
accept-all at the RCPT stage, so a per-address SMTP probe can't tell real from
fake. What we CAN do for free is check whether a domain accepts mail at all — a
domain with no MX record (and no A-record fallback) can't receive email, so any
address there is a guaranteed bounce. We drop those before they reach the send
list.

Uses `dig` (present on macOS/Linux). If `dig` is unavailable or the lookup
errors, we FAIL OPEN (assume deliverable) so a missing tool never silently drops
real prospects.
"""
from __future__ import annotations

import base64
import json
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.request

from prospectus_agent import config

_cache: dict[str, bool] = {}


def _dig(qtype: str, domain: str) -> list[str] | None:
    """Record strings for `qtype`; [] if the domain has none; None if the lookup
    could not run (tool missing / non-zero exit / timeout / error)."""
    if not shutil.which("dig"):
        return None
    try:
        r = subprocess.run(
            ["dig", "+short", qtype, domain],
            capture_output=True, text=True, timeout=8,
        )
    except Exception:
        return None
    if r.returncode != 0:
        return None
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _clean_domain(domain: str) -> str:
    d = (domain or "").strip().lower().rstrip(".")
    d = re.sub(r"^[a-z]+://", "", d)      # strip scheme if a URL slipped in
    d = d.split("/")[0]                    # strip any path
    d = d.split("@")[-1]                   # strip any local-part
    return d


def domain_deliverable(domain: str) -> bool:
    """True if `domain` can plausibly receive mail (has an MX record, or an
    A-record fallback per RFC implicit-MX). Fails OPEN when the lookup can't run,
    so a missing `dig` never drops prospects. Results are cached per process."""
    d = _clean_domain(domain)
    if not d:
        return False
    if d in _cache:
        return _cache[d]
    mx = _dig("MX", d)
    if mx is None:            # couldn't check -> assume deliverable
        _cache[d] = True
    elif mx:                  # has MX -> deliverable
        _cache[d] = True
    else:                     # no MX: fall back to A record (implicit MX)
        a = _dig("A", d)
        _cache[d] = (a is None) or bool(a)
    return _cache[d]


# --- Verifalia mailbox verification (HTTP API, no SDK) ----------------------
# Verifalia ships no Python SDK, so we call the REST API directly with the
# stdlib. Used only for profiles that opt in (settings.verify_emails) AND when
# VERIFALIA_* credentials are configured. Everything fails OPEN: any error,
# timeout, or out-of-credits returns "unknown", so the caller keeps the address
# rather than losing a prospect to a flaky check.

_VERIFALIA_BASE = "https://api.verifalia.com/v2.7"
_email_cache: dict[str, str] = {}

# Verifalia per-entry "classification" -> our simple verdict.
_CLASSIFICATION = {
    "deliverable": "valid",
    "undeliverable": "invalid",
    "risky": "risky",          # catch-all / role / temporary — accepted but unsure
    "unknown": "unknown",
}


def verification_available() -> bool:
    """True when Verifalia credentials are configured (so verification can run)."""
    return bool(config.VERIFALIA_USERNAME and config.VERIFALIA_PASSWORD)


def _verifalia(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{_VERIFALIA_BASE}{path}", data=data, method=method)
    token = base64.b64encode(
        f"{config.VERIFALIA_USERNAME}:{config.VERIFALIA_PASSWORD}".encode()
    ).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Accept", "application/json")
    if body is not None:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        raw = resp.read().decode()
        return resp.status, (json.loads(raw) if raw else {})


def _verdict(job: dict) -> str:
    entries = (job.get("entries") or {}).get("data") or []
    if not entries:
        return "unknown"
    cls = str(entries[0].get("classification") or "").strip().lower()
    return _CLASSIFICATION.get(cls, "unknown")


def verify_email(email: str) -> str:
    """Verify one address via Verifalia. Returns 'valid' | 'invalid' | 'risky' |
    'unknown'. Returns 'unknown' on missing credentials, HTTP error, timeout, or
    exhausted credits (fail open). Cached per process."""
    email = (email or "").strip().lower()
    if not email or not verification_available():
        return "unknown"
    if email in _email_cache:
        return _email_cache[email]
    verdict = "unknown"
    try:
        status, job = _verifalia(
            "POST", "/email-validations",
            {"entries": [{"inputData": email}], "quality": "standard"},
        )
        # 202 = still processing: poll the job until it completes (or we give up).
        job_id = (job.get("overview") or {}).get("id") or job.get("id")
        tries = 0
        while status == 202 and job_id and tries < 8:
            time.sleep(2)
            tries += 1
            status, job = _verifalia("GET", f"/email-validations/{job_id}")
            if (job.get("overview") or {}).get("status") == "Completed":
                break
        verdict = _verdict(job)
    except Exception:
        verdict = "unknown"
    _email_cache[email] = verdict
    return verdict
