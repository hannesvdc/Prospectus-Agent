"""Draft follow-ups on demand (standalone), without running discovery.

Invoked by `prospectus-agent --profile <name> --followup`.

Sweeps for companies in 'sent' status that haven't replied after
FOLLOWUP_BUSINESS_DAYS business days and ALWAYS writes a fresh `followups.md`/`.html`
for today containing every currently-due follow-up — even ones drafted on an earlier
run, so there's always a file to work from.

`--refine` and `--sent` are MODIFIERS within the follow-up scope:
  --followup            draft a follow-up for any due company that lacks one.
  --followup --refine   re-draft every due follow-up with the current prompt/voice.
  --followup --sent     record that you've sent them (reset the follow-up clock);
                        does NOT draft new ones.
  --followup --refine --sent  re-draft, then mark sent.
Either way it (re)writes today's followups.md with the currently-due drafts.
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


def main(refine: bool = False, mark_sent: bool = False) -> int:
    print(f"{agent_profile.NAME} — follow-ups\n")

    try:
        client, conn = runner.open_session()
    except RuntimeError as e:
        print(f"ERROR: {e}")
        return 1

    profile_brief = on_profile.refresh_profile(client)

    # 1) Modify drafts: re-draft (--refine), draft-missing (default), or neither
    #    when we're only recording sends (--sent on its own).
    if refine:
        print("Re-drafting every due follow-up with the current prompt/voice...")
        summaries = redraft.refine_followups(client, conn, profile_brief)
        changed, verb = sum(1 for s in summaries if s.get("refined")), "re-drafted"
    elif not mark_sent:
        print(f"Checking for follow-ups (no reply after "
              f"{config.FOLLOWUP_BUSINESS_DAYS} business days)...")
        summaries = followups.run_followups(client, conn, profile_brief)
        changed, verb = sum(1 for s in summaries if s.get("drafted")), "newly drafted"
    else:
        summaries, verb = [], None  # --sent only: just record sends

    if verb is not None:
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

    # 2) Always (re)write today's followups file with ALL currently-due drafts.
    written = outbox.write_file(conn, followups.due_followup_emails(conn),
                                basename="followups", title="Follow-up drafts")
    if written:
        out_dir, n = written
        print(f"\n✉  Wrote {n} follow-up draft(s) to {out_dir}/ (followups.md + .html).")

    # 3) Record sends (reset the follow-up clock), if asked.
    if mark_sent:
        marked = followups.mark_followups_sent(conn)
        print(f"\n✓ Marked {len(marked)} follow-up(s) as sent "
              "(follow-up clock reset to today).")

    usage = llm.usage_summary()
    if usage:
        print(f"\n{usage}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
