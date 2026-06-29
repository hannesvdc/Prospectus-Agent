"""Shared pytest fixtures and fakes.

Tests never touch the network or need an API key — the OpenAI client is faked.
`FakeClient` scripts a sequence of canned responses for
`client.responses.create(...)`, and the helpers below build the `response.output`
items the llm helpers inspect (function calls, hosted web_search calls, messages).
"""
from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

# The `prospectus_agent` package is importable via pytest's `pythonpath = ["src"]`
# (see pyproject.toml), so no sys.path juggling is needed here.
from prospectus_agent import db


@pytest.fixture
def conn():
    """A fresh in-memory database per test."""
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


# --- Anthropic Messages API fakes -----------------------------------------

def tool_use_block(name: str, input: dict, id: str = "toolu_1"):
    """A `tool_use` content block (input is already a parsed dict, as the API
    returns it under strict tool use)."""
    return SimpleNamespace(type="tool_use", name=name, input=dict(input), id=id)


def text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def server_tool_block():
    """A server-side web_search block (should be ignored by our helpers)."""
    return SimpleNamespace(type="server_tool_use", name="web_search", id="srvtoolu_1")


def message(content: list, stop_reason: str = "end_turn", id: str = "msg_1"):
    """A Messages-API response object. `usage` is omitted by default; tests that
    assert on token accounting set `.usage` explicitly."""
    return SimpleNamespace(content=list(content), stop_reason=stop_reason, id=id)


class _FakeMessages:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self._responses.pop(0)


class FakeClient:
    """Stand-in for anthropic.Anthropic that returns scripted responses."""

    def __init__(self, responses):
        self.messages = _FakeMessages(responses)

    @property
    def call_count(self):
        return len(self.messages.calls)


# --- OpenAI Responses API fakes -------------------------------------------

def oai_function_call(name: str, args: dict):
    """A `function_call` output item (arguments are a JSON string)."""
    return SimpleNamespace(type="function_call", name=name, arguments=json.dumps(args),
                           call_id="call_1")


def oai_message_item(text: str):
    return SimpleNamespace(type="message",
                           content=[SimpleNamespace(type="output_text", text=text)])


def oai_response(output: list, output_text: str = "", id: str = "resp_1"):
    return SimpleNamespace(output=list(output), output_text=output_text, id=id)


class _FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("OpenAIFakeClient ran out of scripted responses")
        return self._responses.pop(0)


class OpenAIFakeClient:
    """Stand-in for openai.OpenAI that returns scripted responses."""

    def __init__(self, responses):
        self.responses = _FakeResponses(responses)

    @property
    def call_count(self):
        return len(self.responses.calls)


# --- client registry fake (duck-typed: .get(vendor)) -----------------------

class FakeClients:
    """Stand-in for runner.Clients — maps a vendor name to a fake SDK client."""

    def __init__(self, by_vendor: dict):
        self._by_vendor = dict(by_vendor)

    def get(self, vendor: str):
        return self._by_vendor[vendor]
