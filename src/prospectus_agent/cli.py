"""Unified command-line entrypoint for the prospecting agent.

CLI contract:
    prospectus-agent                       run the daily pipeline (discover + draft)
    prospectus-agent --refine              re-draft TODAY's emails with the current
                                           prompt (no new discovery or web research)
    prospectus-agent --profile NAME        use a different business: loads
                                           profile.NAME.yaml + NAME.db + outbox/NAME/
                                           (combine with --refine)
    prospectus-agent --version             print the version
    prospectus-agent --help                usage

Installed as the `prospectus-agent` console script (see pyproject.toml). Also
runnable as `python -m prospectus_agent`. Files (.env, profile*.yaml, the db,
outbox/) resolve against the project home, so it runs from any directory.
"""
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path
from typing import Optional, Sequence

from prospectus_agent import __version__

_PROFILE_NAME_RE = re.compile(r"[A-Za-z0-9_-]+")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prospectus-agent",
        description="Daily prospecting agent: discover prospects and draft outreach emails.",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Re-draft existing drafts with the current prompt/profile (no new "
             "discovery). Alone: refines today's prospect emails. Stacked with "
             "--followup (`--followup --refine`): re-drafts the due follow-ups.",
    )
    parser.add_argument(
        "--sent",
        action="store_true",
        help="Record that you've sent the drafted emails: mark all 'drafted' "
             "companies as 'sent' (contact date = their draft date) so the "
             "follow-up clock starts. No drafting or web research. Stackable.",
    )
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Follow-up sweep: draft a follow-up for each company past the no-reply "
             "threshold and write them to followups.md. No new discovery. Add "
             "--refine to re-draft existing follow-ups too.",
    )
    parser.add_argument(
        "--profile",
        metavar="NAME",
        help="Run a different business: loads profile.NAME.yaml, NAME.db, "
             "outbox/NAME/ (e.g. --profile reactionstudio). Defaults to profile.yaml.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def _apply_profile(name: str, home: Path) -> None:
    """Select business `name` by setting $PROSPECTUS_PROFILE BEFORE config is
    imported (config derives profile.<name>.yaml, <name>.db, outbox/<name>/ and the
    brief cache from it). Each business is thus fully isolated from the others."""
    if not _PROFILE_NAME_RE.fullmatch(name):
        raise SystemExit(
            f"error: invalid profile name '{name}' — use letters, digits, '-' or '_'."
        )
    profile_file = home / f"profile.{name}.yaml"
    if not profile_file.exists():
        raise SystemExit(
            f"error: no profile '{name}' found at {profile_file}.\n"
            f"Create it (e.g. copy profile.example.yaml to profile.{name}.yaml) "
            "and fill in that business's details."
        )
    os.environ["PROSPECTUS_PROFILE"] = name


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse args and dispatch. Returns a process exit code.

    Subcommand modules are imported lazily so `--help`/`--version` don't require
    the API key or any configuration, and so the chosen profile can set the
    environment before config/agent_profile are first imported. The profile is
    `--profile` if given, else $DEFAULT_PROFILE (from .env); if neither, the legacy
    profile.yaml / prospects.db defaults apply."""
    args = build_parser().parse_args(argv)

    # Importing paths loads .env (so DEFAULT_PROFILE is visible) and resolves HOME,
    # without yet computing config's path constants.
    from prospectus_agent import paths
    profile = args.profile or os.getenv("DEFAULT_PROFILE")
    if profile:
        _apply_profile(profile, paths.HOME)

    # Flags stack and run in order. With none of these, do the daily pipeline.
    ran = False

    if args.sent:
        from prospectus_agent import mark_sent
        rc = mark_sent.main()
        if rc:
            return rc
        ran = True

    if args.followup:
        from prospectus_agent import followup_run
        rc = followup_run.main(refine=args.refine)  # --followup --refine => re-draft
        if rc:
            return rc
        ran = True
    elif args.refine:
        from prospectus_agent import refine
        rc = refine.main()
        if rc:
            return rc
        ran = True

    if not ran:
        from prospectus_agent import daily_run
        return daily_run.main()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
