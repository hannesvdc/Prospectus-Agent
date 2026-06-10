# Prospectus-Agent

An AI agent that, each morning, finds up to five new North American companies
that could be clients of [Open Numerics](https://opennumerics.com) — firms doing
numerical simulation, uncertainty quantification, scientific machine learning, or
GPU/HPC compute — and drafts a tailored outreach email for each. It keeps a local
database of every company seen and their outreach status, and drafts follow-ups
when a contacted company hasn't replied within five business days.

You send all emails yourself; the agent only finds companies and prepares drafts.

## How it works

`python daily_run.py` runs the pipeline:

1. **Refresh ON profile** — fetches opennumerics.com (cached per day) so drafts
   reflect ON's current services.
2. **Discover** — up to 3 web-search rounds (`MAX_DISCOVERY_CALLS`) to find up to
   5 (`TARGET_COMPANY_COUNT`) companies scoring ≥ 7/10 (`FIT_SCORE_THRESHOLD`),
   rotating industry angle each round and skipping anything already in the DB.
3. **Research + draft** — for each winner, reads its site + leadership, stores
   contacts (public emails + pattern-guessed exec addresses), and drafts a
   tailored, CAN-SPAM-compliant initial email.
4. **Follow-ups** — flags companies marked `sent` with no reply after 5 business
   days and drafts a follow-up.
5. Prints a digest.

Every company ever seen (fits and non-fits) is stored, so none resurface.

### LLM vs. plain Python
The fuzzy work (finding/scoring companies, drafting) uses the OpenAI Responses
API (`gpt-5.5`, the hosted `web_search` tool — which also opens/reads pages — and
structured output via strict function-tool calls). The bookkeeping (SQLite,
dedup, follow-up timing) is plain Python, behind the single `llm.py` seam so the
provider can be swapped without touching the pipeline.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # then fill in OPENAI_API_KEY and SENDER_* fields
```

The agent reads config from `.env` (gitignored). Key fields:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key (platform.openai.com) |
| `OPENAI_MODEL` | Model id (default `gpt-5.5`, OpenAI's recommended model for web search) |
| `SENDER_NAME` / `SENDER_EMAIL` / `SENDER_PHYSICAL_ADDRESS` | Used in the email sign-off; the physical address is required for CAN-SPAM |
| `FIT_SCORE_THRESHOLD`, `TARGET_COMPANY_COUNT`, `MAX_DISCOVERY_CALLS`, `FOLLOWUP_BUSINESS_DAYS` | Pipeline tunables |

## Daily use

```bash
.venv/bin/python daily_run.py            # find prospects + draft emails

.venv/bin/python status.py drafts        # list drafts ready to review
.venv/bin/python status.py show DOMAIN   # see the full draft + contacts
# ... you send the email yourself ...
.venv/bin/python status.py mark DOMAIN sent       # starts the follow-up clock
.venv/bin/python status.py mark DOMAIN replied    # or: not_interested
```

Status values: `new`, `drafted`, `sent`, `replied`, `not_interested`, `not_a_fit`.
Reply tracking is fully manual — the agent never reads your inbox.

## Files

| File | Role |
|---|---|
| `daily_run.py` | Pipeline entrypoint |
| `status.py` | Manual status CLI |
| `config.py` | Loads `.env`, constants, OpenAI client |
| `db.py` | SQLite layer (companies, contacts, emails) |
| `llm.py` | OpenAI Responses API helpers (web_search + strict submit-tool extraction) |
| `on_profile.py` | Daily ON profile refresh |
| `discovery.py` | Bounded web-search discovery loop |
| `research.py` | Per-winner grounding + initial-email drafting |
| `drafting.py` | Signature, CAN-SPAM guidance, follow-up drafting |
| `contacts.py` | Email-pattern guessing |
| `followups.py` | Business-day follow-up sweep |
| `schemas.py` | Pydantic validation models |
| `prompts/` | All LLM prompt text, one module per type (`discovery`, `research`, `followup`, `on_profile`, `common`); each exposes `SYSTEM` + `build_user(...)` |

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The suite (in `tests/`) runs offline — the OpenAI client is faked, so no API
key and no spend. It covers the DB layer (dedup, status, contacts, follow-up
query), email-pattern guessing, business-day math, the discovery loop (including
that service-provider/competitor companies are filtered out), per-winner
research/drafting, the LLM helpers (function-call extraction + submit-tool
nudge), and strict function-tool schema validity.

## v1 limitations / next steps

- Discovery and per-winner research are real API calls — **not yet run live**;
  the web_search + strict-function-tool flow should be verified end-to-end on a
  real key (and `gpt-5.5` confirmed available to your account).
- No public-holiday calendar (business days = Mon–Fri).
- Email guesses are unverified (no SMTP/MX check) — sent at your discretion.
