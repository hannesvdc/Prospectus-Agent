"""Thin helpers around the OpenAI Responses API.

Two patterns are used across the project:

1. run_text()        — let the model use the hosted web_search tool and return
                       its final prose. Used for the ON profile refresh.

2. run_with_submit() — let the model use web_search, then hand back structured
                       data by calling a strict custom "submit" function tool.
                       We read that call's arguments. `strict: true` guarantees
                       the arguments are schema-valid JSON, so parsing is safe.

The hosted web_search tool runs server-side within a single responses.create()
call (and can open/read specific pages), so there is no client-side tool loop to
manage. If the model finishes without calling the submit tool, we nudge once.
"""
from __future__ import annotations

import json
from typing import Optional

# Hosted web search tool. The current version can also open and read specific
# pages (action open_page / find_in_page), covering our grounding/fetch needs.
WEB_SEARCH_TOOL = {"type": "web_search"}


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
) -> str:
    """Run a turn (optionally with the web_search tool) and return final text."""
    response = client.responses.create(
        model=model,
        instructions=system,
        input=user_text,
        tools=tools or [],
        max_output_tokens=max_output_tokens,
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
) -> Optional[dict]:
    """Run a turn and return the parsed arguments of the `submit_tool_name`
    function call, or None if the model never called it. `tools` must include
    the submit function tool plus any hosted tools (e.g. web_search).
    """
    response = client.responses.create(
        model=model,
        instructions=system,
        input=user_text,
        tools=tools,
        max_output_tokens=max_output_tokens,
    )

    raw_args = _find_function_call_args(response, submit_tool_name)

    # Model finished without calling the submit tool — nudge once, continuing
    # the same response thread so it keeps its prior reasoning and searches.
    if raw_args is None:
        followup = client.responses.create(
            model=model,
            instructions=system,
            previous_response_id=response.id,
            input=(
                f"Now call the `{submit_tool_name}` function with your results. "
                "Respond only with that function call, not prose."
            ),
            tools=tools,
            max_output_tokens=max_output_tokens,
        )
        raw_args = _find_function_call_args(followup, submit_tool_name)

    if raw_args is None:
        return None
    try:
        return json.loads(raw_args)
    except (json.JSONDecodeError, TypeError):
        return None
