# Chapter 16 — The analyst agent, with Ollama as the default backend

## What you'll do

Give `agent/analyst.py` a second backend — a local model via [Ollama](https://ollama.com) — and
make it the *default*, with the original Gemini backend from the first version of this agent still
there as an explicit opt-in. Same three read-only tools (`get_trending_ads`, `get_ad_clicks`,
`get_advertisers`), same tool-calling loop shape, two different model SDKs underneath.

```bash
# Default: Ollama, no key needed. Needs a local model pulled first.
ollama pull qwen2.5:7b
docker compose --profile agent run --rm agent "What's trending right now?"

# Opt-in: Gemini, needs a key in .env (see .env.example).
AGENT_BACKEND=gemini docker compose --profile agent run --rm agent "What's trending right now?"
```

## Why default to a backend with worse answers

This started as a direct question: could Ollama be a *fallback* for Gemini's free tier, so an
outage on Google's side doesn't stop the agent from working? That's a reasonable instinct, and I
want to say plainly why I didn't build it that way.

A fallback needs a way to notice the primary has failed, and that's a surprising amount of
judgment to automate correctly: a slow response isn't the same as a dead one, a quota error isn't
the same as a network error, and retrying the same broken thing with a 2-second backoff isn't the
same as giving up on it for this run. Getting that logic *wrong* is worse than not having it —
silently falling back to a different model can turn "the API had a blip" into "the answer you got
was quietly produced by a different, weaker model, and nothing told you that." For a production
system that's worth building carefully. For a lab meant to teach MCP, Kafka, Spark and GitOps, it's
a third model-routing subsystem to maintain and debug, in service of a case (Gemini's free tier
having an outage) that's rare enough I'd be testing failover logic I can't actually trigger on
demand.

So: one backend answers each run, picked by `AGENT_BACKEND`, no silent retry across them. And
Ollama is the *default*, not the fallback, because of what this lab actually optimizes for —
anyone cloning it should be able to run the agent chapter with nothing but `ollama pull <model>`,
no API key, no vendor account, no rate limit to run into while learning. The tradeoff is real and
I'm not hiding it: a 7B local model will reason about "what's trending and why" less sharply than a
hosted frontier model. That's an acceptable trade for a lab whose purpose is "learn how tool-calling
and MCP work," not "get the most incisive ad analysis." If you want the sharper answers, Gemini is
one env var away — `AGENT_BACKEND=gemini`, same three tools, same questions.

## The two SDKs don't agree on tool shape

The existing Gemini backend already had a `TOOL_DECLARATIONS` list — a flat shape:

```python
{"type": "function", "name": "get_trending_ads", "description": "...", "parameters": {...}}
```

I installed the real `ollama` package (0.6.3) in a scratch venv and read its source directly
(`ollama/_types.py`, `ollama/_client.py`) rather than assume its shape matched, since the two
SDKs are unrelated projects. They don't match: Ollama's `chat()` wants the OpenAI-style *nested*
shape —

```python
{"type": "function", "function": {"name": "get_trending_ads", "description": "...", "parameters": {...}}}
```

Rather than keep two hand-written tool lists that could drift apart the first time someone adds a
tool and only updates one of them, `TOOL_DECLARATIONS` stays the single source of truth and a new
`_ollama_tools()` repacks it into the nested shape at call time. Same for tool execution: both
backends' loops now call a shared `_execute_tool(name, arguments, log)` helper instead of each
having its own copy of "look up the function, call it, log the call and result."

The response shapes differ too. Gemini's Interactions API gives you `interaction.steps`, filtered
for `step.type == "function_call"`, with `step.arguments` as a dict and `step.id` as the call
reference for the result you send back. Ollama's `chat()` gives you a `ChatResponse.message`, whose
`tool_calls` is a list of `ToolCall(function=Function(name, arguments))` — `arguments` already a
parsed dict, no JSON-string unwrapping needed — and there's no call-id round-trip at all: a tool
result goes back as a plain `{"role": "tool", "tool_name": ..., "content": ...}` message appended
to the same running `messages` list the whole conversation lives in. That's the other reason the
two backends keep separate `run_gemini()` / `run_ollama()` functions rather than one "generic" loop
forced to paper over both shapes — the control flow (`previous_interaction_id` vs. a growing
message list) is genuinely different, not just a formatting detail.

## `host.docker.internal`, and why it needs a line in `docker-compose.yml`

The agent runs *in* the compose network; Ollama runs on the host, started by hand (or by
`./start.sh`, see Chapter 15's `check_ollama()`) — it's deliberately not containerized here, since
most people run Ollama natively for GPU access. So the agent container needs to reach out of the
Docker network to the host, which is exactly what `host.docker.internal` is for.

On Docker Desktop (Mac, Windows) that hostname just works — the daemon wires it up for you. On
Linux (Docker Engine, no Desktop) it doesn't exist unless you ask for it, which is what this line in
the `agent` service does:

```yaml
extra_hosts:
  - "host.docker.internal:host-gateway"
```

`host-gateway` is a special value Docker Compose resolves to the actual host IP at container start
— not a literal string you'd type into `/etc/hosts` yourself. It's a no-op to include on Desktop
(the mapping is already there; this just adds a second, identical one), so one line in the compose
file covers both platforms rather than branching on which Docker the reader has.

`OLLAMA_BASE_URL` defaults to `http://host.docker.internal:11434` for exactly this reason. If
you're running `analyst.py` directly on the host instead of through `docker compose run`
(nothing stops you — it's one Python file with two pip installs), `host.docker.internal` won't
resolve outside a container at all, so set `OLLAMA_BASE_URL=http://localhost:11434` in that case.

## Timeouts: local inference is not cloud-API-fast

The existing Gemini backend already had a hard-won timeout constant (`GEMINI_TIMEOUT_MS`, discovered
in the earlier version of this chapter the hard way — a stalled connection hung the whole script
forever with no output and no error). Ollama's client takes its timeout in **seconds**, not
milliseconds — confirmed by reading `BaseClient.__init__` in the installed package, which passes
`timeout` straight to `httpx`. I set `OLLAMA_TIMEOUT_S` generously (120s, overridable) rather than
reusing a value tuned for a hosted API: a 7B model doing multi-step tool reasoning on a laptop CPU
is routinely much slower than Gemini's cloud endpoint, and a timeout that's merely "reasonable" for
one is stingy for the other.

## What I could verify here, and what needs your machine

This chapter's sandbox has no Docker daemon reachable for a real `docker compose run`, and
critically, **no `ollama` binary at all** — there's no local model to actually talk to. So the line
between "verified" and "should work, confirm it yourself" is sharper here than in most other
chapters.

**Verified by running it (in this sandbox, against the real installed `ollama` 0.6.3 package):**

- `agent/analyst.py` imports cleanly with *neither* `google-genai` nor `ollama` installed — both
  SDK imports are lazy now, loaded only inside `_gemini_client()` / `_ollama_client()`, never at
  module level.
- `mcp-server/server.py` starts and imports `analyst.py` successfully with only `mcp` and
  `requests` installed — the "dependency that does nothing" cost from Chapter 15 is gone; verified
  by actually running it with those two packages alone in a fresh venv, not by inspection.
- `_ollama_tools()` produces the exact nested shape `ollama.Client.chat()` expects, built from
  `TOOL_DECLARATIONS` with no hand-duplicated second list.
- `run_ollama()`'s loop, built against the real `ollama.Message` / `ollama.ChatResponse` classes
  (not mocks of my own invention) with a fake `Client.chat()` standing in for the network call:
  correctly extracts `tool_calls`, executes the right tool with the right (already-parsed-dict)
  arguments, appends the assistant turn via `message.model_dump(exclude_none=True)`, feeds the
  result back as a `role: "tool"` message, and returns the model's final text once there are no
  more tool calls.
- The `MAX_TOOL_TURNS` cap: a fake client that always calls a tool and never gives a final answer
  is stopped at exactly 6 calls, not 7 — the same off-by-one this project's Gemini loop had to
  fix once already, checked again here rather than assumed inherited.
- `run_gemini()` (renamed from the old `run()`, logic otherwise unchanged beyond sharing
  `_execute_tool()`) still produces the correct answer against a fake Gemini-shaped client.

**Not verified here — needs a real run on a machine with Docker and Ollama installed:**

- An actual local model (`qwen2.5:7b` or whatever you pull) producing a sensible tool call and a
  sensible final answer, as opposed to the fake client standing in for one above.
- `host.docker.internal:host-gateway` actually resolving from inside a real container to a real
  host-run `ollama serve`, on both Linux and Docker Desktop.
- `docker compose --profile agent run --rm agent` actually building the image with the new
  `ollama==0.6.3` dependency and running end to end.
- Whether 120 seconds is actually enough — or more than needed — for your specific model and
  machine. If you hit the timeout, that's `OLLAMA_TIMEOUT_S` to raise, not a bug to report.

If you run this for real, the gap this chapter leaves is exactly that last list — worth confirming
once and moving on, same as the `ollmcp` test in Chapter 15 was the one thing that sandbox couldn't
do either.

## What's next

Path B — a separate repo demonstrating the agent-governance layer itself (written rules and specs,
composable skills, a hand-built minimal agentic loop with its failure modes documented on purpose)
— is still queued, and deliberately not part of AdLab.
