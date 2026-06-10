"""Tests for the extracted prompt builders in prompts/.

These guard the templating (interpolation, included fragments) so a refactor or
edit can't silently drop the deny-list, the provider-exclusion language, the
sender block, or the CAN-SPAM guidance.
"""
from __future__ import annotations

import config
from prompts import common
from prompts import discovery as dprompt
from prompts import followup as fprompt
from prompts import on_profile as oprompt
from prompts import research as rprompt
from schemas import Candidate


def test_discovery_system_carries_provider_distinction():
    assert dprompt.SYSTEM
    assert "is_service_provider" in dprompt.SYSTEM
    assert "competitor" in dprompt.SYSTEM.lower()


def test_discovery_build_user_interpolates():
    out = dprompt.build_user(
        "ON PROFILE TEXT", [{"name": "Acme", "domain": "acme.com"}], "aerospace and energy"
    )
    assert "ON PROFILE TEXT" in out
    assert "- Acme (acme.com)" in out          # deny-list rendered
    assert "aerospace and energy" in out        # angle
    assert "is_service_provider=true" in out     # exclusion language
    assert "submit_candidates" in out
    assert config.TARGET_REGION in out


def test_discovery_build_user_empty_deny():
    out = dprompt.build_user("p", [], "x")
    assert "(none yet)" in out


def test_discovery_build_user_includes_avoid_block():
    out = dprompt.build_user("p", [], "x", ["aerospace, defense, and aviation"])
    assert "HARD EXCLUSION" in out
    assert "aerospace, defense, and aviation" in out


def test_discovery_build_user_no_avoid_block_when_empty():
    out = dprompt.build_user("p", [], "x")
    assert "HARD EXCLUSION" not in out


def test_research_build_user_includes_company_sender_canspam():
    cand = Candidate(name="Acme", domain="acme.com", industry="Aero",
                     why_fit="CFD", fit_score=9, suggested_applications=["GPU CFD"])
    out = rprompt.build_user(cand, "ON PROFILE")
    assert "Acme" in out and "acme.com" in out
    assert "GPU CFD" in out
    assert "submit_company_outreach" in out
    assert common.CANSPAM_GUIDANCE in out
    assert "Sender identity for the sign-off" in out


def test_followup_build_user_interpolates():
    row = {"name": "Acme", "domain": "acme.com", "last_contact_date": "2026-06-01"}
    out = fprompt.build_user(row, "PRIOR EMAIL TEXT", "ON PROFILE")
    assert "Acme" in out
    assert "PRIOR EMAIL TEXT" in out
    assert "submit_followup" in out
    assert str(config.FOLLOWUP_BUSINESS_DAYS) in out


def test_on_profile_build_user_includes_url():
    out = oprompt.build_user("https://opennumerics.com")
    assert "opennumerics.com" in out


def test_sender_block_reflects_config(monkeypatch):
    monkeypatch.setitem(config.SENDER, "name", "Jane Tester")
    assert "Jane Tester" in common.sender_block()


def test_sender_block_flags_missing_fields(monkeypatch):
    monkeypatch.setitem(config.SENDER, "physical_address", "")
    assert "SENDER_PHYSICAL_ADDRESS" in common.sender_block()
