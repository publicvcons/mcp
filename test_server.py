#!/usr/bin/env python3
"""Smoke test for the PublicVCons MCP server over real stdio.

Spawns server.py as an MCP stdio server, lists tools/resources, calls
every tool against the committed corpus, reads a resource, and checks
the bad-uuid error path. Exit 0 = all good.

  ~/venvs/tools/bin/python seed/mcp/test_server.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

HERE = Path(__file__).resolve().parent
SERVER = str(HERE / "server.py")
CORPUS = os.environ.get("PVCONS_CORPUS", str(HERE.parent / "vcons"))


def payload(res):
    sc = getattr(res, "structuredContent", None)
    if isinstance(sc, dict) and set(sc.keys()) == {"result"}:
        return sc["result"]
    if sc is not None:
        return sc
    return json.loads(res.content[0].text)


async def main() -> int:
    params = StdioServerParameters(
        command=sys.executable, args=[SERVER],
        env={**os.environ, "PVCONS_CORPUS": CORPUS})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = {t.name for t in (await s.list_tools()).tools}
            need = {"list_recent", "search_vcons", "get_vcon",
                    "get_lifecycle_receipts", "summarize_for_topic",
                    "verify_vcon"}
            assert need <= tools, f"missing tools: {need - tools}"

            rows = payload(await s.call_tool("list_recent",
                                             {"limit": 5}))
            assert rows, "list_recent returned nothing"
            uuid = rows[0]["uuid"]

            hits = payload(await s.call_tool(
                "search_vcons", {"query": "Lundgren law.gov"}))
            assert hits and hits[0]["score"] > 0, "search failed"

            sm = payload(await s.call_tool(
                "summarize_for_topic",
                {"topic": "open government access", "limit": 2}))
            assert sm and sm[0]["neutral_editorial_summary"]

            g = payload(await s.call_tool("get_lifecycle_receipts",
                                          {"uuid": uuid}))
            assert len(g["statements"]) == 5 and len(g["receipts"]) == 5

            v = payload(await s.call_tool("verify_vcon",
                                          {"uuid": uuid}))
            assert v["verified"] is True, f"verify_vcon: {v}"

            body = json.loads((await s.read_resource(
                f"vcon://v1/vcons/{uuid}/summary")).contents[0].text)
            assert len(body) == 1, "summary resource"

            full = payload(await s.call_tool("get_vcon",
                                             {"uuid": uuid}))
            assert full["vcon"] == "0.4.0" and len(full["parties"]) == 4

            bad = await s.call_tool("get_vcon",
                                    {"uuid": "does-not-exist"})
            assert bad.isError, "bad uuid should be an error result"

    print(f"MCP server smoke test: PASS ({len(tools)} tools, "
          "verify_vcon OK, error path OK)")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
