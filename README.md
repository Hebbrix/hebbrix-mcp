# Hebbrix MCP Server

<!-- mcp-name: io.github.Hebbrix/hebbrix-mcp -->

[![PyPI](https://img.shields.io/pypi/v/hebbrix-mcp)](https://pypi.org/project/hebbrix-mcp/)
[![CI](https://github.com/Hebbrix/hebbrix-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Hebbrix/hebbrix-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/hebbrix-mcp)](https://pypi.org/project/hebbrix-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Model Context Protocol server that gives any AI agent long-term memory and a temporal knowledge graph, backed by [Hebbrix](https://www.hebbrix.com).

Your agent forgets everything when the session ends. This fixes that, and goes further than a plain memory store:

- **Memory** — store, search, correct, and version facts across sessions
- **Knowledge graph** — entities, relationships, timelines, and "what was true at time X"
- **Reasoning** — ask how confident the agent should be before acting, and log outcomes so it improves
- **Outcome Memory** — learn which action works for each customer and context
  from delayed results, with safe baselines and inspectable uncertainty

Works with Claude Desktop, Claude Code, Cursor, Cline, Continue, and any other MCP client.

### Release compatibility

| MCP package | Hosted/API contract | Tool surface | Migration |
|---|---|---:|---|
| 0.5.8 | Hebbrix API 1.0.0 / search-safety-v1 | 32 | Adds procedure lifecycle tools |

Version 0.5.8 adds the complete tenant-scoped procedure lifecycle (including
idempotent deletion), and preserves authoritative batch readiness receipts.
It also retains 0.5.7's API-owned grounding and abstention envelope: missing,
malformed, degraded, or ungrounded receipts fail closed with empty evidence.

The hosted server and PyPI package expose their exact package version during
MCP initialization. The API exposes its immutable deployment build through
`X-Hebbrix-Build` and `GET /v1/health/build`; OpenAPI `info.version` identifies
the stable HTTP contract rather than a mutable deployment.

### Fastest setup: hosted, no account

For an HTTP-capable MCP client, this is the entire setup:

```json
{ "mcpServers": { "hebbrix": { "url": "https://mcp.hebbrix.com/mcp" } } }
```

On the first MCP handshake, Hebbrix creates an isolated free guest memory and
keeps its credential in a Secure, HttpOnly session cookie. There is no signup,
email, dashboard, local process, or API key to paste. A compatible MCP HTTP
client automatically sends that cookie on later requests. Add your own bearer
key at any time if you want to use an existing Hebbrix account instead.

## Quick start (no account needed)

Add this to your MCP client config. On first run with no API key, the server mints a **free agent account** automatically (no email, no dashboard, ~2-4 seconds via proof-of-work) and saves it to `~/.hebbrix/config.json`.

```json
{
  "mcpServers": {
    "hebbrix": { "command": "uvx", "args": ["hebbrix-mcp"] }
  }
}
```

> [!NOTE]
> `uvx` ([from uv](https://docs.astral.sh/uv/)) runs the server with no install step. If you prefer, `pip install hebbrix-mcp` and use `"command": "hebbrix-mcp"` instead.

Restart the client. Done — your agent now has persistent memory.

The free agent account includes **300 learning events** and **2,000 retrievals**, and expires 14 days after last use if unclaimed. The first tool result, material quota/status changes, and every constrained-state result carry a `hebbrix_usage` block; `hebbrix_account_status` returns it on demand at any time.

**Keep it forever** (same key, all memories carry over, unlocks the free monthly tier):

```bash
uvx hebbrix-mcp claim --email you@example.com
```

## Claude Code plugin (recommended)

Install as a Claude Code **plugin** and Claude starts every session already
knowing you — a `SessionStart` hook auto-loads your compiled Hebbrix profile
into context, and the memory tools are wired up in one step:

```bash
/plugin marketplace add Hebbrix/hebbrix-mcp
/plugin install hebbrix@hebbrix
```

That's it. No account needed (agent mode mints one on first run); set your
`api_key` in the plugin config to use your own account instead. The hook degrades
gracefully — a brand-new profile just shows `(none yet)` until you've saved a few
facts, and it never blocks a session.

## Configuration

Get an API key at [hebbrix.com/dashboard/api-keys](https://www.hebbrix.com/dashboard/api-keys) to use your own account instead of agent mode.

<details>
<summary><b>Claude Desktop</b> — <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></summary>

```json
{
  "mcpServers": {
    "hebbrix": {
      "command": "uvx",
      "args": ["hebbrix-mcp"],
      "env": {
        "HEBBRIX_API_KEY": "mem_sk_...",
        "HEBBRIX_COLLECTION_ID": "your-default-collection-uuid"
      }
    }
  }
}
```
</details>

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add hebbrix -- uvx hebbrix-mcp
```
</details>

<details>
<summary><b>Cursor</b> — <code>~/.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "hebbrix": { "command": "uvx", "args": ["hebbrix-mcp"] }
  }
}
```
</details>

<details>
<summary><b>Cline / Continue / other</b></summary>

Point your MCP servers config at the `uvx hebbrix-mcp` command (stdio). Same shape as above. Set `HEBBRIX_API_KEY` in `env` to skip agent mode.
</details>

The env var always wins over saved agent-mode credentials.

### Environment variables

All optional. With nothing set, the server starts in agent mode.

| Variable | Default | Purpose |
|---|---|---|
| `HEBBRIX_API_KEY` | *(agent mode mints one)* | Your Hebbrix bearer token |
| `HEBBRIX_COLLECTION_ID` | *(agent mode sets one)* | Default collection for writes/reads |
| `HEBBRIX_API_BASE` | `https://api.hebbrix.com/v1` | API endpoint override |
| `HEBBRIX_CONFIG` | `~/.hebbrix/config.json` | Where agent-mode credentials are saved |
| `HEBBRIX_MCP_HOST` | `127.0.0.1` | Bind host (HTTP transports) |
| `HEBBRIX_MCP_PORT` | `8080` | Bind port (HTTP transports) |
| `HEBBRIX_MCP_MULTI_TENANT` | off | Hosted mode: per-request `Authorization` header auth |
| `HEBBRIX_MCP_ACCOUNTLESS` | off | Hosted mode: mint a bounded guest identity on unauthenticated `initialize` |
| `HEBBRIX_MCP_SESSION_SECRET` | *(required for accountless)* | HMAC secret for stateless Secure guest cookies |
| `HEBBRIX_MCP_INTERNAL_SECRET` | *(required for accountless)* | HMAC trust bridge for original-client signup throttling |

## Available Tools

A server-level instruction block teaches the model when to reach for each tool, so a well-behaved agent searches before answering and remembers what matters without being told.

**Memory**

- `hebbrix_remember` - Store a fact, decision, or preference.
    - `content` (string, required): the memory text
    - `tags` (list, optional), `collection_id` (string, optional)
    - `extract` (bool, default false): false stores the text exactly (one memory); true starts a tracked fact-extraction job and may create several atomic memories
    - `wait_for_extraction` (bool, default true): for smart ingestion, poll for up to 20 seconds and return normalized atomic memories. Set false for immediate acknowledgement, then call `hebbrix_extraction_status` with the returned job id.
    - `wait_for_index` (bool, default true): guarantees **memory-search** availability — `hebbrix_search` returns the fact the moment the call returns. It does **not** cover knowledge-graph enrichment (entities/timelines/graph), which lands asynchronously (~30s); the response's `graph_enrichment: "processing"` flags this.
- `hebbrix_extraction_status` - Poll a smart-ingestion job until its created/updated memories or terminal error are available.
- `hebbrix_remember_many` - Store **many** facts in one call (one round-trip, one rate-limit hit). Pass `facts` (list of strings). Falls back to sequential writes on free/agent tiers.
- `hebbrix_search` - Semantic search (hybrid vector + BM25 + graph retrieval).
    - `query` (string, required), `limit` (int, optional), `collection_id` (string, optional)
    - `min_score` (float, default 0.0): drop weak matches — zero-relevance padding is always dropped; raise this to filter noise so you don't pay tokens for it.
- `hebbrix_get` - Fetch one memory by id, with metadata.
- `hebbrix_update` - Correct a memory **in place** (old versions are kept).
- `hebbrix_forget` - Delete a memory by id.
- `hebbrix_list` - List recent memories.
- `hebbrix_history` - See how a memory changed over time.
- `hebbrix_mark_used` - Reinforce a memory you actually used (`helpful=True` strengthens it, `False` weakens it) so recall improves over time.
- `hebbrix_export` - Export a whole collection (memories + graph entities + profile) as JSON or Markdown, in one call.
- `hebbrix_import` - The inverse of export: import a list of facts, an export JSON, or notes/markdown into a collection (restore a backup, migrate, or seed from `CLAUDE.md`).

**Knowledge graph** — Hebbrix automatically extracts entities and relationships from the memories you write, on **every tier including agent mode**, so all the graph *reads* below (entities, timelines, traversal, contradictions) work in agent mode too. Only explicit graph *write* / inference operations require a Pro plan.

- `hebbrix_search_entities` - List known entities (people, orgs, tools, places).
- `hebbrix_entity_timeline` - What was true about an entity, and when.
- `hebbrix_graph_query` - Traverse relationships out from a named entity; pass a `timestamp` for point-in-time truth. Results are trimmed (from/to/type/valid_from), not raw backend payloads. (Free-text questions: use `hebbrix_ask`.)
- `hebbrix_contradictions` - Surface facts that conflict with each other.

**Procedural memory**

- `hebbrix_create_procedure` - Store a scoped condition/action procedure.
- `hebbrix_list_procedures` / `hebbrix_get_procedure` - Inspect owned procedures.
- `hebbrix_update_procedure` - Update mutable fields; ownership scope is immutable.
- `hebbrix_execute_procedure` - Execute a procedure and record the execution.
- `hebbrix_delete_procedure` - Idempotently delete a procedure and its executions. The API returns the same 204 for deleted, absent, and foreign-tenant IDs so the tool cannot reveal another tenant's identifier.

**Reasoning & account**

- `hebbrix_ask` - **One-call GraphRAG.** Ask a natural-language question; it searches memory, synthesizes an answer with an LLM, cites the memory ids it used, and enriches with knowledge-graph relationships + your profile. Use instead of orchestrating search + graph + profile yourself.
- `hebbrix_confidence` - How confident should the agent be before acting? Grounded in memory + past outcomes.
- `hebbrix_log_decision` - Record a decision and its outcome; feeds future confidence. Right after a `hebbrix_confidence` check you can log just the `outcome` — the description auto-fills from what you asked.
- `hebbrix_choose_action` - Safely choose among repeatable strategies and create
  a causal decision receipt before acting. Supports per-user/context policies and
  explicitly bounded exploration.
- `hebbrix_report_outcome` - Close that decision loop later with `success`, a
  bounded reward, or configured business metrics. Corrections replace prior
  evidence instead of double-counting it.
- `hebbrix_learning_insights` - Inspect posterior probabilities, credible
  intervals, effective evidence, and optional chronological-holdout policy
  readiness checks for one customer policy.
- `hebbrix_list_collections` - List the memory spaces this key can use.
- `hebbrix_account_status` - Tier, usage, limits, and expiry.
- `hebbrix_claim_start` / `hebbrix_claim_verify` - Optionally keep an accountless
  guest memory permanently, without changing its collection or losing data.

Every tool publishes explicit MCP safety annotations. `hebbrix_claim_start` is
marked as an external side effect because it sends email; deletion is marked
destructive; reads are marked read-only. The six-digit claim code is declared
as a write-only password field and is never logged or returned by this server.
MCP hosts still control their own tool-call history, so configure the host to
redact secret inputs if it persists conversation or tracing data.

The server also exposes a `hebbrix://profile` resource and a `context` prompt that inject the user's compiled profile.

## Make Hebbrix the agent's memory

The server ships an instruction block telling the model to use Hebbrix for anything it would "remember." But some hosts (notably Claude Code) have their **own** file-based memory whose instructions live at the system-prompt level and can outrank an MCP server's instructions — so the agent may quietly write notes to a local file instead of Hebbrix.

The reliable fix is one line in your project's `CLAUDE.md` (or your assistant's system prompt / rules file):

```markdown
## Memory
Use the Hebbrix MCP server as the single source of truth for long-term memory.
When you would remember, note, or save anything durable, call `hebbrix_remember`
(and `hebbrix_search` to recall). Do not write memory to local files or the
host's built-in memory.
```

Cursor users: add the same to `.cursorrules`. This puts the preference at the level the host respects, so Hebbrix wins consistently.

## Running modes

**Local (default) — stdio.** What the quick start does: one process per client.

**Self-hosted HTTP — one instance, your machines:**

```bash
HEBBRIX_API_KEY=mem_sk_... uvx hebbrix-mcp --transport streamable-http
# serves http://127.0.0.1:8080/mcp
```

**Hosted — nothing to run and no account required.** Point any HTTP-capable MCP
client at the official hosted endpoint. The first handshake creates an isolated
guest memory and a Secure, HttpOnly session cookie automatically:

```json
{ "mcpServers": { "hebbrix": {
  "url": "https://mcp.hebbrix.com/mcp"
}}}
```

To use an existing Hebbrix account instead, add its API key (get one at
[hebbrix.com/dashboard/api-keys](https://www.hebbrix.com/dashboard/api-keys)):

```json
{ "mcpServers": { "hebbrix": {
  "url": "https://mcp.hebbrix.com/mcp",
  "headers": { "Authorization": "Bearer mem_sk_..." }
}}}
```

**Self-hosted multi-tenant — one instance, many users.** Same shape on your own
infra. By default every request authenticates with its own `Authorization`
header:

```bash
HEBBRIX_MCP_MULTI_TENANT=1 HEBBRIX_MCP_HOST=0.0.0.0 uvx hebbrix-mcp --transport streamable-http
```

Or run the container (multi-tenant by default, `GET /healthz` for load-balancer probes):

```bash
docker build -t hebbrix-mcp . && docker run -p 8080:8080 hebbrix-mcp
```

In multi-tenant mode, the server resolves each authenticated key's default
collection automatically. An explicit `collection_id` still overrides it.

## How it works

```
┌──────────────────┐   MCP (stdio or HTTP)   ┌─────────────┐    HTTPS     ┌──────────┐
│ Claude / Cursor / │ ───────────────────────→│ hebbrix-mcp │─────────────→│ Hebbrix  │
│ Cline / any agent │      tool calls         │   (this)    │   REST API   │  cloud   │
└──────────────────┘                          └─────────────┘              └──────────┘
```

This package owns **no durable memory state**. Tool calls become REST calls
against your Hebbrix tenant; memories, embeddings, the knowledge graph, and
retrieval all live in the Hebbrix backend. The hosted accountless path keeps only
a signed identity cookie in the MCP client so multiple stateless replicas can
serve it. Delete the local package and your backend memories are still there.

Agent-mode accounts never break mid-task: when a limit is reached you get a structured error with a `resolve` field, not a failure. Writes stop before reads; reads keep working; the account goes read-only before it expires.

## Debugging

Inspect the server with the [MCP Inspector](https://github.com/modelcontextprotocol/inspector):

```bash
npx @modelcontextprotocol/inspector uvx hebbrix-mcp
```

Common issues:

- **`HTTP 401` on every call** — the key is wrong or revoked. Unset `HEBBRIX_API_KEY`, delete `~/.hebbrix/config.json`, and restart to re-provision, or paste a fresh key from the dashboard.
- **Agent mode won't start (`auto-signup unavailable`)** — signup may be at daily capacity or your network blocks the API. Set `HEBBRIX_API_KEY` instead.
- **`claim` says `EMAIL_IN_USE`** — claiming needs an email with no existing Hebbrix account. Use a fresh address (a `you+agent@gmail.com` alias works).
- **A memory isn't searchable immediately** — pass `wait_for_index=true` (the default) for read-after-write on `hebbrix_search`. Otherwise indexing is asynchronous; typical convergence is under 30 seconds.
- **A just-written fact's entities aren't in the graph yet** — knowledge-graph enrichment (entities, timelines, graph queries) runs *asynchronously after* the write and is not covered by `wait_for_index`. It typically lands within ~30s; the write response's `graph_enrichment: "processing"` signals it's still in flight.

## Development

```bash
git clone https://github.com/Hebbrix/hebbrix-mcp
cd hebbrix-mcp
./quick_setup.sh            # venv + editable install
source venv/bin/activate
pytest tests/ -q            # 93 offline tests, no network needed
hebbrix-mcp                 # starts in agent mode on stdio
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

## Links

- [Hebbrix documentation](https://www.hebbrix.com/docs)
- [MCP integration guide](https://www.hebbrix.com/integrations/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io)
