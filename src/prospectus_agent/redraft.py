"""Refine already-drafted emails using the CURRENT prompt, no new web research.

For each existing draft we make ONE cheap call (no web_search) that rewrites the
subject + body to match the latest email rules, preserving the factual content
already in the draft. Contacts and company records are left untouched. The email
row is updated in place.

This is what you run after tuning the email voice (prompts/research.email_rules,
profile.yaml openers/credibility, etc.) to bring today's existing drafts in line
without re-discovering or re-researching anything.
"""
from __future__ import annotations

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent.llm import run_with_submit
from prospectus_agent.prompts import redraft as redraft_prompts

SUBMIT_REFINED_TOOL = {
    "type": "function",
    "name": "submit_refined_email",
    "description": "Submit the refined subject and body for an existing draft.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "email_subject": {"type": "string"},
            "email_body": {"type": "string"},
            "draft_notes": {
                "type": "string",
                "description": "Brief notes for the sender (or empty string).",
            },
        },
        "required": ["email_subject", "email_body", "draft_notes"],
        "additionalProperties": False,
    },
}


def refine_email(client, conn, email_row, on_profile: str) -> dict:
    """Rewrite one existing draft in place. Returns a summary dict."""
    company = db.get_company(conn, email_row["company_id"])
    summary = {
        "name": company["name"] if company else "?",
        "domain": company["domain"] if company else "?",
        "refined": False,
    }
    if company is None:
        return summary

    raw = run_with_submit(
        client,
        model=config.MODEL,
        system=redraft_prompts.system(),
        user_text=redraft_prompts.build_user(
            company, on_profile, email_row["subject"], email_row["body"]
        ),
        tools=[SUBMIT_REFINED_TOOL],  # no web_search — pure restyle
        submit_tool_name="submit_refined_email",
        max_output_tokens=config.DRAFT_MAX_TOKENS,
        effort=config.DRAFTING_EFFORT,
    )
    if not raw:
        print(f"    ! no refined result for {summary['name']}")
        return summary

    subject = (raw.get("email_subject") or "").strip()
    body = (raw.get("email_body") or "").strip()
    if not subject or not body:
        print(f"    ! refined result missing subject/body for {summary['name']}")
        return summary

    db.update_email(conn, email_row["id"], subject=subject, body=body)
    summary.update(refined=True, subject=subject)
    return summary


def refine_today(client, conn, on_profile: str, *, today: str | None = None,
                 type: str = "initial") -> list[dict]:
    """Refine every draft of `type` created today (default initial emails)."""
    from datetime import date

    today = today or date.today().isoformat()
    emails = [e for e in db.emails_on(conn, today) if e["type"] == type]
    summaries = []
    for em in emails:
        company = db.get_company(conn, em["company_id"])
        if company:
            print(f"  ● {company['name']} ({company['domain']})")
        summaries.append(refine_email(client, conn, em, on_profile))
    return summaries
