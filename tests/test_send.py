"""Recipient selection (To/Bcc) + message building for auto-send."""
from __future__ import annotations

from prospectus_agent import send


def _c(email, confidence, name=""):
    return {"email": email, "email_confidence": confidence, "name": name, "role": ""}


def test_confirmed_personal_drops_guesses():
    to, bcc = send.select_recipients([
        _c("jane.doe@acme.com", "verified", "Jane Doe"),
        _c("bob.lee@acme.com", "guessed", "Bob Lee"),
        _c("info@acme.com", "public", ""),
    ])
    # verified personal + public inbox in To; guesses dropped (we have a confirmed person)
    assert set(to) == {"jane.doe@acme.com", "info@acme.com"}
    assert bcc == []


def test_no_confirmed_personal_bccs_guesses():
    to, bcc = send.select_recipients([
        _c("jane.doe@acme.com", "inferred", "Jane Doe"),
        _c("bob.lee@acme.com", "guessed", "Bob Lee"),
    ])
    assert to == ["jane.doe@acme.com"]      # inferred goes To
    assert bcc == ["bob.lee@acme.com"]      # guessed goes Bcc (no confirmed personal)


def test_never_info_alone_promotes_a_person():
    to, bcc = send.select_recipients([
        _c("info@acme.com", "public", ""),
        _c("jane.doe@acme.com", "guessed", "Jane Doe"),
        _c("bob.lee@acme.com", "guessed", "Bob Lee"),
    ])
    # info@ is public (To), but no confident person -> promote the best guessed person.
    assert set(to) == {"info@acme.com", "jane.doe@acme.com"}
    assert bcc == ["bob.lee@acme.com"]


def test_only_generic_inbox_still_sends():
    to, bcc = send.select_recipients([_c("info@acme.com", "guessed", "")])
    assert to == ["info@acme.com"]
    assert bcc == []


def test_cap_limits_total_and_keeps_personal():
    contacts = [_c(f"p{i}@acme.com", "inferred", f"P{i}") for i in range(7)]
    to, bcc = send.select_recipients(contacts, max_recipients=3)
    assert len(to) + len(bcc) <= 3
    assert to  # still has people


def test_dedup_same_email():
    to, bcc = send.select_recipients([
        _c("jane@acme.com", "inferred", "Jane"),
        _c("jane@acme.com", "guessed", "Jane"),
    ])
    assert to == ["jane@acme.com"]
    assert bcc == []


def test_build_message_initial_has_message_id_and_recipients():
    row = {"subject": "Open Numerics: simulation", "body": "Hi there,\nWe're Open Numerics."}
    msg, mid = send.build_message(row, ["jane@acme.com"], ["bob@acme.com"])
    assert msg["To"] == "jane@acme.com"
    assert msg["Bcc"] == "bob@acme.com"
    assert msg["Subject"] == "Open Numerics: simulation"
    assert msg["Message-ID"] == mid and mid.endswith("@opennumerics.com>")
    assert "In-Reply-To" not in msg


def test_build_message_followup_threads():
    row = {"subject": "quick note", "body": "Following up."}
    refs = {"rfc_message_id": "<orig@opennumerics.com>", "subject": "Open Numerics: simulation"}
    msg, _ = send.build_message(row, ["jane@acme.com"], [], thread_refs=refs)
    assert msg["In-Reply-To"] == "<orig@opennumerics.com>"
    assert msg["References"] == "<orig@opennumerics.com>"
    assert msg["Subject"] == "Re: Open Numerics: simulation"
