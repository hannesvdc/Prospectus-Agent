# Prospectus-Agent

*A little agent that does the part of running a business I'm worst at: finding people to email.*

I run [Open Numerics](https://opennumerics.com), a small scientific-computing
consultancy — simulation, uncertainty quantification, scientific ML, GPU/HPC. We're
good at the work. We are not good at *prospecting*. Every week I'd lose a morning to
it: open fifteen tabs, hunt for companies that might need us, get lost, give up,
fire off three awkward cold emails, and then never follow up. I dreaded it, so I
mostly just… didn't.

So I built this. Each morning I run one command and it hands me a short list of
companies that actually fit, each with a tailored draft email I can skim and send
from my own inbox. It turned the worst hour of my week into five minutes over coffee.

Then I realised nothing in it was really about *me* or my business per se. I pulled all the
Open-Numerics-specific bits into a single config file. Now it's a tool anyone can
point at their own business. (The example config that ships with it is Open Numerics;
swap in your own.)

## What it does

- Every run, it **searches the web for companies that fit your business**, scores
  them for fit, spreads them across sectors, and skips anyone you've already seen —
  no re-surfacing the same names, no bloated lead list to pay for.
- It **reads each company before writing**, so the draft talks about *their* actual
  work and concrete ways you could help — not mail-merge filler.
- It keeps a small local database of who you've contacted and **nudges you to follow
  up** when a thread goes quiet (that's where most replies come from, and it's the
  bit I always forgot).
- It **never sends anything.** You get copy-paste-ready drafts and send from your own
  inbox, in your own voice. I did that on purpose — I don't trust any robot, this one
  included, to email strangers for me.
- It runs on a cheap model for **pennies a day**, not a monthly sales-SaaS seat.

The honest pitch: it turns *"spend a morning hunting for leads and writing cold
emails"* into *"skim a few tailored drafts over coffee and hit send."*

## Make it yours

You don't edit code. You write one file — **`profile.yaml`** — describing your
business and who you want to reach: what you sell, who's a good fit, who to *exclude*
(competitors who do what you do), which industries to focus on, and which giants to
steer clear of. See `profile.example.yaml` for a fully worked example.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env                    # then add your OPENAI_API_KEY
cp profile.example.yaml profile.yaml    # then describe YOUR business + ideal customer
```

That's the whole setup. If `profile.yaml` is missing, it falls back to the example
so a fresh clone still runs.

> **Two layers of "template":** `profile.yaml` is the *content* (your business — what
> you'll edit). `prompts/` holds the actual *prompt templates* — one small Python
> module per step. Only touch `prompts/` if you want to change the wording or tone of
> what the agent asks the model.

## How it works

`python daily_run.py` runs the pipeline:

1. **Refresh profile** — fetches your company's website (cached; default weekly via
   `PROFILE_REFRESH_DAYS`) so drafts reflect what you currently do.
2. **Discover** — up to `MAX_DISCOVERY_CALLS` web-search rounds (default 2) to find
   up to `TARGET_COMPANY_COUNT` companies (default 3) scoring ≥ `FIT_SCORE_THRESHOLD`/10,
   rotating the industry angle each round (with a per-day offset) and skipping
   anything already in the DB. A **diversifier** caps how many picks share one sector
   (`MAX_PER_SECTOR`, default 2) so a single sector can't take over the list;
   good-but-capped companies become a backlog that future runs draft first.
3. **Research + draft** — for each winner it reads the site + leadership, stores a
   short contact list (one inbox + a few senior people), and drafts a tailored email.
   The draft has **no sign-off/signature** — your mail client adds yours on send.
4. **Follow-ups** — flags anyone marked `sent` with no reply after five business days
   and drafts a gentle nudge.
5. Writes `outbox/<date>/index.md` — each email with its contact list, ready to
   copy-paste. Running again the same day **appends** the new drafts rather than
   overwriting, so earlier drafts (and any notes you added) are kept.
6. Prints a digest and a token-usage line so you can see what the run cost.

Every company it ever sees (fits and non-fits) is stored, so none resurface.

**Under the hood:** the judgment calls (finding/scoring companies, drafting) use the
OpenAI Responses API (default `gpt-5.4-mini` + the hosted `web_search` tool, with
structured output via strict function tools). The boring-but-important bookkeeping
(SQLite, dedup, follow-up timing) is plain Python, behind a single `llm.py` seam.

## Config dials (`.env`)

`profile.yaml` is your business; `.env` is the machinery. Secrets and cost/runtime
knobs live here (gitignored):

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
# ...you read it, maybe tweak it, and send it from your inbox...
.venv/bin/python status.py mark DOMAIN sent       # starts the follow-up clock
.venv/bin/python status.py mark DOMAIN replied    # or: not_interested
```

Status values: `new`, `drafted`, `sent`, `replied`, `not_interested`, `not_a_fit`.
Reply tracking is fully manual — the agent never reads your inbox.

## A few honest notes

- **Guessed emails are guesses.** When it can't find a published address it pattern-
  guesses one (`jane.doe@…`). Most land; some bounce. For anyone important, sanity-
  check the address before sending.
- **Garbage in, garbage out.** Lead quality tracks how well you describe your ideal
  customer in `profile.yaml`. Vague profile → mediocre leads. Spend ten minutes on it.
- **Watch the cost line.** I burned through $5 in three runs before realising I was
  using a flagship model for everything. The default is now a cheap model; the token-
  usage summary at the end of each run is there so you notice early.
- **Read before you send.** It's good, not infallible — it's writing about companies
  it researched in seconds. Skim each draft. That's the whole point of "it never sends."
- **It's single-user and local** (one SQLite file, one inbox). A hosted, multi-tenant
  version is a someday-maybe, not a today.

## The code

Small and deliberately boring. Engine files know nothing about any particular
business — everything company-specific lives in `profile.yaml` / `prompts/`.

| File | Role |
|---|---|
| `daily_run.py` | Pipeline entrypoint |
| `status.py` | Manual status CLI |
| `profile.yaml` / `agent_profile.py` | Your business + ICP (the thing you edit) and its loader |
| `prompts/` | Prompt templates, one module per step — edit to change wording/tone |
| `config.py` | Loads `.env`, constants, OpenAI client |
| `db.py` | SQLite layer (companies, contacts, emails) |
| `llm.py` | OpenAI Responses API helpers (web_search + strict tool extraction) |
| `on_profile.py` | Company website-brief refresh (cached) |
| `discovery.py` | The discovery loop + per-sector diversifier + backlog seeding |
| `sectors.py` | Keyword sector classifier (powers the diversifier) |
| `research.py` | Per-company research + initial-email drafting |
| `drafting.py` | Follow-up drafting |
| `contacts.py` | Email-pattern guessing |
| `followups.py` | Business-day follow-up sweep |
| `outbox.py` | Writes the copy-paste `index.md` digest of drafts |
| `schemas.py` | Pydantic validation models |

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The suite runs **offline** — the OpenAI client is faked, so no key and no spend. It
covers the database (dedup, status, contacts, follow-up timing), email-pattern
guessing, business-day math, the discovery loop (including that competitors and
over-size companies get filtered out), per-company research/drafting, the LLM helpers,
and the strict tool schemas.

## Roadmap / known gaps

- No public-holiday calendar (business days = Mon–Fri).
- Guessed emails aren't SMTP/MX-verified.
- Single-tenant and local; a configurable hosted version may come later.

Built it for myself; sharing it in case your prospecting mornings look like mine did.

## Contribute
Contributions are very welcome! This is supposed to be a shared project. Many businesses are facing
the same struggles, let's help each other!
