"""Tests for the LLM helpers against the OpenAI Responses API shape.

The OpenAI client is faked (see conftest). Covers function-call extraction,
ignoring hosted web_search items, the nudge-and-continue path, malformed-JSON
handling, and run_text.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from prospectus_agent import config
from prospectus_agent import llm
from conftest import (
    FakeClient,
    function_call,
    message_item,
    raw_function_call,
    response,
    web_search_call,
)


def test_find_function_call_args():
    resp = response([web_search_call(), function_call("submit", {"k": 1})])
    assert json.loads(llm._find_function_call_args(resp, "submit")) == {"k": 1}
    assert llm._find_function_call_args(resp, "other") is None


def test_run_with_submit_direct():
    client = FakeClient([response([function_call("submit_x", {"candidates": []})])])
    out = llm.run_with_submit(
        client, model="m", system="s", user_text="u",
        tools=[], submit_tool_name="submit_x",
    )
    assert out == {"candidates": []}
    assert client.call_count == 1


def test_run_with_submit_ignores_web_search_items():
    client = FakeClient([response([
        web_search_call(),
        web_search_call(),
        function_call("submit_x", {"ok": 1}),
    ])])
    out = llm.run_with_submit(
        client, model="m", system="s", user_text="u",
        tools=[], submit_tool_name="submit_x",
    )
    assert out == {"ok": 1}
    assert client.call_count == 1


def test_run_with_submit_nudges_when_tool_skipped():
    client = FakeClient([
        response([message_item("Here are some companies in prose.")],
                 output_text="prose", id="resp_1"),
        response([function_call("submit_x", {"ok": 2})], id="resp_2"),
    ])
    out = llm.run_with_submit(
        client, model="m", system="s", user_text="u",
        tools=[], submit_tool_name="submit_x",
    )
    assert out == {"ok": 2}
    assert client.call_count == 2
    # The nudge continued the same response thread and named the submit tool.
    second_call = client.responses.calls[1]
    assert second_call["previous_response_id"] == "resp_1"
    assert "submit_x" in second_call["input"]


def test_run_with_submit_gives_up_after_nudge():
    client = FakeClient([
        response([message_item("nope")], output_text="nope"),
        response([message_item("still nope")], output_text="still nope"),
    ])
    out = llm.run_with_submit(
        client, model="m", system="s", user_text="u",
        tools=[], submit_tool_name="submit_x",
    )
    assert out is None
    assert client.call_count == 2


def test_run_with_submit_handles_malformed_json():
    client = FakeClient([response([raw_function_call("submit_x", "{not valid json")])])
    out = llm.run_with_submit(
        client, model="m", system="s", user_text="u",
        tools=[], submit_tool_name="submit_x",
    )
    assert out is None
    assert client.call_count == 1  # found the call, failed to parse -> None (no nudge)


def test_run_text_returns_output_text():
    client = FakeClient([response([message_item("final answer")], output_text="final answer")])
    out = llm.run_text(client, model="m", system="s", user_text="u", tools=[])
    assert out == "final answer"
    assert client.call_count == 1


# --- token controls / usage accounting -------------------------------------

def _usage(input=0, output=0, cached=0, reasoning=0):
    return SimpleNamespace(
        input_tokens=input, output_tokens=output,
        input_tokens_details=SimpleNamespace(cached_tokens=cached),
        output_tokens_details=SimpleNamespace(reasoning_tokens=reasoning),
    )


def test_record_and_reset_usage():
    llm.reset_usage()
    r = response([function_call("submit_x", {"ok": 1})])
    r.usage = _usage(input=100, output=20, cached=40, reasoning=8)
    llm.record_usage(r)
    assert llm.get_usage() == {"calls": 1, "input": 100, "output": 20, "cached": 40, "reasoning": 8}
    llm.reset_usage()
    assert llm.get_usage()["calls"] == 0


def test_record_usage_tolerates_missing_usage():
    llm.reset_usage()
    llm.record_usage(response([]))  # no .usage attribute
    assert llm.get_usage()["calls"] == 0


def test_run_with_submit_passes_effort():
    client = FakeClient([response([function_call("submit_x", {"ok": 1})])])
    llm.run_with_submit(client, model="m", system="s", user_text="u",
                        tools=[], submit_tool_name="submit_x", effort="low")
    assert client.responses.calls[0]["reasoning"] == {"effort": "low"}


def test_run_with_submit_omits_reasoning_without_effort():
    client = FakeClient([response([function_call("submit_x", {"ok": 1})])])
    llm.run_with_submit(client, model="m", system="s", user_text="u",
                        tools=[], submit_tool_name="submit_x")
    assert "reasoning" not in client.responses.calls[0]


def test_web_search_tool_bounds_context_size():
    assert llm.WEB_SEARCH_TOOL["type"] == "web_search"
    assert llm.WEB_SEARCH_TOOL["search_context_size"] == config.SEARCH_CONTEXT_SIZE
