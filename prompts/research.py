"""Prompts for per-winner research + initial-email drafting."""
from __future__ import annotations

from prompts.common import CANSPAM_GUIDANCE, sender_block

SYSTEM = (
    "You research a single prospect company for Open Numerics and draft a "
    "tailored cold outreach email. You ground every claim in what you actually "
    "find on the company's site and public sources — never fabricate facts, "
    "people, or email addresses. If you can't verify something, leave it out."
)


def build_user(cand, on_profile: str) -> str:
    """`cand` is a schemas.Candidate (duck-typed: name/domain/industry/why_fit/
    suggested_applications)."""
    apps = "\n".join(f"- {a}" for a in cand.suggested_applications) or "(none yet)"
    return f"""About Open Numerics:
{on_profile}

Prospect company: {cand.name}
Website: {cand.domain}
Industry: {cand.industry}
Why we think they fit: {cand.why_fit}
Preliminary applications:
{apps}

STEP 1 — Research: use web search to open and read {cand.domain} (home, about,
team/leadership, and any products/R&D pages) and to find the company's senior
people. Confirm what they actually do and who leads engineering / R&D / the company.

STEP 2 — Return, via `submit_company_outreach`:
- refined_applications: 2-4 specific, honest ways ON could help, tied to their real work.
- public_emails: only generic inboxes actually published on their site.
- people: senior/relevant individuals with name + title; include public_email ONLY
  if it is genuinely published, else null. Do NOT guess addresses — we generate
  guesses separately.
- A tailored initial email:
    * email_subject: accurate, specific, non-spammy.
    * email_body: ~120-180 words. Warm and concrete. Open with why you're reaching
      out to THEM specifically (reference their real work), name 1-2 concrete ON
      applications, and end with a low-pressure ask for a short call. Use a neutral
      greeting ("Hi there,") since the sender chooses the recipient. Close with this
      sign-off (verbatim identity):
{sender_block()}
- draft_notes: anything the sender should know before sending.

{CANSPAM_GUIDANCE}
"""
