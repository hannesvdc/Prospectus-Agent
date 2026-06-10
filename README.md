# Prospectus-Agent

A self-hostable AI prospecting agent. Each day it finds new companies that fit
**your** business, drafts a tailored outreach email for each (with a short contact
list), tracks who you've reached out to, and drafts follow-ups when a company
hasn't replied within five business days.

You send all emails yourself; the agent only finds companies and prepares drafts.

**It's fully configurable.** You describe your business and ideal customer once in
`profile.yaml` (see `profile.example.yaml`) — what you sell, who's a good fit, who
to exclude, which industries to focus on — and the agent templatizes everything
around it. The engine code is generic; nothing about a particular company is
hardcoded. (The shipped example profile is [Open Numerics](https://opennumerics.com),
a scientific-computing consultancy — replace it with your own.)

## Why this exists

Cold outreach works — but the grind around it doesn't. The hardest, most expensive
part isn't writing the email; it's **finding companies that are actually a good
fit**. That means hours of manual searching every week (or a pricey
sales-intelligence subscription), and even then most of what you turn up is noise.
Then each promising lead needs real research before you can write something that
doesn't read like mail-merge — and the follow-ups, where most replies actually come
from, quietly slip through the cracks.

This agent takes that whole grind off your plate:

- **Finding companies is the costly part — so it does it for you.** Every run it
  searches the web for genuinely-fitting prospects, scores them, diversifies across
  sectors, and skips anyone you've already seen — no re-surfacing the same names, no
  bloated lead list to pay for.
- **Tailored, not templated.** It reads each company *before* writing, so the draft
  references their real work and concrete ways you could help — not filler.
- **Nothing slips.** It tracks who you've contacted and drafts a follow-up the
  moment a thread goes quiet.
- **Pennies per day, not a monthly seat.** A run costs cents on a small model —
  orders of magnitude less than a sales-intelligence platform.
- **You stay in control.** It never sends anything. You get ready-to-paste drafts
  (and `.eml` files) and send from your own inbox, in your own voice.

In short: it turns "spend a morning hunting for leads and writing cold emails" into
"skim five tailored drafts over coffee and hit send."

## How it works

`python daily_run.py` runs the pipeline:

1. **Refresh profile** — fetches your company's website (cached; default weekly via
   `PROFILE_REFRESH_DAYS`) so drafts reflect your current services.
2. **Discover** — up to `MAX_DISCOVERY_CALLS` web-search rounds (default 2) to find
   up to `TARGET_COMPANY_COUNT` companies (default 3) scoring ≥ `FIT_SCORE_THRESHOLD`/10,
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
API (default `gpt-5.4-mini`, the hosted `web_search` tool — which also opens/reads
pages — and structured output via strict function-tool calls). The bookkeeping
(SQLite, dedup, follow-up timing) is plain Python, behind the single `llm.py` seam.

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env          # then fill in OPENAI_API_KEY
cp profile.example.yaml profile.yaml   # then describe YOUR business + ideal customer
```

**`profile.yaml`** is where you make the agent yours — company name, what you sell,
who's a good prospect, who to exclude (competitors), which industries to focus on,
and giants to avoid. See `profile.example.yaml` for a worked example. (If
`profile.yaml` is absent, the example is used.)

**Templates live in two places:** `profile.yaml` holds the *content* (your business
and ICP — what most users edit), and **`prompts/`** holds the *prompt templates*
themselves — one module per step, plain Python that interpolates your profile. Edit
`prompts/` only if you want to change the wording, tone, or structure of what the
agent asks the model.

The rest of the config lives in `.env` (gitignored) — secrets + runtime/cost dials:

| Variable | Purpose |
|---|---|
| `OPENAI_API_KEY` | Your OpenAI API key (platform.openai.com) |
| `OPENAI_MODEL` | Model id (default `gpt-5.4-mini` — cheap; `gpt-5.4` / `gpt-5.5` cost ~2× / ~6.6× more) |
| `FIT_SCORE_THRESHOLD`, `TARGET_COMPANY_COUNT`, `MAX_DISCOVERY_CALLS`, `FOLLOWUP_BUSINESS_DAYS` | Pipeline tunables |
| `MAX_PER_SECTOR` | Max picks from one sector per day (diversifier; default 2) |
| `AVOID_SECTORS` | Comma-separated sector keys to exclude entirely (e.g. `aerospace_defense`). Avoided-but-qualified companies are kept as reversible backlog. Valid keys are in `sectors.py`. |
| `MAX_COMPANY_SIZE` | Largest company size to target: `startup`\|`small`\|`mid`\|`large`\|`enterprise` (default `mid`). Bigger companies (e.g. multinationals like GM) are excluded. |
| `MAX_PUBLIC_EMAILS` / `MAX_PEOPLE` / `GUESSES_PER_PERSON` | Contact-list size per company (default 1 generic inbox + 3 senior people, 1 address each). |
| `DISCOVERY_EFFORT` / `DRAFTING_EFFORT` | Reasoning effort per step (`none`…`xhigh`; default `low`). Raise `DRAFTING_EFFORT` if email quality dips. |
| `SEARCH_CONTEXT_SIZE` | How much web-search content enters context: `low`\|`medium`\|`high` (default `low`). Main per-call token lever. |
| `DISCOVERY_MODEL` | Model for the mechanical steps (profile + scoring); defaults to `OPENAI_MODEL`. An even cheaper model (e.g. `gpt-5.4-nano`) is fine here. |
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
| `profile.yaml` / `agent_profile.py` | Your business + ICP (the only thing to edit) and its loader |
| `config.py` | Loads `.env`, constants, OpenAI client |
| `db.py` | SQLite layer (companies, contacts, emails) |
| `llm.py` | OpenAI Responses API helpers (web_search + strict submit-tool extraction) |
| `on_profile.py` | Company website-brief refresh (cached) |
| `discovery.py` | Bounded web-search discovery loop + per-sector diversifier + backlog seeding |
| `sectors.py` | Keyword sector classifier (powers the diversifier) |
| `research.py` | Per-winner grounding + initial-email drafting |
| `drafting.py` | Follow-up drafting orchestration |
| `contacts.py` | Email-pattern guessing |
| `followups.py` | Business-day follow-up sweep |
| `outbox.py` | Writes copy-paste `index.md` + `.eml` drafts after a run |
| `schemas.py` | Pydantic validation models |
| `prompts/` | All LLM prompt **templates**, one module per step (`discovery`, `research`, `followup`, `on_profile`); each exposes `system()` / `build_user(...)` that interpolate your profile. Edit here to change wording/tone. |

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
  real key (and your chosen model confirmed available to your account).
- No public-holiday calendar (business days = Mon–Fri).
- Email guesses are unverified (no SMTP/MX check) — sent at your discretion.
