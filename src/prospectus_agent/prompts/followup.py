"""Prompts for follow-up email drafting."""
from __future__ import annotations

from prospectus_agent import agent_profile as profile
from prospectus_agent import config
from prospectus_agent.prompts import SIGNOFF_RULE


def system() -> str:
    return (
        f"You write brief, courteous B2B follow-up emails for {profile.NAME}. "
        "Follow-ups are short, add a little new value or a gentle nudge, and never "
        "guilt-trip. Never invent facts about the recipient's company. "
        "Write in a genuine human voice (contractions, plain everyday words), and never "
        "use em dashes or en dashes; use commas or periods instead."
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


def _recent_innovations() -> str:
    """Recent wins/innovations (profile.recent_innovations) the follow-up draws its
    momentum beat from. Pick ONE (the best fit), frame it as 'a few wins, including
    [that one]' — never a list, never overclaimed."""
    if not profile.RECENT_INNOVATIONS:
        return ""
    items = "\n".join(f"  - {n}" for n in profile.RECENT_INNOVATIONS)
    return (
        f"\nRecent progress at {profile.NAME} to draw the win beat from — pick the ONE "
        "that best fits this prospect and mention ONLY that one, framed as light "
        'momentum since the first email (e.g. "since I wrote, we\'ve had a few '
        'encouraging wins, including [that one]"). Do NOT list several, do NOT '
        "overclaim or invent metrics, and present only what's listed:\n"
        f"{items}\n")


def build_user(company_row, prior_block: str, on_profile: str, final: bool = False) -> str:
    """`company_row` is a sqlite3.Row (name/domain/last_contact_date). `final=True`
    produces the short, last touch-base follow-up."""
    if final:
        return _final_followup(company_row, prior_block, on_profile)
    # The bridge sentence must fit what the seller IS: a consultancy that does the work
    # FOR clients ("we'd love to do the same for you") vs. a self-serve product/platform
    # users run themselves ("we'd love for you to put it to work on your own molecules").
    # Follow the profile's voice notes; never imply bespoke client work for a product.
    if profile.RECENT_INNOVATIONS:
        momentum_step = (
            f"""3. Mention ONE encouraging recent win as light momentum, then ONE short,
     warm bridge sentence connecting it to them — e.g. "Since I wrote, we've had a few
     encouraging wins, including [one result from the recent-progress list below]."
     followed by an invite that FITS {profile.NAME}: for a service, "we'd love to do the
     same for you"; for a self-serve product/platform, "we'd love for you to try it on
     your own work" (do NOT say "do it for you" for a product). Pick just ONE win (do
     NOT list several), keep the bridge to a single short sentence — NOT a prescriptive
     paragraph diagnosing their problem or spelling out exactly where we'd plug in.""")
    else:
        momentum_step = (
            f"""3. Add ONE short, warm sentence on the value — light and high-level, phrased
     to FIT {profile.NAME}: a service, "we'd love to help you do the same"; a self-serve
     product, "we'd love for you to try it on your own work" (never "do it for you" for a
     product). NOT a prescriptive paragraph diagnosing their problem or where we'd plug in.""")
    return f"""About {profile.NAME}:
{on_profile}

We emailed {company_row['name']} ({company_row['domain']}) on
{company_row['last_contact_date']} and have had no reply after
{config.FOLLOWUP_DAYS} days.

{prior_block}

Write a SHORT, warm, low-pressure follow-up (about 80-120 words) — use clean, punchy
sentences, roughly one idea each — in this shape:
  1. Open by gently asking whether they had a chance to look at {profile.NAME} after the
     earlier note — name {profile.NAME} explicitly. e.g. "I was wondering whether you'd
     had a chance to look at {profile.NAME} after my earlier note." Do NOT use throwaway
     openers like "just bumping", "just circling back", or "just following up".
  2. ONE short sentence recapping, at a high level, what {profile.NAME} does.
  {momentum_step}
  4. Invite them to a short call, framed around SOLVING THEIR CHALLENGES — e.g. "I'd
     love to set up a quick call to dig into the challenges {company_row['name']} is
     facing and where {profile.NAME} can help." Keep it warm and low-pressure; you may
     add a friendly closer like "Let me know how we can be of service!". Do NOT add an
     apologetic opt-out line (e.g. "no worries if there's no time", "no need to reply if
     you're busy", "if the timing isn't right") — a confident, warm ask, not an apology.
Keep it concise: do NOT recite a full capabilities list, a multi-step "we advise then
we build" pitch, or a catalogue of tools — this is a light nudge, not a re-pitch.
{SIGNOFF_RULE}
{_recent_innovations()}{_voice_notes()}
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
  3. A final, warm, DIRECT offer of a short call — state it plainly ("I'd be glad to
     set up a short call" / "happy to grab 20 minutes"). Do NOT hedge it as a
     presupposing conditional ("if a call ever makes sense", "if it's useful", "if
     that's helpful", "whenever it's useful") and do NOT add an apologetic opt-out line
     ("no worries if there's no time", "no need to reply"). The low pressure comes from
     it being the last note, not from an apologetic ask.
Keep it genuinely short — NO capabilities list, no re-pitch. {SIGNOFF_RULE}
{_voice_notes()}
Then call `submit_followup`.
"""
