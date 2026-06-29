"""Tests for the vendor-agnostic LLM helpers.

Both backends are faked (see conftest). Covers tool translation, the Anthropic
Messages-API path (tool_use extraction, ignoring server web_search blocks, the
pause_turn drain loop, the nudge), the OpenAI Responses-API path (function-call
extraction, nudge, malformed JSON), run_text, and usage accounting.
"""
from __future__ import annotations

from types import SimpleNamespace

from prospectus_agent import llm
from conftest import (
    FakeClient,
    FakeClients,
    OpenAIFakeClient,
    message,
    oai_function_call,
    oai_message_item,
    oai_response,
    server_tool_block,
    text_block,
    tool_use_block,
)

SUBMIT = llm.function_tool("submit_x", "desc", {"ok": {"type": "integer"}}, ["ok"])


def _anthropic(responses):
    return FakeClients({"anthropic": FakeClient(responses)})


def _openai(responses):
    return FakeClients({"openai": OpenAIFakeClient(responses)})


# --- tool translation ------------------------------------------------------

def test_function_tool_is_neutral():
    assert SUBMIT["_neutral"] == "function"
    assert SUBMIT["schema"]["additionalProperties"] is False


def test_translate_to_anthropic():
    out = llm._to_anthropic_tools([llm.WEB_SEARCH_TOOL, SUBMIT])
    assert out[0] == {"type": "web_search_20250305", "name": "web_search"}
    assert out[1]["input_schema"] == SUBMIT["schema"] and out[1]["strict"] is True


def test_translate_to_openai():
    out = llm._to_openai_tools([llm.WEB_SEARCH_TOOL, SUBMIT])
    assert out[0]["type"] == "web_search"
    assert out[1]["type"] == "function" and out[1]["parameters"] == SUBMIT["schema"]


# --- Anthropic backend -----------------------------------------------------

def test_anthropic_submit_direct():
    clients = _anthropic([message([tool_use_block("submit_x", {"ok": 1})], stop_reason="tool_use")])
    out = llm.run_with_submit(clients, vendor="anthropic", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 1}


def test_anthropic_ignores_server_tool_blocks():
    clients = _anthropic([message([server_tool_block(), server_tool_block(),
                                   tool_use_block("submit_x", {"ok": 1})], stop_reason="tool_use")])
    out = llm.run_with_submit(clients, vendor="anthropic", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 1}


def test_anthropic_drains_pause_turn():
    clients = _anthropic([
        message([server_tool_block()], stop_reason="pause_turn"),
        message([tool_use_block("submit_x", {"ok": 9})], stop_reason="tool_use"),
    ])
    out = llm.run_with_submit(clients, vendor="anthropic", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 9}
    assert clients.get("anthropic").call_count == 2


def test_anthropic_nudges_when_tool_skipped():
    client = FakeClient([
        message([text_block("prose")], stop_reason="end_turn"),
        message([tool_use_block("submit_x", {"ok": 2})], stop_reason="tool_use"),
    ])
    out = llm.run_with_submit(FakeClients({"anthropic": client}), vendor="anthropic",
                              model="m", system="s", user_text="u",
                              tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 2}
    assert client.call_count == 2
    assert "submit_x" in client.messages.calls[1]["messages"][-1]["content"]


def test_anthropic_gives_up_after_nudge():
    clients = _anthropic([
        message([text_block("nope")], stop_reason="end_turn"),
        message([text_block("still nope")], stop_reason="end_turn"),
    ])
    out = llm.run_with_submit(clients, vendor="anthropic", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out is None


def test_anthropic_run_text():
    clients = _anthropic([message([text_block("final answer")], stop_reason="end_turn")])
    out = llm.run_text(clients, vendor="anthropic", model="m", system="s", user_text="u")
    assert out == "final answer"


# --- OpenAI backend --------------------------------------------------------

def test_openai_submit_direct():
    clients = _openai([oai_response([oai_function_call("submit_x", {"ok": 1})])])
    out = llm.run_with_submit(clients, vendor="openai", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 1}


def test_openai_nudges_when_tool_skipped():
    clients = _openai([
        oai_response([oai_message_item("prose")], output_text="prose", id="resp_1"),
        oai_response([oai_function_call("submit_x", {"ok": 2})], id="resp_2"),
    ])
    out = llm.run_with_submit(clients, vendor="openai", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 2}
    second_call = clients.get("openai").responses.calls[1]
    assert second_call["previous_response_id"] == "resp_1"


def test_openai_handles_malformed_json():
    bad = SimpleNamespace(type="function_call", name="submit_x", arguments="{not json",
                          call_id="c")
    clients = _openai([oai_response([bad])])
    out = llm.run_with_submit(clients, vendor="openai", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out is None


def test_openai_run_text():
    clients = _openai([oai_response([oai_message_item("hi")], output_text="hi")])
    out = llm.run_text(clients, vendor="openai", model="m", system="s", user_text="u")
    assert out == "hi"


def test_unknown_vendor_raises():
    import pytest
    with pytest.raises(ValueError):
        llm.run_with_submit(FakeClients({}), vendor="bogus", model="m", system="s",
                            user_text="u", tools=[], submit_tool_name="x")


# --- usage accounting ------------------------------------------------------

def test_record_usage_anthropic_shape():
    llm.reset_usage()
    r = message([], stop_reason="end_turn")
    r.usage = SimpleNamespace(input_tokens=100, output_tokens=20, cache_read_input_tokens=40)
    llm.record_usage(r)
    assert llm.get_usage() == {"calls": 1, "input": 100, "output": 20, "cached": 40, "reasoning": 0}


def test_record_usage_openai_shape():
    llm.reset_usage()
    r = oai_response([])
    r.usage = SimpleNamespace(
        input_tokens=100, output_tokens=20,
        input_tokens_details=SimpleNamespace(cached_tokens=30),
        output_tokens_details=SimpleNamespace(reasoning_tokens=8),
    )
    llm.record_usage(r)
    assert llm.get_usage() == {"calls": 1, "input": 100, "output": 20, "cached": 30, "reasoning": 8}


def test_record_usage_tolerates_missing_usage():
    llm.reset_usage()
    llm.record_usage(message([]))  # no .usage attribute
    assert llm.get_usage()["calls"] == 0


# --- citation stripping (Anthropic web_search markup) ----------------------

def test_strip_citations_recurses():
    out = llm._strip_citations({
        "answer": '<cite index="2-1">Acme builds rockets</cite>.',
        "apps": ['<cite index="3-2">GPU CFD'],
    })
    assert out == {"answer": "Acme builds rockets.", "apps": ["GPU CFD"]}


def test_anthropic_submit_strips_citations():
    clients = _anthropic([message(
        [tool_use_block("submit_x", {"ok": 1, "note": '<cite index="1-1">hi</cite>'})],
        stop_reason="tool_use")])
    out = llm.run_with_submit(clients, vendor="anthropic", model="m", system="s",
                              user_text="u", tools=[SUBMIT], submit_tool_name="submit_x")
    assert out == {"ok": 1, "note": "hi"}
