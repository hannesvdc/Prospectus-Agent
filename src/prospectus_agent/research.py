"""Per-winner grounding + initial-email drafting, in two model calls.

1. RESEARCH (cheap searcher, config.MODEL, hosted web_search): reads the company's
   site + leadership and returns grounded facts — refined applications, public
   inboxes, named senior people, draft notes. No email is written here.
2. DRAFT (writer, config.WRITER_MODEL, no web search): writes the tailored initial
   email from those facts.

We then store contacts (public + pattern-guessed) and the email draft, and mark
the company 'drafted'.
"""
from __future__ import annotations

from prospectus_agent import agent_profile as profile
from prospectus_agent import config
from prospectus_agent import contacts as contacts_mod
from prospectus_agent import db
from prospectus_agent.llm import WEB_SEARCH_TOOL, function_tool, run_with_submit
from prospectus_agent.prompts import research as research_prompts
from prospectus_agent.schemas import Candidate, EmailDraft, ResearchResult

SUBMIT_RESEARCH_TOOL = function_tool(
    "submit_research",
    "Submit the researched, grounded facts about the company (no email).",
    {
        "refined_applications": {
            "type": "array",
            "items": {"type": "string"},
            "description": f"2-4 concrete ways {profile.NAME} could help, grounded in the company's real work",
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
        "draft_notes": {
            "type": "string",
            "description": "Brief notes for the sender (uncertainties, who to address, etc.)",
        },
    },
    ["refined_applications", "public_emails", "people", "draft_notes"],
)

SUBMIT_EMAIL_TOOL = function_tool(
    "submit_email",
    "Submit the drafted initial email.",
    {"email_subject": {"type": "string"}, "email_body": {"type": "string"}},
    ["email_subject", "email_body"],
)


def research_and_draft(client, conn, company_id: int, cand: Candidate, on_profile: str) -> dict:
    """Research one winner, draft the email, store contacts + draft, mark 'drafted'.
    Returns a summary dict for the run digest."""
    summary = {"name": cand.name, "domain": cand.domain, "contacts": 0, "drafted": False}

    # --- 1. Research (cheap searcher + web_search) -> grounded facts -----------
    raw = run_with_submit(
        client,
        vendor=config.SEARCH_VENDOR,
        model=config.SEARCH_MODEL,
        system=research_prompts.research_system(),
        user_text=research_prompts.build_research_user(cand, on_profile),
        tools=[WEB_SEARCH_TOOL, SUBMIT_RESEARCH_TOOL],
        submit_tool_name="submit_research",
        max_output_tokens=config.DRAFT_MAX_TOKENS,
        effort=config.DISCOVERY_EFFORT,
    )
    if not raw:
        print(f"    ! no research result for {cand.name}")
        return summary
    try:
        facts = ResearchResult.model_validate(raw)
    except Exception as e:
        print(f"    ! could not validate research for {cand.name}: {e}")
        return summary

    # --- 2. Draft (writer, no web search) -> email ----------------------------
    raw_email = run_with_submit(
        client,
        vendor=config.WRITER_VENDOR,
        model=config.WRITER_MODEL,
        system=research_prompts.draft_system(),
        user_text=research_prompts.build_user(cand, on_profile, facts),
        tools=[SUBMIT_EMAIL_TOOL],
        submit_tool_name="submit_email",
        max_output_tokens=config.DRAFT_MAX_TOKENS,
        effort=config.DRAFTING_EFFORT,
    )
    if not raw_email:
        print(f"    ! no email draft for {cand.name}")
        return summary
    try:
        email = EmailDraft.model_validate(raw_email)
    except Exception as e:
        print(f"    ! could not validate email for {cand.name}: {e}")
        return summary

    # --- 3. Store contacts + draft --------------------------------------------
    n_contacts = 0
    # One (or few) generic public inbox(es).
    for inbox in facts.public_emails[:config.MAX_PUBLIC_EMAILS]:
        inbox = inbox.strip()
        if inbox:
            db.add_contact(conn, company_id, name="", role="generic inbox",
                           email=inbox, email_confidence="public")
            n_contacts += 1

    # Up to MAX_PEOPLE senior people: published address if found, else a capped
    # number of pattern guesses each.
    for person in facts.people[:config.MAX_PEOPLE]:
        published = person.public_email.strip() if person.public_email else ""
        # Reject "addresses" built from a credential/title (e.g. jeremy.phd@) —
        # treat as not-really-published and fall back to clean pattern guessing.
        if published and contacts_mod.is_credentialed_local_part(published):
            published = ""
        if published:
            db.add_contact(conn, company_id, name=person.name, role=person.title,
                           email=published, email_confidence="public")
            n_contacts += 1
        else:
            for guess in contacts_mod.guess_emails(person.name, cand.domain)[:config.GUESSES_PER_PERSON]:
                db.add_contact(conn, company_id, name=person.name, role=person.title,
                               email=guess, email_confidence="guessed")
                n_contacts += 1

    db.add_email(conn, company_id, type="initial",
                 subject=email.email_subject, body=email.email_body)
    db.set_status(conn, cand.domain, "drafted")

    summary.update(
        contacts=n_contacts,
        drafted=True,
        subject=email.email_subject,
        applications=facts.refined_applications,
        draft_notes=facts.draft_notes,
    )
    return summary
