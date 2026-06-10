"""Shared pytest fixtures and fakes.

Tests never touch the network or need an API key — the OpenAI client is faked.
`FakeClient` scripts a sequence of canned responses for
`client.responses.create(...)`, and the helpers below build the `response.output`
items the llm helpers inspect (function calls, hosted web_search calls, messages).
"""
from __future__ import annotations

import json
import os
import sys
from types import SimpleNamespace

import pytest

# Make the project root importable when pytest runs from anywhere.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402


@pytest.fixture
def conn():
    """A fresh in-memory database per test."""
    c = db.connect(":memory:")
    db.init_db(c)
    yield c
    c.close()


# --- OpenAI Responses API fakes -------------------------------------------

def function_call(name: str, args: dict):
    """A `function_call` output item (arguments are a JSON string, as the API
    returns them)."""
    return SimpleNamespace(
        type="function_call", name=name, arguments=json.dumps(args), call_id="call_1"
    )


def raw_function_call(name: str, arguments: str):
    """A function_call whose arguments string is supplied verbatim (to test
    malformed JSON)."""
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, call_id="call_1")


def web_search_call():
    """A hosted web_search tool call item (should be ignored by our helpers)."""
    return SimpleNamespace(type="web_search_call", id="ws_1", status="completed")


def message_item(text: str):
    return SimpleNamespace(
        type="message", content=[SimpleNamespace(type="output_text", text=text)]
    )


def response(output: list, output_text: str = "", id: str = "resp_1"):
    return SimpleNamespace(output=list(output), output_text=output_text, id=id)


class _FakeResponses:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self._responses.pop(0)


class FakeClient:
    """Stand-in for openai.OpenAI that returns scripted responses."""

    def __init__(self, responses):
        self.responses = _FakeResponses(responses)

    @property
    def call_count(self):
        return len(self.responses.calls)
