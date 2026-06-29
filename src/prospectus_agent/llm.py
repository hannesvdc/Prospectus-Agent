"""Vendor-agnostic LLM helpers.

The pipeline picks a (vendor, model) per task — see config.SEARCH_* / WRITER_*.
Two patterns are exposed, both vendor-neutral:

1. run_text()        — let the model use the hosted web_search tool and return
                       its final prose. Used for the seller-profile refresh.

2. run_with_submit() — let the model use web_search, then hand back structured
                       data by calling a strict custom "submit" tool. We read
                       that call's arguments. The schema is enforced strictly so
                       the arguments are valid without extra parsing.

Tools are built as NEUTRAL specs (`function_tool`, `WEB_SEARCH_TOOL`) and
translated to the active vendor's wire shape at call time. A `clients` registry
(duck-typed: `.get(vendor)`) supplies the right SDK client per vendor.

Supported vendors: "anthropic" (Messages API) and "openai" (Responses API).
Token usage from every call is accumulated for a per-run summary.
"""
from __future__ import annotations

import json
import re
from typing import Optional

from prospectus_agent import config

# Anthropic's hosted web_search injects inline citation markup (e.g.
# `<cite index="2-1">…</cite>`) into generated text. Strip it so it never leaks
# into the profile brief, researched facts, or drafted emails.
_CITE_RE = re.compile(r"</?cite\b[^>]*>", re.IGNORECASE)


def _strip_citations(value):
    """Recursively remove web_search citation tags from strings / lists / dicts."""
    if isinstance(value, str):
        return _CITE_RE.sub("", value)
    if isinstance(value, list):
        return [_strip_citations(v) for v in value]
    if isinstance(value, dict):
        return {k: _strip_citations(v) for k, v in value.items()}
    return value

# Neutral tool markers. `function_tool` returns a vendor-neutral spec; WEB_SEARCH_TOOL
# is a sentinel translated to each vendor's hosted web-search tool.
WEB_SEARCH_TOOL = {"_neutral": "web_search"}

# Drain at most this many server-tool continuations before giving up on a turn.
_MAX_PAUSE_TURNS = 8


def function_tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Build a vendor-neutral strict tool spec. `additionalProperties:false` +
    full `required` make it valid under both vendors' strict modes."""
    return {
        "_neutral": "function",
        "name": name,
        "description": description,
        "schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


# --- usage accounting ------------------------------------------------------
_USAGE = {"calls": 0, "input": 0, "output": 0, "cached": 0, "reasoning": 0}


def reset_usage() -> None:
    for k in _USAGE:
        _USAGE[k] = 0


def get_usage() -> dict:
    return dict(_USAGE)


def usage_summary() -> str | None:
    """One-line token-usage report for the run, or None if no API calls were made."""
    u = _USAGE
    if not u["calls"]:
        return None
    return (
        f"Token usage: {u['calls']} API call(s) — "
        f"input {u['input']:,} (cached {u['cached']:,}), "
        f"output {u['output']:,} (reasoning {u['reasoning']:,})."
    )


def record_usage(response) -> None:
    """Accumulate token usage from either vendor's response.usage shape."""
    u = getattr(response, "usage", None)
    if u is None:
        return
    _USAGE["calls"] += 1
    _USAGE["input"] += getattr(u, "input_tokens", 0) or 0
    _USAGE["output"] += getattr(u, "output_tokens", 0) or 0
    # Anthropic: cache reads are a top-level field. OpenAI: nested under details.
    _USAGE["cached"] += getattr(u, "cache_read_input_tokens", 0) or 0
    itd = getattr(u, "input_tokens_details", None)
    if itd is not None:
        _USAGE["cached"] += getattr(itd, "cached_tokens", 0) or 0
    otd = getattr(u, "output_tokens_details", None)
    if otd is not None:
        _USAGE["reasoning"] += getattr(otd, "reasoning_tokens", 0) or 0


# --- tool translation ------------------------------------------------------

def _to_anthropic_tools(tools: list) -> list:
    out = []
    for t in tools:
        kind = t.get("_neutral")
        if kind == "web_search":
            # Basic variant works across tiers (Haiku 4.5 + Sonnet 4.6).
            out.append({"type": "web_search_20250305", "name": "web_search"})
        elif kind == "function":
            out.append({
                "name": t["name"],
                "description": t["description"],
                "strict": True,
                "input_schema": t["schema"],
            })
    return out


def _to_openai_tools(tools: list) -> list:
    out = []
    for t in tools:
        kind = t.get("_neutral")
        if kind == "web_search":
            out.append({"type": "web_search", "search_context_size": config.SEARCH_CONTEXT_SIZE})
        elif kind == "function":
            out.append({
                "type": "function",
                "name": t["name"],
                "description": t["description"],
                "strict": True,
                "parameters": t["schema"],
            })
    return out


# --- Anthropic backend (Messages API) --------------------------------------

def _anthropic_create(client, *, model, system, messages, tools, max_tokens):
    resp = client.messages.create(
        model=model, max_tokens=max_tokens, system=system, messages=messages, tools=tools,
    )
    record_usage(resp)
    return resp


def _anthropic_tool_input(response, name):
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == name:
            return getattr(block, "input", None)
    return None


def _anthropic_text(response) -> str:
    parts = [getattr(b, "text", "") or "" for b in (getattr(response, "content", []) or [])
             if getattr(b, "type", None) == "text"]
    return "".join(parts)


def _anthropic_drain(client, *, model, system, messages, tools, max_tokens):
    resp = _anthropic_create(client, model=model, system=system, messages=messages,
                             tools=tools, max_tokens=max_tokens)
    pauses = 0
    while getattr(resp, "stop_reason", None) == "pause_turn" and pauses < _MAX_PAUSE_TURNS:
        messages.append({"role": "assistant", "content": resp.content})
        resp = _anthropic_create(client, model=model, system=system, messages=messages,
                                 tools=tools, max_tokens=max_tokens)
        pauses += 1
    return resp


def _anthropic_run_with_submit(client, *, model, system, user_text, tools, submit_tool_name, max_tokens):
    messages = [{"role": "user", "content": user_text}]
    resp = _anthropic_drain(client, model=model, system=system, messages=messages,
                            tools=tools, max_tokens=max_tokens)
    args = _anthropic_tool_input(resp, submit_tool_name)
    if args is not None:
        return _strip_citations(args)
    messages.append({"role": "assistant", "content": resp.content})
    messages.append({"role": "user", "content": (
        f"Now call the `{submit_tool_name}` tool with your results. "
        "Respond only with that tool call, not prose.")})
    resp = _anthropic_drain(client, model=model, system=system, messages=messages,
                            tools=tools, max_tokens=max_tokens)
    args = _anthropic_tool_input(resp, submit_tool_name)
    return _strip_citations(args) if args is not None else None


def _anthropic_run_text(client, *, model, system, user_text, tools, max_tokens):
    messages = [{"role": "user", "content": user_text}]
    resp = _anthropic_drain(client, model=model, system=system, messages=messages,
                            tools=tools, max_tokens=max_tokens)
    return _strip_citations(_anthropic_text(resp).strip())


# --- OpenAI backend (Responses API) ----------------------------------------

def _openai_create(client, *, model, system, input, tools, max_output_tokens, effort,
                   previous_response_id=None):
    kwargs = dict(model=model, instructions=system, input=input, tools=tools,
                  max_output_tokens=max_output_tokens)
    if effort:
        kwargs["reasoning"] = {"effort": effort}
    if previous_response_id:
        kwargs["previous_response_id"] = previous_response_id
    resp = client.responses.create(**kwargs)
    record_usage(resp)
    return resp


def _openai_call_args(response, name):
    for item in getattr(response, "output", []) or []:
        if getattr(item, "type", None) == "function_call" and getattr(item, "name", None) == name:
            return item.arguments
    return None


def _openai_run_with_submit(client, *, model, system, user_text, tools, submit_tool_name,
                            max_output_tokens, effort):
    resp = _openai_create(client, model=model, system=system, input=user_text,
                          tools=tools, max_output_tokens=max_output_tokens, effort=effort)
    raw = _openai_call_args(resp, submit_tool_name)
    if raw is None:
        followup = _openai_create(
            client, model=model, system=system,
            input=(f"Now call the `{submit_tool_name}` function with your results. "
                   "Respond only with that function call, not prose."),
            tools=tools, max_output_tokens=max_output_tokens, effort=effort,
            previous_response_id=resp.id,
        )
        raw = _openai_call_args(followup, submit_tool_name)
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None


def _openai_run_text(client, *, model, system, user_text, tools, max_output_tokens, effort):
    resp = _openai_create(client, model=model, system=system, input=user_text,
                          tools=tools, max_output_tokens=max_output_tokens, effort=effort)
    return (getattr(resp, "output_text", "") or "").strip()


# --- dispatch --------------------------------------------------------------

def run_with_submit(
    clients,
    *,
    vendor: str,
    model: str,
    system: str,
    user_text: str,
    tools: list,
    submit_tool_name: str,
    max_output_tokens: int = 16000,
    effort: Optional[str] = None,
) -> Optional[dict]:
    """Run a turn (optionally with web_search) and return the validated arguments
    of the `submit_tool_name` call, or None if the model never called it."""
    if vendor not in ("anthropic", "openai"):
        raise ValueError(f"Unknown vendor '{vendor}' (expected 'anthropic' or 'openai').")
    client = clients.get(vendor)
    if vendor == "anthropic":
        return _anthropic_run_with_submit(
            client, model=model, system=system, user_text=user_text,
            tools=_to_anthropic_tools(tools), submit_tool_name=submit_tool_name,
            max_tokens=max_output_tokens)
    if vendor == "openai":
        return _openai_run_with_submit(
            client, model=model, system=system, user_text=user_text,
            tools=_to_openai_tools(tools), submit_tool_name=submit_tool_name,
            max_output_tokens=max_output_tokens, effort=effort)
    raise ValueError(f"Unknown vendor '{vendor}' (expected 'anthropic' or 'openai').")


def run_text(
    clients,
    *,
    vendor: str,
    model: str,
    system: str,
    user_text: str,
    tools: Optional[list] = None,
    max_output_tokens: int = 4000,
    effort: Optional[str] = None,
) -> str:
    """Run a turn (optionally with web_search) and return the final text."""
    client = clients.get(vendor)
    tools = tools or []
    if vendor == "anthropic":
        return _anthropic_run_text(client, model=model, system=system, user_text=user_text,
                                   tools=_to_anthropic_tools(tools), max_tokens=max_output_tokens)
    if vendor == "openai":
        return _openai_run_text(client, model=model, system=system, user_text=user_text,
                                tools=_to_openai_tools(tools), max_output_tokens=max_output_tokens,
                                effort=effort)
    raise ValueError(f"Unknown vendor '{vendor}' (expected 'anthropic' or 'openai').")
