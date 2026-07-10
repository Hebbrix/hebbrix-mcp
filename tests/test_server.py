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
    S._RECENT_WRITES.clear()  # process-global session caches — isolate each test
    S._RECENT_DELETES.clear()
    S._RECENT_CONFIDENCE.clear()
    yield
    S._LAST_USAGE.set(None)
    S._RECENT_WRITES.clear()
    S._RECENT_DELETES.clear()
    S._RECENT_CONFIDENCE.clear()


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
    # Auth is now per-request (_auth_headers), not baked into the shared client.
    token = S._REQUEST_KEY.set("mem_sk_tenant_a")
    try:
        assert S._auth_headers()["Authorization"] == "Bearer mem_sk_tenant_a"
    finally:
        S._REQUEST_KEY.reset(token)
    assert S._auth_headers()["Authorization"] == f"Bearer {S.KEY}"


def test_client_is_shared_and_pooled():
    # The connection-pooled client is reused across calls (no TLS handshake per
    # call) and carries NO baked-in Authorization (that's per-request).
    assert S._client() is S._client()
    assert "authorization" not in {k.lower() for k in S._client().headers}


# ------------------------------- customer-reported fixes (v0.3.3) -----------
def test_multi_tenant_client_never_uses_global_key(monkeypatch):
    # In multi-tenant mode with a stray global KEY set, a request with no
    # per-request bearer must NOT borrow the server key (auth is per-request).
    monkeypatch.setattr(S, "MULTI_TENANT", True)
    monkeypatch.setattr(S, "KEY", "mem_sk_server_should_not_leak")
    token = S._REQUEST_KEY.set("")  # simulate a request with no bearer
    try:
        assert S._auth_headers()["Authorization"] == "Bearer "  # empty, not the server key
    finally:
        S._REQUEST_KEY.reset(token)
    # single-tenant still falls back to the configured key
    monkeypatch.setattr(S, "MULTI_TENANT", False)
    tok = S._REQUEST_KEY.set("")
    try:
        assert S._auth_headers()["Authorization"] == "Bearer mem_sk_server_should_not_leak"
    finally:
        S._REQUEST_KEY.reset(tok)


def test_entity_timeline_url_encodes_name(monkeypatch):
    captured = {}
    async def spy(path, params=None):
        captured["path"] = path
        return {"ok": True}
    monkeypatch.setattr(S, "_get", spy)
    import asyncio
    asyncio.run(S.hebbrix_entity_timeline("Acme/Corp?x#y", collection_id="c1"))
    assert "Acme/Corp?x#y" not in captured["path"]
    # lowercased (graph canonicalizes) + percent-encoded
    assert "acme%2Fcorp%3Fx%23y" in captured["path"]


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


def test_pow_solver_produces_valid_nonce():
    import hashlib
    bits = 12  # low so the test is instant
    nonce = S._solve_pow("chal-xyz", bits, max_seconds=10)
    assert nonce is not None
    digest = hashlib.sha256(f"chal-xyz:{nonce}".encode()).digest()
    assert int.from_bytes(digest, "big") < (1 << (256 - bits))


# ------------------------- remember routing + read-after-write (v0.3.5) ------
def test_remember_default_is_raw_with_wait_for_index(monkeypatch):
    client = _fake(monkeypatch, FakeResponse(201, {"id": "m1"}))
    out = asyncio.run(S.hebbrix_remember("a clean fact", collection_id="c1"))
    _, url, kw = client.calls[-1]
    assert url.endswith("/memories/raw")
    assert kw["json"]["wait_for_index"] is True   # searchable on return
    assert "infer" not in kw["json"]              # no more ignored infer flag
    assert out["searchable"] is True


def test_remember_extract_routes_to_smart_endpoint(monkeypatch):
    client = _fake(monkeypatch, FakeResponse(200, {"created_count": 2, "updated_count": 0,
        "results": [
            {"id": "m1", "memory_id": "m1", "event": "ADD", "memory": "Sam is a designer."},
            {"id": "m2", "memory_id": "m2", "event": "ADD", "memory": "Sam is in Oslo."},
        ]}))
    out = asyncio.run(S.hebbrix_remember("messy multi-fact text", collection_id="c1",
                                         extract=True))
    _, url, kw = client.calls[-1]
    assert url.endswith("/memories") and not url.endswith("/memories/raw")
    assert kw["json"]["infer"] is True
    assert out["extracted"] == 2
    # content must come from the "memory" key, not "content" (was returning null)
    assert out["memories"][0]["content"] == "Sam is a designer."
    assert out["memories"][0]["event"] == "ADD"
    assert out["id"] == "m1"  # parent id null -> falls back to first result id


def test_remember_wait_for_index_false_passthrough(monkeypatch):
    client = _fake(monkeypatch, FakeResponse(201, {"id": "m1"}))
    asyncio.run(S.hebbrix_remember("fact", collection_id="c1", wait_for_index=False))
    assert client.calls[-1][2]["json"]["wait_for_index"] is False


def test_instructions_tell_model_to_prefer_hebbrix_over_files():
    ins = S.INSTRUCTIONS.lower()
    assert "prefer hebbrix" in ins
    assert "hebbrix_remember" in ins and "hebbrix_search" in ins
    assert "one place" in ins  # cooperative framing, not an absolute override


# ------------------------- profile prompt/resource (v0.3.7) -----------------
def test_profile_text_reads_static_and_dynamic():
    data = {"profile": {
        "static": [{"key": "home_city", "value": "Oslo", "category": "location"}],
        "dynamic": [{"key": "current_task", "value": "launch", "category": "work"}]}}
    txt = S._profile_text(data)
    assert "home_city: Oslo (location)" in txt
    assert "current_task: launch (work)" in txt


def test_profile_text_handles_flat_facts_shape():
    data = {"static": [{"key": "role", "value": "founder"}], "dynamic": []}
    assert "role: founder" in S._profile_text(data)


def test_profile_text_empty_is_none_yet():
    assert S._profile_text({"static": [], "dynamic": []}) == "(none yet)"


def test_context_prompt_injects_profile_facts(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"static": [{"key": "lang", "value": "Rust"}],
                                          "dynamic": []}))
    out = asyncio.run(S.context())
    body = out.split("Known user profile:")[-1]
    assert "lang: Rust" in body and "(none yet)" not in body


def test_usage_capture_survives_malformed_headers(monkeypatch):
    headers = {"X-Hebbrix-Tier": "shadow", "X-Hebbrix-Status": "ok",
               "X-Hebbrix-Writes-Used": "not-a-number", "X-Hebbrix-Writes-Limit": ""}
    _fake(monkeypatch, FakeResponse(201, {"id": "m1"}, headers=headers))
    out = asyncio.run(S.hebbrix_remember("f", collection_id="c1"))  # must not raise
    assert out["hebbrix_usage"]["writes"] == {"used": 0, "limit": 0}


def test_graph_query_requires_entity_and_lowercases(monkeypatch):
    client = _fake(monkeypatch, FakeResponse(200, {"nodes": []}))
    asyncio.run(S.hebbrix_graph_query(entity="Sarah Chen", collection_id="c1"))
    assert client.calls[-1][2]["json"]["entity"] == "sarah chen"  # lowercased
    # 'query' free-text param no longer exists on the tool
    import inspect
    assert "query" not in inspect.signature(S.hebbrix_graph_query).parameters


# ---------------------------------------------- write-behind read-after-write
def test_get_after_write_served_from_cache_on_remote_miss(monkeypatch):
    # A memory written this session must resolve by id even if the remote
    # read 404s (index not caught up yet).
    S._cache_put("w1", "the launch is on Friday", "c1")
    _fake(monkeypatch, FakeResponse(404, text="not found"))
    out = asyncio.run(S.hebbrix_get("w1"))
    assert out["id"] == "w1" and out["content"] == "the launch is on Friday"
    assert out["pending_index"] is True


def test_get_error_without_cache_still_returns_error(monkeypatch):
    _fake(monkeypatch, FakeResponse(500, text="boom"))
    out = asyncio.run(S.hebbrix_get("never-written"))
    assert out["error"].startswith("HTTP 500")


def test_search_overlays_just_written_memory(monkeypatch):
    S._cache_put("w1", "the sky is blue today", "c1")
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "remote1", "content": "unrelated", "score": 0.4}]}))
    out = asyncio.run(S.hebbrix_search("sky", collection_id="c1", limit=5))
    ids = [r["id"] for r in out["results"]]
    assert "w1" in ids
    top = next(r for r in out["results"] if r["id"] == "w1")
    assert top["just_written"] is True


def test_search_overlay_respects_collection_and_query(monkeypatch):
    S._cache_put("w1", "cats are great", "OTHER")   # wrong collection
    S._cache_put("w2", "dogs are loud", "c1")        # right collection, no match
    _fake(monkeypatch, FakeResponse(200, {"results": []}))
    out = asyncio.run(S.hebbrix_search("elephant", collection_id="c1"))
    assert out["results"] == []  # neither matches scope+query


def test_search_overlay_dedupes_already_returned(monkeypatch):
    S._cache_put("remote1", "the sky is blue", "c1")
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "remote1", "content": "the sky is blue", "score": 0.9}]}))
    out = asyncio.run(S.hebbrix_search("sky", collection_id="c1"))
    assert [r["id"] for r in out["results"]].count("remote1") == 1


def test_list_overlays_just_written(monkeypatch):
    S._cache_put("w1", "fresh memory", "c1")
    _fake(monkeypatch, FakeResponse(200, {"items": []}))
    out = asyncio.run(S.hebbrix_list(collection_id="c1"))
    assert any(m["id"] == "w1" and m.get("just_written") for m in out["memories"])


def test_multi_tenant_disables_local_cache(monkeypatch):
    monkeypatch.setattr(S, "_LOCAL_CACHE", False)
    S._RECENT_WRITES.clear()
    S._cache_put("w1", "should not cache", "c1")
    assert len(S._RECENT_WRITES) == 0
    assert S._cached_write("w1") is None


# ------------------------------------------------- auto-inferred decisions
def test_confidence_is_recorded_for_auto_infer(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"confidence": 0.8, "recommended_action": "act"}))
    asyncio.run(S.hebbrix_confidence("should I ship the release?", collection_id="c1"))
    assert S._RECENT_CONFIDENCE[-1]["query"] == "should I ship the release?"
    assert S._RECENT_CONFIDENCE[-1]["recommended_action"] == "act"


def test_log_decision_auto_fills_from_last_confidence(monkeypatch):
    S._RECENT_CONFIDENCE.append({"query": "ship the release?",
                                 "recommended_action": "act", "ts": 0.0})
    _fake(monkeypatch, FakeResponse(201, {"id": "d1"}))
    out = asyncio.run(S.hebbrix_log_decision(outcome="success", collection_id="c1"))
    assert out["logged"] is True
    assert out["description"] == "Acted on: ship the release?"
    assert out["auto_linked_to_confidence"] is True


def test_log_decision_without_description_or_context_errors(monkeypatch):
    _fake(monkeypatch, FakeResponse(201, {"id": "d1"}))
    out = asyncio.run(S.hebbrix_log_decision(outcome="success", collection_id="c1"))
    assert "error" in out


def test_log_decision_explicit_description_not_overwritten(monkeypatch):
    S._RECENT_CONFIDENCE.append({"query": "ship?", "recommended_action": "act", "ts": 0.0})
    client = _fake(monkeypatch, FakeResponse(201, {"id": "d1"}))
    asyncio.run(S.hebbrix_log_decision(description="Chose Postgres over Mongo",
                                       collection_id="c1"))
    assert client.calls[-1][2]["json"]["description"] == "Chose Postgres over Mongo"


# ----------------------------------------------- hosted health-probe bypass
def _run_mw(method, path, headers=None):
    sent = []

    async def inner(scope, receive, send):
        # Record that the inner MCP app was reached (should NOT happen for a
        # health probe or an unauthenticated request).
        sent.append({"type": "INNER_APP_CALLED"})

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(msg):
        sent.append(msg)

    mw = S._HeaderAuthMiddleware(inner)
    scope = {"type": "http", "method": method, "path": path,
             "headers": [(k.encode(), v.encode()) for k, v in (headers or {}).items()]}
    asyncio.run(mw(scope, receive, send))
    return sent


def test_health_probe_returns_200_without_auth():
    sent = _run_mw("GET", "/healthz")
    start = next(m for m in sent if m.get("type") == "http.response.start")
    assert start["status"] == 200
    assert not any(m.get("type") == "INNER_APP_CALLED" for m in sent)


def test_missing_bearer_still_401():
    sent = _run_mw("POST", "/mcp")
    start = next(m for m in sent if m.get("type") == "http.response.start")
    assert start["status"] == 401
    assert not any(m.get("type") == "INNER_APP_CALLED" for m in sent)


def test_valid_bearer_reaches_inner_app():
    sent = _run_mw("POST", "/mcp", headers={"authorization": "Bearer mem_sk_x"})
    assert any(m.get("type") == "INNER_APP_CALLED" for m in sent)


# ============================================================================
# Mutation-consistency regressions (v0.3.10) — the customer report:
# updates and deletes must not leak stale/deleted content through the cache.
# ============================================================================

# --- #1 update: search returns corrected content, not stale remote ----------
def test_update_refreshes_cache_search_returns_corrected(monkeypatch):
    # hebbrix_update m1 -> Borealis (PATCH response carries collection_id)
    _fake(monkeypatch, FakeResponse(200, {"id": "m1", "collection_id": "c1"}))
    up = asyncio.run(S.hebbrix_update("m1", content="the codename is Borealis"))
    assert up["updated"] is True
    # remote search still returns the stale Aurora row for the SAME id
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "m1", "content": "the codename is Aurora", "score": 0.9}]}))
    out = asyncio.run(S.hebbrix_search("codename", collection_id="c1"))
    row = next(r for r in out["results"] if r["id"] == "m1")
    assert row["content"] == "the codename is Borealis"   # cached correction wins
    assert row.get("corrected") is True
    assert "Aurora" not in row["content"]


def test_update_sends_wait_for_index(monkeypatch):
    client = _fake(monkeypatch, FakeResponse(200, {"id": "m1"}))
    asyncio.run(S.hebbrix_update("m1", content="x", wait_for_index=True))
    assert client.calls[-1][2]["json"]["wait_for_index"] is True


# --- #2 update: remote omits the id -> overlay supplies corrected content ----
def test_update_then_search_overlays_when_remote_omits(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"id": "m1", "collection_id": "c1"}))
    asyncio.run(S.hebbrix_update("m1", content="borealis is the codename"))
    _fake(monkeypatch, FakeResponse(200, {"results": []}))  # remote not indexed yet
    out = asyncio.run(S.hebbrix_search("borealis", collection_id="c1"))
    m1 = next(r for r in out["results"] if r["id"] == "m1")
    assert m1["content"] == "borealis is the codename" and m1.get("just_written") is True


# --- #3 delete: search omits it -> stays absent (no overlay resurrection) -----
def test_delete_removes_from_overlay(monkeypatch):
    S._cache_put("m1", "ephemeral fact", "c1")
    _fake(monkeypatch, FakeResponse(204))
    d = asyncio.run(S.hebbrix_forget("m1"))
    assert d["ok"] is True and S._is_tombstoned("m1")
    _fake(monkeypatch, FakeResponse(200, {"results": []}))
    out = asyncio.run(S.hebbrix_search("ephemeral", collection_id="c1"))
    assert all(r["id"] != "m1" for r in out["results"])


# --- #4 delete: stale remote search STILL returns it -> tombstone filters -----
def test_delete_tombstone_filters_stale_remote_search(monkeypatch):
    _fake(monkeypatch, FakeResponse(204))
    asyncio.run(S.hebbrix_forget("m1"))
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "m1", "content": "still here", "score": 0.8}]}))
    out = asyncio.run(S.hebbrix_search("here", collection_id="c1"))
    assert out["count"] == 0 and all(r["id"] != "m1" for r in out["results"])


# --- #5 delete: remote get 404 must NOT fall back to cached content ----------
def test_get_after_delete_does_not_resurrect(monkeypatch):
    S._cache_put("m1", "old cached content", "c1")   # created earlier this session
    _fake(monkeypatch, FakeResponse(204))
    asyncio.run(S.hebbrix_forget("m1"))
    # get on a tombstoned id: structured deleted response, no cache fallback
    _fake(monkeypatch, FakeResponse(404, text="not found"))
    out = asyncio.run(S.hebbrix_get("m1"))
    assert out.get("deleted") is True and "error" in out
    assert "old cached content" not in str(out)


def test_cached_write_never_returns_tombstoned():
    S._cache_put("m1", "content", "c1")
    assert S._cached_write("m1") is not None
    S._cache_delete("m1")
    assert S._cached_write("m1") is None


def test_forget_on_remote_404_also_tombstones(monkeypatch):
    S._cache_put("m1", "x", "c1")
    _fake(monkeypatch, FakeResponse(404, text="already gone"))
    d = asyncio.run(S.hebbrix_forget("m1"))
    assert d["ok"] is False and S._is_tombstoned("m1")  # idempotent delete


def test_forget_on_5xx_does_not_tombstone(monkeypatch):
    S._cache_put("m1", "x", "c1")
    _fake(monkeypatch, FakeResponse(503, text="unavailable"))
    asyncio.run(S.hebbrix_forget("m1"))
    assert S._is_tombstoned("m1") is False  # transient error must not delete


# --- #6 deleted memory absent from list --------------------------------------
def test_deleted_memory_absent_from_list(monkeypatch):
    _fake(monkeypatch, FakeResponse(204))
    asyncio.run(S.hebbrix_forget("m1"))
    _fake(monkeypatch, FakeResponse(200, {"items": [
        {"id": "m1", "content": "zombie"}, {"id": "m2", "content": "alive"}]}))
    out = asyncio.run(S.hebbrix_list(collection_id="c1"))
    ids = [m["id"] for m in out["memories"]]
    assert "m1" not in ids and "m2" in ids


def test_list_replaces_stale_row_with_cached_update(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"id": "m1", "collection_id": "c1"}))
    asyncio.run(S.hebbrix_update("m1", content="corrected value"))
    _fake(monkeypatch, FakeResponse(200, {"items": [{"id": "m1", "content": "stale value"}]}))
    out = asyncio.run(S.hebbrix_list(collection_id="c1"))
    m1 = next(m for m in out["memories"] if m["id"] == "m1")
    assert m1["content"] == "corrected value"


# --- #7 collection scope + tombstone revival ---------------------------------
def test_cached_update_overlay_is_collection_scoped(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"id": "m1", "collection_id": "c1"}))
    asyncio.run(S.hebbrix_update("m1", content="borealis codename"))
    _fake(monkeypatch, FakeResponse(200, {"results": []}))  # different collection
    out = asyncio.run(S.hebbrix_search("borealis", collection_id="c2"))
    assert all(r["id"] != "m1" for r in out["results"])  # not overlaid into c2


def test_update_after_delete_revives_id(monkeypatch):
    _fake(monkeypatch, FakeResponse(204))
    asyncio.run(S.hebbrix_forget("m1"))
    assert S._is_tombstoned("m1")
    _fake(monkeypatch, FakeResponse(200, {"id": "m1", "collection_id": "c1"}))
    asyncio.run(S.hebbrix_update("m1", content="reborn"))
    assert not S._is_tombstoned("m1")
    assert S._cached_write("m1")["content"] == "reborn"


# --- #8 multi-tenant disables ALL process-global overlays --------------------
def test_multi_tenant_disables_tombstones_and_overlay(monkeypatch):
    monkeypatch.setattr(S, "_LOCAL_CACHE", False)
    S._RECENT_WRITES.clear()
    S._RECENT_DELETES.clear()
    S._cache_put("m1", "x", "c1")
    S._cache_delete("m2")
    assert len(S._RECENT_WRITES) == 0 and len(S._RECENT_DELETES) == 0
    assert S._is_tombstoned("m2") is False
    assert S._overlay_recent_writes("c1", set(), query="x") == []


# --- #9 handshake advertises the Hebbrix package version, not the SDK's -------
def test_handshake_reports_hebbrix_version_not_sdk():
    from importlib.metadata import version
    sdk = version("mcp")
    assert S.mcp._mcp_server.version == S._SERVER_VERSION
    assert S.mcp._mcp_server.version != sdk


# --------------------------- graph enrichment state (v0.3.11) ---------------
def test_remember_flags_async_graph_enrichment(monkeypatch):
    _fake(monkeypatch, FakeResponse(201, {"id": "m1"}))
    out = asyncio.run(S.hebbrix_remember("Atlas is our deploy tool", collection_id="c1"))
    # wait_for_index covers memory search; the graph is enriched separately.
    assert out["graph_enrichment"] == "processing"
    assert out["searchable"] is True


def test_remember_extract_flags_async_graph_enrichment(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"id": "m1", "memory": "Atlas is a deploy tool", "event": "ADD"}]}))
    out = asyncio.run(S.hebbrix_remember("Atlas deploy tool", collection_id="c1", extract=True))
    assert out["graph_enrichment"] == "processing"


# ================= write-behind overlay precision (v0.3.12) =================
# N1: an unrelated cached write must not be injected via a shared stopword, and
# never at a fake score 1.0.
def test_overlay_does_not_inject_on_stopword_only_overlap(monkeypatch):
    S._cache_put("w1", "The user's favorite color is teal.", "c1")
    _fake(monkeypatch, FakeResponse(200, {"results": []}))
    out = asyncio.run(S.hebbrix_search(
        "what is the deployment schedule for the api", collection_id="c1"))
    assert all(r["id"] != "w1" for r in out["results"])   # "the" is not a match


def test_overlay_injects_on_content_word_below_score_one(monkeypatch):
    S._cache_put("w1", "the deployment schedule is Friday at noon", "c1")
    _fake(monkeypatch, FakeResponse(200, {"results": []}))
    out = asyncio.run(S.hebbrix_search("deployment schedule", collection_id="c1"))
    w1 = next(r for r in out["results"] if r["id"] == "w1")
    assert w1["just_written"] is True
    assert w1["score"] < 1.0        # never a fake perfect match
    assert w1["score"] >= 0.5


def test_overlay_never_outranks_a_stronger_remote_hit(monkeypatch):
    # A partial-overlap local write must not beat a strong genuine remote match.
    S._cache_put("w1", "deployment notes for later", "c1")
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "r1", "content": "the deployment schedule is Friday", "score": 0.95}]}))
    out = asyncio.run(S.hebbrix_search("deployment schedule", collection_id="c1"))
    assert out["results"][0]["id"] == "r1"   # strong remote hit stays #1


# N2: corrected must be set ONLY when the cached content actually differs.
def test_freshly_created_memory_is_not_flagged_corrected(monkeypatch):
    S._cache_put("m1", "Widget pricing is confidential.", "c1")
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "m1", "content": "Widget pricing is confidential.", "score": 0.99}]}))
    out = asyncio.run(S.hebbrix_search("widget pricing", collection_id="c1"))
    m1 = next(r for r in out["results"] if r["id"] == "m1")
    assert "corrected" not in m1        # never updated -> not corrected


def test_actually_corrected_memory_is_flagged(monkeypatch):
    S._cache_put("m1", "Widget pricing is public.", "c1")   # in-session correction
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "m1", "content": "Widget pricing is confidential.", "score": 0.99}]}))
    out = asyncio.run(S.hebbrix_search("widget pricing", collection_id="c1"))
    m1 = next(r for r in out["results"] if r["id"] == "m1")
    assert m1.get("corrected") is True and m1["content"] == "Widget pricing is public."


# ============ profile durable/recent separation + zero-relevance (v0.3.13) ===
def test_profile_text_separates_durable_from_recent():
    data = {"static": [{"key": "home_city", "value": "Berlin", "category": "location"}],
            "dynamic": [{"key": "project_deadline", "value": "April 15", "category": "current_project"}]}
    out = S._profile_text(data)
    durable, _, recent = out.partition("Recent / temporary")
    assert "home_city: Berlin" in durable          # durable identity up top
    assert "project_deadline" not in durable        # ephemeral NOT in durable
    assert "project_deadline: April 15" in recent    # ephemeral under recent


def test_profile_text_only_static_has_no_recent_header():
    data = {"static": [{"key": "diet", "value": "vegan"}], "dynamic": []}
    out = S._profile_text(data)
    assert "diet: vegan" in out and "Recent / temporary" not in out


def test_search_drops_zero_score_padding(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "hit", "content": "the real match", "score": 0.8},
        {"memory_id": "pad", "content": "unrelated padding", "score": 0.0}]}))
    out = asyncio.run(S.hebbrix_search("real match", collection_id="c1"))
    ids = [r["id"] for r in out["results"]]
    assert "hit" in ids and "pad" not in ids


def test_search_keeps_weak_positive_match(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {"results": [
        {"memory_id": "weak", "content": "barely relevant", "score": 0.002}]}))
    out = asyncio.run(S.hebbrix_search("relevant", collection_id="c1"))
    assert any(r["id"] == "weak" for r in out["results"])   # positive score kept


# =========== error paths carry the usage/claim block (v0.3.14) ==============
def test_error_response_still_carries_usage_block(monkeypatch):
    # A quota-limit 402 carries X-Hebbrix-* headers; the tool's error return must
    # still surface the usage block + claim nudge (the moment it matters most).
    headers = {
        "X-Hebbrix-Tier": "shadow", "X-Hebbrix-Status": "limited",
        "X-Hebbrix-Writes-Used": "300", "X-Hebbrix-Writes-Limit": "300",
        "X-Hebbrix-Claim": "hebbrix-mcp claim --email <you>",
    }
    _fake(monkeypatch, FakeResponse(402, text="WRITE_LIMIT_REACHED", headers=headers))
    out = asyncio.run(S.hebbrix_search("q", collection_id="c1"))
    assert out["error"].startswith("HTTP 402")
    assert out["hebbrix_usage"]["status"] == "limited"
    assert "claim" in out["hebbrix_usage"]["action_for_human"].lower()


# ============ confidence surfaces constraint conflict (v0.3.15) =============
def test_confidence_surfaces_constraint_conflict(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {
        "confidence": 0.68, "recommended_action": "do_not_act",
        "answer_confidence": 0.68, "reasoning": "CONFLICT ...",
        "constraint_conflict": {"rule": "PRs must be < 400 lines",
                                "query_value": 600, "threshold": 400,
                                "direction": "upper", "unit": "line"}}))
    out = asyncio.run(S.hebbrix_confidence("open a 600-line PR?", collection_id="c1"))
    assert out["recommended_action"] == "do_not_act"
    assert out["constraint_conflict"]["threshold"] == 400


def test_confidence_omits_constraint_conflict_when_none(monkeypatch):
    _fake(monkeypatch, FakeResponse(200, {
        "confidence": 0.8, "recommended_action": "act_autonomously",
        "reasoning": "Strong direct match"}))
    out = asyncio.run(S.hebbrix_confidence("what is the wifi password?", collection_id="c1"))
    assert "constraint_conflict" not in out
