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
        f'experience (not a re-list of capabilities), e.g. "{profile.CREDIBILITY}".'
    )


def _opener_examples() -> str:
    if not profile.EXAMPLE_OPENERS:
        return ""
    examples = "\n".join(f'  - "{o}"' for o in profile.EXAMPLE_OPENERS)
    return (
        "\n\n           GOLD-STANDARD opener example(s) for the tone and structure to "
        "aim for (ADAPT the wording to this prospect — do NOT copy verbatim):\n"
        f"{examples}"
    )


def _voice_notes_block() -> str:
    """Business-specific framing dos/don'ts (profile.voice_notes). These carry the
    seller's messaging (e.g. how to describe what they do, words to avoid) so the
    generic engine stays business-agnostic."""
    if not profile.VOICE_NOTES:
        return ""
    notes = "\n".join(f"           - {n}" for n in profile.VOICE_NOTES)
    return (f"\n           Follow these {profile.NAME}-specific voice notes when "
            f"writing the email:\n{notes}")


def _opening_step(opener_examples: str, voice_notes: str) -> str:
    """Step 1 of the email body. Two shapes, chosen by profile.OPENING_STYLE:
    'problem' leads with a challenge inherent to the prospect's own work, then
    introduces the seller; anything else opens with a plain seller introduction."""
    if profile.OPENING_STYLE == "problem":
        return (
            f"""1. LEAD WITH THE PROBLEM, not with {profile.NAME}. Open by naming a
           challenge that is INHERENT to the prospect's OWN work — rooted in the
           technical nature of what THEY specifically build, drawn from your research on
           their actual products/workflows. Frame it as an intrinsic difficulty of that
           work, spoken directly to them — NOT as a statistical pattern that lots of
           similar companies share. Do NOT use generic-plurality framings like "teams
           often…", "companies like yours frequently…", "the same bottleneck", or "many
           teams run into…": in a niche field there may be only a handful of such
           companies, so claiming a widespread pattern rings hollow and generic. Instead
           tie the challenge to what THEIR work demands, e.g. "Building [their specific
           product] means [challenge] gets harder exactly as [constraint — accuracy,
           safety margins, latency, scale] gets tighter." Keep it to a sentence or two.
           Do NOT claim to know their internal stack, tools, or that they specifically
           have a problem ("your pipeline is too slow") — name the difficulty the work
           itself imposes, not a diagnosis of their internals. Then, in ONE short
           sentence, pivot to introduce {profile.NAME} as the team that helps with
           exactly that — a LIGHT, high-level intro of what {profile.NAME} does and who
           it helps (draw on the brief and offerings above; use the example opener(s)
           below for tone, but ADAPT them to land AFTER the problem hook rather than as
           the first line).{opener_examples}{voice_notes}""")
    return (
        f"""1. Open with a plain one-sentence introduction of {profile.NAME} and what it
           helps its audience do — e.g. "I'm reaching out to introduce {profile.NAME}.
           We help [audience] with [a few of its capabilities]." Draw on the brief and
           offerings above. Keep it LIGHT and high-level — a short sentence or two,
           conversational, like the example opener(s) below.{opener_examples}
           Do NOT open by recapping the prospect's own work, and do NOT diagnose their
           needs (no "your work suggests you need…").{voice_notes}""")


def email_rules() -> str:
    """The subject + body writing rules for an outreach email. Shared by the
    initial-draft prompt and the refine/redraft prompt so the two never drift.

    The GENERIC skeleton (prose not lists, value-to-them, greeting/CTA/no-signature,
    word count) lives here; everything business-specific is pulled from the profile
    (capability_areas, voice_notes, credibility, example_openers) so the engine
    serves any seller, not just Open Numerics."""
    credibility_note = _credibility_note()
    opener_examples = _opener_examples()
    voice_notes = _voice_notes_block()
    areas = (f" (e.g. {', '.join(profile.CAPABILITY_AREAS)})"
             if profile.CAPABILITY_AREAS else "")
    return f"""    * email_subject: accurate, non-spammy, and framed around the AREAS {profile.NAME}
      helps with{areas} — NOT a guess about the prospect's specific product or internal
      applications. Name {profile.NAME}'s capability areas, not the prospect's use cases.
    * email_body: ~90-130 words, never more than 160 — keep it short and skimmable. A cold INTRODUCTION and offer
      from an outside specialist — NOT an industry peer, and never "compare notes."
      Write the ENTIRE email as natural, flowing PROSE in SHORT paragraphs (2-3
      sentences each; keep it skimmable) — NO bullet points, numbered lists, or
      headings anywhere. Throughout, keep the focus on WHAT'S IN IT FOR THEM — frame
      everything around the outcomes and value they would get, not a feature tour of
      {profile.NAME}. The numbered points below are instructions to you, not a format
      for the email. In order:
        {_opening_step(opener_examples, voice_notes)}
        2. The "what's in it for them" paragraph — SPECIFIC ABOUT US, LIGHT ABOUT THEM.
           From {profile.NAME}'s capability areas / offerings listed above, pick the TWO
           that fit this prospect best, NAME them, and where natural name the concrete
           METHOD within each (e.g. "transient conjugate-heat-transfer CFD", "a surrogate
           model", "global sensitivity analysis") — be confident and concrete about what
           WE do. But stay LIGHT on THEIR side: connect those capabilities to their BROAD
           area of work, NOT to a specific internal product, project, or workflow you've
           guessed at. We do NOT know the details of their business and must not pretend
           to — so do NOT prescribe exactly where in their pipeline we'd plug in, or
           claim to know what they're working on. OFFER the capability and let THEM see
           where it fits, e.g. "we help teams working on [their broad area] with
           [capability + method]" rather than "for your [specific product] we'd do X to
           your Y". Keep it to a sentence or two. AVOID broad, fluffy benefit lists that
           could apply to any company ("faster turnaround, more confidence, cleaner
           paths"), do NOT cram in more than two capabilities, and do NOT hedge ("we'd
           most likely help", "we may be able to", "that could mean"). Keep every claim
           truthful — don't invent metrics, numbers, or internal details.
        3. Close with a clear, low-pressure ask for a short next step (e.g. a brief
           intro call), framed around the VALUE to them — e.g. "to see where we could
           help" or "to explore how {profile.NAME} could create value for your team".
           Make it concrete and to the point. Do NOT use vague, weak phrasings like
           "to see whether there's a fit" or "if it would be useful". Above all, do NOT
           open the ask with a conditional that presupposes it might not be worth their
           time — never start with "If it's useful,", "If that's helpful,", "If it
           would be valuable,", or similar. State the ask directly (e.g. "I'd love to
           set up a short intro call to explore where {profile.NAME} could create value
           for your team"). Keep it warm and pressure-free, but the ask should sound
           purposeful and assume the value is real.
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
