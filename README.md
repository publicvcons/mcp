# publicvcons/mcp

MCP server for PublicVCons, exposed at api.publicvcons.org.

Part of the PublicVCons project. Reference implementation of the IETF vcon lawful basis and lifecycle extensions.

## Stack

FastMCP (Python, official `mcp` SDK). `server.py` is a thin read-only
facade over the publicvcons/vcons corpus — the same JSON the web
viewer serves. No database (PROTOTYPE_PLAN.md §7): the corpus directory
is the store.

The upstream `vcon-dev/vcon-mcp` is TypeScript + Supabase, which
conflicts with this project's FastMCP-Python / no-DB mandate, so this
is a separate implementation that stays **contract-compatible**: tool
names (`get_vcon`, `search_vcons`, `list_recent`) and the
`vcon://v1/vcons/{uuid}[/...]` resource URIs match upstream so clients
built for it work here too.

## Tools

- `list_recent` — newest vCons first
- `search_vcons` — keyword search over subject/transcript/analysis/parties
- `get_vcon` — full vCon JSON
- `get_lifecycle_receipts` — SCITT statements + transparency receipts
- `summarize_for_topic` — topic matches with neutral editorial summaries
- `verify_vcon` — walks & verifies the SCITT chain offline
  (countersignature + inclusion proof + statement signature)
- `refresh_index` — re-scan the corpus

Resources: `vcon://v1/vcons/{uuid}` plus `/metadata`, `/parties`,
`/dialog`, `/attachments`, `/analysis`, `/transcript`, `/summary`.

## Run / test

```
PVCONS_CORPUS=/path/to/vcons ~/venvs/tools/bin/python server.py   # stdio
~/venvs/tools/bin/python test_server.py                           # smoke test
```

Corpus is auto-located (`$PVCONS_CORPUS`, then
`/Volumes/publicvcons/data`, then a sibling `vcons` checkout). Wire it
into Claude with `claude_desktop_config.json` (see that file).

### Status

Runs locally over stdio; every tool and resource is exercised by
`test_server.py` (PASS) and the protocol is the same one Claude uses.
The `api.publicvcons.org` HTTP deployment is a separate cloud step
(§8) and is not done here.

## License

Apache 2.0. The patent grant is intentional because this codebase is a reference implementation of IETF drafts authored by the project owner.
