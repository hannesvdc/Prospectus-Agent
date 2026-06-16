"""Prompts for per-winner research + initial-email drafting."""
from __future__ import annotations

from prospectus_agent import agent_profile as profile


def system() -> str:
    return (
        f"You research a single prospect company for {profile.NAME} and draft a "
        "tailored cold outreach email. You ground every claim in what you actually "
        "find on the company's site and public sources — never fabricate facts, "
        "people, or email addresses. If you can't verify something, leave it out."
    )


def _credibility_note() -> str:
    if not profile.CREDIBILITY:
        return ""
    return (
        ' Include one strong credibility sentence grounded in track record and '
        'experience — not a re-list of capabilities. Lean on the team\'s deep ties '
        'to academic research and its hands-on experience delivering for companies '
        f'in industry; dress it up naturally, e.g. "{profile.CREDIBILITY}".'
    )


def _opener_examples() -> str:
    if not profile.EXAMPLE_OPENERS:
        return ""
    examples = "\n".join(f'  - "{o}"' for o in profile.EXAMPLE_OPENERS)
    return (
        "\n\n           GOLD-STANDARD opener example(s) for the tone and two-tier "
        "framing to aim for (ADAPT the wording to this prospect — do NOT copy "
        f"verbatim):\n{examples}"
    )


def email_rules() -> str:
    """The subject + body writing rules for an outreach email. Shared by the
    initial-draft prompt and the refine/redraft prompt so the two never drift —
    tweak the email voice here and both paths pick it up."""
    credibility_note = _credibility_note()
    opener_examples = _opener_examples()
    return f"""    * email_subject: accurate, non-spammy, and framed around the AREAS {profile.NAME}
      helps with (e.g. simulation, scientific ML/AI, uncertainty quantification,
      HPC/GPU acceleration, computational advisory) — NOT a guess about the prospect's
      specific product or internal applications. e.g. "Open Numerics — simulation, AI
      and HPC for {{their field}}". Name our capability areas, not their use cases.
    * email_body: ~120-160 words, never more than 200. A cold INTRODUCTION and offer
      of services from outside specialists — NOT an industry peer, and never "compare
      notes." Write the ENTIRE email as natural, flowing PROSE in SHORT paragraphs
      (2-3 sentences each; keep it skimmable) — NO bullet points, numbered lists, or
      headings anywhere. Throughout, keep the focus on WHAT'S IN IT FOR THEM — frame
      everything around the outcomes and value they would get, not a feature tour of
      {profile.NAME}. The numbered points below are instructions to you, not a format
      for the email. In order:
        1. Open with a plain one-sentence introduction of {profile.NAME} and what it
           helps teams do — e.g. "I'm reaching out to introduce {profile.NAME}. We help
           [audience] with [a few of its capabilities]." Draw the capabilities from what
           {profile.NAME} offers. Convey that {profile.NAME} works at TWO levels —
           it ADVISES (helping teams see where modeling, simulation, ML, or
           acceleration can make the biggest difference, and define the path forward)
           and then BUILDS the software/workflows itself. Keep it LIGHT and easy to
           read: a short sentence or two for the advise-then-build idea, then you MAY
           add ONE short follow-up sentence naming a few example tools (as the example
           opener does, e.g. "That can include custom solvers, surrogate models,
           GPU/HPC workflows, and uncertainty-aware analysis."). Do NOT cram the dual
           purpose AND the tool list into a single heavy sentence; the specific value
           belongs in the next paragraph. Conversational, like the example opener(s)
           below. Phrase the build side as "then we build…" — do NOT use stiff
           role-nouns like "implementers". Avoid phrasing that implies the client
           doesn't understand their own work — NEVER say "decide what to model" or
           "what to model" (condescending); "decide where [techniques] can make the
           biggest difference" is good. It must NEVER read as advising the client to
           build it themselves; {profile.NAME} does the hands-on work and hands over
           working tools.{opener_examples}
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
      sender's email client appends their own on send."""


def build_user(cand, on_profile: str) -> str:
    """`cand` is a schemas.Candidate (duck-typed: name/domain/industry/why_fit/
    suggested_applications)."""
    apps = "\n".join(f"- {a}" for a in cand.suggested_applications) or "(none yet)"
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
{email_rules()}
- draft_notes: anything the sender should know before sending.
"""
