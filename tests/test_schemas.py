"""Sanity tests for the strict tool schemas and config helpers.

Anthropic strict tools require every object's `required` to list all its
properties and `additionalProperties: false`. A mismatch here would error at
call time, so we catch it without an API call.
"""
from __future__ import annotations

import pytest

from prospectus_agent import config
from prospectus_agent import discovery
from prospectus_agent import drafting
from prospectus_agent import research


def _assert_strict(schema, path="root"):
    t = schema.get("type")
    if t == "object":
        props = schema.get("properties", {})
        assert schema.get("additionalProperties") is False, f"{path}: additionalProperties must be False"
        assert set(schema.get("required", [])) == set(props), (
            f"{path}: required {set(schema.get('required', []))} != properties {set(props)}"
        )
        for name, sub in props.items():
            _assert_strict(sub, f"{path}.{name}")
    elif t == "array":
        _assert_strict(schema["items"], f"{path}[]")
    # scalar or union type (e.g. ["string","null"]) — nothing to recurse into.


@pytest.mark.parametrize("tool", [
    discovery.SUBMIT_CANDIDATES_TOOL,
    research.SUBMIT_RESEARCH_TOOL,
    research.SUBMIT_EMAIL_TOOL,
    drafting.SUBMIT_FOLLOWUP_TOOL,
])
def test_submit_tool_is_valid_neutral_tool(tool):
    # Vendor-neutral tool spec (translated per vendor at call time).
    assert tool.get("_neutral") == "function"
    assert "name" in tool and "description" in tool
    assert "schema" in tool
    _assert_strict(tool["schema"], tool["name"])


def test_candidate_schema_includes_provider_and_size():
    props = discovery.SUBMIT_CANDIDATES_TOOL["schema"]["properties"]
    item_props = props["candidates"]["items"]["properties"]
    assert "is_service_provider" in item_props
    assert item_props["company_size"]["enum"] == [
        "startup", "small", "mid", "large", "enterprise"
    ]


def test_size_allowed(monkeypatch):
    monkeypatch.setattr(config, "MAX_COMPANY_SIZE", "mid")
    assert config.size_allowed("startup")
    assert config.size_allowed("mid")
    assert not config.size_allowed("large")
    assert not config.size_allowed("enterprise")
    # Unknown values are treated leniently (as 'mid'), not silently excluded.
    assert config.size_allowed("ginormous")


def test_config_int_fallback():
    assert config._int("DEFINITELY_MISSING_VAR_XYZ", 42) == 42


def test_require_api_key_raises_when_missing(monkeypatch):
    monkeypatch.setattr(config, "ANTHROPIC_API_KEY", "")
    with pytest.raises(RuntimeError):
        config.require_api_key("anthropic")
    monkeypatch.setattr(config, "OPENAI_API_KEY", "")
    with pytest.raises(RuntimeError):
        config.require_api_key("openai")
