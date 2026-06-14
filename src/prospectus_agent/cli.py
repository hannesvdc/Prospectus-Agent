"""Unified command-line entrypoint for the prospecting agent.

CLI contract:
    prospectus-agent              run the daily pipeline (discover + draft)
    prospectus-agent --refine     re-draft TODAY's emails with the current prompt
                                  (no new discovery or web research)
    prospectus-agent --version    print the version
    prospectus-agent --help       usage

Installed as the `prospectus-agent` console script (see pyproject.toml). Also
runnable as `python -m prospectus_agent`. Run from the project root so the
working-directory files (.env, profile.yaml, the SQLite db, outbox/) resolve.
"""
from __future__ import annotations

import argparse
from typing import Optional, Sequence

from prospectus_agent import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="prospectus-agent",
        description="Daily prospecting agent: discover prospects and draft outreach emails.",
    )
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Re-draft today's existing emails with the current prompt/profile "
             "(no new discovery or web research), then regenerate the outbox.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse args and dispatch. Returns a process exit code.

    Subcommand modules are imported lazily so `--help`/`--version` don't require
    the API key or any configuration to be present."""
    args = build_parser().parse_args(argv)

    if args.refine:
        from prospectus_agent import refine
        return refine.main()

    from prospectus_agent import daily_run
    return daily_run.main()


if __name__ == "__main__":
    raise SystemExit(main())
