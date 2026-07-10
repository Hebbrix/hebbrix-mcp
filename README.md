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

Works with Claude Desktop, Claude Code, Cursor, Cline, Continue, and any other MCP client.

## Quick start (no account needed)

Add this to your MCP client config. On first run with no API key, the server mints a **free agent account** automatically (no email, no dashboard, ~1 second) and saves it to `~/.hebbrix/config.json`.

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

The free agent account includes **300 learning events** and **2,000 retrievals**, and expires 14 days after last use if unclaimed. Every tool result carries a `hebbrix_usage` block so the agent always knows where it stands and will tell you when it's time to claim.

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

## Available Tools

A server-level instruction block teaches the model when to reach for each tool, so a well-behaved agent searches before answering and remembers what matters without being told.

**Memory**

- `hebbrix_remember` - Store a fact, decision, or preference.
    - `content` (string, required): the memory text
    - `tags` (list, optional), `collection_id` (string, optional)
    - `extract` (bool, default false): false stores the text exactly (one memory); true runs fact-extraction and may create several atomic memories
    - `wait_for_index` (bool, default true): guarantees **memory-search** availability — `hebbrix_search` returns the fact the moment the call returns. It does **not** cover knowledge-graph enrichment (entities/timelines/graph), which lands asynchronously (~30s); the response's `graph_enrichment: "processing"` flags this.
- `hebbrix_search` - Semantic search (hybrid vector + BM25 + graph retrieval).
    - `query` (string, required), `limit` (int, optional), `collection_id` (string, optional)
- `hebbrix_get` - Fetch one memory by id, with metadata.
- `hebbrix_update` - Correct a memory **in place** (old versions are kept).
- `hebbrix_forget` - Delete a memory by id.
- `hebbrix_list` - List recent memories.
- `hebbrix_history` - See how a memory changed over time.

**Knowledge graph** — Hebbrix automatically extracts entities and relationships from the memories you write, on **every tier including agent mode**, so all the graph *reads* below (entities, timelines, traversal, contradictions) work in agent mode too. Only explicit graph *write* / inference operations require a Pro plan.

- `hebbrix_search_entities` - List known entities (people, orgs, tools, places).
- `hebbrix_entity_timeline` - What was true about an entity, and when.
- `hebbrix_graph_query` - Traverse relationships out from a named entity; pass a `timestamp` for point-in-time truth. (Free-text questions: use `hebbrix_search`.)
- `hebbrix_contradictions` - Surface facts that conflict with each other.

**Reasoning & account**

- `hebbrix_confidence` - How confident should the agent be before acting? Grounded in memory + past outcomes.
- `hebbrix_log_decision` - Record a decision and its outcome; feeds future confidence. Right after a `hebbrix_confidence` check you can log just the `outcome` — the description auto-fills from what you asked.
- `hebbrix_list_collections` - List the memory spaces this key can use.
- `hebbrix_account_status` - Tier, usage, limits, and expiry.

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

**Hosted — nothing to run.** Point any HTTP-capable MCP client at the official hosted endpoint and authenticate with your own key (get one at [hebbrix.com/dashboard/api-keys](https://www.hebbrix.com/dashboard/api-keys)):

```json
{ "mcpServers": { "hebbrix": {
  "url": "https://mcp.hebbrix.com/mcp",
  "headers": { "Authorization": "Bearer mem_sk_..." }
}}}
```

**Self-hosted multi-tenant — one instance, many users.** Same shape on your own infra. The server holds no key; every request authenticates with its own `Authorization` header:

```bash
HEBBRIX_MCP_MULTI_TENANT=1 HEBBRIX_MCP_HOST=0.0.0.0 uvx hebbrix-mcp --transport streamable-http
```

Or run the container (multi-tenant by default, `GET /healthz` for load-balancer probes):

```bash
docker build -t hebbrix-mcp . && docker run -p 8080:8080 hebbrix-mcp
```

In multi-tenant mode there is no default collection — pass `collection_id` on tool calls.

## How it works

```
┌──────────────────┐   MCP (stdio or HTTP)   ┌─────────────┐    HTTPS     ┌──────────┐
│ Claude / Cursor / │ ───────────────────────→│ hebbrix-mcp │─────────────→│ Hebbrix  │
│ Cline / any agent │      tool calls         │   (this)    │   REST API   │  cloud   │
└──────────────────┘                          └─────────────┘              └──────────┘
```

This package owns **zero state**. Tool calls become REST calls against your Hebbrix account; memories, embeddings, the knowledge graph, and retrieval all live in the Hebbrix backend. Delete this package and your memories are still there.

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
pytest tests/ -q            # 66 offline tests, no network needed
hebbrix-mcp                 # starts in agent mode on stdio
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

MIT — see [LICENSE](LICENSE).

## Links

- [Hebbrix documentation](https://www.hebbrix.com/docs)
- [MCP integration guide](https://www.hebbrix.com/integrations/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io)
