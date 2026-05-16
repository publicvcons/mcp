# publicvcons/mcp

MCP server for PublicVCons, exposed at api.publicvcons.org.

Part of the PublicVCons project. Reference implementation of the IETF vcon lawful basis and lifecycle extensions.

## Stack

FastMCP (Python). Extends the upstream vcon-dev MCP server rather than reimplementing it. Hosted on Digital Ocean App Platform.

## Tools

Planned tool surface:

- `search_vcons`
- `get_vcon`
- `get_lifecycle_receipts`
- `list_recent`
- `summarize_for_topic`
- `verify_vcon`: walks the SCITT chain for a vcon UUID

The server is a thin facade in front of the JSON files served by the web view. It does not maintain its own database.

## License

Apache 2.0. The patent grant is intentional because this codebase is a reference implementation of IETF drafts authored by the project owner.
