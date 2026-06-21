"""Draft follow-ups on demand (standalone), without running discovery.

Invoked by `prospectus-agent --profile <name> --followup`.

Sweeps for companies in 'sent' status that haven't replied after
FOLLOWUP_BUSINESS_DAYS business days and ALWAYS writes a fresh `followups.md`/`.html`
for today containing every currently-due follow-up — even ones drafted on an earlier
run, so there's always a file to work from.

Default (`--followup`): drafts a follow-up for any due company that doesn't have one
yet (leaving existing drafts as they are). Stacked with `--refine`
(`--followup --refine`): RE-drafts every due follow-up with the current prompt/voice.
"""
from __future__ import annotations

import sys

from prospectus_agent import agent_profile
from prospectus_agent import config
from prospectus_agent import followups
from prospectus_agent import llm
from prospectus_agent import on_profile
from prospectus_agent import outbox
from prospectus_agent import redraft
from prospectus_agent import runner


def main(refine: bool = False) -> int:
    mode = "refine due follow-ups" if refine else "follow-up sweep"
    print(f"{agent_profile.NAME} — {mode}\n")

    try:
        client, conn = runner.open_session()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    profile_brief = on_profile.refresh_profile(client)

    if refine:
        print("Re-drafting every due follow-up with the current prompt/voice...")
        summaries = redraft.refine_followups(client, conn, profile_brief)
        changed = sum(1 for s in summaries if s.get("refined"))
        verb = "re-drafted"
    else:
        print(f"Checking for follow-ups (no reply after "
              f"{config.FOLLOWUP_BUSINESS_DAYS} business days)...")
        summaries = followups.run_followups(client, conn, profile_brief)
        changed = sum(1 for s in summaries if s.get("drafted"))
        verb = "newly drafted"

    print(f"\n{len(summaries)} due follow-up(s); {changed} {verb} this run:")
    if not summaries:
        print("  (none due — nothing in 'sent' status has passed the threshold)")
    for s in summaries:
        if refine:
            state = "re-drafted" if s.get("refined") else "unchanged"
        else:
            state = "newly drafted" if s.get("drafted") else s.get("note", "—")
        bdays = f" — {s['business_days']} business days" if "business_days" in s else ""
        print(f"  ● {s['name']} ({s['domain']}){bdays}, {state}")

    # Always (re)write today's followups file with ALL currently-due drafts, so the
    # file exists even when nothing changed this run.
    written = outbox.write_file(conn, followups.due_followup_emails(conn),
                                basename="followups", title="Follow-up drafts")
    if written:
        out_dir, n = written
        print(f"\n✉  Wrote {n} follow-up draft(s) to {out_dir}/ (followups.md + .html).")

    usage = llm.usage_summary()
    if usage:
        print(f"\n{usage}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
