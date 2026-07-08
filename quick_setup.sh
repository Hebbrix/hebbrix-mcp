#!/usr/bin/env bash
# Hebbrix MCP — quick setup script.
#
# Installs the hebbrix-mcp package + prints the JSON snippet you paste into
# your MCP client config (Claude Desktop, Cline, Cursor, etc).
#
# Usage:
#   ./quick_setup.sh
#
# Or, if installing from PyPI directly:
#   pip install hebbrix-mcp
#   export HEBBRIX_API_KEY=...
#   hebbrix-mcp   # stdio MCP server

set -euo pipefail

echo "=== Hebbrix MCP — quick setup ==="
echo

# --- 1. Python check ------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 not found. Install Python 3.10+ first." >&2
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print("{}.{}".format(*sys.version_info[:2]))')
echo "Python $PY_VERSION detected."

# --- 2. venv --------------------------------------------------------------
VENV_DIR="${PWD}/venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating venv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

# --- 3. Install -----------------------------------------------------------
if [ -f "pyproject.toml" ]; then
    echo "Installing hebbrix-mcp from local source (editable)..."
    pip install -e . >/dev/null
else
    echo "Installing hebbrix-mcp from PyPI..."
    pip install --upgrade pip hebbrix-mcp >/dev/null
fi

# --- 4. API key check -----------------------------------------------------
if [ -z "${HEBBRIX_API_KEY:-}" ]; then
    if [ -f ".env" ]; then
        # shellcheck disable=SC1091
        set -a; source .env; set +a
    fi
fi

if [ -z "${HEBBRIX_API_KEY:-}" ]; then
    echo
    echo "ℹ️  No HEBBRIX_API_KEY set — that's fine. On first run the server starts"
    echo "    in AGENT MODE: it mints a free agent account automatically (no email,"
    echo "    no dashboard) and saves credentials to ~/.hebbrix/config.json."
    echo "    Prefer your own key? Get one at https://www.hebbrix.com/dashboard/api-keys"
    echo
fi

# --- 5. Print MCP client config -------------------------------------------
SERVER_BIN="$VENV_DIR/bin/hebbrix-mcp"
cat <<EOF

✅ Installed. Paste this into your MCP client config:

   Claude Desktop:  ~/Library/Application Support/Claude/claude_desktop_config.json
   Cline:           VS Code settings → "cline.mcp.servers"
   Cursor:          ~/.cursor/mcp.json

── no account needed (agent mode) ────────────────────────────────
{
  "mcpServers": {
    "hebbrix": { "command": "$SERVER_BIN" }
  }
}
── or with your own API key ──────────────────────────────────────
{
  "mcpServers": {
    "hebbrix": {
      "command": "$SERVER_BIN",
      "env": {
        "HEBBRIX_API_KEY": "your_key_here",
        "HEBBRIX_COLLECTION_ID": "your_default_collection_uuid"
      }
    }
  }
}
──────────────────────────────────────────────────────────────────

Then restart your MCP client. Your agent now has persistent memory.

Quick test in the venv:
   $ source venv/bin/activate
   $ hebbrix-mcp          # agent mode — mints a free account and runs on stdio
Keep the account later:
   $ hebbrix-mcp claim --email you@example.com

EOF
