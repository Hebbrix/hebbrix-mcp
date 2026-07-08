"""Offline tests for the Hebbrix MCP server — no network, httpx is faked.

Covers: tool/resource/prompt registration, result reshaping, the
hebbrix_usage block, error handling, credential loading, and claim helpers.
Run: pytest tests/ -q
"""
import asyncio
import json
import os

import pytest

os.environ.setdefault("HEBBRIX_API_KEY", "mem_sk_test_dummy")
from hebbrix_mcp import server as S  # noqa: E402


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}
        self.text = text or json.dumps(self._payload)

    def json(self):
        return self._payload


class FakeClient:
    """Stands in for httpx.AsyncClient inside `async with _client() as c`."""

    def __init__(self, response: FakeResponse):
        self._response = response
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def get(self, url, **kw):
        self.calls.append(("GET", url, kw))
        return self._response

    async def post(self, url, **kw):
        self.calls.append(("POST", url, kw))
        return self._response

    async def patch(self, url, **kw):
        self.calls.append(("PATCH", url, kw))
        return self._response

    async def delete(self, url, **kw):
        self.calls.append(("DELETE", url, kw))
        return self._response


@pytest.fixture(autouse=True)
def reset_usage():
    S._LAST_USAGE.set(None)  # per-request ContextVar, cleared between tests
    yield
    S._LAST_USAGE.set(None)


def _fake(monkeypatch, response: FakeResponse) -> FakeClient:
    client = FakeClient(response)
    monkeypatch.setattr(S, "_client", lambda: client)
    return client


# ------------------------------------------------------------- registration
def test_all_tools_resources_prompts_registered():
    async def check():
        tools = await S.mcp.list_tools()
        assert len(tools) == 15
        names = {t.name for t in tools}
        for expected in ("hebbrix_remember", "hebbrix_search", "hebbrix_get",
                         "hebbrix_update", "hebbrix_forget", "hebbrix_list",
                         "hebbrix_history", "hebbrix_search_entities",
                         "hebbrix_entity_timeline", "hebbrix_graph_query",
                         "hebbrix_contradictions", "hebbrix_confidence",
                         "hebbrix_log_decision", "hebbrix_list_collections",
                         "hebbrix_account_status"):
            assert expected in names
        resources = await S.mcp.list_resources()
        assert [str(r.uri) for r in resources] == ["hebbrix://profile"]
        prompts = await S.mcp.list_prompts()
        assert [p.name for p in prompts] == ["context"]

    asyncio.run(check())


# ---------------------------------------------------------------- reshaping
def test_remember_returns_id_and_status(monkeypatch):
    _fake(monkeypatch, FakeResponse(201, {"id": "m1", "processing_status": "pending",
                                          "importance": 0.5}))
    out = asyncio.run(S.hebbrix_remember("fact", collection_id="c1"))
    assert out["id"] == "m1" and out["status"] == "pending"


def test_remember_requires_collection(monkeypatch):
    monkeypatch.setattr(S, "DEFAULT_COLLECTION", "")
    out = asyncio.run(S.hebbrix_remember("fact"))
    assert "error" in out


def test_search_reshapes_results(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "m1", "content": "hello", "score": 0.91}],
        "processing_time_ms": 42}))
    out = asyncio.run(S.hebbrix_search("q", collection_id="c1"))
    assert out["count"] == 1
    assert out["results"][0] == {"id": "m1", "content": "hello", "score": 0.91}


def test_error_responses_are_structured(monkeypatch):
    _fake(monkeypatch, FakeResponse(500, text="boom"))
    out = asyncio.run(S.hebbrix_get("m1"))
    assert out["error"].startswith("HTTP 500")


# ------------------------------------------------------------- usage block
def test_usage_block_captured_and_attached(monkeypatch):
    headers = {
        "X-Hebbrix-Tier": "shadow", "X-Hebbrix-Status": "warning",
        "X-Hebbrix-Writes-Used": "241", "X-Hebbrix-Writes-Limit": "300",
        "X-Hebbrix-Retrievals-Used": "3", "X-Hebbrix-Retrievals-Limit": "2000",
        "X-Hebbrix-Expires-At": "2026-07-21T00:00:00+00:00",
        "X-Hebbrix-Claim": "hebbrix-mcp claim --email <you>",
    }
    _fake(monkeypatch, FakeResponse(201, {"id": "m1"}, headers=headers))
    out = asyncio.run(S.hebbrix_remember("fact", collection_id="c1"))
    u = out["hebbrix_usage"]
    assert u["tier"] == "shadow" and u["writes"] == {"used": 241, "limit": 300}
    # warning status must produce the human-relay string (the conversion loop)
    assert "claim" in u["action_for_human"].lower()


def test_no_usage_block_for_normal_accounts(monkeypatch):
    _fake(monkeypatch, FakeResponse(201, {"id": "m1"}))
    out = asyncio.run(S.hebbrix_remember("fact", collection_id="c1"))
    assert "hebbrix_usage" not in out


# ------------------------------------------------------------- credentials
def test_load_saved_credentials(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"api_key": "mem_sk_saved", "collection_id": "c9"}))
    monkeypatch.setattr(S, "CONFIG_PATH", cfg)
    monkeypatch.setattr(S, "KEY", "")
    monkeypatch.setattr(S, "DEFAULT_COLLECTION", "")
    assert S._load_saved_credentials() is True
    assert S.KEY == "mem_sk_saved" and S.DEFAULT_COLLECTION == "c9"


def test_env_key_wins_over_saved(monkeypatch, tmp_path):
    cfg = tmp_path / "config.json"
    cfg.write_text(json.dumps({"api_key": "mem_sk_saved"}))
    monkeypatch.setattr(S, "CONFIG_PATH", cfg)
    monkeypatch.setattr(S, "KEY", "mem_sk_env")
    S._load_saved_credentials()
    assert S.KEY == "mem_sk_env"


def test_cid_precedence(monkeypatch):
    monkeypatch.setattr(S, "DEFAULT_COLLECTION", "default-c")
    assert S._cid("explicit") == "explicit"
    assert S._cid(None) == "default-c"
    monkeypatch.setattr(S, "DEFAULT_COLLECTION", "")
    assert S._cid(None) is None


# ----------------------------------------------------------- multi-tenant
def test_request_key_contextvar_overrides_global(monkeypatch):
    token = S._REQUEST_KEY.set("mem_sk_tenant_a")
    try:
        client = S._client()
        assert client.headers["authorization"] == "Bearer mem_sk_tenant_a"
    finally:
        S._REQUEST_KEY.reset(token)
    client = S._client()
    assert client.headers["authorization"] == f"Bearer {S.KEY}"


# ------------------------------- customer-reported fixes (v0.3.3) -----------
def test_multi_tenant_client_never_uses_global_key(monkeypatch):
    # In multi-tenant mode with a stray global KEY set, a request with no
    # per-request bearer must NOT borrow the server key.
    monkeypatch.setattr(S, "MULTI_TENANT", True)
    monkeypatch.setattr(S, "KEY", "mem_sk_server_should_not_leak")
    token = S._REQUEST_KEY.set("")  # simulate a request with no bearer
    try:
        c = S._client()
        assert c.headers["authorization"] == "Bearer "  # empty, not the server key
    finally:
        S._REQUEST_KEY.reset(token)
    # single-tenant still falls back to the configured key
    monkeypatch.setattr(S, "MULTI_TENANT", False)
    tok = S._REQUEST_KEY.set("")
    try:
        assert S._client().headers["authorization"] == "Bearer mem_sk_server_should_not_leak"
    finally:
        S._REQUEST_KEY.reset(tok)


def test_entity_timeline_url_encodes_name(monkeypatch):
    captured = {}
    orig = S._get
    async def spy(path, params=None):
        captured["path"] = path
        return {"ok": True}
    monkeypatch.setattr(S, "_get", spy)
    import asyncio
    asyncio.run(S.hebbrix_entity_timeline("Acme/Corp?x#y", collection_id="c1"))
    assert "Acme/Corp?x#y" not in captured["path"]
    assert "Acme%2FCorp%3Fx%23y" in captured["path"]


def test_load_saved_credentials_reads_api_base(monkeypatch, tmp_path):
    import json as _json
    cfg = tmp_path / "config.json"
    cfg.write_text(_json.dumps({"api_key": "mem_sk_x", "api_base": "https://staging.hebbrix.com/v2"}))
    monkeypatch.setattr(S, "CONFIG_PATH", cfg)
    monkeypatch.setattr(S, "KEY", "")
    monkeypatch.setattr(S, "BASE", "https://api.hebbrix.com/v1")
    monkeypatch.setattr(S, "_API_BASE_FROM_ENV", False)  # user did NOT set env
    S._load_saved_credentials()
    assert S.BASE == "https://staging.hebbrix.com/v2"


def test_env_api_base_wins_over_saved(monkeypatch, tmp_path):
    import json as _json
    cfg = tmp_path / "config.json"
    cfg.write_text(_json.dumps({"api_key": "mem_sk_x", "api_base": "https://staging.hebbrix.com/v2"}))
    monkeypatch.setattr(S, "CONFIG_PATH", cfg)
    monkeypatch.setattr(S, "KEY", "")
    monkeypatch.setattr(S, "BASE", "https://api.hebbrix.com/v1")
    monkeypatch.setattr(S, "_API_BASE_FROM_ENV", True)  # user DID set env
    S._load_saved_credentials()
    assert S.BASE == "https://api.hebbrix.com/v1"  # env wins, saved ignored
