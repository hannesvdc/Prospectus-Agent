"""Thin helpers around the OpenAI Responses API.

Two patterns are used across the project:

1. run_text()        — let the model use the hosted web_search tool and return
                       its final prose. Used for the seller-profile refresh.

2. run_with_submit() — let the model use web_search, then hand back structured
                       data by calling a strict custom "submit" function tool.
                       We read that call's arguments. `strict: true` guarantees
                       the arguments are schema-valid JSON, so parsing is safe.

The hosted web_search tool runs server-side within a single responses.create()
call (and can open/read specific pages), so there is no client-side tool loop to
manage. If the model finishes without calling the submit tool, we nudge once.

Token controls: callers pass `effort` (reasoning depth) per step, and the
web_search tool's `search_context_size` (from config) bounds how much page
content enters context. Token usage from every call is accumulated for a
per-run summary (see record/get/reset_usage).
"""
from __future__ import annotations

import json
from typing import Optional

from prospectus_agent import config

# Hosted web search tool. search_context_size bounds how much search/page content
# is pulled into context (low|medium|high) — the main per-call token lever.
WEB_SEARCH_TOOL = {"type": "web_search", "search_context_size": config.SEARCH_CONTEXT_SIZE}

# --- usage accounting ------------------------------------------------------
_USAGE = {"calls": 0, "input": 0, "output": 0, "cached": 0, "reasoning": 0}


def reset_usage() -> None:
    for k in _USAGE:
        _USAGE[k] = 0


def get_usage() -> dict:
    return dict(_USAGE)


def record_usage(response) -> None:
    u = getattr(response, "usage", None)
    if u is None:
        return
    _USAGE["calls"] += 1
    _USAGE["input"] += getattr(u, "input_tokens", 0) or 0
    _USAGE["output"] += getattr(u, "output_tokens", 0) or 0
    itd = getattr(u, "input_tokens_details", None)
    if itd is not None:
        _USAGE["cached"] += getattr(itd, "cached_tokens", 0) or 0
    otd = getattr(u, "output_tokens_details", None)
    if otd is not None:
        _USAGE["reasoning"] += getattr(otd, "reasoning_tokens", 0) or 0


def _create(client, *, model, system, input, tools, max_output_tokens, effort,
            previous_response_id=None):
    kwargs = dict(
        model=model,
        instructions=system,
        input=input,
        tools=tools,
        max_output_tokens=max_output_tokens,
    )
    if effort:
        kwargs["reasoning"] = {"effort": effort}
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    resp = client.responses.create(**kwargs)
    record_usage(resp)
    return resp


def _find_function_call_args(response, name: str) -> Optional[str]:
    """Return the raw JSON-string arguments of the named function_call, or None."""
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "function_call" and getattr(item, "name", None) == name:
            return item.arguments
    return None


def run_text(
    client,
    *,
    model: str,
    system: str,
    user_text: str,
    tools: Optional[list] = None,
    max_output_tokens: int = 4000,
    effort: Optional[str] = None,
) -> str:
    """Run a turn (optionally with the web_search tool) and return final text."""
    response = _create(
        client, model=model, system=system, input=user_text,
        tools=tools or [], max_output_tokens=max_output_tokens, effort=effort,
    )
    return (getattr(response, "output_text", "") or "").strip()


def run_with_submit(
    client,
    *,
    model: str,
    system: str,
    user_text: str,
    tools: list,
    submit_tool_name: str,
    max_output_tokens: int = 16000,
    effort: Optional[str] = None,
) -> Optional[dict]:
    """Run a turn and return the parsed arguments of the `submit_tool_name`
    function call, or None if the model never called it. `tools` must include
    the submit function tool plus any hosted tools (e.g. web_search).
    """
    response = _create(
        client, model=model, system=system, input=user_text,
        tools=tools, max_output_tokens=max_output_tokens, effort=effort,
    )

    raw_args = _find_function_call_args(response, submit_tool_name)

    # Model finished without calling the submit tool — nudge once, continuing
    # the same response thread so it keeps its prior reasoning and searches.
    if raw_args is None:
        followup = _create(
            client, model=model, system=system,
            input=(
                f"Now call the `{submit_tool_name}` function with your results. "
                "Respond only with that function call, not prose."
            ),
            tools=tools, max_output_tokens=max_output_tokens, effort=effort,
            previous_response_id=response.id,  # keep the prior turn's context
        )
        raw_args = _find_function_call_args(followup, submit_tool_name)

    if raw_args is None:
        return None
    try:
        return json.loads(raw_args)
    except (json.JSONDecodeError, TypeError):
        return None
