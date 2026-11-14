# Hebbrix MCP Server

<!-- mcp-name: io.github.Hebbrix/hebbrix-mcp -->

[![PyPI](https://img.shields.io/pypi/v/hebbrix-mcp)](https://pypi.org/project/hebbrix-mcp/)
[![CI](https://github.com/Hebbrix/hebbrix-mcp/actions/workflows/ci.yml/badge.svg)](https://github.com/Hebbrix/hebbrix-mcp/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/hebbrix-mcp)](https://pypi.org/project/hebbrix-mcp/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

A Model Context Protocol server that gives any AI agent persistent memory, a
temporal knowledge graph, and outcome-based learning, backed by
[Hebbrix](https://www.hebbrix.com).

This repository is the MIT-licensed MCP adapter. Durable storage, retrieval,
graph processing, reasoning, and Outcome Memory are provided by the Hebbrix
cloud API; this repository does not claim that the backend is self-hostable or
open source.

Your agent forgets everything when the session ends. This fixes that, and goes further than a plain memory store:

- **Memory** — store, search, correct, and version facts across sessions
- **Knowledge graph** — entities, relationships, timelines, and "what was true at time X"
- **Reasoning** — ask how confident the agent should be before acting, and log outcomes so it improves
- **Outcome Memory** — learn which action works for each customer and context
  from delayed results, with safe baselines and inspectable uncertainty

Works with Claude Desktop, Claude Code, Cursor, Cline, Continue, and any other MCP client.

> [!IMPORTANT]
> **Serving more than one end user? Bind each session's user in your application.**
> The account API key is the principal: whoever holds it, a model included, can
> reach every memory of the account. A `user_id` is a filter, not proof of who is
> asking. Authenticate the end user in your application, pin their `user_id` for
> the MCP session before the agent sees any tool (`X-Hebbrix-User-Id` on a hosted
> server, `HEBBRIX_USER_ID` on a local one), and never let the model choose it.
> Complete hosted and local examples:
> [End users, scope and authorization](#end-users-scope-and-authorization).

### Release compatibility

| MCP package | Hosted/API contract | Tool surface | Migration |
|---|---|---:|---|
| 0.5.15 | Hebbrix API 1.4 / search-safety-v1 | 38 | End-user scope, readiness answer gate, supporting-passage citations, one `isError` rule, fail-closed envelope validation, working extraction defaults |
| 0.5.12 | Hebbrix API 1.1.3 / search-safety-v1 / claim-grounding-v29 | 33 | Canonical extraction polling, safe transport errors, consistent evidence diagnostics |
| 0.5.8 | Hebbrix API 1.0.0 / search-safety-v1 | 32 | Adds procedure lifecycle tools |

Version 0.5.15 adds explicit `user_id` / `agent_id` / `run_id` scope to every
memory, retrieval and graph tool the API can scope (see
[End users, scope and authorization](#end-users-scope-and-authorization)),
exposes the API's readiness fields and an SDK-equivalent `answer_gate` on search
and ask (see [Answer readiness](#answer-readiness-and-strict-gating)), returns
the API's supporting passage (or the whole memory) as each ask citation, and
validates every search and ask envelope with one fail-closed check (see
[Errors and fail-closed evidence](#errors-and-fail-closed-evidence)).
`hebbrix_remember(extract=True)` works with its defaults again. Behaviour changes
to note when upgrading: quota exhaustion, degraded evidence and malformed
evidence receipts are now MCP errors (`isError: true`) on every tool; `degraded`
now means the evidence pipeline itself degraded, while a scope that is still
indexing is reported through `indexing` and `answer_gate.ready` and keeps the
evidence the API keeps; citations gain `passage`, `truncated` and
`content_length` fields.

Version 0.5.10 preserves upstream indexing receipts across writes, updates, and
polling. Graph status distinguishes related memories from entity relationships.
The companion API's claim-grounding-v28 contract verifies named-subject evidence
consistently across cold and cached retrieval and preserves purpose and direction;
the adapter never bypasses upstream grounding to manufacture an answer.

Version 0.5.11 adds response-local `diagnostics` (request ID, build, grounding and
safety versions, and search cache path). An ask fallback includes separate
`reasoning` and `retrieval` diagnostics. No credentials or memory content are
included in diagnostics. `synthesis_status` distinguishes `synthesized`,
`retrieval_only`, and `abstained`. `failure_category` distinguishes unknown facts,
unverified candidates, unavailable verification, service failures, quota
exhaustion, and malformed evidence receipts. Legitimate abstention is not a
transport error. These labels do not weaken the evidence gate.

Reproduce the full customer set and additional distractor checks with
`python scripts/verify_recall.py --require-graph` against a local API first;
use `--mcp http://localhost:8099/mcp` for HTTP. Remote fixture writes require
`--allow-remote`. The verifier creates isolated guests, tests both result limits
before and after asynchronous processing, then deletes its collections.
This targeted regression suite is not a representative accuracy benchmark;
conservative abstentions and probabilistic synthesis remain possible.

Version 0.5.9 makes structured failures real MCP errors over both stdio and
hosted HTTP, preserves authoritative recall when GraphRAG abstains by returning
an explicitly retrieval-only result, and adds bounded graph-enrichment status
polling. Version 0.5.8 added the complete tenant-scoped procedure lifecycle (including
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
| `HEBBRIX_USER_ID` / `HEBBRIX_AGENT_ID` / `HEBBRIX_RUN_ID` | *(none)* | Pin the end-user / agent / run scope of a local server; tool arguments cannot change it |
| `HEBBRIX_EXTRACTION_POLL_SECONDS` | `20` (max 25) | How long `hebbrix_remember(extract=True)` waits for its extraction job and search readiness |
| `HEBBRIX_MCP_SESSION_SECRET` | *(required for accountless)* | HMAC secret for stateless Secure guest cookies |
| `HEBBRIX_MCP_INTERNAL_SECRET` | *(required for accountless)* | HMAC trust bridge for original-client signup throttling |

## Available Tools

A server-level instruction block teaches the model when to reach for each tool, so a well-behaved agent searches before answering and remembers what matters without being told.

**Memory**

- `hebbrix_remember` - Store a fact, decision, or preference.
    - `content` (string, required): the memory text
    - `tags` (list, optional), `collection_id` (string, optional)
    - `user_id`, `agent_id`, `run_id` (string, optional): store the memory for one end user / agent / run
    - `extract` (bool, default false): false stores the text exactly (one memory); true starts a tracked fact-extraction job and may create several atomic memories
    - `wait_for_extraction` (bool, default true): for smart ingestion, poll for up to 20 seconds and return normalized atomic memories. Set false for immediate acknowledgement, then call `hebbrix_extraction_status` with the returned job id.
    - `wait_for_index` (bool, default true): waits, within a bounded deadline, for **memory-search** availability. For a raw write the API performs the wait; for `extract=true` the adapter polls the job and its readiness receipt (`/v1/memories/batches/{outbox_event_id}`), because the API rejects `wait_for_index` together with background extraction. Check the returned `searchable` acknowledgement: if false, the write is durable but indexing is not confirmed; poll `hebbrix_get(id)` and do not repeat the write. It does **not** cover asynchronous knowledge-graph enrichment; use `hebbrix_graph_status` for durable completion. Its `related_memory_count` counts neighboring memories, not entity relationships; zero neighbors does not mean zero extracted edges.
- `hebbrix_extraction_status` - Poll a smart-ingestion job until its created/updated memories or terminal error are available; a completed job's `searchable` comes from its readiness receipt.
- `hebbrix_remember_many` - Store **many** facts in one call (one round-trip, one rate-limit hit). Pass `facts` (list of strings). Falls back to sequential writes on free/agent tiers.
- `hebbrix_search` - Semantic search (hybrid vector + BM25 + graph retrieval).
    - `query` (string, required), `limit` (int, optional), `collection_id` (string, optional)
    - `user_id`, `agent_id`, `run_id` (string, optional): search one end user / agent / run (required for a collection holding end-user data)
    - `min_score` (float, default 0.0): drop weak matches — zero-relevance padding is always dropped; raise this to filter noise so you don't pay tokens for it.
    - Results carry the readiness fields and `answer_gate` described in [Answer readiness](#answer-readiness-and-strict-gating).
- `hebbrix_get` - Fetch one memory by id, with metadata. `user_id` / `agent_id` / `run_id` / `collection_id` require the memory to belong to that exact scope.
- `hebbrix_update` - Correct a memory **in place** (old versions are kept).
- `hebbrix_forget` - Delete a memory by id.
- `hebbrix_list` - List recent memories (content previews; a cut preview has `truncated: true`).
- `hebbrix_history` - See how a memory changed over time.

All memory tools above, `hebbrix_export`, `hebbrix_import` and `hebbrix_graph_status`
accept `user_id`, `agent_id` and `run_id`; the graph read tools and
`hebbrix_confidence` accept `user_id` (graph data is attributed to end users, not
agents or runs).
- `hebbrix_mark_used` - Reinforce a memory you actually used (`helpful=True` strengthens it, `False` weakens it) so recall improves over time.
- `hebbrix_export` - Export a whole collection (memories + graph entities + profile) as JSON or Markdown, in one call.
- `hebbrix_import` - The inverse of export: import a list of facts, an export JSON, or notes/markdown into a collection (restore a backup, migrate, or seed from `CLAUDE.md`).

**Knowledge graph** — Hebbrix automatically extracts entities and relationships from the memories you write, on **every tier including agent mode**, so all the graph *reads* below (entities, timelines, traversal, contradictions) work in agent mode too. Only explicit graph *write* / inference operations require a Pro plan.

- `hebbrix_search_entities` - List known entities (people, orgs, tools, places).
- `hebbrix_entity_timeline` - What was true about an entity, and when.
- `hebbrix_graph_query` - Traverse relationships out from a named entity; pass a `timestamp` for point-in-time truth. Results are trimmed (from/to/type/valid_from), not raw backend payloads. (Free-text questions: use `hebbrix_ask`.)
- `hebbrix_graph_status` - Check one memory's asynchronous graph readiness, optionally polling for up to 30 seconds. Readiness comes from durable, source-revision-bound delivery acknowledgements—not elapsed time, search readiness, or an empty graph query. It distinguishes successful enrichment with no related facts from a still-processing, failed, or temporarily unreadable graph.
- `hebbrix_contradictions` - Surface facts that conflict with each other.

**Procedural memory**

- `hebbrix_create_procedure` - Store a scoped condition/action procedure.
- `hebbrix_list_procedures` / `hebbrix_get_procedure` - Inspect owned procedures.
- `hebbrix_update_procedure` - Update mutable fields; ownership scope is immutable.
- `hebbrix_execute_procedure` - Execute a procedure and record the execution.
- `hebbrix_delete_procedure` - Idempotently delete a procedure and its executions. The API returns the same 204 for deleted, absent, and foreign-tenant IDs so the tool cannot reveal another tenant's identifier.

**October 2 follow-up:** the setup/report tools, automatic v2 selection,
decision proposal priors and structured paraphrase matching below require the
matching October 2 outcome-followup backend. Inspect `/v1/release` before use.
No learning-performance superiority, reliable model compliance with feedback,
or automatic execution is established. These tools never grant permission.

**Reasoning & account**

- `hebbrix_ask` - **One-call GraphRAG.** Ask a natural-language question; it searches memory, synthesizes an answer with an LLM, and cites the memory ids it used. If synthesis abstains while authoritative search has grounded evidence, it returns that evidence as `synthesis_status: "retrieval_only"` instead of silently losing recall or pretending synthesis succeeded. Accepts `user_id` / `agent_id` / `run_id`.
    - Each citation is `{id, content, score, passage, truncated, content_length}`. `content` is the API's verbatim supporting passage for that memory (`passage: "supporting_span"`) when the API reports one, otherwise the whole memory (`"full_content"`), cut only beyond 4,000 characters (`"leading_characters"`). Whenever `content` is not the whole memory, `truncated` is `true` and `fetch_full_content` names the `hebbrix_get` call (with the same scope) that returns all of it.
- `hebbrix_confidence` - Read separate memory support and action-confidence signals,
  with ASK/REVIEW/ACT advice. Pass policy/action/context for exact configured
  evidence. Memory similarity alone never earns ACT. Advice is not permission.
- `hebbrix_log_decision` - Record a decision and its outcome; feeds future confidence. Right after a `hebbrix_confidence` check you can log just the `outcome` — the description auto-fills from what you asked.
- `hebbrix_choose_action` - Choose among repeatable strategies and create a
  decision receipt before acting. Supports per-user/context policies and bounded
  exploration; neither a receipt nor caller-supplied outcomes establish causality
  or execution authority. `adaptive_exploration=true` requires an explicitly
  configured posterior-sampling policy and low-risk exploration opt-ins. The new
  default `auto` enables sampling only for v2 low-risk opted-in actions; old or
  unconfigured policies stay conservative. `prior_action` and `prior_strength`
  supply a bounded, decaying proposal for one server-selected decision, never a
  reported outcome or a permission grant.
- `hebbrix_setup_policy` - Atomically enroll context and configure a new policy.
  Requires owner-declared action risk and exploration permission; cannot reset
  an existing policy. Unknown/high-risk actions remain conservative.
- `hebbrix_learning_report` - Read a bounded scoped weekly report of observed
  leaders and recorded evidence-readiness transitions. Current adaptive-policy
  uplift is not identified; descriptive action rates are not causal lift.
- `hebbrix_context_schema` - Enroll the immutable declared context before the
  first decision. Fields use `{name: {values: [...], required: true}}`. Optional
  backoff never drops required fields. Only change contracts on owner instruction.
- `hebbrix_configure_policy` - Revision-checked configuration of strategy, bounded
  priors, decay, window and action risk. Requires explicit owner instruction;
  never silently lower risk or replace the action target to obtain ACT advice.
- `hebbrix_policy_advice` - Read a scoped evidence card with ranked actions,
  uncertainty, reported failure attempts, descriptive change alerts and an
  exploration candidate. Not a chosen-action receipt or permission to execute.
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

## End users, scope and authorization

Read this before giving an agent memory tools in an application with several
end users. Hebbrix cannot tell which of your users is talking to the agent; only
your application can. The rules:

1. **The account API key is the principal.** Keep it on your server.
2. **A `user_id` is not proof of identity.** It is a filter the API applies
   exactly, whoever sends it.
3. **Bind the authenticated user's scope before the agent sees a tool.** Pin
   `user_id` (and `agent_id` / `run_id` if you use them) for the MCP session from
   your own authentication, and do not let the model or the end user supply it.
4. **Reads by ID need your authorization boundary too.** A memory ID is not a
   secret or a capability: `hebbrix_get` (and `GET /v1/memories/{id}`) return any
   memory of the account unless the scope is passed, so pin the scope (the
   adapter then applies it to every ID-addressed tool) or check the memory's
   owner in your application before showing it.

In detail:

- **The account API key is the principal.** Every tool call authenticates as the
  account that owns the key, and that account can read and write every memory in
  its collections.
- **`user_id`, `agent_id` and `run_id` are caller-asserted scope.** The API
  applies them exactly: writes are stored under them; search, ask, list and export
  return only that scope; ID-addressed tools (`hebbrix_get`, `hebbrix_update`,
  `hebbrix_forget`, `hebbrix_history`, `hebbrix_graph_status`) return not found
  unless the memory belongs to it. A collection that holds end-user data refuses
  an unscoped read (`HTTP 400 end_user_scope_required`, surfaced as an MCP error):
  a collection alone is not a user boundary. A collection with the API's
  `require_user_id` setting also refuses unscoped ID reads.
- **Your application must bind `user_id` to its own authenticated user.** The
  adapter does not authenticate end users. Never take `user_id` from end-user
  input or let a model choose it. When a model drives the tool calls, pin the
  scope for the whole session: `HEBBRIX_USER_ID` / `HEBBRIX_AGENT_ID` /
  `HEBBRIX_RUN_ID` for a local server, or the `X-Hebbrix-User-Id` /
  `X-Hebbrix-Agent-Id` / `X-Hebbrix-Run-Id` request headers for a hosted one. A
  tool argument that differs from a pinned value is refused (`error_code:
  scope_pinned`), and a tool that cannot be narrowed to a pinned field refuses
  rather than read wider (`unsupported_scope`; Outcome Memory tools apply only
  `user_id`, which is their only scope dimension).
- **Memory IDs are not secrets.** Any holder of the account key can fetch any of
  the account's memories by ID; pass the scope to `hebbrix_get` to require that
  the memory belongs to it, and never treat an ID as a capability.
- **Enforcement.** API keys carry operation permissions (for example
  `memories:read`) and an admin capability for cross-user reads, but the API has
  no end-user-bound keys today. The end-user boundary is therefore asserted by the
  application that holds the key, not enforced by the credential: keep the
  account key out of end-user-controlled code and pin the scope where your
  application, not the end user or the model, sets it.

### Secure multi-user setup: hosted server

Your application's server is the gateway: it authenticates the end user, then
opens that user's MCP session to `https://mcp.hebbrix.com/mcp` with the account
key and `X-Hebbrix-User-Id` set to the authenticated user. The hosted server is
stateless and reads the pin from every request, so set the header on every
request of the session; a client created with fixed headers, as below, does.

```python
# Runs on your server, never in the browser. pip install mcp
import os
from contextlib import asynccontextmanager

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

HEBBRIX_MCP_URL = "https://mcp.hebbrix.com/mcp"
HEBBRIX_API_KEY = os.environ["HEBBRIX_API_KEY"]  # the account key: server-side only

# Scope belongs to the application. The model never sees or sets these.
SCOPE_ARGUMENTS = {"user_id", "agent_id", "run_id", "collection_id"}


@asynccontextmanager
async def memory_session(authenticated_user_id: str):
    """One MCP session per authenticated end-user session.

    authenticated_user_id comes from your own sign-in (session cookie, OAuth
    token, ...), never from the request body, a tool argument or the model.
    """
    headers = {
        "Authorization": f"Bearer {HEBBRIX_API_KEY}",
        "X-Hebbrix-User-Id": authenticated_user_id,  # pinned for every request
    }
    async with streamablehttp_client(HEBBRIX_MCP_URL, headers=headers) as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def tools_for_model(tools):
    """The tool list the model sees: scope arguments removed from every schema."""
    exposed = []
    for tool in tools:
        schema = dict(tool.inputSchema or {})
        schema["properties"] = {
            name: spec
            for name, spec in (schema.get("properties") or {}).items()
            if name not in SCOPE_ARGUMENTS
        }
        schema["required"] = [
            name for name in schema.get("required", []) if name not in SCOPE_ARGUMENTS
        ]
        exposed.append({"name": tool.name, "description": tool.description,
                        "input_schema": schema})
    return exposed


async def call_tool_for_model(session: ClientSession, name: str, arguments: dict):
    """Forward a model's tool call; reject any attempt to choose the scope."""
    overrides = SCOPE_ARGUMENTS & set(arguments)
    if overrides:
        return {"isError": True,
                "error": f"scope is set by the application: {sorted(overrides)}"}
    return await session.call_tool(name, arguments)


# In a request handler, after your own authentication:
#   async with memory_session(current_user.id) as session:
#       tools = tools_for_model((await session.list_tools()).tools)
#       ... run the model with `tools`; route each tool call through
#       call_tool_for_model(session, call.name, call.arguments)
```

Two layers hold the scope. Your application drops and rejects scope arguments
from the model, and the pinned header makes the server refuse any tool argument
that differs from it (`error_code: "scope_pinned"`, `isError: true`) and apply the
pinned user to every tool, including the ID-addressed ones: `hebbrix_get` with
another user's memory ID returns not found. A tool that cannot be narrowed to a
pinned field refuses (`unsupported_scope`) rather than read wider.

If instead you put a reverse proxy between an MCP client you do not control and
the hosted server, the proxy must do the same on every request: authenticate
the end user, remove any `Authorization`, `Cookie` and `X-Hebbrix-*` headers the
client sent, then add the account key and `X-Hebbrix-User-Id` for the
authenticated user. A request that reaches the server without the header is not
pinned. A self-hosted multi-tenant server (`HEBBRIX_MCP_MULTI_TENANT=1`) reads
the same headers.

### Secure multi-user setup: local server

A local (stdio) server reads its pin from the environment when it starts, so run
one process per end-user session and set `HEBBRIX_USER_ID` from your
authentication:

```python
import os

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def hebbrix_server_for(authenticated_user_id: str) -> StdioServerParameters:
    return StdioServerParameters(
        command="uvx",
        args=["hebbrix-mcp"],
        env={
            "PATH": os.environ["PATH"],
            "HEBBRIX_API_KEY": os.environ["HEBBRIX_API_KEY"],
            "HEBBRIX_USER_ID": authenticated_user_id,  # fixed for this process
        },
    )


# async with stdio_client(hebbrix_server_for(current_user.id)) as (read, write):
#     async with ClientSession(read, write) as session:
#         await session.initialize()
#         ... expose tools_for_model(...) and call_tool_for_model(...) as above
```

For one person on their own machine the same pin is a client config entry:

```json
{
  "mcpServers": {
    "hebbrix": {
      "command": "uvx",
      "args": ["hebbrix-mcp"],
      "env": { "HEBBRIX_API_KEY": "mem_sk_...", "HEBBRIX_USER_ID": "user-123" }
    }
  }
}
```

Never share one local process between end users: its pin is the user it was
started for. A self-hosted single-tenant HTTP server (`--transport
streamable-http` without `HEBBRIX_MCP_MULTI_TENANT`) also takes its pin from the
environment, for every request it serves; run one per end user, or run the
multi-tenant mode and pin with headers.

## Answer readiness and strict gating

`hebbrix_search` and `hebbrix_ask` return the API's readiness and abstention
fields in a stable shape. `answer_status`, `indexing`, `no_match`,
`abstain_recommended`, `evidence_withheld`, `failure_category` and `answer_gate`
are always present (`answer_status` and `indexing` are `null` when the API did
not send them); the verbatim API fields below appear when the API sends them, and
`safety_reason` whenever evidence is withheld:

| Field | Meaning |
|---|---|
| `answer_status` | The API's `answer_status`: `answerable`, `conflicting`, `superseded`, `unverified`, `indexing`, `no_relevant_memory` |
| `indexing` | The API's scope readiness: `status` (`ready`/`incomplete`/`failed`/`unknown`), `pending_memories`, `keyword_only_memories`, `failed_memories`, `capped`, `answer_risk` (`none`/`may_change`/`incomplete_set`) |
| `no_match`, `abstain_recommended` | Abstention flags (true whenever evidence is withheld) |
| `confidence_reason`, `degraded_sources` | Search only, verbatim from the API |
| `decision_abstained`, `abstain_reason`, `reasoning_status` | Ask only, verbatim from the reasoning API |
| `evidence_withheld`, `failure_category`, `safety_reason` | Whether and why this adapter withheld evidence |
| `answer_gate` | The answer decision below |

`answer_gate` is `{ready, safe_to_answer, reason, action, require_ready:
{safe_to_answer, reason, action}}`. It is derived only from those REST fields,
exactly as the Python SDK derives it: `safe_to_answer` equals
`should_answer(response)` and `require_ready.safe_to_answer` equals
`should_answer(response, require_ready=True)` on the same REST response
(history mode off). `ready` is the SDK's readiness test (`indexing.status` is
`ready` and `answer_risk` is `none`). Both decisions are additionally `false`
whenever this adapter withheld the evidence. `action` is one of `answer`,
`ask_user`, `say_no_longer_current`, `abstain`, `retry`, `say_unknown`,
`verify_authorization` or `use_as_context`.

For high-stakes flows (money, health, actions), answer only when
`answer_gate.require_ready.safe_to_answer` is true and otherwise follow
`answer_gate.require_ready.action` (`retry` while the scope is indexing). No
separate MCP helper tool is planned: the gate is part of every search and ask
result. An answer read from a scope that is still indexing (`answer_risk:
may_change`) is returned with `ready: false`, as the API returns it; a count,
total or list over an incompletely indexed scope is withheld by the API itself.

## Errors and fail-closed evidence

One rule decides `isError` for every tool, at the protocol boundary, over stdio
and hosted HTTP alike: a result is an MCP error exactly when it carries a
top-level `error`, reports `degraded: true` (the evidence pipeline itself
degraded), or has an operational `failure_category` (`service_failure`,
`verification_unavailable`, `quota_exhausted`, `malformed_evidence_receipt`).
The error content is the same JSON payload with `ok: false`. An ordinary
abstention is a successful result with no evidence: `unknown_fact`,
`synthesis_abstention`, `unverified_candidates` or `index_pending`. An ask that
recovers through its retrieval-only fallback succeeds and reports the failed leg
in `reasoning_failure_category`.

Every search and ask envelope (including the ask fallback's search) passes one
fail-closed check before any evidence or answer is returned. Evidence and answers
are withheld, with `evidence_withheld: true` and the reason in `safety_reason`,
whenever:

- any abstention or no-match signal is set (`no_match`, `abstain_recommended`,
  `decision_abstained`, or an `answer_status` other than `answerable`);
- the grounding receipt is missing, empty, lacks a status, has an unknown status,
  or is ungrounded (`no_grounded_match`, `verification_unavailable`,
  `grounded: false`) while evidence is present;
- `safety_contract_version` is missing, null or unsupported (supported:
  `search-safety-v1`);
- the envelope contradicts itself: evidence beside `no_match`, an answer beside
  `decision_abstained`, `answerable` beside an abstention flag, evidence IDs that
  are not exactly the returned rows, duplicate or empty IDs, or a non-abstaining
  response without rows;
- the API reports its evidence pipeline degraded or verification unavailable.

Contradictions and contract violations are `malformed_evidence_receipt` (an MCP
error); abstentions are not errors.

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
- **`HTTP 400 ... Provide user_id to read a collection containing end-user data`** — the collection stores memories for end users; pass the end user's `user_id` (or pin it) on search, ask, list and export.
- **A memory isn't searchable immediately** — `wait_for_index=true` requests a bounded wait, not an unconditional guarantee. Check `searchable`; if false, poll `hebbrix_get(id)` and preserve the receipt. Do not repeat an accepted write.
- **A just-written fact's entities aren't in the graph yet** — knowledge-graph enrichment (entities, timelines, graph queries) runs *asynchronously after* the write and is not covered by `wait_for_index`. It typically lands within ~30s; the write response's `graph_enrichment: "processing"` signals it's still in flight.

## Development

```bash
git clone https://github.com/Hebbrix/hebbrix-mcp
cd hebbrix-mcp
python -m pip install uv==0.8.4
uv sync --frozen --extra dev
uv run --frozen pytest tests/ -q -W error  # offline; no network or key needed
hebbrix-mcp                 # starts in agent mode on stdio
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

An opt-in integration check reproduces conversational recall, corrections,
fresh-process retrieval, abstention, isolation, and disposable collection cleanup:

```bash
uv run --frozen python scripts/verify_recall.py --api http://localhost:8000
```

It creates synthetic data in two new guest collections and deletes them in a
cleanup block. Remote targets require `--allow-remote`; `--mcp URL` selects the
hosted transport and `--require-graph` checks asynchronous graph enrichment too.

The offline suite includes protocol tests that drive the real server over stdio
against a loopback mock of the REST API. An opt-in live compatibility test runs
the same stdio protocol against a real API (remember plain and with extraction,
search, ask, get, and end-user scope), in disposable collections it deletes
afterwards:

```bash
HEBBRIX_LIVE_API_URL=http://localhost:8000 \
HEBBRIX_LIVE_API_KEY_FILE=/path/to/key.json \
uv run --frozen pytest tests/test_live_api.py -q -W error
```

The key is read from `HEBBRIX_LIVE_API_KEY` or the `api_key` field of the JSON
file and is never printed. Non-local APIs require `HEBBRIX_LIVE_ALLOW_REMOTE=1`.

## License

MIT — see [LICENSE](LICENSE).

## Links

- [Hebbrix documentation](https://www.hebbrix.com/docs)
- [MCP integration guide](https://www.hebbrix.com/integrations/mcp)
- [Model Context Protocol](https://modelcontextprotocol.io)
