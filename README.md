# Prospectus-Agent

*A little agent that does the part of running a business I'm worst at: finding people to email.*

I run [Open Numerics](https://opennumerics.com), a small scientific-computing consultancy.
We're good at the work, not at *prospecting* — every week I'd lose a morning opening fifteen
tabs, fire off three awkward cold emails, and never follow up. So I built this: each morning
one command hands me a short list of companies that fit, each with a tailored draft I skim and
send from my own inbox. The worst hour of my week became five minutes over coffee.

Nothing in it is specific to me — the business-specific bits live in one config file, so you can
point it at your own. (It ships configured for Open Numerics; swap in yours.)

## What it does

- **Finds fitting companies** — searches the web each run, scores for fit, spreads picks across
  sectors, and skips anyone you've already seen. No bloated lead list to pay for.
- **Reads before writing** — the draft talks about *their* actual work, in a plain human voice
  (no mail-merge filler, no AI tells).
- **Finds the right person's real email**, not a generic `info@` — checks the contact page and
  footer, infers the company's address format from a real address and applies it, and optionally
  verifies deliverability. One best address per senior person.
- **Nudges you to follow up** when a thread goes quiet (that's where most replies come from).
- **Never sends anything** — you get copy-paste-ready drafts and send from your own inbox. I
  don't trust any robot, this one included, to email strangers for me.
- Runs on a cheap model for **pennies a day**, not a monthly sales-SaaS seat.

## Make it yours

You don't edit code — you write one file, **`profile.yaml`**: what you sell, who's a good fit,
who to *exclude* (competitors), which industries to focus on, which giants to avoid. See
`profile.example.yaml` for a worked example.

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"       # package + the `prospectus-agent` command
cp .env.example .env                    # add your ANTHROPIC_API_KEY (and/or OPENAI_API_KEY)
cp profile.example.yaml profile.yaml    # describe your business + ideal customer
```

That's the whole setup (if `profile.yaml` is missing, the example is used). The install puts
`prospectus-agent` on your PATH and resolves its files relative to the project folder, so you can
run it from any directory — point `PROSPECTUS_AGENT_HOME` elsewhere to relocate them. Prompt
templates live in `src/prospectus_agent/prompts/`; edit only to change wording/tone.

**More than one business:** a profile named `acme` lives in `profile.acme.yaml` with its own
`acme.db`, `outbox/acme/`, and brief cache — fully isolated. Run `prospectus-agent --profile
acme`, or set `DEFAULT_PROFILE=acme` in `.env`. Each profile carries its own voice
(`capability_areas`, `voice_notes`, `credibility`, opener examples, `recent_innovations`), so the
engine stays business-agnostic.

## How it works

`prospectus-agent` runs the pipeline:

1. **Refresh profile** — fetches your website (cached weekly via `PROFILE_REFRESH_DAYS`) so
   drafts reflect what you do now.
2. **Discover** — up to `MAX_DISCOVERY_CALLS` web-search rounds for companies scoring ≥
   `FIT_SCORE_THRESHOLD`/10, rotating the industry angle and skipping anything already seen. A
   diversifier caps picks per sector (`MAX_PER_SECTOR`); good-but-capped companies wait in a
   backlog that future runs draft first.
3. **Research + draft** — reads the site (contact page + footer, where addresses live) and
   leadership, then builds **one best email per senior person**: a published one if found, else
   the domain's inferred format applied, else a `first.last@` guess. Generic `info@` is a
   fallback only; dead domains (no MX) are skipped; opt in per profile to verify addresses via
   [Verifalia](https://verifalia.com) (catch-all aware, fails open). The email is drafted in a
   human voice — no em dashes or AI clichés, subject led by your company name, no signature (your
   client adds it).
4. **Follow-ups** — flags `sent` companies with no reply after `FOLLOWUP_DAYS` (default 5) calendar days; two nudges max
   (a fuller first, weaving in a `recent_innovations` win, then a short final touch-base), then
   stops.
5. **Writes `outbox/<date>/`** — `new_prospects.{md,html}` + `followups.{md,html}`, each with its
   contact list and a copyable comma-separated `To:` line. The HTML links your company name so
   pasting into Gmail keeps the hyperlink; re-running the same day **appends** rather than
   overwrites.
6. Prints a digest and a token-usage line.

`prospectus-agent --refine` re-drafts **today's** existing drafts with the current prompt (no
re-discovery or research — cheap and fast), then regenerates the outbox; curated contacts are left
untouched. Every company it ever sees is stored, so none resurface.

**Two roles, your choice of model — and vendor.** A cheap **searcher** (discovery, research,
profile refresh, with `web_search`; default Anthropic `claude-haiku-4-5`) does the high-volume
work; a stronger **writer** (every email; default `claude-sonnet-4-6`) writes the short drafts.
Mix Anthropic and OpenAI freely in `.env` — both go through one vendor-neutral `llm.py` seam
(Messages / Responses API, structured output via strict tools).

## Config dials (`.env`)

`profile.yaml` is your business; `.env` is the machinery (gitignored):

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` | Key(s) for the vendor(s) you use — only those named in `SEARCH_VENDOR` / `WRITER_VENDOR`. |
| `DEFAULT_PROFILE` | Business to run with no `--profile` (loads `profile.<name>.yaml` + `<name>.db` + `outbox/<name>/`). |
| `SEARCH_VENDOR` / `SEARCH_MODEL` | Vendor (`anthropic`\|`openai`) + model for the **searcher**. Default `anthropic` / `claude-haiku-4-5`. |
| `WRITER_VENDOR` / `WRITER_MODEL` | Vendor + model for the **writer** (drafting). Default `anthropic` / `claude-sonnet-4-6`. |
| `DISCOVERY_MODEL` | Override the searcher model for the mechanical steps only; defaults to `SEARCH_MODEL`. |
| `FIT_SCORE_THRESHOLD`, `TARGET_COMPANY_COUNT`, `MAX_DISCOVERY_CALLS`, `FOLLOWUP_DAYS` | Pipeline tunables (`FOLLOWUP_DAYS` = calendar days before a follow-up is due, default 5). |
| `MAX_PER_SECTOR` | Max picks from one sector per day (diversifier; default 2). |
| `AVOID_SECTORS` | Comma-separated sector keys to exclude (kept as reversible backlog). Valid keys in `sectors.py`. |
| `MAX_COMPANY_SIZE` | Largest size to target: `startup`\|`small`\|`mid`\|`large`\|`enterprise` (default `mid`). |
| `MAX_PUBLIC_EMAILS` / `MAX_PEOPLE` / `GUESSES_PER_PERSON` | Contact-list size (≤3 people, **one** address each; inbox as fallback). Keep `GUESSES_PER_PERSON=1`. |
| `VERIFALIA_USERNAME` / `VERIFALIA_PASSWORD` | Optional [Verifalia](https://verifalia.com) HTTP-Basic creds for mailbox verification. Blank = off. Enable per business with `settings.verify_emails: true` in its `profile.<name>.yaml`. |
| `VERIFY_MAX_CANDIDATES` | Max address formats verified per person (default 2 — keeps a 25/day free tier in budget). |
| `DISCOVERY_EFFORT` / `DRAFTING_EFFORT` / `SEARCH_CONTEXT_SIZE` | OpenAI backend only; ignored on Anthropic. |
| `DISCOVERY_MAX_TOKENS` / `DRAFT_MAX_TOKENS` / `PROFILE_MAX_TOKENS` | Per-step output-token caps. |

## Daily use

The CLI is **scope × action**. Scope: which business (`--profile`) and which drafts — *new
prospects* by default, *follow-ups* with `--followup`. Action: `--refine` (re-draft) or `--sent`
(record sends); no action = discover + draft. `--refine` and `--sent` can't combine.

```bash
prospectus-agent                    # NEW PROSPECTS: discover + draft
prospectus-agent --refine           # re-draft today's with the latest prompt
prospectus-agent --sent             # record you sent them (starts the follow-up clock)

prospectus-agent --followup           # FOLLOW-UPS: draft one for anyone past the threshold
prospectus-agent --followup --refine  # re-draft them with the latest voice
prospectus-agent --followup --sent    # record you sent them (resets the clock)

prospectus-agent --profile acme       # any of the above, for a different business
prospectus-agent --runall             # daily pipeline for EVERY profile (add actions to fan out)

prospectus-status drafts            # list drafts ready to review
prospectus-status show DOMAIN       # full draft + contacts
prospectus-status mark DOMAIN sent  # (or: replied / not_interested) — drives the follow-up clock
```

(Activate the venv, or prefix with `.venv/bin/`.) Status values: `new`, `drafted`, `sent`,
`followed_up`, `no_reply` (both follow-ups sent, done), `replied`, `not_interested`, `not_a_fit`.
Reply tracking is fully manual — the agent never reads your inbox.

## A few honest notes

- **Guessed emails are guesses.** Unverified ones may bounce; verify (or turn on Verifalia) for
  anyone important.
- **Garbage in, garbage out.** Lead quality tracks how well you describe your ideal customer in
  `profile.yaml`. Spend ten minutes on it.
- **Watch the cost line.** The defaults split the work (cheap searcher, stronger writer); the
  token-usage summary each run is there so you notice early.
- **Read before you send.** It's good, not infallible — skim each draft. That's the whole point
  of "it never sends."
- **Single-user and local** (a SQLite file per business, your own inbox). A hosted multi-tenant
  version is a someday-maybe.

## The code

Small and deliberately boring. Engine code lives in `src/prospectus_agent/` and knows nothing
about any business — everything company-specific is in `profile.yaml` and `prompts/`.

| Area | Files |
|---|---|
| CLI / entrypoints | `cli.py`, `daily_run.py`, `refine.py`, `mark_sent.py`, `followup_run.py`, `status.py` |
| Config / setup | `paths.py` (home + `.env`), `config.py` (`.env` + per-profile paths + client factory), `runner.py` (session prologue + DB backup), `agent_profile.py` (loads `profile.*.yaml`) |
| Pipeline | `discovery.py` (+ `sectors.py` diversifier), `research.py` (research + initial draft), `drafting.py` / `followups.py` (follow-ups), `redraft.py` (`--refine`), `on_profile.py` (website brief) |
| Contacts / email | `contacts.py` (address pattern inference + guessing), `verify.py` (MX + Verifalia), `outbox.py` (md/html digests) |
| Data / model | `db.py` (SQLite), `llm.py` (vendor-neutral seam), `prompts/`, `schemas.py` |

## Tests

```bash
.venv/bin/pip install -e ".[dev]"
.venv/bin/python -m pytest
```

Runs **offline** — both vendor clients are faked, so no key and no spend. Covers the database,
address inference/verification, follow-up timing, the discovery loop (competitor + over-size
filtering), research/drafting, the LLM helpers, and the strict tool schemas.

## Roadmap / known gaps

- Follow-up timing is plain calendar days (`FOLLOWUP_DAYS`); no working-day/holiday calendar.
- Address verification is opt-in; unverified guesses can still bounce.
- Single-tenant and local; a configurable hosted version may come later.

## Contribute

Contributions very welcome — this is meant to be shared. Lots of businesses face the same
prospecting struggle; let's help each other.
