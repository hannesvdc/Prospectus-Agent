"""Auto-send layer: recipient selection, message building, and the Gmail send seam.

Everything here works in DRY-RUN with no network — compute recipients + threading and
report what WOULD send. The actual Gmail API call (`send_via_gmail`) is a stub until the
OAuth increment (see docs/auto-send-design.md, task 7).
"""
from __future__ import annotations

import base64
import sqlite3
from email.message import EmailMessage
from email.utils import make_msgid

from prospectus_agent import config
from prospectus_agent import outbox

# gmail.send to deliver; gmail.settings.basic to read the signature/footer. Both are
# requested at consent time (see prospectus_agent.gmail_auth).
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.settings.basic",
]

# Confidence ordering for To/Bcc placement, promotion, and the recipient cap.
_RANK = {"verified": 4, "public": 3, "inferred": 2, "guessed": 1}
_CONFIRMED = {"public", "verified"}          # a real/known address
_TO_CONFIDENCES = {"public", "verified", "inferred"}


def _rank(contact) -> int:
    return _RANK.get(contact["email_confidence"], 0)


def _is_personal(contact) -> bool:
    return bool((contact["name"] or "").strip())


def select_recipients(
    contacts: list[sqlite3.Row], *, max_recipients: int = 5
) -> tuple[list[str], list[str]]:
    """Return (to, bcc) email lists per the delivery policy (§6 of the design doc):

    - **To:** personal public/verified/inferred addresses + a public generic inbox.
    - **Bcc:** guessed PERSONAL addresses, only when there's no verified/public personal.
    - **Always reach a person:** if To has no personal address (only a generic inbox),
      promote the best personal address (inferred, else guessed) into To.
    - **Cap** total at `max_recipients`, highest-confidence first, but never drop the
      last personal recipient. Emails are de-duplicated (To wins over Bcc).
    """
    personal = [c for c in contacts if _is_personal(c)]
    generic = [c for c in contacts if not _is_personal(c)]
    has_confirmed_personal = any(c["email_confidence"] in _CONFIRMED for c in personal)

    to = [c for c in personal if c["email_confidence"] in _TO_CONFIDENCES]
    to += [c for c in generic if c["email_confidence"] == "public"]
    bcc = ([c for c in personal if c["email_confidence"] == "guessed"]
           if not has_confirmed_personal else [])

    # Always reach a real person.
    if not any(_is_personal(c) for c in to):
        best_personal = max(personal, key=_rank, default=None)
        if best_personal is not None:
            if best_personal in bcc:
                bcc.remove(best_personal)
            to.append(best_personal)
        elif not to and generic:            # no people at all -> best generic inbox
            to.append(max(generic, key=_rank))

    to, bcc = _cap(to, bcc, max_recipients)
    return ([c["email"] for c in to], [c["email"] for c in bcc])


def _cap(to: list[sqlite3.Row], bcc: list[sqlite3.Row],
         max_recipients: int) -> tuple[list[sqlite3.Row], list[sqlite3.Row]]:
    """De-dup across To/Bcc (To wins) and enforce the recipient cap: drop lowest-
    confidence first (Bcc before To), but always keep at least one personal in To."""
    seen: set[str] = set()

    def dedup(rows: list[sqlite3.Row]) -> list[sqlite3.Row]:
        out = []
        for c in sorted(rows, key=_rank, reverse=True):
            e = (c["email"] or "").strip().lower()
            if e and e not in seen:
                seen.add(e)
                out.append(c)
        return out

    to = dedup(to)
    bcc = dedup(bcc)

    room = max_recipients - len(to)
    if room >= 0:
        return to, bcc[:room]

    # More confident To's than the cap: keep the top `max_recipients`, but guarantee a
    # personal survives.
    kept = to[:max_recipients]
    if any(_is_personal(c) for c in to) and not any(_is_personal(c) for c in kept):
        kept[-1] = next(c for c in to if _is_personal(c))
    return kept, []


def generate_message_id() -> str:
    """A self-owned RFC-2822 Message-ID on the sender's domain, so follow-ups can thread
    (via In-Reply-To/References) without ever reading the inbox."""
    domain = config.AUTOSEND_FROM.split("@")[-1] or "localhost"
    return make_msgid(domain=domain)


def build_message(email_row: sqlite3.Row, to: list[str], bcc: list[str], *,
                  thread_refs: sqlite3.Row | None = None,
                  footer_html: str = "") -> tuple[EmailMessage, str]:
    """Build the outbound EmailMessage. Returns (message, message_id). For a follow-up,
    pass `thread_refs` (from db.get_thread_refs) to thread it: reuse the original subject
    as `Re: …` and set In-Reply-To/References to the original's Message-ID. `footer_html`
    (the sender's fetched Gmail signature) is appended to the HTML part when provided."""
    msg = EmailMessage()
    message_id = generate_message_id()
    msg["Message-ID"] = message_id
    msg["From"] = config.AUTOSEND_FROM
    msg["To"] = ", ".join(to)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)

    subject = email_row["subject"] or ""
    if thread_refs and thread_refs["rfc_message_id"]:
        if subject and not subject.lower().startswith("re:"):
            subject = f"Re: {thread_refs['subject'] or subject}"
        msg["In-Reply-To"] = thread_refs["rfc_message_id"]
        msg["References"] = thread_refs["rfc_message_id"]
    msg["Subject"] = subject

    body = email_row["body"] or ""
    msg.set_content(body)                                    # plain-text part
    html = outbox._linkify_body(body)
    if footer_html:
        html = f"{html}<br><br>{footer_html}"
    msg.add_alternative(html, subtype="html")                # rich part
    return msg, message_id


def gmail_service():
    """Build an authenticated Gmail API client from the OAuth refresh token in config.
    Lazy-imports google-* so the package works (and tests run) without them installed —
    dry-run needs none. Raises RuntimeError with clear guidance if creds/libs are missing."""
    if not config.gmail_configured():
        raise RuntimeError(
            "Gmail credentials missing — set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET / "
            "GMAIL_REFRESH_TOKEN in .env (run `python -m prospectus_agent.gmail_auth` once)."
        )
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as e:
        raise RuntimeError("Gmail libraries not installed — run `pip install '.[gmail]'`.") from e
    creds = Credentials(
        None,
        refresh_token=config.GMAIL_REFRESH_TOKEN,
        client_id=config.GMAIL_CLIENT_ID,
        client_secret=config.GMAIL_CLIENT_SECRET,
        token_uri="https://oauth2.googleapis.com/token",
        scopes=GMAIL_SCOPES,
    )
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def send_via_gmail(message: EmailMessage, *, thread_id: str | None = None,
                   service=None) -> dict:
    """Send an EmailMessage via the Gmail API as the authenticated user (lands in Sent).
    Returns the API response (with 'id' and 'threadId'). Pass a shared `service` and,
    for a follow-up, the original `thread_id` to keep it in the same conversation."""
    svc = service or gmail_service()
    body = {"raw": base64.urlsafe_b64encode(message.as_bytes()).decode()}
    if thread_id:
        body["threadId"] = thread_id
    return svc.users().messages().send(userId="me", body=body).execute()


def fetch_signature(service=None) -> str:
    """The sender's Gmail signature as HTML (image URL included), or '' if none/error.
    Needs the gmail.settings.basic scope; best-effort — never blocks a send."""
    try:
        svc = service or gmail_service()
        resp = (svc.users().settings().sendAs()
                .get(userId="me", sendAsEmail=config.AUTOSEND_FROM).execute())
        return resp.get("signature", "") or ""
    except Exception:
        return ""
