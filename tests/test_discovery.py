"""Tests for the discovery loop with run_with_submit stubbed.

Covers: qualification by score, storing all-seen, dedup (within run and vs DB),
exclusion of service-providers/competitors, stop-early on target, and
accumulation across rounds.
"""
from __future__ import annotations

import config
import db
import discovery


def _cand(name, domain, score, *, provider=False, why="reason"):
    return {
        "name": name,
        "domain": domain,
        "hq_location": "Denver, CO",
        "industry": "Aero",
        "why_fit": why,
        "suggested_applications": ["GPU-accelerate CFD"],
        "fit_score": score,
        "is_service_provider": provider,
        "source_urls": ["http://x"],
    }


def _stub_rounds(monkeypatch, rounds):
    """Make discovery.run_with_submit return one canned payload per round."""
    calls = {"n": 0}
    it = iter(rounds)

    def fake(client, **kwargs):
        calls["n"] += 1
        try:
            payload = next(it)
        except StopIteration:
            return None
        return payload  # dict like {"candidates": [...]} or None

    monkeypatch.setattr(discovery, "run_with_submit", fake)
    return calls


def test_qualifies_and_stores_everything(conn, monkeypatch):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", 7)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", 5)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", 1)

    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("Good Co", "good.com", 9),
            _cand("Weak Co", "weak.com", 4),                 # below threshold
            _cand("Rival Sim", "rival.com", 10, provider=True),  # competitor
        ]},
    ])

    winners = discovery.discover(client=None, conn=conn, on_profile="ON")

    # Only the genuine end-user client qualifies.
    assert [c.domain for _, c in winners] == ["good.com"]
    # But all three are stored so none resurface.
    assert db.get_seen_domains(conn) == {"good.com", "weak.com", "rival.com"}
    assert db.get_company_by_domain(conn, "good.com")["status"] == "new"
    assert db.get_company_by_domain(conn, "weak.com")["status"] == "not_a_fit"
    assert db.get_company_by_domain(conn, "rival.com")["status"] == "not_a_fit"


def test_service_provider_excluded_even_with_top_score(conn, monkeypatch):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", 7)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", 5)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", 1)
    _stub_rounds(monkeypatch, [
        {"candidates": [_cand("CFD Vendor", "cfdvendor.com", 10, provider=True)]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert winners == []
    assert db.get_company_by_domain(conn, "cfdvendor.com")["status"] == "not_a_fit"


def test_dedup_against_existing_db(conn, monkeypatch):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", 7)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", 5)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", 1)
    # Pre-existing company already contacted.
    db.upsert_company(conn, name="Existing", domain="existing.com", hq_location="",
                      industry="", fit_score=9, why_fit="", suggested_applications=[],
                      source_urls=[], status="sent")

    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("Existing again", "https://www.existing.com/x", 9),  # dup
            _cand("Fresh", "fresh.com", 8),
        ]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert [c.domain for _, c in winners] == ["fresh.com"]
    # Existing kept its 'sent' status, not overwritten.
    assert db.get_company_by_domain(conn, "existing.com")["status"] == "sent"


def test_stops_early_when_target_reached(conn, monkeypatch):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", 7)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", 2)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", 3)
    calls = _stub_rounds(monkeypatch, [
        {"candidates": [_cand("A", "a.com", 9), _cand("B", "b.com", 9)]},
        {"candidates": [_cand("C", "c.com", 9)]},  # should never be requested
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert len(winners) == 2
    assert calls["n"] == 1  # stopped after first round hit the target


def test_accumulates_across_rounds(conn, monkeypatch):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", 7)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", 3)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", 3)
    calls = _stub_rounds(monkeypatch, [
        {"candidates": [_cand("A", "a.com", 9), _cand("Weak", "weak.com", 2)]},
        None,  # a dry round
        {"candidates": [_cand("B", "b.com", 8), _cand("C", "c.com", 7)]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert {c.domain for _, c in winners} == {"a.com", "b.com", "c.com"}
    assert calls["n"] == 3


def test_company_ids_are_real(conn, monkeypatch):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", 7)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", 5)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", 1)
    _stub_rounds(monkeypatch, [{"candidates": [_cand("A", "a.com", 9)]}])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    cid, cand = winners[0]
    assert db.get_company_by_domain(conn, "a.com")["id"] == cid
