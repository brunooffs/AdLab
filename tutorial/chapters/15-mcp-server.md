# Chapter 15 — An MCP server for AdLab (the 2026-07-28 stateless spec)

## What you'll do

Take the three read-only tools the Gemini analyst agent already uses (`get_trending_ads`,
`get_ad_clicks`, `get_advertisers`) and expose them through the Model Context Protocol, so *any*
MCP client — not just my one script — can query live AdLab data. Then prove it works by talking to
it twice: once with hand-written JSON-RPC, once with the official SDK client.

```bash
cd mcp-server
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
ADLAB_API_URL=http://localhost:3000 .venv/bin/python verify_client.py
```

Nothing here touches `agent/`. The Gemini experiment is exactly as it was.

## What MCP actually is

The agent in `agent/analyst.py` has its tools wired directly into one specific model's SDK: a list
of Gemini-shaped function declarations, a dict mapping names to Python functions, a loop that
shuttles results back. Swap Gemini for something else and all of that is rewritten.

MCP is the attempt to make that seam a standard. A *server* says "here are my tools, here's the
JSON Schema for each one's arguments"; a *client* (Claude Desktop, an IDE, someone else's agent)
discovers them and calls them. The protocol itself is just JSON-RPC 2.0 messages. Over **stdio**,
which is what I used, the client launches the server as a subprocess and the two exchange one JSON
message per line over stdin/stdout. That's the whole transport. It's why "point your own MCP client
at this" is a realistic demo: the client only needs a command to run.

## Why this chapter targets 2026-07-28, specifically

The MCP spec had its biggest rewrite since launch on 2026-07-28. Nearly everything I'd have
written from habit — and most public tutorials — describe the older protocol, where a connection
begins with an `initialize` request, the client replies `notifications/initialized`, and (over HTTP)
the server hands out an `Mcp-Session-Id` that every later request must carry. I didn't want a
tutorial chapter that teaches a pattern already removed.

I did not take that on faith either — including from the task description that started this
chapter. I read the spec changelog directly (`modelcontextprotocol.io/specification/2026-07-28/
changelog`, plus the stdio and `server/discover` pages) and confirmed these, in practice:

- **No handshake, no session.** Each request is self-describing: it carries
  `io.modelcontextprotocol/protocolVersion`, `.../clientInfo` and `.../clientCapabilities` in its own
  `_meta`. A server doesn't need to remember anything about a client between requests.
- **`server/discover` is mandatory** for servers. It returns `supportedVersions`, `capabilities`,
  and the server's identity (as `_meta["io.modelcontextprotocol/serverInfo"]`).
- **Every result has `resultType`** (`"complete"` or `"input_required"`).
- **`tools/list` should be deterministic** and carries `ttlMs` / `cacheScope` hints.
- **Roots, Sampling and Logging are deprecated.** I use none of them. On stdio, logs go to stderr.
- If I ever needed cross-call state, the spec's answer is an explicit handle the server returns and
  the client passes back as a normal tool argument. These tools are pure reads, so they don't need
  it, and I didn't invent a use for it.

In practice, "stateless" made the server *smaller*, not bigger: there is no connection object, no
session table, nothing to clean up. The server file is three decorated functions.

### SDK version, checked rather than assumed

The latest `mcp` on PyPI is **2.3.0**; the 1.x line (up to 1.30.0) is still there. I installed 2.3.0
and checked it against the spec instead of trusting the version number: its source has a dedicated
2026-07-28 HTTP path, a built-in `server/discover` handler, `CacheHint` support for `ttlMs`/
`cacheScope`, and a client whose default mode probes `server/discover` and only falls back to
`initialize` for legacy servers. The wire output further down is the real proof. Two caveats I
noticed along the way: the SDK still carries the legacy handshake for compatibility (a `TODO` in
`mcp/server/runner.py` says as much), and `supportedVersions` from my server lists *only*
`2026-07-28` — so an older client that can't speak it won't be able to connect. That's the honest
price of building against the current spec only.

## Why re-use the agent's tool logic instead of rewriting it

Those three functions in `analyst.py` already encode things I learned the hard way: the endpoints and
their parameter names (`from`/`to`, not `from_ts`), a request timeout so a stalled API can't hang the
caller forever, and the decision to catch `requests` errors and *return* `{"error": ...}` rather
than raise. Rewriting them for MCP would mean re-deriving all of that, and creating a second copy
that drifts the first time someone fixes a bug in one of them.

So `mcp-server/server.py` imports `analyst` and its tool bodies are one-liners that call the
originals:

```python
@mcp.tool(annotations=_READ_ONLY)
def get_advertisers() -> dict:
    """List every advertiser and their campaigns."""
    return analyst.get_advertisers()
```

This has real costs, and I'd rather say so than pretend it's free:

1. **A dependency that does nothing.** `analyst.py` imports `google.genai` at the top, so merely
   importing it requires `google-genai` to be installed — even though the MCP server never talks to
   Gemini and needs no API key. `mcp-server/requirements.txt` pins it with a comment. The clean fix is
   splitting the HTTP tool functions out of `analyst.py` into a shared module, but that means editing
   the working agent, which this chapter deliberately doesn't do. If you ever do that refactor,
   `server.py` shrinks to just its import line changing.
2. **Config is read at import time.** `analyst.py` reads `API_BASE_URL` once, when imported, and
   defaults to `http://api:3000` — a hostname that only exists *inside* the compose network. So
   `server.py` sets `API_BASE_URL` (from `ADLAB_API_URL`, default `http://localhost:3000`) *before*
   the import. Get that order wrong and the server starts happily, then fails every call.
3. **Upstream failures aren't protocol errors.** Because the agent's functions return
   `{"error": ...}` instead of raising, a dead API shows up to the MCP client as a *successful* tool
   call whose payload contains an error string (`is_error=False`). I checked this by pointing the
   server at a closed port. For an LLM client that's arguably fine — it reads the text and reacts, which is
   exactly what the agent wanted — but a strict programmatic client would have to inspect the body.
   I left it, since changing it would mean the two front-ends disagree about what a failure is.

## Standing it up

The server is `mcp-server/server.py`, built on the SDK's `MCPServer` class. The parts that are about
the spec rather than the tools:

```python
mcp = MCPServer(
    name="adlab", version="0.1.0", title="AdLab analytics",
    instructions="Read-only access to AdLab's live ad-click analytics. ...",
    cache_hints={
        "server/discover": CacheHint(ttl_ms=300_000, scope="public"),
        "tools/list":      CacheHint(ttl_ms=300_000, scope="public"),
    },
)
```

- The tools are registered **alphabetically on purpose**. The SDK lists tools in registration order,
  and the spec asks for deterministic ordering, so "keep them sorted" is the rule that guarantees it.
  The test asserts it.
- All three carry `read_only_hint=True`. That's an *annotation* — a hint to clients — not an
  enforcement; the real guarantee that nothing writes is that the underlying functions only `GET`.
- `logging.basicConfig(stream=sys.stderr, ...)`. On stdio, stdout *is* the protocol; one stray
  `print()` corrupts the stream. Every log line goes to stderr.

## Querying it for real

Stack: the core profile plus `streaming`, then the Spark job and a batch of events so
"trending" has something to report (`./start.sh streaming`, `./spark.sh`, `./produce.sh 600 40`).
`verify_client.py` does two things.

**Part 1 is raw wire protocol, no SDK.** It spawns the server and writes JSON lines to its stdin. The
very first message it ever sends is `server/discover`:

```json
{"jsonrpc":"2.0","id":1,"method":"server/discover","params":{"_meta":{
  "io.modelcontextprotocol/protocolVersion":"2026-07-28",
  "io.modelcontextprotocol/clientInfo":{"name":"verify-client","version":"0"},
  "io.modelcontextprotocol/clientCapabilities":{}}}}
```

and what came back (real output, from `mcp-server/verify_output.txt`):

```
"result": {
  "cacheScope": "public",
  "resultType": "complete",
  "supportedVersions": ["2026-07-28"],
  "ttlMs": 300000,
  "instructions": "Read-only access to AdLab's live ad-click analytics. ...",
  "_meta": {"io.modelcontextprotocol/serverInfo": {"name": "adlab", "title": "AdLab analytics", "version": "0.1.0"}}
}
```

Then `tools/list` straight away, with no `initialize` ever sent — and it works, which is the stateless
claim demonstrated rather than asserted:

```
{"names": ["get_ad_clicks", "get_advertisers", "get_trending_ads"],
 "ttlMs": 300000, "cacheScope": "public", "resultType": "complete"}
```

Then it closes stdin and checks the server exits with code 0 — the spec says servers should exit on
stdin EOF.

**Part 2 uses the official SDK client** and asserts it negotiated `2026-07-28` rather than silently
falling back to the legacy handshake (the client's default mode would do exactly that against an old
server, so without the assertion a "pass" could mean nothing). Then it calls every tool against the
live API:

```
negotiated protocol version: 2026-07-28
tools/list -> ['get_ad_clicks', 'get_advertisers', 'get_trending_ads'] ttl_ms=300000 scope=public

--- get_trending_ads(limit=5) ---
{"as_of": "2026-11-18T00:35:57.297Z",
 "ads": [{"ad_id": "ad_cmuyb1yg_002", "clicks": 8}, {"ad_id": "ad_cmuycs4k_001", "clicks": 8},
         {"ad_id": "ad_cmus7z8x_002", "clicks": 7}, ...]}

--- get_ad_clicks(ad_cmuyb1yg_002, last hour) ---
{"ad_id": "ad_cmuyb1yg_002", "from": 1794958557, "to": 1794962157, "clicks": 8,
 "as_of": "2026-11-18T00:35:57.331Z", "breakdown": {"confirmed": 8, "in_progress": 0}}

missing-args call -> is_error=True: Error executing tool get_ad_clicks: 2 validation errors ...
ALL CHECKS PASSED
```

`get_advertisers` returned the real advertiser list (full output in
`verify_output.txt`). The `ad_id` passed to `get_ad_clicks` is taken from the trending result, so
that call is chained off real data rather than a hardcoded id. Note the last check: a call with
missing arguments comes back as a *protocol-level tool error* — argument validation comes from the
JSON Schema the SDK derived from the Python type hints, so I didn't write any of it.

## What went wrong on the way

Not everything was a straight line, and the cheap-to-fix failures are the useful ones.

- **Docker wasn't running.** The first `docker compose` call failed with "cannot connect to the
  Docker daemon." Obvious in hindsight; starting Docker Desktop and waiting for `docker info` to
  succeed fixed it.
- **Port 3000 was taken — by something that wasn't AdLab.** `start.sh` brought up everything except
  `api`: `bind: address already in use`. `lsof` showed a `node server.js` from a completely unrelated
  project on my machine. `curl localhost:3000/v1/metrics/trending` returned an Express "Cannot GET"
  page — the kind of failure that looks like "AdLab is broken" when it's really "wrong server."
  I didn't kill it (it wasn't mine to kill); I ran the AdLab API on host port 3100 with a throwaway
  compose override and pointed `ADLAB_API_URL` at that. That's the entire reason `ADLAB_API_URL` is
  configurable rather than hardcoded.
- **`server/discover` first came back with `ttlMs: 0` and `cacheScope: "private"`.** I'd set a cache
  hint only for `tools/list`. The raw JSON in Part 1 showed discover's defaults — the spec gives
  `server/discover` the same cache fields, and the SDK accepts a hint for it too. One more entry
  in `cache_hints`, and the test now asserts it.
- **A capability oddity I haven't fixed.** In that same discover response, `capabilities` advertises
  `prompts.listChanged`, `resources.listChanged` and `resources.subscribe`, even though this server
  defines no prompts or resources. It's harmless to the client I tested with, but it's the SDK's
  default for `MCPServer`, not something I chose, and it's slightly misleading advertising. If you
  care, that's the next thing to tighten.

## What I could verify, and what I couldn't

**Verified by running it:** server starts over stdio; `server/discover` and `tools/list` work with no
handshake and no session (raw JSON-RPC); the official SDK client negotiates 2026-07-28; all three
tools return live data from the real API running in the compose stack; argument
validation failures are reported as tool errors; the unreachable-API path returns the agent's
`{"error": ...}` payload; the server exits 0 on stdin EOF; `agent/` is unmodified.

**Not verified:**

- **A real third-party client.** I never connected Claude Desktop, an IDE, or anyone else's MCP
  client. Everything above is my own raw script plus the SDK's own client — which is the same SDK
  family as the server, so it could share a misreading of the spec that an independent client
  wouldn't. The raw Part 1 check is the partial defence (I wrote the messages from the spec text, not
  from the SDK), but it isn't independent proof. If you try Claude Desktop and it disagrees, believe it.
- **Version-mismatch behavior.** The spec says a server should answer an unsupported
  `protocolVersion` with `UnsupportedProtocolVersionError` (code `-32022`). I didn't send one.
- **The `draft` spec.** I confirmed nothing dated is newer than 2026-07-28, but I didn't read the
  unreleased `draft/` revision.
- **HTTP transport**, and anything about auth. Stdio only.
- **Spec reading went through a summarizing fetch tool**, which at one point contradicted the page it
  had just quoted (it claimed the stdio and discover pages didn't exist). I re-read those pages
  directly, but the usual caveat about second-hand reading applies. Check the changelog yourself.

## Trying it with your own client

An MCP client config entry is just the command to launch (shown in the common `mcpServers` JSON
shape; I did not test this in any client):

```json
{
  "mcpServers": {
    "adlab": {
      "command": "/absolute/path/to/mcp-server/.venv/bin/python",
      "args": ["/absolute/path/to/mcp-server/server.py"],
      "env": { "ADLAB_API_URL": "http://localhost:3000" }
    }
  }
}
```

Use the venv's Python by absolute path — a client launching `python` bare won't have the SDK. The
stack has to be up, and `produce.sh` + `spark.sh` have to have run recently, or `get_trending_ads`
will honestly return an empty list (trending covers only the last 10 minutes; I saw exactly that
before producing events).

## What's next

Chapter 13 is still ahead: a real bug, deliberately reintroduced, no chapter number telling you where
to look.
