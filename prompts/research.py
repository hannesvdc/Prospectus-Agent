"""Prompts for per-winner research + initial-email drafting."""
from __future__ import annotations

import agent_profile as profile


def system() -> str:
    return (
        f"You research a single prospect company for {profile.NAME} and draft a "
        "tailored cold outreach email. You ground every claim in what you actually "
        "find on the company's site and public sources — never fabricate facts, "
        "people, or email addresses. If you can't verify something, leave it out."
    )


def build_user(cand, on_profile: str) -> str:
    """`cand` is a schemas.Candidate (duck-typed: name/domain/industry/why_fit/
    suggested_applications)."""
    apps = "\n".join(f"- {a}" for a in cand.suggested_applications) or "(none yet)"
    credibility_note = (
        f' Also work in one brief credibility line, e.g. "{profile.CREDIBILITY}".'
        if profile.CREDIBILITY else ""
    )
    return f"""About {profile.NAME}:
{on_profile}

Prospect company: {cand.name}
Website: {cand.domain}
Industry: {cand.industry}
Why we think they fit: {cand.why_fit}
Preliminary applications:
{apps}

STEP 1 — Research (keep it lean): open and read at most the homepage plus ONE or
TWO key pages of {cand.domain} (an about/team or products page), and do at most a
couple of focused searches for the company's senior people. That's enough — don't
crawl the whole site. Confirm what they do and who leads engineering / R&D.

STEP 2 — Return, via `submit_company_outreach`:
- refined_applications: 2-4 specific, honest ways {profile.NAME} could help, tied to their real work.
- public_emails: at most ONE generic inbox published on their site (e.g. info@/contact@).
- people: the 3 most senior / relevant decision-makers (e.g. CEO, CTO, VP/Head of
  Engineering or R&D) — no more than 3, with name + title. Include public_email
  ONLY if genuinely published, else null. Do NOT guess addresses — we do that separately.
- A tailored initial email:
    * email_subject: accurate, specific, non-spammy.
    * email_body: ~120-170 words. This is a cold INTRODUCTION and offer of services.
      Position {profile.NAME} as outside specialists who could help — NOT as an
      industry peer. Do NOT imply you already work in or know their industry, and
      never use phrases like "compare notes." Cover, in this order:
        1. One specific line on why you're reaching out, grounded in their real work.
        2. One sentence introducing what {profile.NAME} does (the offer of services).
        3. 2-3 concrete example applications for THIS company — this is the most
           important part; tie each to their actual work.
        4. A simple, low-pressure ask for a short intro call to walk through how
           {profile.NAME} could help (do NOT frame it as comparing notes or trading
           expertise — you're offering yours).
      Use a neutral greeting ("Hi there,").{credibility_note} You may close with
      "Best,". Do NOT add a signature, sender name, title, company, or contact
      details — the sender's email client appends their own on send.
- draft_notes: anything the sender should know before sending.
"""
