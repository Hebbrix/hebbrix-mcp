# Hebbrix MCP — hosted / self-hosted HTTP server image.
#
# Runs the MULTI-TENANT streamable-http server: one instance serves many users,
# and every request authenticates with its own `Authorization: Bearer <key>`
# header (the server holds no key of its own). This is the image behind the
# hosted mcp.hebbrix.com endpoint; it also works for self-hosting on your own
# infra.
#
#   docker build -t hebbrix-mcp .
#   docker run -p 8080:8080 hebbrix-mcp        # serves http://0.0.0.0:8080/mcp
#   curl localhost:8080/healthz                # -> {"status":"ok",...} (no auth)
#
FROM ghcr.io/astral-sh/uv:0.12.9@sha256:8b940d3a9d65bed080436972241af2e21c84b5e8c9193f7014ed71479ee795ff AS uv
FROM python:3.12-slim@sha256:e5c9fa26ffb76e11e0f054f30dc2523a2f9693f0c36c0cf1e39b27e152d899fc AS runtime

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    HEBBRIX_MCP_MULTI_TENANT=1 \
    HEBBRIX_MCP_HOST=0.0.0.0 \
    HEBBRIX_MCP_PORT=8080 \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

# Install exactly the hash-locked dependency graph, including the project.
COPY --from=uv /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY hebbrix_mcp ./hebbrix_mcp
RUN uv sync --frozen --no-dev --extra hosted --no-editable

# Run as a non-root user.
RUN useradd -m -u 10001 hebbrix
USER hebbrix

EXPOSE 8080

# GET /healthz returns 200 without auth (load-balancer health probe).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=4).status==200 else 1)"

CMD ["hebbrix-mcp", "--transport", "streamable-http"]
