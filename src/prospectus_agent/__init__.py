"""prospectus_agent — daily prospecting agent that finds prospective clients and
drafts tailored outreach emails.

Engine modules are business-agnostic; everything company-specific lives in
profile.yaml (loaded by agent_profile) and prompts/. The console entrypoint is
`prospectus-agent` (see cli.main)."""
from __future__ import annotations

__version__ = "0.2.0"
