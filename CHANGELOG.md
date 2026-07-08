# Changelog

## 0.3.3 — 2026-07-08

Fixes from external integrator feedback.

- **Multi-tenant safety**: `_client()` no longer falls back to the server's
  global key in multi-tenant mode, and `_HeaderAuthMiddleware` now rejects any
  request without an `Authorization: Bearer` header with 401 — a stray
  `HEBBRIX_API_KEY` on a hosted deployment can never serve an unauthenticated
  request.
- **URL-encode** `entity_name` in `hebbrix_entity_timeline` so names with
  `/ ? # %` don't break the request path.
- **Honor saved `api_base`**: `_load_saved_credentials()` now reads `api_base`
  back from `~/.hebbrix/config.json` (explicit `HEBBRIX_API_BASE` env still
  wins), so custom-endpoint users don't silently revert to the default.
- **Actionable rate-limit message**: when the free no-account signup is
  rate-limited (shared/office/CGNAT IPs), the server now points to the 30-second
  free-API-key path instead of dumping the raw HTTP error.
- Docs: `__init__` tool count corrected to 15 (`hebbrix_account_status`).


## 0.3.2 — 2026-07-08

- Fix: the per-response usage snapshot is now request-scoped (ContextVar), so
  concurrent requests in multi-tenant hosted mode never cross-contaminate each
  other's `hebbrix_usage` block.
- Docs: README restructured to the MCP-ecosystem idiom (mcp-name registry
  marker, `uvx` as the recommended runner, canonical tool list, Debugging
  section via MCP Inspector).

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
