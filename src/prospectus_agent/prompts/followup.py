"""Prompts for follow-up email drafting."""
from __future__ import annotations

from prospectus_agent import agent_profile as profile
from prospectus_agent import config


def system() -> str:
    return (
        f"You write brief, courteous B2B follow-up emails for {profile.NAME}. "
        "Follow-ups are short, add a little new value or a gentle nudge, and never "
        "guilt-trip. Never invent facts about the recipient's company."
    )


def _voice_notes() -> str:
    """The seller's voice dos/don'ts (profile.voice_notes) — use for TONE/voice only
    in a follow-up (personal first-person voice, vocabulary, words to avoid). The
    structure above governs WHAT to say; keep it short."""
    if not profile.VOICE_NOTES:
        return ""
    notes = "\n".join(f"- {n}" for n in profile.VOICE_NOTES)
    return (f"\nVoice/tone notes for {profile.NAME} — apply these for VOICE only (do "
            f"NOT let them expand the follow-up into a full pitch):\n{notes}\n")


def build_user(company_row, prior_block: str, on_profile: str, final: bool = False) -> str:
    """`company_row` is a sqlite3.Row (name/domain/last_contact_date). `final=True`
    produces the short, last touch-base follow-up."""
    if final:
        return _final_followup(company_row, prior_block, on_profile)
    return f"""About {profile.NAME}:
{on_profile}

We emailed {company_row['name']} ({company_row['domain']}) on
{company_row['last_contact_date']} and have had no reply after
{config.FOLLOWUP_BUSINESS_DAYS} business days.

{prior_block}

Write a SHORT, warm, low-pressure follow-up (about 80-120 words) in this shape:
  1. Open by gently asking whether they had a chance to look at {profile.NAME} — name
     {profile.NAME} explicitly and refer to the earlier note. e.g. "I was wondering
     whether you'd had a chance to look at {profile.NAME}." Do NOT use throwaway
     openers like "just bumping", "just circling back", or "just following up".
  2. ONE short sentence recapping, at a high level, what {profile.NAME} does.
  3. A short paragraph in the first person ("we") on how we could help with the
     problem from the original note — concrete and value-oriented. Address them by
     their COMPANY NAME ({company_row['name']}) — e.g. "For {company_row['name']}, we
     can…" — NOT by an impersonal description of their field (avoid "For
     biologically-aware generative AI,").
  4. Make it easy to decline (e.g. "if this isn't a priority right now, no need to reply").
Keep it concise: do NOT recite a full capabilities list, a multi-step "we advise then
we build" pitch, or a catalogue of tools — this is a light nudge, not a re-pitch.
You may end with "Best,", but do NOT add a signature, sender name, or contact details
— the sender's email client appends their own signature.
{_voice_notes()}
Then call `submit_followup`.
"""


def _final_followup(company_row, prior_block: str, on_profile: str) -> str:
    """The second and LAST follow-up: very short — touch base, a link to the website,
    a final low-key offer of a quick chat, and a clear sign-off that this is the last
    time we'll reach out."""
    return f"""About {profile.NAME}:
{on_profile}

We've emailed {company_row['name']} ({company_row['domain']}) twice (initial + one
follow-up) with no reply. This is the SECOND and FINAL follow-up.

{prior_block}

Write a VERY SHORT, warm, no-pressure final note (about 40-70 words):
  1. Briefly touch base with {company_row['name']} — make clear this is a last check-in
     and that we won't keep emailing.
  2. One line on what {profile.NAME} does, with a link to learn more: {profile.WEBSITE}
     (include the URL in the body so it's clickable).
  3. A final, low-key offer of a short chat whenever it's useful — and an easy out
     ("no need to reply if the timing isn't right").
Keep it genuinely short — NO capabilities list, no re-pitch. You may end with "Best,",
but do NOT add a signature, sender name, or contact details.
{_voice_notes()}
Then call `submit_followup`.
"""
