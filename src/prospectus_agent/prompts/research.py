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
    if profile.EXAMPLE_OPENERS:
        examples = "\n".join(f'  - "{o}"' for o in profile.EXAMPLE_OPENERS)
        opener_examples = (
            "\n\n           GOLD-STANDARD opener example(s) for the tone and two-tier "
            "framing to aim for (ADAPT the wording to this prospect — do NOT copy "
            f"verbatim):\n{examples}"
        )
    else:
        opener_examples = ""
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
- public_emails: at most ONE generic inbox actually published on their site. Look for
  it on the contact/about page and in the site footer — common forms are
  info@, contact@, hello@, sales@, support@, careers@/jobs@. Include it ONLY if you
  truly see it on the site; do NOT invent one. If none is published, return none.
- people: the 3 most senior / relevant decision-makers (e.g. CEO, CTO, VP/Head of
  Engineering or R&D) — no more than 3, with name + title. For the `name` field use
  ONLY the person's actual first and last name — STRIP academic/professional titles
  and credentials (Dr, Prof, PhD, MD, MBA, MSc, P.Eng, etc.); never let them leak into
  a name or an email. Include public_email ONLY if genuinely published, else null.
  Do NOT guess addresses (and never build one from a credential like ".phd@") — we
  generate guesses separately from the clean name.
- A tailored initial email:
    * email_subject: accurate, non-spammy, and framed around the AREAS {profile.NAME}
      helps with (e.g. simulation, scientific ML/AI, uncertainty quantification,
      HPC/GPU acceleration, computational advisory) — NOT a guess about the prospect's
      specific product or internal applications. e.g. "Open Numerics — simulation, AI
      and HPC for {{their field}}". Name our capability areas, not their use cases.
    * email_body: ~130-200 words, never more than 250. A cold INTRODUCTION and offer
      of services from outside specialists — NOT an industry peer, and never "compare
      notes." Throughout, keep the focus on WHAT'S IN IT FOR THEM — frame everything
      around the outcomes and value they would get, not a feature tour of {profile.NAME}.
      In order:
        1. Open with a plain one-sentence introduction of {profile.NAME} and what it
           helps teams do — e.g. "I'm reaching out to introduce {profile.NAME}. We help
           [audience] with [a few of its capabilities]." Draw the capabilities from what
           {profile.NAME} offers. Present {profile.NAME}'s offering as TWO DISTINCT,
           clearly-separated TIERS — make the two-tier structure obvious to the reader,
           e.g. "We do two things:" or "We work at two levels:":
             (i) WE ADVISE — help teams decide what to model, what's worth accelerating,
                 ML vs. numerical/simulation, build-vs-outsource, what a computational
                 roadmap should look like; and
             (ii) WE CODE — {profile.NAME} then builds and delivers the tools FOR them
                 (custom solvers, surrogate/ML models, GPU/HPC workflows,
                 uncertainty-aware analysis).
           Keep the two tiers visibly separate rather than merged into one run-on
           sentence. It must NEVER read as advising the client to build it themselves;
           {profile.NAME} does the hands-on work and hands over working tools.{opener_examples}
           Do NOT open by recapping the prospect's own work, and do NOT diagnose their
           needs (no "your work suggests you need…").
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
