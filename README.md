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
   rotating industry angle each round (with a per-day offset) and skipping
   anything already in the DB. A **diversifier** caps how many picks share a
   sector (`MAX_PER_SECTOR`, default 2) so one sector (e.g. aviation) can't
   dominate; qualified-but-capped companies become a backlog that future runs
   draft first.
3. **Research + draft** — for each winner, reads its site + leadership, stores
   contacts (public emails + pattern-guessed exec addresses), and drafts a
   tailored initial email body. The draft has **no sign-off/signature** — your
   own mail client appends your signature (name, contact, address) on send.
4. **Follow-ups** — flags companies marked `sent` with no reply after 5 business
   days and drafts a follow-up.
5. Writes ready-to-send drafts to `outbox/<date>/` — `index.md` (each email with
   its contact list, for copy-paste) plus one `.eml` per email (double-click to
   open as a pre-filled draft in your mail client).
6. Prints a digest.

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
cp .env.example .env      # then fill in OPENAI_API_KEY
```

The agent reads config from `.env` (gitignored). Key fields:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key (platform.openai.com) |
| `OPENAI_MODEL` | Model id (default `gpt-5.5`, OpenAI's recommended model for web search) |
| `FIT_SCORE_THRESHOLD`, `TARGET_COMPANY_COUNT`, `MAX_DISCOVERY_CALLS`, `FOLLOWUP_BUSINESS_DAYS` | Pipeline tunables |
| `MAX_PER_SECTOR` | Max picks from one sector per day (diversifier; default 2) |
| `AVOID_SECTORS` | Comma-separated sector keys to exclude entirely (e.g. `aerospace_defense`). Avoided-but-qualified companies are kept as reversible backlog. Valid keys are in `sectors.py`. |
| `MAX_COMPANY_SIZE` | Largest company size to target: `startup`\|`small`\|`mid`\|`large`\|`enterprise` (default `mid`). Bigger companies (e.g. multinationals like GM) are excluded. |
| `MAX_PUBLIC_EMAILS` / `MAX_PEOPLE` / `GUESSES_PER_PERSON` | Contact-list size per company (default 1 generic inbox + 3 senior people, 1 address each). |
| `DISCOVERY_EFFORT` / `DRAFTING_EFFORT` | Reasoning effort per step (`none`…`xhigh`; default `low`). Raise `DRAFTING_EFFORT` if email quality dips. |
| `SEARCH_CONTEXT_SIZE` | How much web-search content enters context: `low`\|`medium`\|`high` (default `low`). Main per-call token lever. |
| `DISCOVERY_MODEL` | Model for the mechanical steps (profile + scoring); defaults to `OPENAI_MODEL`. A cheaper model (e.g. `gpt-5-mini`) is fine here. |
| `DISCOVERY_MAX_TOKENS` / `DRAFT_MAX_TOKENS` / `PROFILE_MAX_TOKENS` | Per-step output-token caps. |

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
| `discovery.py` | Bounded web-search discovery loop + per-sector diversifier + backlog seeding |
| `sectors.py` | Keyword sector classifier (powers the diversifier) |
| `research.py` | Per-winner grounding + initial-email drafting |
| `drafting.py` | Follow-up drafting orchestration |
| `contacts.py` | Email-pattern guessing |
| `followups.py` | Business-day follow-up sweep |
| `outbox.py` | Writes copy-paste `index.md` + `.eml` drafts after a run |
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
