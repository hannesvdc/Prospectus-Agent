"""Refine today's already-generated drafts with the CURRENT prompt/profile.

Invoked by `prospectus-agent --refine`.

Run this after tuning the email voice (prompts/research.email_rules, the openers
or credibility line in profile.yaml, etc.) to rewrite TODAY's existing drafts so
they reflect your changes — without re-discovering or re-researching anything.

It rewrites each initial draft's subject/body in place (contacts and company
records are left untouched), then regenerates today's outbox (index.md + .html)
from scratch. No web search is used, so it's cheap and fast.
"""
from __future__ import annotations

import sys
from datetime import date

from prospectus_agent import agent_profile
from prospectus_agent import on_profile
from prospectus_agent import outbox
from prospectus_agent import redraft
from prospectus_agent import runner


def main() -> int:
    banner = f"{agent_profile.NAME} — refine today's drafts ({date.today().isoformat()})\n"
    try:
        with runner.session(banner) as (client, conn):
            # Cached profile brief — no new web call unless the daily cache is stale.
            profile_brief = on_profile.refresh_profile(client)

            print("Refining today's drafts...")
            summaries = redraft.refine_today(client, conn, profile_brief)

            refined = [s for s in summaries if s["refined"]]
            print(f"\nRefined {len(refined)}/{len(summaries)} draft(s).")
            for s in refined:
                print(f"  ● {s['name']} ({s['domain']})")
                print(f"      subject: {s.get('subject', '')}")

            if refined:
                written = outbox.generate(conn, overwrite=True)
                if written:
                    out_dir, n = written
                    print(f"\n✉  Regenerated {n} draft(s) in {out_dir}/ (new_prospects.md + .html).")
            else:
                print("\nNothing refined — outbox left unchanged.")
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
