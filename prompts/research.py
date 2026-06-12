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
        f' Include one strong credibility sentence grounded in track record and '
        f'experience — not a re-list of capabilities. Lean on the team\'s deep ties '
        f'to academic research and its hands-on experience delivering for companies '
        f'in industry; dress it up naturally, e.g. "{profile.CREDIBILITY}".'
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
    * email_body: ~130-200 words, never more than 250. A cold INTRODUCTION and offer
      of services from outside specialists — NOT an industry peer, and never "compare
      notes." Throughout, keep the focus on WHAT'S IN IT FOR THEM — frame everything
      around the outcomes and value they would get, not a feature tour of {profile.NAME}.
      In order:
        1. Open with a plain one-sentence introduction of {profile.NAME} and what it
           helps teams do — e.g. "I'm reaching out to introduce {profile.NAME}. We help
           [audience] with [a few of its capabilities]." Draw the capabilities from what
           {profile.NAME} offers. Do NOT open by recapping the prospect's own work, and
           do NOT diagnose their needs (no "your work suggests you need…").
        2. Then, at a HIGH LEVEL, suggest the kinds of problems {profile.NAME} helps
           with that are relevant to their space, expressed as the benefit to them
           (e.g. faster turnaround, more confidence in results, less compute cost) —
           illustrative, not prescriptive; one or two light, plausible connections to
           their domain. Do NOT prescribe fixes for their specific product or claim to
           know their internals.
        3. A simple, low-pressure ask for a short intro call to see whether
           {profile.NAME} could be useful to them.
      Use a neutral greeting ("Hi there,").{credibility_note} You may close with "Best,".
      Do NOT add a signature, sender name, title, company, or contact details — the
      sender's email client appends their own on send.
- draft_notes: anything the sender should know before sending.
"""
