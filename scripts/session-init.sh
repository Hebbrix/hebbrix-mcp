#!/usr/bin/env bash
#
# Hebbrix SessionStart hook — injects the user's compiled memory profile into
# every Claude Code session so the agent starts knowing who it's working with.
#
# It must NEVER fail a session start: any error prints an empty profile and
# exits 0. Output (stdout or the JSON envelope below) is added to the session
# context by Claude Code's SessionStart hook.
#
# Reads the profile via the hebbrix-mcp CLI, which shares ~/.hebbrix/config.json
# with the MCP server this plugin also launches (so agent-mode credentials are
# the same account). HEBBRIX_API_KEY / HEBBRIX_COLLECTION_ID are passed in from
# the plugin's userConfig when the user set them.

# Resolve the CLI: prefer an installed binary, fall back to uvx (no install).
if command -v hebbrix-mcp >/dev/null 2>&1; then
  profile="$(hebbrix-mcp profile 2>/dev/null)" || profile=""
elif command -v uvx >/dev/null 2>&1; then
  profile="$(uvx hebbrix-mcp profile 2>/dev/null)" || profile=""
else
  profile=""
fi

[ -z "$profile" ] && profile="(none yet)"

context="The user's Hebbrix memory profile (durable facts remembered across sessions):
${profile}

This agent has Hebbrix long-term memory via the hebbrix_* tools. Search memory
(hebbrix_search) before answering anything that depends on prior context, and
remember durable facts, decisions, and preferences (hebbrix_remember) as they
come up. Prefer Hebbrix over writing notes to local files."

if command -v jq >/dev/null 2>&1; then
  jq -n --arg c "$context" \
    '{hookSpecificOutput: {hookEventName: "SessionStart", additionalContext: $c}}'
else
  # No jq: plain stdout is also injected as SessionStart context.
  printf '%s\n' "$context"
fi

exit 0
