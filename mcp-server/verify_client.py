#!/usr/bin/env python3
"""
Verify the AdLab MCP server end to end, against the LIVE stack.

Part 1 — raw wire check: spawn the server and talk newline-delimited JSON-RPC
to it by hand, with no SDK in the way, to show what 2026-07-28 looks like on
the wire (no initialize; server/discover; per-request _meta).
Part 2 — SDK client: connect with the official client, assert it negotiated
2026-07-28 (not the legacy handshake), list tools, call every tool.

Usage: ADLAB_API_URL=http://localhost:3000 .venv/bin/python verify_client.py
Exits non-zero on any failed assertion.
"""
import asyncio
import json
import os
import subprocess
import sys
import time

from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
SERVER = os.path.join(HERE, "server.py")
VERSION = "2026-07-28"
META = {
    "io.modelcontextprotocol/protocolVersion": VERSION,
    "io.modelcontextprotocol/clientInfo": {"name": "verify-client", "version": "0"},
    "io.modelcontextprotocol/clientCapabilities": {},
}


def show(title, obj):
    print(f"\n--- {title} ---")
    print(json.dumps(obj, indent=2, default=str)[:1800])


def raw_wire_check():
    print("=== Part 1: raw JSON-RPC over stdio, no SDK, no handshake ===")
    p = subprocess.Popen([PY, SERVER], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, env=os.environ)

    def rpc(i, method, params=None):
        msg = {"jsonrpc": "2.0", "id": i, "method": method,
               "params": {**(params or {}), "_meta": META}}
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()
        return json.loads(p.stdout.readline())

    d = rpc(1, "server/discover")
    show("server/discover response", d)
    assert d["result"]["supportedVersions"] and VERSION in d["result"]["supportedVersions"]
    assert d["result"]["resultType"] == "complete"
    assert d["result"]["ttlMs"] > 0 and d["result"]["cacheScope"] == "public"

    # First and only request the server ever sees before this: discover. No
    # initialize, no session id — tools/list works straight away.
    t = rpc(2, "tools/list")
    names = [x["name"] for x in t["result"]["tools"]]
    show("tools/list response (names + cache hints)",
         {"names": names, "ttlMs": t["result"].get("ttlMs"), "cacheScope": t["result"].get("cacheScope"),
          "resultType": t["result"].get("resultType")})
    assert names == sorted(names), "tools/list must be deterministic"
    assert t["result"]["ttlMs"] > 0 and t["result"]["cacheScope"] == "public"

    p.stdin.close()
    p.wait(timeout=10)
    err = p.stderr.read()
    print("\n--- server stderr (logs go here, not stdout) ---\n" + err.strip())
    assert p.returncode == 0, f"server should exit cleanly on stdin EOF, got {p.returncode}"
    print("\nserver exited cleanly on stdin EOF (rc=0)")


async def sdk_check():
    print("\n=== Part 2: official SDK client ===")
    params = StdioServerParameters(command=PY, args=[SERVER], env=dict(os.environ))
    async with Client(params) as c:
        print(f"negotiated protocol version: {c.protocol_version}")
        print(f"server_info: {c.server_info}")
        print(f"instructions: {c.instructions}")
        assert c.protocol_version == VERSION, "client fell back to a legacy handshake!"

        tools = await c.list_tools()
        print(f"tools/list -> {[t.name for t in tools.tools]} ttl_ms={tools.ttl_ms} scope={tools.cache_scope}")

        def payload(res):
            assert not res.is_error, res
            return res.structured_content if res.structured_content is not None else json.loads(res.content[0].text)

        r = payload(await c.call_tool("get_advertisers", {}))
        show("get_advertisers", r)
        assert "error" not in r and len(r["advertisers"]) > 0

        r = payload(await c.call_tool("get_trending_ads", {"limit": 5}))
        show("get_trending_ads(limit=5)", r)
        assert "error" not in r
        ads = r.get("ads", [])
        assert ads, "no trending ads — did the pipeline ingest clicks in the last 10 minutes?"

        ad_id = ads[0].get("ad_id") or ads[0].get("adId") or ads[0].get("id")
        now = int(time.time())
        r = payload(await c.call_tool("get_ad_clicks", {"ad_id": ad_id, "from_ts": now - 3600, "to_ts": now}))
        show(f"get_ad_clicks({ad_id}, last hour)", r)
        assert "error" not in r

        # An argument-validation failure should surface as a tool error, not crash the server.
        bad = await c.call_tool("get_ad_clicks", {"ad_id": ad_id})
        print(f"\nmissing-args call -> is_error={bad.is_error}: {bad.content[0].text[:200]}")
        assert bad.is_error


if __name__ == "__main__":
    raw_wire_check()
    asyncio.run(sdk_check())
    print("\nALL CHECKS PASSED")
