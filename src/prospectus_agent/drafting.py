"""Email-drafting orchestration: the follow-up generator. Prompt text lives in
prompts/ (prompts.followup).
"""
from __future__ import annotations

import sqlite3

from prospectus_agent import db
from prospectus_agent.llm import run_writer, submit_email_tool
from prospectus_agent.prompts import followup as followup_prompts
from prospectus_agent.schemas import FollowUpResult

SUBMIT_FOLLOWUP_TOOL = submit_email_tool(
    "submit_followup", "Submit the drafted follow-up email.")


def draft_followup(client, conn: sqlite3.Connection, company_row: sqlite3.Row,
                   on_profile: str, *, final: bool = False) -> FollowUpResult | None:
    """Draft a follow-up for a company that hasn't replied. `final=True` produces the
    short second/last follow-up. Returns a FollowUpResult or None. No web tools — it
    references the prior email."""
    prior = db.latest_email(conn, company_row["id"], "initial")
    prior_block = (
        f"Original email subject: {prior['subject']}\n\nOriginal email body:\n{prior['body']}"
        if prior
        else "(No prior initial email on record.)"
    )

    raw = run_writer(
        client,
        system=followup_prompts.system(),
        user_text=followup_prompts.build_user(company_row, prior_block, on_profile, final=final),
        tools=[SUBMIT_FOLLOWUP_TOOL],
        submit_tool_name="submit_followup",
    )
    if not raw:
        return None
    try:
        return FollowUpResult.model_validate(raw)
    except Exception:
        return None
