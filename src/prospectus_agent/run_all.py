"""Fan a command out across EVERY configured profile (`prospectus-agent --runall`).

`--runall` runs the same thing you'd run for one business, but for all of them. With
no action flags it's the daily pipeline (new prospects + follow-up sweep); combined
with `--followup`/`--refine`/`--sent` it forwards those to each profile (e.g.
`--runall --followup --refine` re-drafts every profile's follow-ups).

Each profile runs in its own subprocess — config/agent_profile are per-process
singletons keyed to the active profile, so separate processes keep the businesses
fully isolated, and one profile failing doesn't stop the rest.
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


def main(followup: bool = False, refine: bool = False, sent: bool = False,
         deliver: bool = False, live: bool = False) -> int:
    names = profile_names()
    if not names:
        print("No business profiles found (looked for profile.<name>.yaml in "
              f"{paths.HOME}). Create one (see profile.example.yaml).")
        return 0

    extra = [flag for flag, on in (
        ("--followup", followup), ("--refine", refine), ("--sent", sent),
        ("--deliver", deliver), ("--live", live)) if on]
    label = " ".join(extra) if extra else "daily pipeline"
    # flush=True on every banner: subprocess stdout streams straight to the terminal, so
    # unflushed parent prints would otherwise appear AFTER the output they introduce.
    print(f"Running `{label}` for {len(names)} profile(s): {', '.join(names)}\n", flush=True)

    results: dict[str, int] = {}
    for name in names:
        print("=" * 72, flush=True)
        print(f"▶  {name}  ({label})", flush=True)
        print("=" * 72, flush=True)
        # Re-invoke ourselves for this profile, forwarding the action flags. Output
        # streams live.
        results[name] = subprocess.run(
            [sys.executable, "-m", "prospectus_agent", "--profile", name, *extra]
        ).returncode

    print("\n" + "=" * 72, flush=True)
    print("RUN-ALL SUMMARY", flush=True)
    for name, rc in results.items():
        print(f"  {'✓' if rc == 0 else '✗'} {name} (exit {rc})", flush=True)
    return 0 if all(rc == 0 for rc in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
