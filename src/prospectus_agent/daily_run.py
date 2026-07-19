"""Daily pipeline for the prospecting agent (invoked by `prospectus-agent`).

Pipeline:
  1. Refresh the seller's own profile from its website (cached per day).
  2. Discover up to TARGET_COMPANY_COUNT new qualifying companies (<=
     MAX_DISCOVERY_CALLS web-search rounds).
  3. Research each winner and draft a tailored initial email; store contacts.
  4. Sweep for stale outreach and draft follow-ups.
  5. Print a digest.

You then review drafts and send them yourself, and track replies with
`prospectus-status`.
"""
from __future__ import annotations

import sys
from datetime import date

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import discovery
from prospectus_agent import followups
from prospectus_agent import on_profile
from prospectus_agent import outbox
from prospectus_agent import research
from prospectus_agent import runner


def _print_digest(winners_summaries: list[dict], followup_summaries: list[dict]) -> None:
    print("\n" + "=" * 78)
    print(f"DAILY DIGEST — {date.today().isoformat()}")
    print("=" * 78)

    print(f"\nNEW PROSPECTS DRAFTED ({sum(1 for s in winners_summaries if s['drafted'])}):")
    if not winners_summaries:
        print("  (none found today)")
    for s in winners_summaries:
        if not s["drafted"]:
            print(f"  ✗ {s['name']} ({s['domain']}) — research/draft failed")
            continue
        print(f"\n  ● {s['name']} ({s['domain']})")
        if s.get("warning"):
            print(f"      ⚠ {s['warning']}")
        print(f"      contacts stored: {s['contacts']}")
        print(f"      subject: {s.get('subject', '')}")
        apps = s.get("applications") or []
        if apps:
            print("      applications:")
            for a in apps:
                print(f"        - {a}")
        if s.get("draft_notes"):
            print(f"      notes: {s['draft_notes']}")

    print(f"\nFOLLOW-UPS ({len(followup_summaries)} flagged):")
    if not followup_summaries:
        print("  (none due)")
    for f in followup_summaries:
        status = "drafted" if f["drafted"] else f.get("note", "—")
        print(f"  ● {f['name']} ({f['domain']}) — {f['days']} days, {status}")

    print("\nNext steps:")
    print("  • Review drafts:   prospectus-status drafts   →   prospectus-status show DOMAIN")
    print("  • After sending:   prospectus-status mark DOMAIN sent")
    print("  • On reply:        prospectus-status mark DOMAIN replied   (or not_interested)")
    print("=" * 78)


def main() -> int:
    banner = f"{agent_profile.NAME} prospecting agent — {date.today().isoformat()}\n"
    try:
        with runner.session(banner) as (client, conn):
            emails_before = db.max_email_id(conn)  # so the outbox emits only THIS run's drafts

            print(f"Refreshing {agent_profile.NAME} profile...")
            profile = on_profile.refresh_profile(client)

            # Each phase below is best-effort: a failure in one (a flaky API call, a
            # single bad company) must not abort the run or, crucially, skip the
            # follow-up sweep and the digest write. We keep whatever succeeds.
            winners = []
            try:
                print("\nDiscovering prospects...")
                winners = discovery.discover(client, conn, profile)
                print(f"\nQualified winners: {len(winners)} (target {config.TARGET_COMPANY_COUNT})")
            except Exception as e:
                print(f"  ⚠ discovery step failed, continuing without new prospects: {e}")

            print("\nResearching winners and drafting emails...")
            winner_summaries = []
            for company_id, cand in winners:
                print(f"  ● {cand.name} ({cand.domain})")
                try:
                    winner_summaries.append(
                        research.research_and_draft(client, conn, company_id, cand, profile))
                except Exception as e:
                    # Drop just this company; the rest of the batch and follow-ups go on.
                    print(f"    ⚠ skipped {cand.name} ({cand.domain}): {e}")

            # Runs even if discovery/drafting partly failed — this is where follow-ups
            # were getting stranded when an earlier step crashed the whole run.
            followup_summaries = []
            try:
                print("\nChecking for follow-ups...")
                followup_summaries = followups.run_followups(client, conn, profile)
            except Exception as e:
                print(f"  ⚠ follow-up sweep failed: {e}")

            _print_digest(winner_summaries, followup_summaries)

            # Write the digest for whatever's ready, even if a step above failed, so drafts
            # never strand in the DB. New-prospect initials come from THIS run; the
            # follow-up file is the COMPLETE currently-due set (same as `--followup`), so
            # it's always written, even when a due follow-up was drafted on an earlier day
            # (outbox.generate alone only writes TODAY's newly-created emails).
            out_dir = None
            try:
                new_written = outbox.generate(conn, since_email_id=emails_before)
                if new_written:
                    out_dir = new_written[0]
            except Exception as e:
                print(f"  ⚠ could not write new-prospect drafts: {e}")
            try:
                fu_written = outbox.write_file(
                    conn, followups.due_followup_emails(conn),
                    basename="followups", title="Follow-up drafts")
                if fu_written:
                    out_dir = fu_written[0]
            except Exception as e:
                print(f"  ⚠ could not write follow-up drafts: {e}")
            if out_dir:
                print(f"\n✉  Wrote drafts to {out_dir}/ (new_prospects.md / followups.md "
                      "+ .html) — recipients + subject + body, ready to copy-paste.")
    except Exception as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
