# Contributing to hebbrix-mcp

Thanks for helping make agent memory better. This is a small, focused codebase — the whole server is one file.

## Setup

```bash
git clone https://github.com/Hebbrix/hebbrix-mcp
cd hebbrix-mcp
./quick_setup.sh              # creates ./venv and installs editable
source venv/bin/activate
pip install -e ".[dev]"       # pytest + ruff (CI runs both)
```

## Layout

```
hebbrix_mcp/server.py     — the entire server: tools, transports, agent mode,
                            claim + profile CLI, multi-tenant middleware
hebbrix_mcp/__init__.py   — public exports + version
tests/test_server.py      — offline tests (httpx is faked; no network, no key)
.claude-plugin/           — Claude Code plugin manifest + single-plugin marketplace
hooks/hooks.json          — plugin SessionStart hook wiring
scripts/session-init.sh   — hook script: injects the compiled profile into a session
Dockerfile                — hosted / self-hosted multi-tenant image
```

## Running

```bash
hebbrix-mcp                                  # stdio, agent mode if no key
HEBBRIX_API_KEY=... hebbrix-mcp              # stdio with your key
hebbrix-mcp --transport streamable-http      # HTTP at 127.0.0.1:8080/mcp
pytest tests/ -q                             # must stay green
```

## Guidelines

- **Tests must pass offline.** The suite fakes `httpx` — never add a test that
  needs the network or a real key.
- **Keep the tool surface deliberate.** Every tool costs context in the client.
  A new tool needs a reason an agent can't get from an existing one.
- **Tool docstrings are prompts.** The first line of each docstring is what the
  model reads when deciding to call it — write for the model, not for pydoc.
- **Zero state here.** This package must never persist user data beyond the
  credentials file. All state lives in the Hebbrix backend.
- **No new runtime dependencies** without discussion — the core is `mcp` +
  `httpx` on purpose (the optional `hosted` extra adds only `uvicorn`).

## Pull requests

1. Fork, branch from `main`.
2. Make the change + add/adjust tests.
3. `pytest tests/ -q` green, `python -m py_compile hebbrix_mcp/server.py` clean.
4. Update `CHANGELOG.md` under an "Unreleased" heading.
5. Open the PR with a clear description of the behavior change.

## Reporting issues

Use [GitHub issues](https://github.com/Hebbrix/hebbrix-mcp/issues). For
anything security-sensitive (keys, auth, tenant isolation), email
support@hebbrix.com instead of filing publicly.
