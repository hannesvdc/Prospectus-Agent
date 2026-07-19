"""Manual status CLI — you drive outreach state with this (no inbox access).

Usage:
    prospectus-status list [STATUS]      # list all companies, or only one status
    prospectus-status show DOMAIN        # full detail: company, contacts, emails
    prospectus-status mark DOMAIN STATUS  # update status (mark sent => starts follow-up clock)
    prospectus-status drafts             # show companies with drafts ready to send

STATUS is one of: new, drafted, sent, replied, not_interested, not_a_fit
Marking 'sent' records today as the last-contact date (drives the follow-up timer).
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys


def _select_profile_early() -> None:
    """Honor a leading `--profile NAME` before config (which reads the active
    profile at import) is loaded. $DEFAULT_PROFILE from .env is picked up by config
    automatically, so this only matters when overriding it on the command line."""
    argv = sys.argv[1:]
    if "--profile" in argv:
        i = argv.index("--profile")
        if i + 1 < len(argv) and not argv[i + 1].startswith("-"):
            os.environ["PROSPECTUS_PROFILE"] = argv[i + 1]


_select_profile_early()

from prospectus_agent import db  # noqa: E402
from prospectus_agent import runner  # noqa: E402


def _conn() -> sqlite3.Connection:
    return runner.open_db()


def cmd_list(args: argparse.Namespace) -> None:
    conn = _conn()
    if args.status:
        rows = conn.execute(
            "SELECT * FROM companies WHERE status=? ORDER BY fit_score DESC, name",
            (args.status,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM companies ORDER BY status, fit_score DESC, name"
        ).fetchall()
    if not rows:
        print("No companies found.")
        return
    print(f"{'DOMAIN':<32}{'SCORE':>6}  {'STATUS':<15}{'LAST CONTACT':<14}NAME")
    print("-" * 100)
    for r in rows:
        print(f"{r['domain']:<32}{r['fit_score'] or 0:>6}  {r['status']:<15}"
              f"{(r['last_contact_date'] or '-'):<14}{r['name']}")


def cmd_show(args: argparse.Namespace) -> None:
    conn = _conn()
    c = db.get_company_by_domain(conn, args.domain)
    if not c:
        print(f"No company with domain '{args.domain}'.")
        return
    print(f"\n{c['name']}  ({c['domain']})")
    print(f"  status={c['status']}  fit_score={c['fit_score']}  "
          f"first_seen={c['first_seen']}  last_contact={c['last_contact_date'] or '-'}")
    print(f"  industry: {c['industry']}   hq: {c['hq_location']}")
    print(f"  why_fit: {c['why_fit']}")

    contacts = db.get_contacts(conn, c["id"])
    print(f"\n  Contacts ({len(contacts)}):")
    for ct in contacts:
        who = f"{ct['name']} ({ct['role']})" if ct["name"] else ct["role"]
        print(f"    [{ct['email_confidence']:<7}] {ct['email']:<40} {who}")

    for etype in ("initial", "followup"):
        em = db.latest_email(conn, c["id"], etype)
        if em:
            print(f"\n  --- {etype} email (drafted {em['created_at']}) ---")
            print(f"  Subject: {em['subject']}")
            print("  " + em["body"].replace("\n", "\n  "))


def cmd_mark(args: argparse.Namespace) -> None:
    conn = _conn()
    if args.status not in db.VALID_STATUSES:
        print(f"Invalid status. Valid: {sorted(db.VALID_STATUSES)}")
        sys.exit(1)
    if not db.get_company_by_domain(conn, args.domain):
        print(f"No company with domain '{args.domain}'.")
        sys.exit(1)
    set_date = args.status == "sent"
    db.set_status(conn, args.domain, args.status, set_contact_date=set_date)
    extra = " (last-contact date set to today; follow-up clock started)" if set_date else ""
    print(f"Marked {args.domain} as '{args.status}'.{extra}")


def cmd_drafts(args: argparse.Namespace) -> None:
    conn = _conn()
    rows = conn.execute(
        "SELECT * FROM companies WHERE status='drafted' ORDER BY fit_score DESC"
    ).fetchall()
    if not rows:
        print("No drafts pending.")
        return
    print("Drafts ready to review/send (use `show DOMAIN` for the full draft):\n")
    for r in rows:
        print(f"  {r['domain']:<32} score {r['fit_score']}  {r['name']}")


def main() -> None:
    p = argparse.ArgumentParser(description="Manual outreach status tracker.")
    p.add_argument(
        "--profile", metavar="NAME",
        help="business profile to act on (default: $DEFAULT_PROFILE). Put it before "
             "the subcommand, e.g. `prospectus-status --profile reactionstudio drafts`.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    pl = sub.add_parser("list", help="list companies")
    pl.add_argument("status", nargs="?", help="optional status filter")
    pl.set_defaults(func=cmd_list)

    ps = sub.add_parser("show", help="show one company in detail")
    ps.add_argument("domain")
    ps.set_defaults(func=cmd_show)

    pm = sub.add_parser("mark", help="set a company's status")
    pm.add_argument("domain")
    pm.add_argument("status")
    pm.set_defaults(func=cmd_mark)

    pd = sub.add_parser("drafts", help="list pending drafts")
    pd.set_defaults(func=cmd_drafts)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
