"""Resolve the project HOME and load .env — done ONCE, before any config constants
are computed.

Splitting this out of config lets the CLI load .env (to read DEFAULT_PROFILE) and
choose a profile — which sets the PROFILE_PATH/DB_PATH/OUTBOX_DIR/BRIEF_CACHE env
vars — *before* config reads those vars to build its typed path constants.
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def _resolve_home() -> Path:
    """The project home directory — where .env, profile*.yaml, the SQLite db and
    the outbox live. This is what lets the agent run from ANY working directory.

    Resolution order:
      1. $PROSPECTUS_AGENT_HOME, if set (point this at your project dir).
      2. The repo root inferred from this file's location (works for an editable
         `pip install -e .`, where this file stays at <home>/src/prospectus_agent/).
      3. The current working directory (last resort)."""
    env_home = os.getenv("PROSPECTUS_AGENT_HOME")
    if env_home:
        return Path(env_home).expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[2]  # <home>/src/prospectus_agent/paths.py
    anchors = (".env", "profile.example.yaml", "pyproject.toml")
    if any((repo_root / a).exists() for a in anchors) or list(repo_root.glob("profile.*.yaml")):
        return repo_root
    return Path.cwd()


HOME = _resolve_home()
# Load .env from the resolved home (not just the CWD) so running from elsewhere works.
load_dotenv(HOME / ".env")
