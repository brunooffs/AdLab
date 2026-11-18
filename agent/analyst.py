#!/usr/bin/env python3
"""
analyst.py — a read-only campaign analyst agent.

Ask it a question in plain English; it calls AdLab's own real endpoints as
tools, reasons over the real data, and prints a synthesized answer. Nothing
here writes anything — every tool is a GET against an endpoint that already
exists, so the worst this can do is read wrong data, never change any.

Two backends, picked by AGENT_BACKEND (default "ollama"):
  ollama  — a local model via the Ollama Python client. No API key, no
            vendor account, no rate limit — just needs `ollama serve`
            running somewhere reachable. Default, because this is an open-
            source lab meant for learning, not a benchmark of answer
            quality: anyone who clones the repo should be able to run the
            agent chapter with nothing but `ollama pull <model>`.
  gemini  — Google's Interactions API (client.interactions.create), opt-in,
            for whoever wants the better answers a hosted frontier model
            gives and already has a GEMINI_API_KEY. Not a fallback Ollama
            flips to automatically on a Gemini outage — AGENT_BACKEND picks
            one backend for the run; there's no silent retry across them.
            See Chapter 16 for why automatic failover was considered and
            skipped.

Both backends share the same tool declarations and the same tool-execution
helper (_execute_tool) — only the wire format of "here are the tools" and
"here's what the model asked to run" differs between the two SDKs.
"""
import argparse
import json
import os
import sys

import requests

API_BASE = os.getenv("API_BASE_URL", "http://api:3000")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
GEMINI_TIMEOUT_MS = 60_000  # HttpOptions.timeout is milliseconds, not seconds —
# confirmed by inspecting the real installed SDK, not assumed. Without this,
# a stalled connection to Gemini's API hangs the whole script forever with
# zero output and zero error — exactly what "running forever, no output"
# looks like from the dashboard's log pane.

OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")
# host.docker.internal resolves to the Docker host from inside a container on
# Docker Desktop (Mac/Windows) for free. On Linux it needs the matching
# extra_hosts entry in docker-compose.yml (see the agent service there) — a
# plain host-run `ollama serve` is not on the "pipeline" bridge network AdLab's
# other services share, so this can't just be "ollama:11434" like a compose
# service name. Running analyst.py directly on the host (not in Docker), set
# OLLAMA_BASE_URL=http://localhost:11434 instead. See Chapter 16.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_TIMEOUT_S = float(os.getenv("OLLAMA_TIMEOUT_S", "120"))  # seconds, not ms —
# confirmed against the installed ollama 0.6.3 client (httpx underneath, which
# takes seconds). Generous on purpose: local CPU inference is routinely far
# slower than Gemini's cloud API, and a timeout that's merely "reasonable" for
# a hosted frontier model will clip a 7B model still mid-thought on a laptop.

REQUEST_TIMEOUT = 10
MAX_TOOL_TURNS = 6  # hard cap so a confused model can't loop forever


# ── Tools: thin wrappers around AdLab's own real endpoints ─────────────────
# Each one catches its own errors and returns a dict either way — a tool
# that raises would crash the whole agent loop over a single transient
# connection hiccup; returning {"error": ...} instead lets the model see
# the failure and react to it (or just say "the metrics API is unreachable").

def get_trending_ads(limit: int = 10) -> dict:
    try:
        r = requests.get(f"{API_BASE}/v1/metrics/trending", params={"limit": limit}, timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def get_ad_clicks(ad_id: str, from_ts: int, to_ts: int) -> dict:
    try:
        r = requests.get(
            f"{API_BASE}/v1/metrics/clicks",
            params={"ad_id": ad_id, "from": from_ts, "to": to_ts},
            timeout=REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        return {"error": str(e)}


def get_advertisers() -> dict:
    try:
        r = requests.get(f"{API_BASE}/v1/advertisers", timeout=REQUEST_TIMEOUT)
        r.raise_for_status()
        return {"advertisers": r.json()}
    except requests.RequestException as e:
        return {"error": str(e)}


TOOL_IMPLS = {
    "get_trending_ads": get_trending_ads,
    "get_ad_clicks": get_ad_clicks,
    "get_advertisers": get_advertisers,
}

# The single source of truth for tool schemas — Gemini's Interactions API
# takes this flat shape directly. Ollama wants a different (OpenAI-style,
# nested) shape; _ollama_tools() below repacks this rather than duplicating
# it, so the two backends can't quietly drift out of sync with each other.
TOOL_DECLARATIONS = [
    {
        "type": "function",
        "name": "get_trending_ads",
        "description": "Top ads by click count in the last 10 minutes.",
        "parameters": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "description": "Max number of ads to return"}},
            "required": [],
        },
    },
    {
        "type": "function",
        "name": "get_ad_clicks",
        "description": "Click count for one specific ad over a time range.",
        "parameters": {
            "type": "object",
            "properties": {
                "ad_id": {"type": "string", "description": "The ad's id, e.g. 'ad_42'"},
                "from_ts": {"type": "integer", "description": "Start of the range, Unix seconds"},
                "to_ts": {"type": "integer", "description": "End of the range, Unix seconds"},
            },
            "required": ["ad_id", "from_ts", "to_ts"],
        },
    },
    {
        "type": "function",
        "name": "get_advertisers",
        "description": "List every advertiser and their campaigns.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    },
]


def _ollama_tools() -> list:
    """
    Ollama's Python client (confirmed against the real installed 0.6.3
    package by inspecting ollama/_types.py, not assumed) wants the
    OpenAI-style nested shape: {"type": "function", "function": {"name",
    "description", "parameters"}} — Gemini's flat shape isn't accepted.
    TOOL_DECLARATIONS stays the one place these are defined; this just
    repacks it for the wire.
    """
    return [
        {
            "type": "function",
            "function": {
                "name": decl["name"],
                "description": decl["description"],
                "parameters": decl["parameters"],
            },
        }
        for decl in TOOL_DECLARATIONS
    ]


def _execute_tool(name: str, arguments: dict, log=print) -> dict:
    """Shared by both backends: look up the tool, run it, log call and result."""
    log(f"[tool call] {name}({arguments})")
    impl = TOOL_IMPLS.get(name)
    result = {"error": f"unknown tool: {name}"} if impl is None else impl(**arguments)
    log(f"[tool result] {json.dumps(result)[:300]}")
    return result


def _gemini_client():
    # Imported lazily, not at module top level: anything that only needs
    # TOOL_IMPLS/TOOL_DECLARATIONS/_execute_tool from this module (the MCP
    # server in mcp-server/, which reuses this file's tool logic without
    # running either agent loop) shouldn't have to install the Gemini SDK
    # just to import this one. See Chapter 15 and Chapter 16.
    from google import genai
    from google.genai import types
    return genai.Client(http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))


def _ollama_client():
    # Same reasoning as _gemini_client(): lazy, so importing this module
    # never requires the ollama package either, unless you actually use it.
    import ollama
    return ollama.Client(host=OLLAMA_BASE_URL, timeout=OLLAMA_TIMEOUT_S)


def run_gemini(client: "genai.Client", question: str, log=print) -> str:
    """
    The actual tool-calling loop: ask, execute whatever tools the model
    calls, send results back, repeat until the model answers in plain text
    or MAX_TOOL_TURNS is hit (whichever comes first — a hard cap, not a
    suggestion, so a confused model can't spin forever burning API calls).

    The initial question counts as the first turn — MAX_TOOL_TURNS bounds
    the TOTAL number of API calls this makes, not the number of additional
    calls after the first. (An earlier version got this wrong: the initial
    call sat outside the loop, so MAX_TOOL_TURNS=6 actually allowed 7 total
    calls. Caught by testing the cap directly, not by inspection.)
    """
    interaction = None
    previous_id = None
    next_input = question

    for _ in range(MAX_TOOL_TURNS):
        kwargs = {"model": GEMINI_MODEL, "input": next_input, "tools": TOOL_DECLARATIONS}
        if previous_id is not None:
            kwargs["previous_interaction_id"] = previous_id
        interaction = client.interactions.create(**kwargs)
        previous_id = interaction.id

        calls = [s for s in interaction.steps if s.type == "function_call"]
        if not calls:
            return interaction.output_text

        results_input = []
        for step in calls:
            result = _execute_tool(step.name, step.arguments, log)
            results_input.append({
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": json.dumps(result)}],
            })
        next_input = results_input

    return f"(stopped after {MAX_TOOL_TURNS} tool-call turns without a final answer — " \
           f"last raw output: {getattr(interaction, 'output_text', '') or '(none)'})"


def run_ollama(client: "ollama.Client", question: str, log=print) -> str:
    """
    Same loop as run_gemini(), reshaped for Ollama's chat() API: a running
    `messages` list instead of previous_interaction_id, and tool results fed
    back as plain {"role": "tool", ...} dict messages instead of a
    function_result step. Confirmed against the real installed ollama 0.6.3
    package (Client.chat, Message.tool_calls, ToolCall.function.arguments
    already parsed as a dict) rather than assumed from memory. See Chapter 16.
    """
    messages = [{"role": "user", "content": question}]
    tools = _ollama_tools()
    last_message = None

    for _ in range(MAX_TOOL_TURNS):
        response = client.chat(model=OLLAMA_MODEL, messages=messages, tools=tools)
        last_message = response.message
        messages.append(last_message.model_dump(exclude_none=True))

        if not last_message.tool_calls:
            return last_message.content or "(empty response)"

        for call in last_message.tool_calls:
            result = _execute_tool(call.function.name, dict(call.function.arguments), log)
            messages.append({
                "role": "tool",
                "tool_name": call.function.name,
                "content": json.dumps(result),
            })

    last_content = last_message.content if last_message else ""
    return f"(stopped after {MAX_TOOL_TURNS} tool-call turns without a final answer — " \
           f"last raw output: {last_content or '(none)'})"


def main():
    parser = argparse.ArgumentParser(description="AdLab read-only campaign analyst agent")
    parser.add_argument(
        "question", nargs="?",
        default="What's trending right now, and is there anything interesting about it?",
        help="The question to ask the agent",
    )
    args = parser.parse_args()

    backend = os.getenv("AGENT_BACKEND", "ollama").strip().lower()
    print(f"Question: {args.question}\n")

    try:
        if backend == "ollama":
            answer = run_ollama(_ollama_client(), args.question)
        elif backend == "gemini":
            if not os.getenv("GEMINI_API_KEY"):
                print("ERROR: GEMINI_API_KEY is not set. Copy .env.example to .env and add your key, "
                      "or unset AGENT_BACKEND / set it to 'ollama' to use the no-key default instead.")
                sys.exit(1)
            answer = run_gemini(_gemini_client(), args.question)
        else:
            print(f"ERROR: unknown AGENT_BACKEND '{backend}' — use 'ollama' (default) or 'gemini'.")
            sys.exit(1)
    except Exception as e:
        print(f"\n=== Error ===\n{type(e).__name__}: {e}")
        sys.exit(1)
    print(f"\n=== Answer ===\n{answer}")


if __name__ == "__main__":
    main()
