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
        "--runall",
        action="store_true",
        help="Fan out across EVERY configured profile (each profile.<name>.yaml), one "
             "per subprocess. Alone: the daily pipeline. Forwards action flags, so "
             "`--runall --followup --refine` re-drafts every profile's follow-ups. "
             "(Can't combine with --profile.)",
    )
    parser.add_argument(
        "--followup",
        action="store_true",
        help="Switch scope from new prospects (the default) to follow-ups: work on "
             "companies past the no-reply threshold. Alone, drafts a follow-up for "
             "each. Combine with --refine or --sent (below).",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Action: re-draft the in-scope existing drafts with the current "
             "prompt/profile (no discovery). Default scope = today's prospect "
             "emails; with --followup = the due follow-ups. Can't combine with --sent.",
    )
    parser.add_argument(
        "--sent",
        action="store_true",
        help="Action: record that you've sent the in-scope drafts (starts/resets the "
             "follow-up clock). Default scope = mark drafted prospects sent; with "
             "--followup = mark due follow-ups sent. Can't combine with --refine.",
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
    _validate(args)

    # --runall fans out to one subprocess per profile (forwarding the action flags),
    # so the parent stays profile-agnostic (don't apply a profile or import config).
    if args.runall:
        from prospectus_agent import run_all
        return run_all.main(followup=args.followup, refine=args.refine, sent=args.sent)

    # Importing paths loads .env (so DEFAULT_PROFILE is visible) and resolves HOME,
    # without yet computing config's path constants.
    from prospectus_agent import paths
    profile = args.profile or os.getenv("DEFAULT_PROFILE")
    if profile:
        _apply_profile(profile, paths.HOME)

    # `--followup` selects the follow-up SCOPE; `--refine`/`--sent` are modifiers that
    # act within it. Without `--followup` the same modifiers act on the initial drafts,
    # and with no modifiers at all we run the daily discovery pipeline.
    if args.followup:
        from prospectus_agent import followup_run
        return followup_run.main(refine=args.refine, mark_sent=args.sent)

    if args.refine:  # re-draft today's initial prospect emails
        from prospectus_agent import refine
        return refine.main()

    if args.sent:  # record that the initial drafts were sent
        from prospectus_agent import mark_sent
        return mark_sent.main()

    from prospectus_agent import daily_run
    return daily_run.main()


def _validate(args) -> None:
    """Reject flag combinations that can't be honoured coherently."""
    if args.runall and args.profile:
        raise SystemExit(
            "error: --runall already runs every profile — drop --profile (or run that "
            "one profile on its own, without --runall)."
        )
    if args.refine and args.sent:
        raise SystemExit(
            "error: --refine and --sent can't be combined. --refine re-drafts an "
            "email into a NEW, unsent version, while --sent records that you've "
            "already sent it — marking a fresh re-draft as 'sent' would be wrong. "
            "Re-draft first, send it, then run --sent."
        )


if __name__ == "__main__":
    raise SystemExit(main())
