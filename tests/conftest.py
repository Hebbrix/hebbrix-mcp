"""Shared harness: the real MCP server over the real stdio protocol.

``MockBackend`` is a loopback HTTP double of the Hebbrix REST API (no network
beyond 127.0.0.1, no key). ``StdioMCP`` spawns ``hebbrix-mcp`` as a child
process exactly as an MCP host does and speaks JSON-RPC to it over stdio, so
tests observe what a client observes: ``isError``, structured content and the
exact HTTP requests the adapter sends upstream.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Optional, Union
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

Response = tuple[int, Any]
Route = Union[Response, Callable[[dict[str, Any]], Response]]


class MockBackend:
    """Loopback REST double. Routes map (METHOD, /v1 path) to a response."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], Route] = {}
        self.requests: list[dict[str, Any]] = []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: Any) -> None:  # keep test output clean
                return

            def _handle(self) -> None:
                url = urlparse(self.path)
                length = int(self.headers.get("content-length") or 0)
                raw = self.rfile.read(length) if length else b""
                try:
                    body = json.loads(raw) if raw else None
                except ValueError:
                    body = None
                request = {
                    "method": self.command,
                    "path": url.path,
                    "query": {k: v[-1] for k, v in parse_qs(url.query).items()},
                    "json": body,
                    "authorization": self.headers.get("authorization"),
                }
                backend.requests.append(request)
                route = backend.routes.get((self.command, url.path))
                if route is None:
                    status, payload = 404, {"detail": "Not found"}
                elif callable(route):
                    status, payload = route(request)
                else:
                    status, payload = route
                data = b"" if payload is None else json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            do_GET = do_POST = do_PATCH = do_PUT = do_DELETE = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.server.server_address[1]}/v1"

    def reset(self, routes: Optional[dict[tuple[str, str], Route]] = None) -> None:
        self.routes = dict(routes or {})
        self.requests.clear()

    def sent(self, method: str, path: str) -> list[dict[str, Any]]:
        return [r for r in self.requests if r["method"] == method and r["path"] == path]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=10)


class StdioMCP:
    """One hebbrix-mcp child process driven through the MCP stdio client."""

    def __init__(self, env: dict[str, str]) -> None:
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._loop.run_forever, daemon=True)
        self._thread.start()
        self._ready: concurrent.futures.Future = concurrent.futures.Future()
        self._stop: Optional[asyncio.Event] = None
        self._main_future = asyncio.run_coroutine_threadsafe(self._main(env), self._loop)
        self.session, self.server_version = self._ready.result(timeout=90)

    async def _main(self, env: dict[str, str]) -> None:
        self._stop = asyncio.Event()
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from hebbrix_mcp.server import run; run()"],
            env=env,
        )
        with open(os.devnull, "w") as quiet:
            try:
                async with stdio_client(params, errlog=quiet) as streams:
                    async with ClientSession(*streams) as session:
                        init = await session.initialize()
                        self._ready.set_result((session, init.serverInfo.version))
                        await self._stop.wait()
            except BaseException as exc:
                if not self._ready.done():
                    self._ready.set_exception(exc)
                raise

    def call(self, name: str, **arguments: Any) -> tuple[bool, dict[str, Any]]:
        """Call a tool; return (isError, payload) exactly as a client sees them."""
        result = asyncio.run_coroutine_threadsafe(
            self.session.call_tool(name, arguments), self._loop
        ).result(timeout=120)
        text = next(
            (item.text for item in result.content if getattr(item, "type", "") == "text"),
            "",
        )
        if result.isError:
            start = text.find("{")
            try:
                payload = json.loads(text[start:]) if start >= 0 else {"error": text}
            except ValueError:
                payload = {"error": text}
        else:
            payload = result.structuredContent or (json.loads(text) if text else {})
        return bool(result.isError), payload

    def close(self) -> None:
        if self._stop is not None:
            self._loop.call_soon_threadsafe(self._stop.set)
        try:
            self._main_future.result(timeout=30)
        finally:
            self._loop.call_soon_threadsafe(self._loop.stop)
            self._thread.join(timeout=10)
            self._loop.close()


def server_env(base: str, tmp_dir: str, **extra: str) -> dict[str, str]:
    """Child environment: explicit key/base/collection, isolated credentials file."""
    env = {
        "HEBBRIX_API_KEY": "mem_sk_offline_protocol_test",
        "HEBBRIX_API_BASE": base,
        "HEBBRIX_COLLECTION_ID": "c-protocol",
        "HEBBRIX_CONFIG": os.path.join(tmp_dir, "config.json"),
        "HEBBRIX_EXTRACTION_POLL_SECONDS": "4",
    }
    env.update(extra)
    return env
