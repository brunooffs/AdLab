#!/usr/bin/env python3
"""
analyst.py — a read-only campaign analyst agent.

Ask it a question in plain English; it calls AdLab's own real endpoints as
tools, reasons over the real data, and prints a synthesized answer. Nothing
here writes anything — every tool is a GET against an endpoint that already
exists, so the worst this can do is read wrong data, never change any.

Uses Gemini's Interactions API (client.interactions.create), the current
recommended pattern as of the google-genai SDK — not the older
generate_content/chat-session style, and not the deprecated
google-generativeai package.
"""
import argparse
import json
import os
import sys

import requests
from google import genai
from google.genai import types

API_BASE = os.getenv("API_BASE_URL", "http://api:3000")
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
REQUEST_TIMEOUT = 10
MAX_TOOL_TURNS = 6  # hard cap so a confused model can't loop forever
GEMINI_TIMEOUT_MS = 60_000  # HttpOptions.timeout is milliseconds, not seconds —
# confirmed by inspecting the real installed SDK, not assumed. Without this,
# a stalled connection to Gemini's API hangs the whole script forever with
# zero output and zero error — exactly what "running forever, no output"
# looks like from the dashboard's log pane.


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


def run(client: "genai.Client", question: str, log=print) -> str:
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
        kwargs = {"model": MODEL, "input": next_input, "tools": TOOL_DECLARATIONS}
        if previous_id is not None:
            kwargs["previous_interaction_id"] = previous_id
        interaction = client.interactions.create(**kwargs)
        previous_id = interaction.id

        calls = [s for s in interaction.steps if s.type == "function_call"]
        if not calls:
            return interaction.output_text

        results_input = []
        for step in calls:
            log(f"[tool call] {step.name}({step.arguments})")
            impl = TOOL_IMPLS.get(step.name)
            result = {"error": f"unknown tool: {step.name}"} if impl is None else impl(**step.arguments)
            log(f"[tool result] {json.dumps(result)[:300]}")
            results_input.append({
                "type": "function_result",
                "name": step.name,
                "call_id": step.id,
                "result": [{"type": "text", "text": json.dumps(result)}],
            })
        next_input = results_input

    return f"(stopped after {MAX_TOOL_TURNS} tool-call turns without a final answer — " \
           f"last raw output: {getattr(interaction, 'output_text', '') or '(none)'})"


def main():
    parser = argparse.ArgumentParser(description="AdLab read-only campaign analyst agent")
    parser.add_argument(
        "question", nargs="?",
        default="What's trending right now, and is there anything interesting about it?",
        help="The question to ask the agent",
    )
    args = parser.parse_args()

    if not os.getenv("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY is not set. Copy .env.example to .env and add your key.")
        sys.exit(1)

    client = genai.Client(http_options=types.HttpOptions(timeout=GEMINI_TIMEOUT_MS))
    print(f"Question: {args.question}\n")
    try:
        answer = run(client, args.question)
    except Exception as e:
        print(f"\n=== Error ===\n{type(e).__name__}: {e}")
        sys.exit(1)
    print(f"\n=== Answer ===\n{answer}")


if __name__ == "__main__":
    main()
