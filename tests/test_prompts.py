"""Tests for the extracted prompt builders in prompts/.

These guard the templating (interpolation, included fragments) so a refactor or
edit can't silently drop the deny-list, the provider-exclusion language, or the
no-signature instruction.
"""
from __future__ import annotations

from prospectus_agent import config
from prospectus_agent.prompts import discovery as dprompt
from prospectus_agent.prompts import followup as fprompt
from prospectus_agent.prompts import on_profile as oprompt
from prospectus_agent.prompts import research as rprompt
from prospectus_agent.schemas import Candidate


def test_discovery_system_carries_provider_distinction():
    sys = dprompt.system()
    assert sys
    assert "is_service_provider" in sys
    assert "competitor" in sys.lower()


def test_prompts_use_profile_name(monkeypatch):
    from prospectus_agent import agent_profile
    monkeypatch.setattr(agent_profile, "NAME", "Acme Consulting")
    assert "Acme Consulting" in dprompt.system()


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


def test_draft_build_user_includes_company_and_omits_signature():
    cand = Candidate(name="Acme", domain="acme.com", industry="Aero",
                     why_fit="CFD", fit_score=9, suggested_applications=["GPU CFD"])
    out = rprompt.build_user(cand, "ON PROFILE")
    assert "Acme" in out and "acme.com" in out
    assert "GPU CFD" in out  # falls back to candidate applications when no facts
    assert "submit_email" in out
    # The model must NOT generate a sign-off; the user's client adds the signature.
    assert "do NOT add a signature" in out


def test_research_build_user_gathers_facts_only():
    cand = Candidate(name="Acme", domain="acme.com", industry="Aero",
                     why_fit="CFD", fit_score=9, suggested_applications=["GPU CFD"])
    out = rprompt.build_research_user(cand, "ON PROFILE")
    assert "submit_research" in out
    assert "Acme" in out and "acme.com" in out
    # The research step does NOT write the email.
    assert "submit_email" not in out


def test_research_build_user_includes_credibility(monkeypatch):
    from prospectus_agent import agent_profile
    monkeypatch.setattr(agent_profile, "CREDIBILITY", "20 years building widgets")
    cand = Candidate(name="Acme", domain="acme.com", why_fit="x", fit_score=9,
                     suggested_applications=["y"])
    out = rprompt.build_user(cand, "BRIEF")
    assert "20 years building widgets" in out
    assert "credibility sentence" in out


def test_research_build_user_omits_credibility_when_unset(monkeypatch):
    from prospectus_agent import agent_profile
    monkeypatch.setattr(agent_profile, "CREDIBILITY", "")
    cand = Candidate(name="Acme", domain="acme.com", why_fit="x", fit_score=9,
                     suggested_applications=["y"])
    out = rprompt.build_user(cand, "BRIEF")
    assert "note of experience" not in out


def test_followup_build_user_interpolates_and_omits_signature():
    row = {"name": "Acme", "domain": "acme.com", "last_contact_date": "2026-06-01"}
    out = fprompt.build_user(row, "PRIOR EMAIL TEXT", "ON PROFILE")
    assert "Acme" in out
    assert "PRIOR EMAIL TEXT" in out
    assert "submit_followup" in out
    assert str(config.FOLLOWUP_DAYS) in out
    assert "NOT add a signature" in " ".join(out.split())  # no-signature instruction


def test_on_profile_build_user_includes_url():
    out = oprompt.build_user("https://opennumerics.com")
    assert "opennumerics.com" in out
