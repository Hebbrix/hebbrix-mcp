# Changelog

## 0.3.10 — 2026-07-09

Mutation-consistency fixes from an external correctness report. The 0.3.8
write-behind cache handled `create` but not `update` or `delete`, so stale or
deleted content could leak through immediately after a mutation.

- **Update now reflects immediately (read-after-write for corrections).** The
  session cache is keyed by memory id; a successful `hebbrix_update` replaces the
  cached content, and `hebbrix_search`/`hebbrix_list` now REPLACE a stale remote
  row that has the same id with the corrected content (previously the cache only
  supplemented *missing* ids, so a lagging remote row won). `hebbrix_update`
  gained `wait_for_index=True` (matches `hebbrix_remember`).
- **Deletes are no longer resurrected.** `hebbrix_forget` now tombstones the id
  (on a 2xx delete or a remote 404). `hebbrix_search` and `hebbrix_list` filter
  tombstoned ids out of BOTH cached and remote results. A tombstone is cleared if
  the id is re-created/updated.
- **`hebbrix_get` can't return a deleted memory.** It checks the tombstone set
  first and returns a structured `{"error":"not found","deleted":true}`;
  `_cached_write` never falls back to a tombstoned id, so a remote 404 after a
  delete no longer resurrects old cached content.
- **Handshake reports the Hebbrix version.** `serverInfo.version` is now the
  installed `hebbrix-mcp` version (via `importlib.metadata`) instead of the MCP
  SDK version.
- **Docs:** clarified that automatic graph extraction (entities/timelines/
  traversal reads) works in agent mode; only explicit graph writes/inference
  need Pro.
- 15 new offline regressions (55 total), verified live against the real API
  (create → update → search/get → delete → search/get).

Multi-tenant hosted mode still disables all process-global overlays, so none of
this can cross tenants.

## 0.3.9 — 2026-07-09

Hosted-server support.

- **`GET /healthz` (and `/health`)** on the multi-tenant HTTP server returns an
  unauthenticated `200 {"status":"ok"}` for load-balancer health probes. Scoped
  so it can never expose an MCP endpoint without a bearer.
- **`Dockerfile`** for the hosted / self-hosted multi-tenant server, plus a
  `hosted` extra (`pip install "hebbrix-mcp[hosted]"`, adds uvicorn). Runs the
  one-instance-many-users streamable-http server; the image behind
  `mcp.hebbrix.com`.

## 0.3.8 — 2026-07-09

New features.

- **Claude Code plugin.** The repo is now an installable Claude Code plugin +
  single-plugin marketplace. `/plugin marketplace add Hebbrix/hebbrix-mcp` then
  `/plugin install hebbrix@hebbrix` wires up the MCP server AND a `SessionStart`
  hook that auto-loads your compiled Hebbrix profile into every session — Claude
  starts each session already knowing your durable facts. See the README.
- **`hebbrix-mcp profile` CLI.** Prints the compiled profile as plain text
  (used by the plugin's session hook; always exits 0).
- **Write-behind read-after-write cache (local/stdio).** A memory written this
  session is instantly recallable by `hebbrix_search` / `hebbrix_get` /
  `hebbrix_list` even before the remote index catches up — so you can safely use
  `wait_for_index=False` for speed without a just-written fact ever going
  missing. Disabled in multi-tenant hosted mode so one tenant's writes can never
  surface in another's results.
- **Auto-inferred decisions.** After a `hebbrix_confidence` check you can log
  just the outcome (`hebbrix_log_decision(outcome="success")`) with no
  description — it auto-fills from what you just asked about, closing the
  confidence → action → outcome loop in one call.

## 0.3.7 — 2026-07-09

Fixes from two external code reviews.

- **Profile resource + `context` prompt were dead.** Both read a `facts` key
  that `/profile` never returns. They now call `/profile/facts` and render the
  compiled `static`/`dynamic` facts via a shared `_profile_text` helper (and say
  `(none yet)` while the profile is still compiling instead of showing nothing).
- **`hebbrix_graph_query` took a `query` it ignored.** The graph endpoint
  traverses relationships out from a named entity, it does not do free-text
  search. Removed the misleading `query` param; the tool now takes `entity`
  (+ `relation_type`, `depth`, `timestamp`), and the docstring points free-text
  questions at `hebbrix_search`.
- **`hebbrix_entity_timeline` now lowercases the entity name** before
  URL-encoding it, matching how entities are canonicalized server-side, so
  `Acme Corp` and `acme corp` resolve to the same timeline.
- **`hebbrix_contradictions` accepts `collection_id`** so it works under hosted
  multi-tenant mode (no default collection).
- **Usage capture no longer throws on malformed headers**, and error bodies are
  surfaced up to 800 chars (was 300) for easier debugging.
- Softened the server instruction block from a hard "do NOT write to local
  files" directive to "prefer Hebbrix … keeps memory in one place."
- Test suite expanded to 26 offline tests; CI now runs `ruff`.

## 0.3.6 — 2026-07-09

- Fix: `hebbrix_remember(extract=True)` returned each extracted memory's content
  as null. The `/memories` result items carry the text under `memory` (not
  `content`); the reshaping now reads the right key and also surfaces each
  fact's `event` (ADD/UPDATE) and id. Data was always stored correctly — this
  was display-only.
- Docs: `hebbrix_remember` now advises using one `extract=True` call (or
  `wait_for_index=False`) when saving several facts, since blocking writes are
  serial (~a few seconds each).


## 0.3.5 — 2026-07-09

Fixes from external integrator feedback.

- **Read-after-write**: `hebbrix_remember` now defaults `wait_for_index=True`, so
  a stored memory is searchable the moment the call returns (previously raw
  writes indexed asynchronously and could be missing from search for many
  seconds). Pass `wait_for_index=False` for fire-and-forget bulk writes.
- **Honest `remember` semantics**: the old `verbatim` flag was a no-op —
  `/memories/raw` ignores fact-extraction, so both values stored raw. Replaced
  with `extract` (default False = exact/raw storage, one memory). `extract=True`
  routes to the fact-extraction endpoint and returns the atomic memories it
  created.
- **Use Hebbrix as the agent's memory**: the server instruction block now tells
  the model to prefer Hebbrix over writing notes to local files / the host's
  built-in memory, and the README documents a `CLAUDE.md` / `.cursorrules`
  snippet as the reliable lever where host memory outranks MCP instructions.


## 0.3.4 — 2026-07-08

- **Proof-of-work signup for shared-IP / CGNAT.** On the accountless path the
  client now solves a small (~1-2s) proof-of-work before minting; a PoW-verified
  signup skips the per-IP cap server-side, so users behind a shared office or
  carrier-grade NAT IP can each still get a free agent account. Falls back to a
  plain mint automatically if the server doesn't offer a challenge. No user-
  visible change — it stays fully automatic (no CAPTCHA).


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
