#!/usr/bin/env python3
"""
AdLab MCP server — read-only analytics tools over stdio, MCP spec 2026-07-28.

Re-exposes the three tools the Gemini analyst agent already uses
(agent/analyst.py) through the Model Context Protocol. The query logic is NOT
reimplemented: the tool bodies here call the agent's own functions, imported
as-is. This file only adds the protocol surface.

Spec notes (2026-07-28, stateless):
  - No initialize handshake and no session: every request carries its own
    protocol version / client info in _meta. The SDK handles that framing;
    this server holds no per-connection state at all.
  - server/discover is implemented by the SDK from the name/version/
    instructions below.
  - tools/list is deterministic (registered in alphabetical order) and carries
    ttlMs/cacheScope hints (cache_hints below).
  - stdio: stdout is the protocol channel and nothing else may write to it, so
    all logging goes to stderr.

Config: ADLAB_API_URL (default http://localhost:3000) — where AdLab's API is
reachable *from this process*. (The agent's own default, http://api:3000, only
resolves inside the compose network.)
"""
import logging
import os
import sys

# agent/analyst.py reads API_BASE_URL at import time, so set it first.
os.environ["API_BASE_URL"] = os.getenv("ADLAB_API_URL", "http://localhost:3000")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agent"))

import analyst  # noqa: E402  (the existing agent module, unmodified)
from mcp.server.caching import CacheHint  # noqa: E402
from mcp.server.mcpserver import MCPServer  # noqa: E402
from mcp_types import ToolAnnotations  # noqa: E402

# Never print() in this process — stdout belongs to the protocol.
logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="[adlab-mcp] %(message)s")

mcp = MCPServer(
    name="adlab",
    version="0.1.0",
    title="AdLab analytics",
    instructions=(
        "Read-only access to AdLab's live ad-click analytics. Tool results are "
        "JSON; on upstream failure a tool returns {\"error\": ...} rather than raising."
    ),
    # The tool list is static for the life of the process, so it's safe to
    # cache for a while. 'public': nothing in it varies by caller.
    cache_hints={
        "server/discover": CacheHint(ttl_ms=300_000, scope="public"),
        "tools/list": CacheHint(ttl_ms=300_000, scope="public"),
    },
)

_READ_ONLY = ToolAnnotations(read_only_hint=True, idempotent_hint=True, open_world_hint=False)


# Registered alphabetically on purpose: the spec says servers SHOULD return
# tools/list in a deterministic order, and registration order is what the SDK
# uses. Keep this order when adding tools.

@mcp.tool(annotations=_READ_ONLY)
def get_ad_clicks(ad_id: str, from_ts: int, to_ts: int) -> dict:
    """Click count for one specific ad over a time range (Unix seconds)."""
    return analyst.get_ad_clicks(ad_id, from_ts, to_ts)


@mcp.tool(annotations=_READ_ONLY)
def get_advertisers() -> dict:
    """List every advertiser and their campaigns."""
    return analyst.get_advertisers()


@mcp.tool(annotations=_READ_ONLY)
def get_trending_ads(limit: int = 10) -> dict:
    """Top ads by click count in the last 10 minutes."""
    return analyst.get_trending_ads(limit)


if __name__ == "__main__":
    logging.info("starting on stdio, upstream %s", analyst.API_BASE)
    mcp.run("stdio")
