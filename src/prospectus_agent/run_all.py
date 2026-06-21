"""Run the daily pipeline for EVERY configured profile (`prospectus-agent --runall`).

Each profile is run in its own subprocess — config/agent_profile are per-process
singletons keyed to the active profile, so separate processes keep the businesses
fully isolated, and one profile failing doesn't stop the rest. The per-profile daily
run already does both new prospects and the follow-up sweep.
"""
from __future__ import annotations

import subprocess
import sys

from prospectus_agent import paths


def profile_names() -> list[str]:
    """Names of all configured business profiles — profile.<name>.yaml in the project
    home, excluding the committed profile.example.yaml template."""
    names = []
    for p in sorted(paths.HOME.glob("profile.*.yaml")):
        name = p.name[len("profile."):-len(".yaml")]
        if name and name != "example":
            names.append(name)
    return names


def main() -> int:
    names = profile_names()
    if not names:
        print("No business profiles found (looked for profile.<name>.yaml in "
              f"{paths.HOME}). Create one (see profile.example.yaml).")
        return 0

    print(f"Running the daily pipeline for {len(names)} profile(s): {', '.join(names)}\n")
    results: dict[str, int] = {}
    for name in names:
        print("=" * 72)
        print(f"▶  {name}")
        print("=" * 72)
        # Re-invoke ourselves for this profile; output streams live.
        results[name] = subprocess.run(
            [sys.executable, "-m", "prospectus_agent", "--profile", name]
        ).returncode

    print("\n" + "=" * 72)
    print("RUN-ALL SUMMARY")
    for name, rc in results.items():
        print(f"  {'✓' if rc == 0 else '✗'} {name} (exit {rc})")
    return 0 if all(rc == 0 for rc in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
