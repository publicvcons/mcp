#!/usr/bin/env python3
"""PublicVCons MCP server (FastMCP, Python).

A thin, read-only facade over the publicvcons/vcons corpus — the same
vcon JSON the web viewer serves. No database (PROTOTYPE_PLAN.md §7):
the corpus directory *is* the store.

The upstream vcon-dev/vcon-mcp server is TypeScript + Supabase, which
conflicts with this project's FastMCP-Python / no-DB mandate, so this
is a fresh implementation that stays *contract-compatible*: tool names
(`get_vcon`, `search_vcons`, `list_recent`) and the `vcon://v1/...`
resource URIs match upstream so existing clients work, plus the
project-specific tools the plan calls for (`get_lifecycle_receipts`,
`summarize_for_topic`, `verify_vcon`).

Corpus location (first that exists wins, override with PVCONS_CORPUS):
  $PVCONS_CORPUS                         explicit dir
  /Volumes/publicvcons/data              canonical local drive
  <repo>/../vcons  and  ./seed/vcons     dev checkouts

Run:  ~/venvs/tools/bin/python server.py        # stdio (Claude/MCP)
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

REPO = Path(__file__).resolve().parent


def _find_corpus() -> Path:
    cands = []
    if os.environ.get("PVCONS_CORPUS"):
        cands.append(Path(os.environ["PVCONS_CORPUS"]))
    cands += [
        Path("/Volumes/publicvcons/data"),
        REPO.parent / "vcons",
        REPO.parent / "seed" / "vcons",
    ]
    for c in cands:
        if c.is_dir() and any(c.rglob("vcon.json")):
            return c
    # last resort: still return the first preference so errors are clear
    return cands[0] if cands else Path("/Volumes/publicvcons/data")


CORPUS = _find_corpus()
SCITT_CLI = REPO.parent / "scitt" / "cli" / "pvcons_scitt.py"
SCITT_SIGN = REPO.parent / "conserver" / "pipeline" / "scitt_sign.py"
PY = sys.executable

mcp = FastMCP("publicvcons")


# --------------------------------------------------------------------------
# corpus index (built lazily, refreshable)
# --------------------------------------------------------------------------
_INDEX: dict[str, dict[str, Any]] | None = None


def _vcon_dir(uuid: str) -> Path | None:
    e = _index().get(uuid)
    return Path(e["dir"]) if e else None


def _load(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def _entry(vp: Path) -> dict[str, Any]:
    v = _load(vp)
    analysis = v.get("analysis", [])
    summ = next((a for a in analysis if a.get("type") == "summary"), {})
    tr = next((a for a in analysis if a.get("type") == "transcript"), {})
    sb = summ.get("body", {}) if isinstance(summ, dict) else {}
    return {
        "uuid": v.get("uuid"),
        "dir": str(vp.parent),
        "path": str(vp),
        "subject": v.get("subject", ""),
        "created_at": v.get("created_at", ""),
        "vcon": v.get("vcon"),
        "parties": [p.get("name") for p in v.get("parties", [])],
        "n_segments": len(tr.get("body", {}).get("segments", []))
        if isinstance(tr, dict) else 0,
        "topics": sb.get("topics", []),
        "summary": sb.get("summary", ""),
        "neutral_editorial_summary":
            sb.get("neutral_editorial_summary", ""),
    }


def _index(refresh: bool = False) -> dict[str, dict[str, Any]]:
    global _INDEX
    if _INDEX is not None and not refresh:
        return _INDEX
    idx: dict[str, dict[str, Any]] = {}
    for vp in sorted(CORPUS.rglob("vcon.json")):
        try:
            e = _entry(vp)
            if e["uuid"]:
                idx[e["uuid"]] = e
        except Exception:
            continue
    _INDEX = idx
    return idx


def _haystack(uuid: str) -> str:
    e = _index()[uuid]
    parts = [e["subject"], e["summary"],
             e["neutral_editorial_summary"], " ".join(e["topics"]),
             " ".join(e["parties"])]
    try:
        v = _load(Path(e["path"]))
        tr = next((a for a in v.get("analysis", [])
                   if a.get("type") == "transcript"), None)
        if tr:
            parts.append(" ".join(s.get("text", "")
                         for s in tr["body"]["segments"]))
    except Exception:
        pass
    return "\n".join(parts).lower()


# --------------------------------------------------------------------------
# tools
# --------------------------------------------------------------------------
@mcp.tool()
def list_recent(limit: int = 20) -> list[dict]:
    """List the most recent vCons in the corpus (newest first).

    Returns uuid, subject, created_at, parties and segment count.
    """
    rows = sorted(_index().values(),
                  key=lambda e: e["created_at"], reverse=True)
    return [{k: r[k] for k in ("uuid", "subject", "created_at",
                               "parties", "n_segments")}
            for r in rows[:max(1, limit)]]


@mcp.tool()
def search_vcons(query: str, limit: int = 20) -> list[dict]:
    """Keyword search across subject, transcript, analysis and parties.

    Case-insensitive; ranks by number of query-term hits. Returns
    matching vCons with a short snippet.
    """
    terms = [t for t in query.lower().split() if t]
    out = []
    for uuid in _index():
        hay = _haystack(uuid)
        score = sum(hay.count(t) for t in terms)
        if score:
            e = _index()[uuid]
            pos = min((hay.find(t) for t in terms if t in hay),
                      default=0)
            out.append({
                "uuid": uuid,
                "subject": e["subject"],
                "created_at": e["created_at"],
                "score": score,
                "snippet": hay[max(0, pos - 60):pos + 140]
                .strip().replace("\n", " "),
            })
    out.sort(key=lambda r: r["score"], reverse=True)
    return out[:max(1, limit)]


@mcp.tool()
def get_vcon(uuid: str) -> dict:
    """Return the full vCon JSON document for a uuid."""
    e = _index().get(uuid)
    if not e:
        raise ValueError(f"no vcon with uuid {uuid}")
    return _load(Path(e["path"]))


@mcp.tool()
def get_lifecycle_receipts(uuid: str) -> dict:
    """Return the SCITT lifecycle statements and transparency receipts.

    The statement binds the vCon + lawful-basis hashes; the receipt is
    the Merkle inclusion proof countersigned by the SCITT service.
    """
    d = _vcon_dir(uuid)
    if not d:
        raise ValueError(f"no vcon with uuid {uuid}")
    sc = d / "scitt"
    if not sc.is_dir():
        return {"uuid": uuid, "statements": [], "receipts": []}
    return {
        "uuid": uuid,
        "statements": [json.loads(p.read_text())
                       for p in sorted(sc.glob("*.scitt.json"))],
        "receipts": [json.loads(p.read_text())
                     for p in sorted(sc.glob("*.scitt-receipt.json"))],
    }


@mcp.tool()
def summarize_for_topic(topic: str, limit: int = 10) -> list[dict]:
    """Find vCons relevant to a topic and return their neutral summaries.

    Useful for "what does the corpus say about X" — returns the
    project's neutral editorial summary plus a corpus path per match.
    """
    hits = search_vcons(topic, limit=limit)
    res = []
    for h in hits:
        e = _index()[h["uuid"]]
        res.append({
            "uuid": h["uuid"],
            "subject": e["subject"],
            "created_at": e["created_at"],
            "topics": e["topics"],
            "neutral_editorial_summary":
                e["neutral_editorial_summary"],
            "summary": e["summary"],
        })
    return res


@mcp.tool()
def verify_vcon(uuid: str) -> dict:
    """Walk and verify the SCITT chain for a vCon (offline).

    Checks every lifecycle receipt: service countersignature, the
    inclusion proof re-derives the logged Merkle root, the statement
    hashes to the logged leaf, and the issuer statement signature.
    Also runs the statement-only signature check. Returns per-stage
    results and an overall verdict.
    """
    d = _vcon_dir(uuid)
    if not d:
        raise ValueError(f"no vcon with uuid {uuid}")
    sc = d / "scitt"
    out: dict[str, Any] = {"uuid": uuid, "scitt_dir": str(sc)}

    def _run(script: Path) -> dict:
        if not script.is_file():
            return {"ran": False, "reason": f"missing {script.name}"}
        r = subprocess.run(
            [PY, str(script), "verify", "--receipts", str(sc)],
            capture_output=True, text=True)
        return {
            "ran": True,
            "ok": r.returncode == 0 and "BAD" not in r.stdout,
            "n_ok": r.stdout.count("OK "),
            "n_bad": r.stdout.count("BAD"),
            "detail": r.stdout.strip().splitlines(),
        }

    out["receipts"] = _run(SCITT_CLI)      # full chain (incl. proofs)
    out["statements"] = _run(SCITT_SIGN)   # statement signatures only
    out["verified"] = bool(
        out["receipts"].get("ok") and out["statements"].get("ok"))
    return out


@mcp.tool()
def refresh_index() -> dict:
    """Re-scan the corpus directory (call after new vCons are added)."""
    n = len(_index(refresh=True))
    return {"corpus": str(CORPUS), "vcons": n}


# --------------------------------------------------------------------------
# resources — contract parity with vcon-dev/vcon-mcp
# --------------------------------------------------------------------------
def _section(uuid: str, key: str):
    v = get_vcon(uuid)
    return v.get(key, [])


@mcp.resource("vcon://v1/vcons/{uuid}")
def res_vcon(uuid: str) -> str:
    return json.dumps(get_vcon(uuid), indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/metadata")
def res_meta(uuid: str) -> str:
    v = get_vcon(uuid)
    return json.dumps({k: v.get(k) for k in
                       ("vcon", "uuid", "created_at", "updated_at",
                        "subject", "extensions")}, indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/parties")
def res_parties(uuid: str) -> str:
    return json.dumps(_section(uuid, "parties"), indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/dialog")
def res_dialog(uuid: str) -> str:
    return json.dumps(_section(uuid, "dialog"), indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/attachments")
def res_attach(uuid: str) -> str:
    return json.dumps(_section(uuid, "attachments"), indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/analysis")
def res_analysis(uuid: str) -> str:
    return json.dumps(_section(uuid, "analysis"), indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/transcript")
def res_transcript(uuid: str) -> str:
    a = [x for x in _section(uuid, "analysis")
         if x.get("type") == "transcript"]
    return json.dumps(a, indent=2)


@mcp.resource("vcon://v1/vcons/{uuid}/summary")
def res_summary(uuid: str) -> str:
    a = [x for x in _section(uuid, "analysis")
         if x.get("type") == "summary"]
    return json.dumps(a, indent=2)


if __name__ == "__main__":
    # stdio for local Claude/MCP clients; streamable-http when the
    # cloud api.publicvcons.org droplet runs it behind Caddy.
    transport = os.environ.get("PVCONS_MCP_TRANSPORT", "stdio")
    if transport in ("http", "streamable-http"):
        mcp.settings.host = os.environ.get("PVCONS_MCP_HOST", "127.0.0.1")
        mcp.settings.port = int(os.environ.get("PVCONS_MCP_PORT", "8001"))
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
