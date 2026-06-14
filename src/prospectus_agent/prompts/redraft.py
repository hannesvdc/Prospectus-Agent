"""Prompt for refining an already-drafted outreach email.

Re-applies the CURRENT email-writing rules (shared with the initial-draft prompt,
see prompts/research.email_rules) to an existing draft — no new web research. The
factual content is preserved from the existing draft; only wording, structure, and
style are brought in line with the latest guidance.
"""
from __future__ import annotations

from prospectus_agent import agent_profile as profile
from prospectus_agent.prompts.research import email_rules


def system() -> str:
    return (
        f"You revise an existing cold outreach email for {profile.NAME} so it matches "
        "the latest style guidance. Keep the factual, company-specific content already "
        "in the draft — do NOT invent new facts, people, numbers, or claims about the "
        "prospect, and do NOT add web research. Improve only wording, structure, tone, "
        "and adherence to the rules. Return the revised email via `submit_refined_email`."
    )


def build_user(company, on_profile: str, subject: str, body: str) -> str:
    """`company` is a duck-typed row with name/domain/industry/why_fit."""
    return f"""About {profile.NAME}:
{on_profile}

Prospect company: {company['name']}
Website: {company['domain']}
Industry: {company['industry']}
Why we think they fit: {company['why_fit']}

CURRENT DRAFT — subject:
{subject}

CURRENT DRAFT — body:
{body}

TASK: Rewrite this email so it fully follows the rules below, while preserving the
factual, prospect-specific substance already present (the concrete value points,
the company's domain, any genuine specifics). Don't research anything new and don't
fabricate. If the current draft already complies, still return the best version of
it. Return via `submit_refined_email` with these fields:
{email_rules()}
- draft_notes: anything the sender should know before sending (or "").
"""
