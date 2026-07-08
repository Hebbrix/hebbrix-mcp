# hebbrix-mcp

**Long-term memory and a knowledge graph for any MCP-compatible agent.**

Your agent forgets everything when the session ends. This server fixes that — and goes further than a plain memory store:

- **Memory** — store, search, correct, and version facts across sessions
- **Knowledge graph** — entities, relationships, timelines, and "what was true at time X"
- **Reasoning** — ask how confident the agent should be before acting, and log outcomes so it improves

Works with Claude Desktop, Claude Code, Cursor, Cline, Continue, and any other MCP client. Backed by [Hebbrix](https://www.hebbrix.com).

---

## Quick start (10 seconds, no account)

**1. Install**

```bash
pip install hebbrix-mcp
```

**2. Add to your MCP client** — no API key needed:

<details open>
<summary><b>Claude Desktop</b> — <code>~/Library/Application Support/Claude/claude_desktop_config.json</code></summary>

```json
{
  "mcpServers": {
    "hebbrix": { "command": "hebbrix-mcp" }
  }
}
```
</details>

<details>
<summary><b>Claude Code</b></summary>

```bash
claude mcp add hebbrix -- hebbrix-mcp
```
</details>

<details>
<summary><b>Cursor</b> — <code>~/.cursor/mcp.json</code></summary>

```json
{
  "mcpServers": {
    "hebbrix": { "command": "hebbrix-mcp" }
  }
}
```
</details>

<details>
<summary><b>Cline / Continue / other</b></summary>

Point your MCP servers config at the `hebbrix-mcp` command (stdio). Same shape as above.
</details>

**3. Restart the client.** Done — your agent now has persistent memory.

### What just happened?

On first run with no API key, the server mints a **free agent account** automatically (no email, no dashboard, ~1 second) and saves the credentials to `~/.hebbrix/config.json`. The account includes:

| | |
|---|---|
| Learning events (writes) | 300 |
| Retrievals (searches) | 2,000 |
| Expiry | 14 days after last activity, if unclaimed |

Every tool result includes a `hebbrix_usage` block (tier, usage, expiry), so the agent always knows where it stands and will tell you when it's time to claim.

### Keep it forever (one command)

```bash
hebbrix-mcp claim --email you@example.com
```

You'll get a 6-digit code by email; enter it and the account switches to the **free monthly tier with no expiry**. Same API key, all memories carry over. Confirming decision outcomes (`hebbrix_log_decision`) also extends the trial — the system rewards exactly the usage that makes it smarter.

---

## Using your own API key

Already have a Hebbrix account? Get a key at [hebbrix.com/dashboard/api-keys](https://www.hebbrix.com/dashboard/api-keys) and pass it instead:

```json
{
  "mcpServers": {
    "hebbrix": {
      "command": "hebbrix-mcp",
      "env": {
        "HEBBRIX_API_KEY": "mem_sk_...",
        "HEBBRIX_COLLECTION_ID": "your-default-collection-uuid"
      }
    }
  }
}
```

The env var always wins over saved agent-mode credentials.

---

## Tools

15 tools, one resource, one prompt. A server-level instruction block teaches the model when to reach for each, so a well-behaved agent searches before answering and remembers what matters — without being told.

### Memory

| Tool | What it does |
|---|---|
| `hebbrix_remember(content, tags?, collection_id?, verbatim?)` | Store a fact, decision, or preference. `verbatim=true` skips fact-extraction |
| `hebbrix_search(query, limit?, collection_id?)` | Semantic search (hybrid vector + BM25 + graph retrieval) |
| `hebbrix_get(memory_id)` | Fetch one memory with metadata |
| `hebbrix_update(memory_id, content?, importance?)` | Correct a memory **in place** — old versions are kept |
| `hebbrix_forget(memory_id)` | Delete a memory |
| `hebbrix_list(limit?, collection_id?)` | List recent memories |
| `hebbrix_history(memory_id)` | See how a memory changed over time |

### Knowledge graph

Reads are available on **every tier** (including agent mode). Graph writes and inference need a Pro plan.

| Tool | What it does |
|---|---|
| `hebbrix_search_entities(entity_type?, limit?, collection_id?)` | List known entities (people, orgs, tools, places) |
| `hebbrix_entity_timeline(entity_name, collection_id?)` | What was true about an entity, and when |
| `hebbrix_graph_query(query?, entity?, relation_type?, depth?, timestamp?)` | Query relationships — pass a `timestamp` to ask about a point in time |
| `hebbrix_contradictions(memory_id?)` | Surface facts that conflict with each other |

### Reasoning & account

| Tool | What it does |
|---|---|
| `hebbrix_confidence(query, collection_id?)` | How confident should the agent be before acting? Grounded in memory + past outcomes |
| `hebbrix_log_decision(description, outcome?, decision_type?)` | Record a decision and how it turned out — feeds future confidence |
| `hebbrix_list_collections()` | List the memory spaces this key can use |
| `hebbrix_account_status()` | Tier, usage, limits, and expiry |

**Also:** the `hebbrix://profile` resource and the `context` prompt inject the user's compiled profile into the conversation.

---

## Running modes

### 1. Local (default) — stdio

What the quick start above does. One process per client, credentials from env or `~/.hebbrix/config.json`.

### 2. Self-hosted HTTP — one instance, your machines

```bash
HEBBRIX_API_KEY=mem_sk_... hebbrix-mcp --transport streamable-http
# serves http://127.0.0.1:8080/mcp
```

```json
{ "mcpServers": { "hebbrix": { "url": "http://127.0.0.1:8080/mcp" } } }
```

### 3. Hosted multi-tenant — one instance, many users

The server holds **no key at all**; every request authenticates with its own `Authorization` header:

```bash
HEBBRIX_MCP_MULTI_TENANT=1 HEBBRIX_MCP_HOST=0.0.0.0 hebbrix-mcp --transport streamable-http
```

```json
{ "mcpServers": { "hebbrix": {
  "url": "https://your-host/mcp",
  "headers": { "Authorization": "Bearer mem_sk_..." }
}}}
```

In this mode there is no default collection — pass `collection_id` on tool calls.

---

## Configuration

All optional. With nothing set, the server starts in agent mode.

| Variable | Default | Purpose |
|---|---|---|
| `HEBBRIX_API_KEY` | *(agent mode mints one)* | Your Hebbrix bearer token |
| `HEBBRIX_COLLECTION_ID` | *(agent mode sets one)* | Default collection for writes/reads |
| `HEBBRIX_API_BASE` | `https://api.hebbrix.com/v1` | API endpoint override |
| `HEBBRIX_CONFIG` | `~/.hebbrix/config.json` | Where agent-mode credentials are saved |
| `HEBBRIX_MCP_HOST` | `127.0.0.1` | Bind host (HTTP transports) |
| `HEBBRIX_MCP_PORT` | `8080` | Bind port (HTTP transports) |
| `HEBBRIX_MCP_MULTI_TENANT` | off | Hosted mode: per-request header auth |

---

## How it works

```
┌──────────────────┐   MCP (stdio or HTTP)   ┌─────────────┐    HTTPS     ┌──────────┐
│ Claude / Cursor / │ ───────────────────────→│ hebbrix-mcp │─────────────→│ Hebbrix  │
│ Cline / any agent │      tool calls         │   (this)    │   REST API   │  cloud   │
└──────────────────┘                          └─────────────┘              └──────────┘
```

This package owns **zero state**. Tool calls become REST calls against your Hebbrix account; memories, embeddings, the knowledge graph, and retrieval all live in the Hebbrix backend. Delete this package and your memories are still there.

### Limits degrade gracefully

Agent-mode accounts never break mid-task. When a limit is reached you get a structured error, not a failure:

| Code | Meaning | What still works |
|---|---|---|
| `WRITE_LIMIT_REACHED` | 300 lifetime writes used | Reads, searches, confirmations |
| `READ_LIMIT_REACHED` | 2,000 lifetime retrievals used | Claim to continue |
| `SHADOW_READ_ONLY` | Unclaimed past 14 days | Reads (7-day grace window) |
| `SHADOW_EXPIRED` | Past the grace window | Nothing — account is reaped |
| `CLAIM_REQUIRED_FOR_BATCH` | Batch writes need a claimed account | Everything else |

Every error carries a `resolve` field with the exact command to fix it, so agents can relay it to you verbatim.

---

## Troubleshooting

**"HTTP 401" on every call** — the key is wrong or revoked. Unset `HEBBRIX_API_KEY`, delete `~/.hebbrix/config.json`, and restart to re-provision; or paste a fresh key from the dashboard.

**Agent mode won't start (`auto-signup unavailable`)** — signup may be at daily capacity (it's capped) or your network blocks the API. Set `HEBBRIX_API_KEY` from the dashboard instead.

**`claim` says `EMAIL_IN_USE`** — v1 claiming needs an email with no existing Hebbrix account. Use a fresh address (a `you+agent@gmail.com` alias works).

**A memory doesn't show up in search immediately** — indexing is asynchronous; typical convergence is under 30 seconds.

**Multi-tenant mode returns errors about collections** — there's no default collection in hosted mode; pass `collection_id` explicitly.

---

## Development

```bash
git clone https://github.com/Hebbrix/hebbrix-mcp
cd hebbrix-mcp
./quick_setup.sh            # venv + editable install
source venv/bin/activate
pytest tests/ -q            # 11 offline tests, no network needed
hebbrix-mcp                 # starts in agent mode on stdio
```

See [CHANGELOG.md](CHANGELOG.md) for release history and [CONTRIBUTING.md](CONTRIBUTING.md) for how to contribute.

## License

MIT — see [LICENSE](LICENSE).

## Related

- [Hebbrix documentation](https://www.hebbrix.com/docs)
- [MCP integration guide](https://www.hebbrix.com/integrations/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io)
