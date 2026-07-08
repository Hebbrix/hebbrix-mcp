"""Hebbrix MCP server — memory + knowledge graph tools for any MCP-compatible agent.

Tool surface (14 tools + a profile resource + a context prompt):
  Memory:  hebbrix_remember, hebbrix_search, hebbrix_get, hebbrix_update,
           hebbrix_forget, hebbrix_list, hebbrix_history
  Graph:   hebbrix_search_entities, hebbrix_entity_timeline,
           hebbrix_graph_query, hebbrix_contradictions
  Reason:  hebbrix_confidence, hebbrix_log_decision
  Scope:   hebbrix_list_collections

Transports: stdio (default) and streamable-http (--transport streamable-http).

AGENT MODE (accountless): with no HEBBRIX_API_KEY and no saved credentials,
the server mints a shadow account automatically (POST /v1/agent-signup) and
starts in <10s — no email, no dashboard. Every tool result then carries a
`hebbrix_usage` block (tier, limits, expiry, claim command) so the agent can
tell its human when to claim. `hebbrix-mcp claim --email <you>` upgrades to
the free monthly tier with the same key and all memories intact.

Configure with env vars:
  HEBBRIX_API_KEY        — optional (agent mode mints one), your bearer token
  HEBBRIX_COLLECTION_ID  — optional, default collection for new memories
  HEBBRIX_API_BASE       — optional, default https://api.hebbrix.com/v1
  HEBBRIX_MCP_HOST/PORT  — optional, streamable-http bind (default 127.0.0.1:8080)
  HEBBRIX_CONFIG         — optional, credentials path (default ~/.hebbrix/config.json)
"""
from .server import mcp, run

__version__ = "0.3.2"
__all__ = ["mcp", "run", "__version__"]
