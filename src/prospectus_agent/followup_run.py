"""Draft follow-ups on demand (standalone), without running discovery.

Invoked by `prospectus-agent --profile <name> --followup`.

Sweeps for companies in 'sent' status that haven't replied after
FOLLOWUP_BUSINESS_DAYS business days, lists them, drafts a follow-up for each
(skipping any already drafted since the last contact), and writes the new drafts
to the outbox. This is the same follow-up step the daily run does — just on its
own, so you can chase replies without finding new prospects.
"""
from __future__ import annotations

import sys

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import followups
from prospectus_agent import llm
from prospectus_agent import on_profile
from prospectus_agent import outbox


def main() -> int:
    print(f"{agent_profile.NAME} — follow-up sweep\n")

    try:
        config.require_api_key()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    client = config.get_client()
    conn = db.connect(config.DB_PATH)
    db.init_db(conn)
    llm.reset_usage()
    emails_before = db.max_email_id(conn)  # so the outbox emits only this run's drafts

    profile_brief = on_profile.refresh_profile(client)

    print(f"Checking for follow-ups (no reply after "
          f"{config.FOLLOWUP_BUSINESS_DAYS} business days)...")
    summaries = followups.run_followups(client, conn, profile_brief)

    due = len(summaries)
    drafted = sum(1 for s in summaries if s["drafted"])
    print(f"\n{due} company(ies) ready for follow-up; {drafted} new draft(s):")
    if not summaries:
        print("  (none due — nothing in 'sent' status has passed the threshold)")
    for s in summaries:
        state = "drafted" if s["drafted"] else s.get("note", "—")
        print(f"  ● {s['name']} ({s['domain']}) — {s['business_days']} business days, {state}")

    written = outbox.generate(conn, since_email_id=emails_before)
    if written:
        out_dir, n = written
        print(f"\n✉  Wrote {n} follow-up draft(s) to {out_dir}/ (index.md + index.html).")

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
