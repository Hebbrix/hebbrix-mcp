# Changelog

## 0.3.1 — 2026-07-07

- `hebbrix-mcp claim --email <you>` is now the full interactive flow: requests
  the emailed 6-digit code, prompts for it, verifies, and updates the saved
  config (tier, claimed email, expiry removed).
- Multi-tenant hosted mode: `HEBBRIX_MCP_MULTI_TENANT=1` with
  `--transport streamable-http` authenticates every request from its own
  `Authorization: Bearer` header (stateless HTTP; no shared server key).

## 0.3.0 — 2026-07-07

- **Agent Mode (accountless start):** with no `HEBBRIX_API_KEY` and no saved
  credentials, the server mints a free shadow account via
  `POST /v1/agent-signup` and starts in under 10 seconds — no email, no
  dashboard. Credentials persist to `~/.hebbrix/config.json` (0600).
- Every tool result carries a `hebbrix_usage` block (tier, writes/retrievals
  used vs limit, expiry, claim command) with an `action_for_human` string at
  warning/limited/read_only.
- New tool `hebbrix_account_status` (15 tools total).

## 0.2.0 — 2026-07-06

- Tool surface expanded 4 → 14: memory CRUD + version history (`get`,
  `update`, `history`), knowledge graph (`search_entities`, `entity_timeline`,
  `graph_query`, `contradictions`), reasoning layer (`confidence`,
  `log_decision`), `list_collections`.
- Server-level `instructions` block teaching agents the data model.
- `hebbrix://profile` resource + `context` prompt.
- Streamable HTTP transport (`--transport streamable-http`) alongside stdio.

## 0.1.0 — 2026-05-11

- Initial release: `remember`, `search`, `list`, `forget` over the Hebbrix
  REST API; stdio transport; env-var configuration.
