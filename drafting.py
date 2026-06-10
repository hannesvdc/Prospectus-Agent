"""Email-drafting orchestration: the follow-up generator. Prompt text lives in
prompts/ (prompts.followup).
"""
from __future__ import annotations

import config
import db
from llm import run_with_submit
from prompts import followup as followup_prompts
from schemas import FollowUpResult

SUBMIT_FOLLOWUP_TOOL = {
    "type": "function",
    "name": "submit_followup",
    "description": "Submit the drafted follow-up email.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "email_subject": {"type": "string"},
            "email_body": {"type": "string"},
        },
        "required": ["email_subject", "email_body"],
        "additionalProperties": False,
    },
}


def draft_followup(client, conn, company_row, on_profile: str):
    """Draft a short follow-up for a company that hasn't replied. Returns a
    FollowUpResult or None. No web tools needed — references the prior email."""
    prior = db.latest_email(conn, company_row["id"], "initial")
    prior_block = (
        f"Original email subject: {prior['subject']}\n\nOriginal email body:\n{prior['body']}"
        if prior
        else "(No prior initial email on record.)"
    )

    raw = run_with_submit(
        client,
        model=config.MODEL,
        system=followup_prompts.SYSTEM,
        user_text=followup_prompts.build_user(company_row, prior_block, on_profile),
        tools=[SUBMIT_FOLLOWUP_TOOL],
        submit_tool_name="submit_followup",
        max_output_tokens=4000,
    )
    if not raw:
        return None
    try:
        return FollowUpResult.model_validate(raw)
    except Exception:
        return None
