"""Tests for the discovery loop with run_with_submit stubbed.

Covers: qualification by score, storing all-seen, dedup (within run and vs DB),
exclusion of service-providers/competitors, the per-sector diversifier cap,
backlog seeding, stop-early on target, and accumulation across rounds.
"""
from __future__ import annotations

from prospectus_agent import config
from prospectus_agent import db
from prospectus_agent import discovery


def _cand(name, domain, score, *, provider=False, why="reason", industry="Aerospace", size="mid"):
    return {
        "name": name,
        "domain": domain,
        "hq_location": "Denver, CO",
        "industry": industry,
        "why_fit": why,
        "suggested_applications": ["GPU-accelerate CFD"],
        "fit_score": score,
        "company_size": size,
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
            return next(it)
        except StopIteration:
            return None

    monkeypatch.setattr(discovery, "run_searcher", fake)
    return calls


def _seed_defaults(monkeypatch, *, threshold=7, target=5, per_sector=2, calls=1):
    monkeypatch.setattr(config, "FIT_SCORE_THRESHOLD", threshold)
    monkeypatch.setattr(config, "TARGET_COMPANY_COUNT", target)
    monkeypatch.setattr(config, "MAX_PER_SECTOR", per_sector)
    monkeypatch.setattr(config, "MAX_DISCOVERY_CALLS", calls)
    # Isolate tests from whatever the local .env happens to set.
    monkeypatch.setattr(config, "AVOID_SECTORS", [])
    monkeypatch.setattr(config, "MAX_COMPANY_SIZE", "enterprise")  # allow all sizes


def test_qualifies_and_stores_everything(conn, monkeypatch):
    _seed_defaults(monkeypatch)
    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("Good Co", "good.com", 9),
            _cand("Weak Co", "weak.com", 4),                     # below threshold
            _cand("Rival Sim", "rival.com", 10, provider=True),  # competitor
        ]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert [c.domain for _, c in winners] == ["good.com"]
    assert db.get_seen_domains(conn) == {"good.com", "weak.com", "rival.com"}
    assert db.get_company_by_domain(conn, "good.com")["status"] == "new"
    assert db.get_company_by_domain(conn, "weak.com")["status"] == "not_a_fit"
    assert db.get_company_by_domain(conn, "rival.com")["status"] == "not_a_fit"


def test_service_provider_excluded_even_with_top_score(conn, monkeypatch):
    _seed_defaults(monkeypatch)
    _stub_rounds(monkeypatch, [
        {"candidates": [_cand("CFD Vendor", "cfdvendor.com", 10, provider=True)]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert winners == []
    assert db.get_company_by_domain(conn, "cfdvendor.com")["status"] == "not_a_fit"


def test_dedup_against_existing_db(conn, monkeypatch):
    _seed_defaults(monkeypatch)
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
    assert db.get_company_by_domain(conn, "existing.com")["status"] == "sent"


def test_stops_early_when_target_reached(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=2, calls=3)
    calls = _stub_rounds(monkeypatch, [
        {"candidates": [_cand("A", "a.com", 9, industry="Aerospace"),
                        _cand("B", "b.com", 9, industry="Automotive")]},
        {"candidates": [_cand("C", "c.com", 9)]},  # should never be requested
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert len(winners) == 2
    assert calls["n"] == 1


def test_accumulates_across_rounds(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=3, calls=3)
    calls = _stub_rounds(monkeypatch, [
        {"candidates": [_cand("A", "a.com", 9, industry="Aerospace"),
                        _cand("Weak", "weak.com", 2)]},
        None,  # a dry round
        {"candidates": [_cand("B", "b.com", 8, industry="Automotive"),
                        _cand("C", "c.com", 7, industry="Energy / power")]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert {c.domain for _, c in winners} == {"a.com", "b.com", "c.com"}
    assert calls["n"] == 3


# --- diversifier ----------------------------------------------------------

def _sector_of(cand):
    from prospectus_agent import sectors
    return sectors.classify(cand.industry, cand.why_fit)


def test_sector_cap_limits_concentration(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, per_sector=2, calls=1)
    _stub_rounds(monkeypatch, [
        {"candidates": [_cand(f"Av{i}", f"av{i}.com", 9, industry="Commercial aviation")
                        for i in range(4)]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    # Only 2 of the 4 aviation companies are picked.
    assert len(winners) == 2
    assert all(_sector_of(c) == "aerospace_defense" for _, c in winners)
    # All 4 are still stored as backlog (status 'new') so none are wasted.
    assert sum(1 for d in ("av0.com", "av1.com", "av2.com", "av3.com")
               if db.get_company_by_domain(conn, d)["status"] == "new") == 4


def test_diversifies_across_sectors(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, per_sector=2, calls=1)
    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("Av1", "av1.com", 9, industry="Aviation"),
            _cand("Av2", "av2.com", 9, industry="Aviation"),
            _cand("Av3", "av3.com", 9, industry="Aviation"),
            _cand("Car1", "car1.com", 9, industry="Automotive OEM"),
            _cand("Pow1", "pow1.com", 9, industry="Energy / power grid"),
        ]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    buckets = [_sector_of(c) for _, c in winners]
    assert buckets.count("aerospace_defense") == 2  # capped
    assert "automotive" in buckets
    assert "energy" in buckets
    assert len(winners) == 4  # av3 dropped by the cap


def test_backlog_is_seeded_first_and_capped(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, per_sector=2, calls=0)  # no fresh rounds

    # run_with_submit must NOT be called when there are no rounds.
    def boom(*a, **k):
        raise AssertionError("run_with_submit should not be called")
    monkeypatch.setattr(discovery, "run_searcher", boom)

    for i in range(3):
        db.upsert_company(conn, name=f"OldAv{i}", domain=f"oldav{i}.com", hq_location="",
                          industry="Commercial aviation", fit_score=9, why_fit="cfd",
                          suggested_applications=["x"], source_urls=[], status="new")
    db.upsert_company(conn, name="OldCar", domain="oldcar.com", hq_location="",
                      industry="Automotive", fit_score=8, why_fit="crash sim",
                      suggested_applications=["x"], source_urls=[], status="new")

    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    domains = {c.domain for _, c in winners}
    # 2 aviation (capped) + 1 automotive = 3, drawn entirely from the backlog.
    assert len(winners) == 3
    assert "oldcar.com" in domains
    assert sum(1 for d in domains if d.startswith("oldav")) == 2


def test_avoid_sector_excludes_winners(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, per_sector=2, calls=1)
    monkeypatch.setattr(config, "AVOID_SECTORS", ["aerospace_defense"])
    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("Av", "av.com", 10, industry="Commercial aviation"),
            _cand("Car", "car.com", 8, industry="Automotive OEM"),
        ]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert [c.domain for _, c in winners] == ["car.com"]
    # Aviation kept as backlog (reversible) — not drafted, not discarded.
    assert db.get_company_by_domain(conn, "av.com")["status"] == "new"


def test_avoid_applies_to_backlog(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, per_sector=2, calls=0)
    monkeypatch.setattr(config, "AVOID_SECTORS", ["aerospace_defense"])

    def boom(*a, **k):
        raise AssertionError("no fresh rounds expected")
    monkeypatch.setattr(discovery, "run_searcher", boom)

    db.upsert_company(conn, name="OldAv", domain="oldav.com", hq_location="",
                      industry="Aviation", fit_score=9, why_fit="cfd",
                      suggested_applications=["x"], source_urls=[], status="new")
    db.upsert_company(conn, name="OldCar", domain="oldcar.com", hq_location="",
                      industry="Automotive", fit_score=8, why_fit="crash sim",
                      suggested_applications=["x"], source_urls=[], status="new")

    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert [c.domain for _, c in winners] == ["oldcar.com"]


def test_excludes_companies_above_size_ceiling(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, calls=1)
    monkeypatch.setattr(config, "MAX_COMPANY_SIZE", "mid")
    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("Giant", "giant.com", 10, industry="Automotive OEM", size="enterprise"),
            _cand("SmallCo", "smallco.com", 8, industry="Automotive parts", size="small"),
        ]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    assert [c.domain for _, c in winners] == ["smallco.com"]
    # The giant is stored as not_a_fit (won't recur).
    assert db.get_company_by_domain(conn, "giant.com")["status"] == "not_a_fit"


def test_size_ceiling_is_configurable(conn, monkeypatch):
    _seed_defaults(monkeypatch, target=5, calls=1)
    monkeypatch.setattr(config, "MAX_COMPANY_SIZE", "large")  # allow up to large
    _stub_rounds(monkeypatch, [
        {"candidates": [
            _cand("BigCo", "bigco.com", 9, industry="Energy utility", size="large"),
            _cand("Mega", "mega.com", 9, industry="Energy major", size="enterprise"),
        ]},
    ])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    domains = [c.domain for _, c in winners]
    assert "bigco.com" in domains       # large allowed under the raised ceiling
    assert "mega.com" not in domains    # enterprise still excluded


def test_company_ids_are_real(conn, monkeypatch):
    _seed_defaults(monkeypatch)
    _stub_rounds(monkeypatch, [{"candidates": [_cand("A", "a.com", 9)]}])
    winners = discovery.discover(client=None, conn=conn, on_profile="ON")
    cid, cand = winners[0]
    assert db.get_company_by_domain(conn, "a.com")["id"] == cid
