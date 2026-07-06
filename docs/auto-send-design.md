# Design: autonomous sending (Gmail / Google Workspace)

**Status:** draft for review · **Scope:** send initial + follow-up emails automatically
from `hannesv@opennumerics.com` (both ON and RS), instead of copy-paste.

This is the "earn the send button" step. The whole tool has, on purpose, never sent
anything — you review drafts and send by hand. This adds *optional* automated sending,
gated hard behind guardrails, and rolled out ON-first after the soak week.

---

## 1. Goal & non-goals

**Goal:** on a run, actually deliver the drafts the agent would otherwise hand you —
initial outreach and due follow-ups — as `hannesv@opennumerics.com`, with follow-ups
threaded under the original email, appearing in your Sent folder like normal mail.

**Non-goals (v1):**
- Reading replies / detecting bounces (stays manual — send-only scope).
- Per-recipient body personalization (still one draft per company, To/Bcc'd to its contacts — see §6).
- RS auto-send at launch (ON-first; RS enabled once its quality soak passes).

---

## 2. Sending identity

Both profiles send from **`hannesv@opennumerics.com`** — a Google Workspace inbox Hannes
administers. RS is an Open Numerics LLC product, so it reuses the ON inbox (one inbox,
one Workspace config). Never Campbell.

Because it's an **admin-controlled Workspace**, the restricted-scope friction that
plagues personal Gmail (7-day token expiry, mandatory verification) does **not** apply.

---

## 3. Transport & auth — recommendation

Use the **Gmail API** (`users.messages.send`). Two viable auth models; both are clean
on Workspace and need no Google verification:

| | Path A — OAuth "Internal" app | Path B — Service account + domain-wide delegation |
|---|---|---|
| Setup | One-time browser consent as yourself | Admin authorizes a service-account client ID for `gmail.send` |
| Unattended | Yes (refresh token persists — Internal apps are exempt from the 7-day expiry) | Yes, fully headless — no browser, no token refresh ever |
| Best for | Getting started; agent run interactively | A scheduled/headless daily agent |
| Complexity | Low | Medium (Admin console step) |

**DECIDED: Path A** (Internal OAuth) for now — Hannes runs it manually / via a local
script, so a one-time browser consent is fine and the token doesn't expire. Revisit
Path B (service-account DWD) if it ever moves to a headless schedule. Scope is send-only
(`https://www.googleapis.com/auth/gmail.send`) — it cannot read the inbox, which keeps
the trust story tight.

*(SMTP + app password is a fallback, but Workspace policy may disable app passwords and
the API is clean here, so we skip it.)*

---

## 4. What "send" does (mechanics)

Per email to send:
1. Build a MIME message (`email.message.EmailMessage`): From = `hannesv@opennumerics.com`,
   To = the chosen recipient (§6), Subject, Body. **Self-generate a `Message-ID`
   header** so we own it (lets us thread follow-ups without a read scope).
2. For a **follow-up**, also set `In-Reply-To` + `References` to the initial email's
   stored `Message-ID`, and reuse the **original subject** (as `Re: …`).
3. base64url-encode → `messages.send(userId="me", body={"raw": …, "threadId": <initial's threadId, for follow-ups>})`.
4. From the response, capture and store `id` (gmail message id) and `threadId`.

- **Sent folder:** automatic — the API applies the `SENT` label, so it shows in Gmail
  Sent normally.
- **Threading:** follow-ups land in the same conversation because we set `threadId` +
  `In-Reply-To`/`References` + matching subject (all three are required by Gmail).

---

## 5. Data model changes

Add to the `emails` table (or a small `sends` table):
- `gmail_message_id` — returned by the API.
- `gmail_thread_id` — returned by the API; the follow-up sets this to thread.
- `rfc_message_id` — the `Message-ID` header we generated (for `References`).
- `sent_at` — actual send timestamp.

Sending an initial email records its thread/message ids so the eventual follow-up can
thread off them. Sending advances company status exactly like the current manual `--sent`
does (`drafted → sent`, follow-up clock starts; follow-up sends advance
`sent → followed_up → no_reply`), so the existing follow-up timing logic is reused
unchanged.

---

## 6. Recipient policy — DECIDED

One email per company, capped at **5 recipients**, and **always aimed at a real person —
never *only* a generic `info@` inbox.**

Split contacts into **personal** (a named individual) vs **generic** (info@/contact@, no
name), then:
- **To:** confident addresses — personal `public` / `verified` / `inferred`, plus a
  `public` generic inbox if present.
- **Bcc:** `guessed` **personal** addresses — included **whenever there is no
  verified/public *personal* address** (we haven't confirmed we're reaching a real
  human). A generic `info@` does **not** count as reaching a person, so it does *not*
  suppress these guesses. If a verified/public personal address exists, drop the guesses.
- **Always reach a person:** if the only confident contact is a generic inbox, promote
  the best personal address (inferred, else guessed) into **To** — we never send to
  `info@` alone.
- **Cap: 5** (To + Bcc), highest-confidence first (`AUTOSEND_MAX_RECIPIENTS`, default 5),
  but never drop the guaranteed personal recipient to satisfy the cap.
- Skip only if the company has zero contacts (shouldn't happen — never-empty fallback).

Gentle on deliverability: guesses ride along only when no personal address is confirmed,
and never more than 5 addresses total.

---

## 7. CLI integration — DECIDED: `--deliver`

`--deliver` it is (kept distinct from the existing `--sent` = "I sent by hand, record
it", which stays for the manual workflow). `--deliver` actually sends *and* records.

- `prospectus-agent --deliver` — send today's unsent initial drafts (per §6), record them.
- `prospectus-agent --followup --deliver` — send due follow-ups, threaded under the original.
- `prospectus-agent --runall --deliver` — fan delivery across every profile (forwards like the other actions).
- **Defaults to dry-run**; add `--live` to actually send. Guardrails in §8 always apply.
- **Profile gate:** ON delivers; RS is gated off until its quality soak passes
  (`--deliver` on RS just dry-run-logs "skipped: RS not enabled for delivery"), so the
  all-profiles script below is safe to run now — RS simply won't send.

### The daily driver (Hannes's workflow)

A one-file wrapper — run it manually now, cron/launchd later:

```bash
#!/usr/bin/env bash
# run-daily.sh — discover, draft, and send for every profile.
set -euo pipefail
prospectus-agent --runall                          # 1. discover + draft new prospects
prospectus-agent --runall --deliver --live         # 2. send new-prospect drafts (RS gated → skipped)
prospectus-agent --runall --followup --deliver --live   # 3. send due follow-ups, threaded
```

Drop `--live` (or run once without it) to see the full dry-run first. Because auth is
Path A (interactive OAuth), the first `--live` run may open a browser for the one-time
consent; after that the cached token runs it unattended.

---

## 8. Guardrails (the whole point)

- **Dry-run by default.** `--deliver` logs "WOULD send to X as hannesv@opennumerics.com,
  threaded under Y" and sends nothing. Real sending needs an explicit `--live`.
- **Daily cap.** `AUTOSEND_DAILY_MAX` (e.g. 10) — hard stop per run/day.
- **Confidence-aware recipients (§6).** Guesses ride along only when no verified/public
  *personal* address exists; capped at 5; never a generic inbox alone.
- **No double-send.** A `sent_at`/status check ensures nothing is delivered twice.
- **Pacing.** Space sends out (a few seconds apart) so a burst doesn't trip spam heuristics.
- **Profile gate.** ON-only initially.
- **Kill switch.** A single env/flag to disable all sending.
- **Audit log.** Every send (and every skip + reason) written to a log the digest surfaces.

---

## 9. Deliverability & spam-filter risk (the main concern)

How the design addresses each spam signal:
- **Email authentication — verify DKIM is ON (highest-impact item).** Workspace gives
  SPF automatically, but **DKIM must be explicitly enabled** in the Admin console (Apps →
  Google Workspace → Gmail → Authenticate email) — it's off by default on many domains.
  Confirm DKIM is on for `opennumerics.com` and that a **DMARC** record exists (at least
  `p=none`). Sending via the API *as you* means the mail is DKIM-signed with the domain
  key → aligned and trusted. Do this before any live send.
- **Bounce rate (the biggest reputation killer).** Invalid addresses that bounce tank
  your domain fast. Already mitigated: MX gate drops dead domains, Verifalia verifies,
  and §6 only sends guesses when no confirmed personal address exists, capped at 5. Watch
  the bounce rate; if it climbs, tighten what earns a guessed Bcc.
- **Volume & velocity.** ~5–10/day is trivial and non-spiky. Pace sends a few seconds
  apart, and **warm up** — start with a tiny daily cap and raise it slowly so a new
  sending pattern doesn't look like a sudden blast.
- **Content.** Plain, human voice, no marketing clichés or spam-trigger words (already
  tuned), one link. Keep the signature image small — image-heavy/image-only mail scores
  worse.
- **Complaints/relevance.** The best long-term protection is recipients *not* marking it
  spam — which comes from tight targeting (the fit scoring) and the two-follow-up cap
  (no nagging).
- **Monitor.** Set up **Google Postmaster Tools** for `opennumerics.com` (free; confirms
  SPF/DKIM/DMARC pass, and gives spam-rate + domain-reputation *if* volume grows — at
  10–40/day it'll mostly show "not enough data"). So at low volume the real early-warning
  system is **(a) watching bounce-backs in the inbox** (the agent's audit log says who it
  emailed — a rising bounce rate is the #1 signal) and **(b) a weekly seed test** (send to
  your own Gmail/Outlook accounts, check inbox vs. spam).
- **Primary-domain risk — DECIDED:** cold outreach runs from `opennumerics.com`, the real
  business domain, accepting the (low, non-zero) reputation risk rather than setting up a
  separate outreach domain. At 10–40/day of targeted mail with low bounces it's
  defensible; revisit a separate domain only if the spam/bounce signals turn bad or volume
  climbs well past 100/day.
- **CAN-SPAM / GDPR:** deferred (no footer in v1; the "no signature" drafting rule
  stays). A genuine opt-out line also lowers spam complaints, so worth adding with compliance.
- No reply/bounce detection in v1 — watch the inbox manually.

---

## 9b. Footer / signature (important)

Hannes has a Gmail **signature** (image + text) set in Gmail Settings. Gmail inserts it
only in the **compose UI** — it is **NOT** applied to mail sent via the API/SMTP. So:
- **Manual (copy-paste):** signature applied for free by Gmail. Drafts stay
  signature-free on purpose (the `SIGNOFF_RULE`).
- **Auto-send (`--deliver`):** the signature is **not** attached automatically — we must
  append it ourselves, or emails go out footer-less.

**DECIDED — Option 1:** fetch the signature HTML once via `users.settings.sendAs.get`
(adds the read scope `gmail.settings.basic` — fine on the admin Workspace), cache it, and
append it to every auto-sent email. This pulls the hosted image URL along, so the image
renders, and re-fetching keeps it in sync.

Consequences:
- Auto-sent mail must be **HTML** (we already build an HTML body for the outbox) so the
  footer's image + formatting render.
- The footer is appended **at send time** (`send.py`), not baked into the stored draft —
  so the copy-paste flow stays signature-free and the `SIGNOFF_RULE` stays correct for
  both paths.
- Fallback if we'd rather not add the read scope: paste the signature HTML into a profile
  field (`email_footer_html`); downside is manual extraction (incl. the image URL) and
  keeping it in sync.

---

## 10. Rollout

1. **Dry-run scaffold** — `send.py` + schema columns + `--deliver` that only logs. Verify
   recipient selection, threading data, and status transitions on real drafts, no sends.
2. **ON live, first week** — `--deliver --live` at `AUTOSEND_DAILY_MAX=10` (validates the
   *automation*, not the domain — it's already warm). Watch Sent, threading, and
   **especially bounce rate** + Postmaster.
3. **Ramp** — raise the cap toward **40** over that first week; if bounces/complaints stay
   low, up to **100**. Staying on `opennumerics.com` (§9); revisit only if signals sour.
4. **RS** — flip the profile gate on once its quality soak passes.

(Cap counts *company-emails* — one send per company, To/Bcc'd to its contacts — not
individual recipients.)

---

## 11. Decisions (resolved 2026-07-06)

1. **Recipient policy:** one email/company — **To = public/verified/inferred**; **Bcc =
   guessed *personal* addresses, only when no verified/public personal address exists**;
   always reach a real person (never `info@` alone); **≤5 recipients total** (§6).
2. **CLI verb:** `--deliver` (dry-run default, `--live` to send).
3. **Auth:** Path A — Internal OAuth, for now.
4. **Compliance footer:** deferred; none in v1.
5. **Follow-ups:** thread under the original (reuse subject as `Re:`). Confirmed.
6. **Runtime:** manual / a local bash wrapper (§7) for now; headless later → revisit Path B.

### Still to nail down while building
- `Message-ID` domain/format for self-generated ids (use `@opennumerics.com`).
- **Token storage — DECIDED:** keep only `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`,
  `GMAIL_REFRESH_TOKEN` in `.env`; build `Credentials` and refresh the short-lived access
  token **in memory** each run (never rewritten — the refresh token is stable on an
  Internal Workspace app). A one-time `InstalledAppFlow` consent obtains the refresh
  token, pasted into `.env` once. (Don't store the whole mutable `token.json` in `.env`.)
- `AUTOSEND_DAILY_MAX`: start **10**, ramp to **40** over week 1, then **100** if clean
  (revisit separate domain before 100). `AUTOSEND_MAX_RECIPIENTS`: **5**.
- Self-generated `Message-ID` via stdlib `email.utils.make_msgid(domain="opennumerics.com")`.

### Deferred (post-v1 TODO)
- **Set up Google Postmaster Tools** for `opennumerics.com` (deferred — sparse at current
  volume; do it when volume grows or if deliverability looks shaky).
- CAN-SPAM/GDPR compliance footer.
- Service-account domain-wide delegation (Path B) if it ever runs headless.
