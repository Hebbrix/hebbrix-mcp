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
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HEBBRIX_MCP_MULTI_TENANT=1 \
    HEBBRIX_MCP_HOST=0.0.0.0 \
    HEBBRIX_MCP_PORT=8080

WORKDIR /app

# Install deps first (better layer caching), then the package itself.
COPY pyproject.toml README.md ./
COPY hebbrix_mcp ./hebbrix_mcp
RUN pip install ".[hosted]"

# Run as a non-root user.
RUN useradd -m -u 10001 hebbrix
USER hebbrix

EXPOSE 8080

# GET /healthz returns 200 without auth (load-balancer health probe).
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz',timeout=4).status==200 else 1)"

CMD ["hebbrix-mcp", "--transport", "streamable-http"]
