"""Tests for the free MX/deliverability gate (no network — _dig is stubbed)."""
from __future__ import annotations

from prospectus_agent import verify


def _reset():
    verify._cache.clear()


def test_has_mx_is_deliverable(monkeypatch):
    _reset()
    monkeypatch.setattr(verify, "_dig", lambda qt, d: ["10 mail.acme.com."] if qt == "MX" else [])
    assert verify.domain_deliverable("acme.com") is True


def test_no_mx_but_a_record_is_deliverable(monkeypatch):
    _reset()
    monkeypatch.setattr(verify, "_dig", lambda qt, d: [] if qt == "MX" else ["1.2.3.4"])
    assert verify.domain_deliverable("acme.com") is True


def test_no_mx_no_a_is_not_deliverable(monkeypatch):
    _reset()
    monkeypatch.setattr(verify, "_dig", lambda qt, d: [])
    assert verify.domain_deliverable("dead-domain.com") is False


def test_lookup_unavailable_fails_open(monkeypatch):
    _reset()
    monkeypatch.setattr(verify, "_dig", lambda qt, d: None)  # dig missing/errored
    assert verify.domain_deliverable("acme.com") is True


def test_empty_domain_is_not_deliverable():
    _reset()
    assert verify.domain_deliverable("") is False


def test_url_and_scheme_are_stripped(monkeypatch):
    _reset()
    seen = {}
    def fake(qt, d):
        seen["d"] = d
        return ["10 mx"] if qt == "MX" else []
    monkeypatch.setattr(verify, "_dig", fake)
    assert verify.domain_deliverable("https://Acme.com/contact") is True
    assert seen["d"] == "acme.com"


# --- Verifalia mailbox verification (HTTP stubbed — no network) ---

from prospectus_agent import config  # noqa: E402


def _creds(monkeypatch):
    monkeypatch.setattr(config, "VERIFALIA_USERNAME", "user")
    monkeypatch.setattr(config, "VERIFALIA_PASSWORD", "pass")
    verify._email_cache.clear()


def _job(classification):
    return {"overview": {"status": "Completed"},
            "entries": {"data": [{"classification": classification}]}}


def test_verify_email_maps_classifications(monkeypatch):
    _creds(monkeypatch)
    cases = {"Deliverable": "valid", "Undeliverable": "invalid",
             "Risky": "risky", "Unknown": "unknown"}
    for cls, expected in cases.items():
        verify._email_cache.clear()
        monkeypatch.setattr(verify, "_verifalia", lambda m, p, body=None, c=cls: (200, _job(c)))
        assert verify.verify_email("a@acme.com") == expected


def test_verify_email_no_credentials_is_unknown(monkeypatch):
    monkeypatch.setattr(config, "VERIFALIA_USERNAME", "")
    monkeypatch.setattr(config, "VERIFALIA_PASSWORD", "")
    verify._email_cache.clear()
    assert verify.verification_available() is False
    assert verify.verify_email("a@acme.com") == "unknown"


def test_verify_email_errors_fail_open(monkeypatch):
    _creds(monkeypatch)
    def boom(*a, **k):
        raise RuntimeError("HTTP 402 out of credits")
    monkeypatch.setattr(verify, "_verifalia", boom)
    assert verify.verify_email("a@acme.com") == "unknown"


def test_verify_email_polls_until_completed(monkeypatch):
    _creds(monkeypatch)
    monkeypatch.setattr(verify.time, "sleep", lambda *_: None)
    calls = {"n": 0}
    def fake(method, path, body=None):
        calls["n"] += 1
        if method == "POST":
            return 202, {"overview": {"id": "job-1", "status": "InProgress"}}
        return 200, _job("Deliverable")     # GET poll -> done
    monkeypatch.setattr(verify, "_verifalia", fake)
    assert verify.verify_email("a@acme.com") == "valid"
    assert calls["n"] >= 2                    # submitted, then polled
