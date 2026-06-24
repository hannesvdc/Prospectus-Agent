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
    'problem' leads with a challenge common to teams like the prospect's, then
    introduces the seller; anything else opens with a plain seller introduction."""
    if profile.OPENING_STYLE == "problem":
        return (
            f"""1. LEAD WITH THE PROBLEM, not with {profile.NAME}. Open by naming a
           challenge that is TYPICAL of teams doing THIS prospect's kind of work —
           framed as a recognizable pattern, NOT a claim about their specific internal
           situation. Anchor it in their domain / products / workflows from your
           research, and phrase it as something the reader will nod along to, e.g.
           "For teams [doing X], [a typical challenge — long simulation campaigns,
           slow design-iteration loops, uncertainty that's hard to quantify, results
           that are hard to trust] often [becomes the bottleneck / slows every cycle]."
           Keep it to a sentence or two. Stay at the level of "teams like yours often…"
           — do NOT assert you know their internal stack, tools, or that they
           specifically have this problem ("your pipeline is too slow"). Then, in ONE
           short sentence, pivot to introduce {profile.NAME} as the team that helps
           remove exactly that kind of bottleneck — a LIGHT, high-level intro of what
           {profile.NAME} does and who it helps (draw on the brief and offerings above;
           use the example opener(s) below for tone, but ADAPT them to land AFTER the
           problem hook rather than as the first line).{opener_examples}{voice_notes}""")
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
    * email_body: ~120-160 words, never more than 200. A cold INTRODUCTION and offer
      from an outside specialist — NOT an industry peer, and never "compare notes."
      Write the ENTIRE email as natural, flowing PROSE in SHORT paragraphs (2-3
      sentences each; keep it skimmable) — NO bullet points, numbered lists, or
      headings anywhere. Throughout, keep the focus on WHAT'S IN IT FOR THEM — frame
      everything around the outcomes and value they would get, not a feature tour of
      {profile.NAME}. The numbered points below are instructions to you, not a format
      for the email. In order:
        {_opening_step(opener_examples, voice_notes)}
        2. The "what's in it for them" paragraph — make it SPECIFIC, not generic.
           From {profile.NAME}'s capability areas / offerings listed above, pick the
           TWO that map most closely to THIS prospect's actual work, NAME those two
           explicitly, and tie each to a concrete outcome. Anchor on the prospect's
           SPECIFIC products, projects, or workflows from your research (not just their
           industry), and where natural name the concrete METHOD within the capability
           (a particular kind of simulation, model, solver, or analysis — e.g.
           "transient conjugate-heat-transfer CFD", "a surrogate model of …",
           "global sensitivity analysis"), not just the capability label. Write it
           in the first person ("we") and address them by COMPANY NAME — e.g. "For
           [their company], we can use [specific method from capability one] to
           [specific outcome on their actual product/workflow], and [capability two]
           to [specific outcome]." The reader should see exactly which two of our
           capabilities fit them and why. Keep every claim truthful — don't invent
           metrics, numbers, or internal details you can't ground in the research. AVOID broad, fluffy benefit lists that could apply to any company
           ("faster turnaround, more confidence, cleaner paths") and do NOT cram in
           more than two capabilities. Be CONFIDENT and direct ("we help teams like
           yours do X", "we can use Y to Z") — do NOT hedge with phrasings like "we'd
           most likely help", "we may be able to", or "that could mean". Ground it in
           what they publicly do, but don't claim to know their internal stack — keep
           any challenge framed as a pattern common to teams like them, never asserted
           as a specific internal problem you've diagnosed.
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
