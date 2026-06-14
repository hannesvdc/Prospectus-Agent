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
from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import llm
from prospectus_agent import on_profile
from prospectus_agent import outbox
from prospectus_agent import redraft


def main() -> int:
    print(f"{agent_profile.NAME} — refine today's drafts ({date.today().isoformat()})\n")

    try:
        config.require_api_key()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    client = config.get_client()
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)
    llm.reset_usage()

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
            print(f"\n✉  Regenerated {n} draft(s) in {out_dir}/ (index.md + index.html).")
    else:
        print("\nNothing refined — outbox left unchanged.")

    u = llm.get_usage()
    if u["calls"]:
        print(
            f"\nToken usage: {u['calls']} API call(s) — "
            f"input {u['input']:,} (cached {u['cached']:,}), "
            f"output {u['output']:,} (reasoning {u['reasoning']:,})."
        )

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
