"""Tests for the ON profile cache freshness logic (no network)."""
from __future__ import annotations

from datetime import date, timedelta

from prospectus_agent import config
from prospectus_agent import on_profile


def test_cache_fresh_within_window(monkeypatch):
    monkeypatch.setattr(config, "PROFILE_REFRESH_DAYS", 7)
    today = date.today().isoformat()
    assert on_profile._cache_is_fresh({"date": today, "profile": "x"})
    recent = (date.today() - timedelta(days=3)).isoformat()
    assert on_profile._cache_is_fresh({"date": recent, "profile": "x"})


def test_cache_stale_past_window(monkeypatch):
    monkeypatch.setattr(config, "PROFILE_REFRESH_DAYS", 7)
    old = (date.today() - timedelta(days=8)).isoformat()
    assert not on_profile._cache_is_fresh({"date": old, "profile": "x"})


def test_cache_invalid_entries(monkeypatch):
    monkeypatch.setattr(config, "PROFILE_REFRESH_DAYS", 7)
    today = date.today().isoformat()
    assert not on_profile._cache_is_fresh({"date": today, "profile": ""})  # empty profile
    assert not on_profile._cache_is_fresh({})                               # missing keys
    assert not on_profile._cache_is_fresh({"date": "not-a-date", "profile": "x"})
