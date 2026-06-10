"""Daily entrypoint for the Open Numerics prospecting agent.

    python daily_run.py

Pipeline:
  1. Refresh ON's own profile from opennumerics.com (cached per day).
  2. Discover up to TARGET_COMPANY_COUNT new qualifying companies (<=
     MAX_DISCOVERY_CALLS web-search rounds).
  3. Research each winner and draft a tailored initial email; store contacts.
  4. Sweep for stale outreach and draft follow-ups.
  5. Print a digest.

You then review drafts and send them yourself, and track replies with status.py.
"""
from __future__ import annotations

import sys
from datetime import date

import config
import db
import discovery
import followups
import on_profile
import outbox
import research


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
        print(f"  ● {f['name']} ({f['domain']}) — {f['business_days']} business days, {status}")

    print("\nNext steps:")
    print("  • Review drafts:   python status.py drafts   →   python status.py show DOMAIN")
    print("  • After sending:   python status.py mark DOMAIN sent")
    print("  • On reply:        python status.py mark DOMAIN replied   (or not_interested)")
    print("=" * 78)


def main() -> int:
    print(f"Open Numerics prospecting agent — {date.today().isoformat()}\n")

    try:
        config.require_api_key()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    client = config.get_client()
    conn = db.connect( config.DB_PATH )
    db.init_db( conn )

    print("Refreshing Open Numerics profile...")
    profile = on_profile.refresh_profile( client )

    print("\nDiscovering prospects...")
    winners = discovery.discover( client, conn, profile )
    print(f"\nQualified winners: {len(winners)} (target {config.TARGET_COMPANY_COUNT})")

    print("\nResearching winners and drafting emails...")
    winner_summaries = []
    for company_id, cand in winners:
        print(f"  ● {cand.name} ({cand.domain})")
        winner_summaries.append( research.research_and_draft(client, conn, company_id, cand, profile) )

    print("\nChecking for follow-ups...")
    followup_summaries = followups.run_followups( client, conn, profile )

    _print_digest( winner_summaries, followup_summaries )

    written = outbox.generate(conn)
    if written:
        out_dir, n = written
        print(f"\n✉  Wrote {n} ready-to-send draft(s) to {out_dir}/")
        print(f"   • {out_dir}/index.md  — recipients + subject + body, ready to copy-paste")
        print("   • one .eml per email   — double-click to open as a draft in your mail client")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
