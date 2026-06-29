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

from datetime import date

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import drafting
from prospectus_agent import followups
from prospectus_agent.llm import function_tool, run_with_submit
from prospectus_agent.prompts import redraft as redraft_prompts

SUBMIT_REFINED_TOOL = function_tool(
    "submit_refined_email",
    "Submit the refined subject and body for an existing draft.",
    {
        "email_subject": {"type": "string"},
        "email_body": {"type": "string"},
        "draft_notes": {"type": "string",
                        "description": "Brief notes for the sender (or empty string)."},
    },
    ["email_subject", "email_body", "draft_notes"],
)


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
        vendor=config.WRITER_VENDOR,
        model=config.WRITER_MODEL,
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
                 email_type: str = "initial") -> list[dict]:
    """Refine every draft of `email_type` created today (default initial emails)."""
    today = today or date.today().isoformat()
    emails = [e for e in db.emails_on(conn, today) if e["type"] == email_type]
    summaries = []
    for em in emails:
        company = db.get_company(conn, em["company_id"])
        if company:
            print(f"  ● {company['name']} ({company['domain']})")
        summaries.append(refine_email(client, conn, em, on_profile))
    return summaries


def refine_followups(client, conn, on_profile: str) -> list[dict]:
    """Re-draft every currently-due follow-up IN PLACE with the current follow-up
    prompt/voice (uses the follow-up prompt, not the initial-email rules). Returns a
    summary list."""
    summaries = []
    for row in db.companies_awaiting_followup(conn):
        if not followups.is_due(row):
            continue
        existing = db.latest_email(conn, row["id"], "followup")
        if not existing:
            continue
        summary = {"name": row["name"], "domain": row["domain"], "refined": False}
        result = drafting.draft_followup(client, conn, row, on_profile,
                                         final=followups.is_final(row))
        if result:
            db.update_email(conn, existing["id"],
                            subject=result.email_subject, body=result.email_body)
            summary.update(refined=True, subject=result.email_subject)
        else:
            print(f"    ! no refined follow-up for {row['name']}")
        summaries.append(summary)
    return summaries
