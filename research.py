"""Per-winner grounding + initial-email drafting.

For each qualified company we make ONE call that uses the hosted web_search tool
(which can open/read pages) to research the company's own site and leadership,
then returns (via a strict tool): refined applications, public emails, named
senior people, and a tailored initial email. We then store contacts (public +
pattern-guessed) and the email draft, and mark the company 'drafted'.
"""
from __future__ import annotations

import config
import contacts as contacts_mod
import db
from llm import WEB_SEARCH_TOOL, run_with_submit
from prompts import research as research_prompts
from schemas import Candidate, OutreachResult

SUBMIT_OUTREACH_TOOL = {
    "type": "function",
    "name": "submit_company_outreach",
    "description": "Submit researched contacts and the drafted initial email.",
    "strict": True,
    "parameters": {
        "type": "object",
        "properties": {
            "refined_applications": {
                "type": "array",
                "items": {"type": "string"},
                "description": "2-4 concrete ON applications grounded in the company's real work",
            },
            "public_emails": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Generic public inboxes found on the site (info@, contact@, sales@)",
            },
            "people": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "public_email": {
                            "type": ["string", "null"],
                            "description": "Only if published publicly; otherwise null",
                        },
                    },
                    "required": ["name", "title", "public_email"],
                    "additionalProperties": False,
                },
                "description": "Senior / relevant people (leadership, R&D, engineering heads)",
            },
            "email_subject": {"type": "string"},
            "email_body": {"type": "string"},
            "draft_notes": {
                "type": "string",
                "description": "Brief notes for the sender (uncertainties, who to address, etc.)",
            },
        },
        "required": [
            "refined_applications",
            "public_emails",
            "people",
            "email_subject",
            "email_body",
            "draft_notes",
        ],
        "additionalProperties": False,
    },
}

def research_and_draft(client, conn, company_id: int, cand: Candidate, on_profile: str) -> dict:
    """Research one winner, store contacts + draft, mark 'drafted'.
    Returns a summary dict for the run digest."""
    raw = run_with_submit(
        client,
        model=config.MODEL,
        system=research_prompts.system(),
        user_text=research_prompts.build_user(cand, on_profile),
        tools=[WEB_SEARCH_TOOL, SUBMIT_OUTREACH_TOOL],
        submit_tool_name="submit_company_outreach",
        max_output_tokens=config.DRAFT_MAX_TOKENS,
        effort=config.DRAFTING_EFFORT,
    )

    summary = {"name": cand.name, "domain": cand.domain, "contacts": 0, "drafted": False}
    if not raw:
        print(f"    ! no outreach result for {cand.name}")
        return summary

    try:
        result = OutreachResult.model_validate(raw)
    except Exception as e:
        print(f"    ! could not validate outreach for {cand.name}: {e}")
        return summary

    n_contacts = 0
    # One (or few) generic public inbox(es).
    for email in result.public_emails[:config.MAX_PUBLIC_EMAILS]:
        email = email.strip()
        if email:
            db.add_contact(conn, company_id, name="", role="generic inbox",
                           email=email, email_confidence="public")
            n_contacts += 1

    # Up to MAX_PEOPLE senior people: published address if found, else a capped
    # number of pattern guesses each.
    for person in result.people[:config.MAX_PEOPLE]:
        if person.public_email:
            db.add_contact(conn, company_id, name=person.name, role=person.title,
                           email=person.public_email.strip(), email_confidence="public")
            n_contacts += 1
        else:
            for guess in contacts_mod.guess_emails(person.name, cand.domain)[:config.GUESSES_PER_PERSON]:
                db.add_contact(conn, company_id, name=person.name, role=person.title,
                               email=guess, email_confidence="guessed")
                n_contacts += 1

    db.add_email(conn, company_id, type="initial",
                 subject=result.email_subject, body=result.email_body)
    db.set_status(conn, cand.domain, "drafted")

    summary.update(
        contacts=n_contacts,
        drafted=True,
        subject=result.email_subject,
        applications=result.refined_applications,
        draft_notes=result.draft_notes,
    )
    return summary
