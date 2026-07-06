"""Per-winner grounding + initial-email drafting, in two model calls.

1. RESEARCH (cheap searcher, config.SEARCH_MODEL, hosted web_search): reads the company's
   site + leadership and returns grounded facts — refined applications, public
   inboxes, named senior people, draft notes. No email is written here.
2. DRAFT (writer, config.WRITER_MODEL, no web search): writes the tailored initial
   email from those facts.

We then store contacts and the email draft, and mark the company 'drafted'. Contacts
are one best address per person — published if found, else pattern-INFERRED from a
real address on the domain, else a single top-format guess — gated by an MX
deliverability check, with the generic inbox kept only as a fallback.
"""
from __future__ import annotations

from prospectus_agent import agent_profile as profile
from prospectus_agent import config
from prospectus_agent import contacts as contacts_mod
from prospectus_agent import db
from prospectus_agent import verify
from prospectus_agent.llm import (
    WEB_SEARCH_TOOL, function_tool, run_searcher, run_writer, submit_email_tool,
)
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

SUBMIT_EMAIL_TOOL = submit_email_tool("submit_email", "Submit the drafted initial email.")


def research_and_draft(client, conn, company_id: int, cand: Candidate, on_profile: str) -> dict:
    """Research one winner, draft the email, store contacts + draft, mark 'drafted'.
    Returns a summary dict for the run digest."""
    summary = {"name": cand.name, "domain": cand.domain, "contacts": 0, "drafted": False}

    # --- 1. Research (cheap searcher + web_search) -> grounded facts -----------
    raw = run_searcher(
        client,
        system=research_prompts.research_system(),
        user_text=research_prompts.build_research_user(cand, on_profile),
        tools=[WEB_SEARCH_TOOL, SUBMIT_RESEARCH_TOOL],
        submit_tool_name="submit_research",
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
    raw_email = run_writer(
        client,
        system=research_prompts.draft_system(),
        user_text=research_prompts.build_user(cand, on_profile, facts),
        tools=[SUBMIT_EMAIL_TOOL],
        submit_tool_name="submit_email",
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
    # Free deliverability gate: a domain with no MX/A record can't receive mail,
    # so don't manufacture sure-to-bounce addresses for it (fails open if the
    # lookup can't run, so we never silently drop real prospects).
    deliverable = verify.domain_deliverable(cand.domain)

    people = list(facts.people[:config.MAX_PEOPLE])

    def _clean_published(person) -> str:
        pub = person.public_email.strip() if person.public_email else ""
        # Keep only a genuinely usable published address — drops credential-built
        # locals (jeremy.phd@) and obfuscation placeholders ([email protected]).
        return pub if contacts_mod.is_real_email(pub) else ""

    # Learn this domain's email format from the REAL personal addresses research
    # actually found, so we can build the ONE correct address for the others
    # instead of blasting several guesses per person.
    known = [(p.name, _clean_published(p)) for p in people if _clean_published(p)]
    pattern = contacts_mod.infer_pattern(known, cand.domain) if known else None

    # Real mailbox verification — opt-in per profile (settings.verify_emails) and
    # only when Verifalia credentials are configured; otherwise a no-op.
    verify_on = profile.VERIFY_EMAILS and verify.verification_available()

    domain_catch_all = False  # once a domain proves catch-all, stop spending credits

    def _pick_addresses(person) -> list[tuple[str, str]]:
        """(email, confidence) to store for one person — never a multi-guess blast.
        With verification on: try candidate formats in order, keep the FIRST
        deliverable one ('verified'), drop invalids, keep a risky/unknown as a
        low-confidence 'guessed' fallback. Off (or once the domain is known
        catch-all): the pattern-inferred address, or the top guess(es)."""
        nonlocal domain_catch_all
        name = person.name
        if pattern:
            primary = contacts_mod.apply_pattern(name, cand.domain, pattern)
            rest = [g for g in contacts_mod.guess_emails(name, cand.domain) if g != primary]
            candidates = [primary, *rest] if primary else rest
        else:
            candidates = contacts_mod.guess_emails(name, cand.domain)
        candidates = [c for c in candidates if c]
        if not candidates:
            return []
        # No verification, or the domain already proved catch-all (every address
        # "accepts", so verifying more just burns credits): use pattern/guess.
        if not verify_on or domain_catch_all:
            if pattern:
                return [(candidates[0], "inferred")]
            return [(g, "guessed") for g in candidates[:config.GUESSES_PER_PERSON]]
        fallback: tuple[str, str] | None = None
        for addr in candidates[:config.VERIFY_MAX_CANDIDATES]:
            verdict = verify.verify_email(addr)
            if verdict == "valid":
                return [(addr, "verified")]
            if verdict == "risky":
                # Catch-all / accept-all domain: no format can be confirmed, so
                # stop here (and skip verification for the rest of this company).
                domain_catch_all = True
                return [(addr, "guessed")]
            if verdict == "unknown" and fallback is None:
                fallback = (addr, "guessed")  # transient/inconclusive — keep as backup
            # 'invalid' -> try the next candidate format
        # Verification confirmed nothing (all tried formats came back invalid/unknown).
        # Fall back to the best guess rather than dropping the person — a guessed
        # address is a lead to chase; "(no contacts found)" is a dead end.
        return [fallback] if fallback else [(candidates[0], "guessed")]

    n_contacts = 0
    has_reliable_personal = False  # a confirmed/published/inferred address exists

    # One best address per named person: published > verified > pattern-inferred.
    for person in people:
        published = _clean_published(person)
        if published:
            db.add_contact(conn, company_id, name=person.name, role=person.title,
                           email=published, email_confidence="public")
            n_contacts += 1
            has_reliable_personal = True
            continue
        if not deliverable:
            continue  # domain can't receive mail — inventing guesses just bounces
        for addr, conf in _pick_addresses(person):
            db.add_contact(conn, company_id, name=person.name, role=person.title,
                           email=addr, email_confidence=conf)
            n_contacts += 1
            if conf in ("verified", "inferred"):
                has_reliable_personal = True

    # Generic inbox (info@/contact@) only as a FALLBACK — kept when we have no
    # reliable personal target (published or pattern-inferred) to aim at, since
    # those inboxes are usually screened or ignored.
    if deliverable and not has_reliable_personal:
        for inbox in facts.public_emails[:config.MAX_PUBLIC_EMAILS]:
            inbox = inbox.strip()
            if contacts_mod.is_real_email(inbox):  # skip [email protected] placeholders
                db.add_contact(conn, company_id, name="", role="generic inbox",
                               email=inbox, email_confidence="public")
                n_contacts += 1

    # Last resort: a deliverable company must never come out with ZERO contacts (e.g.
    # no people found and no inbox published) — a guessed generic inbox beats
    # "(no contacts found)".
    if deliverable and n_contacts == 0:
        db.add_contact(conn, company_id, name="", role="generic inbox",
                       email=f"info@{cand.domain}", email_confidence="guessed")
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
