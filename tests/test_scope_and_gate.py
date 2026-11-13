"""Scope pinning, the answer gate's SDK parity, and the single isError rule."""

import asyncio
import os

import pytest

os.environ.setdefault("HEBBRIX_API_KEY", "mem_sk_test_dummy")
from hebbrix_mcp import server as S  # noqa: E402

from test_server import _run_mw  # noqa: E402


@pytest.fixture(autouse=True)
def isolated_scope(monkeypatch):
    monkeypatch.setattr(S, "_ENV_SCOPE", {})
    S._REQUEST_SCOPE.set(None)
    yield
    S._REQUEST_SCOPE.set(None)


# ------------------------------------------------------------------ pinning
def test_hosted_headers_pin_scope_for_one_request(monkeypatch):
    seen = []

    async def resolve(_token):
        return "c-default", None

    async def inner(scope, receive, send):
        seen.append(S._pinned_scope())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    monkeypatch.setattr(S, "_default_collection_for_token", resolve)
    _run_mw("POST", "/mcp", headers={
        "authorization": "Bearer mem_sk_x",
        "x-hebbrix-user-id": "end-user-a",
        "x-hebbrix-run-id": "run-7",
    }, inner=inner)
    assert seen == [{"user_id": "end-user-a", "run_id": "run-7"}]
    assert S._REQUEST_SCOPE.get() is None  # reset after the request


def test_hosted_invalid_scope_header_is_rejected(monkeypatch):
    async def resolve(_token):
        return "c-default", None

    monkeypatch.setattr(S, "_default_collection_for_token", resolve)
    sent = _run_mw("POST", "/mcp", headers={
        "authorization": "Bearer mem_sk_x", "x-hebbrix-user-id": "   ",
    })
    start = next(m for m in sent if m.get("type") == "http.response.start")
    assert start["status"] == 400
    assert not any(m.get("type") == "INNER_APP_CALLED" for m in sent)


def test_hosted_mode_never_uses_process_environment_pins(monkeypatch):
    monkeypatch.setattr(S, "_ENV_SCOPE", {"user_id": "stdio-user"})
    monkeypatch.setattr(S, "MULTI_TENANT", True)
    assert S._pinned_scope() == {}
    monkeypatch.setattr(S, "MULTI_TENANT", False)
    assert S._pinned_scope() == {"user_id": "stdio-user"}


def test_pinned_user_flows_into_learning_tools_but_agent_pin_does_not(monkeypatch):
    calls = []

    async def get(path, params=None):
        calls.append(params)
        return {"policy_key": "support.reply", "actions": []}

    monkeypatch.setattr(S, "_ENV_SCOPE", {"user_id": "end-user-a", "agent_id": "bot"})
    monkeypatch.setattr(S, "_get", get)
    out = asyncio.run(S.hebbrix_learning_insights("support.reply", collection_id="c1"))
    assert "error" not in out
    assert calls[-1]["user_id"] == "end-user-a"
    out = asyncio.run(S.hebbrix_learning_insights("support.reply", user_id="end-user-b"))
    assert out["error_code"] == "scope_pinned"


def test_confidence_refuses_an_agent_scope_it_cannot_apply(monkeypatch):
    monkeypatch.setattr(S, "_ENV_SCOPE", {"agent_id": "bot"})
    out = asyncio.run(S.hebbrix_confidence("deploy now?", collection_id="c1"))
    assert out["error_code"] == "unsupported_scope"


def test_export_omits_user_attributed_data_for_agent_scope(monkeypatch):
    paths = []

    async def get(path, params=None):
        paths.append((path, params))
        return {"items": [{"id": "m1", "content": "fact"}]}

    monkeypatch.setattr(S, "_get", get)
    out = asyncio.run(S.hebbrix_export(collection_id="c1", agent_id="bot"))
    assert [p for p, _ in paths] == ["/memories"]
    assert paths[0][1]["agent_id"] == "bot"
    assert out["entities"] == [] and out["profile"] is None and out["scope_note"]


# ------------------------------------------------- answer gate = SDK parity
def _response(status, rows=None, **extra):
    return {
        "answer_status": status,
        "results": rows if rows is not None else [
            {"memory_id": "m1", "revision_status": "current", "low_confidence": False}
        ],
        "indexing": {"status": "ready", "answer_risk": "none"},
        **extra,
    }


@pytest.mark.parametrize("response,expected", [
    (_response("answerable"), (True, "answerable", "answer")),
    (_response("conflicting"), (False, "conflicting", "ask_user")),
    (_response("superseded"), (False, "superseded", "say_no_longer_current")),
    (_response("indexing"), (False, "indexing", "retry")),
    (_response("no_relevant_memory", rows=[]), (False, "no_relevant_memory", "say_unknown")),
    (_response("unverified"), (False, "unverified", "abstain")),
    (_response("unverified", rows=[{"memory_id": "r", "evidence_role": "applicable_rule"}]),
     (False, "applicable_rule", "use_as_context")),
    (_response("answerable", confidence_reason="authorization_not_verifiable"),
     (False, "authorization_not_verifiable", "verify_authorization")),
    (_response("answerable", grounding={"answerability": "context_only"}),
     (False, "context_only", "use_as_context")),
    (_response("answerable", abstain_recommended=True), (False, "abstain_recommended", "abstain")),
    # A search row must say low_confidence=false to be evidence.
    (_response("answerable", rows=[{"memory_id": "m1", "revision_status": "current"}]),
     (False, "no_usable_memories", "abstain")),
    (_response("answerable", rows=[{"memory_id": "m1", "revision_status": "superseded",
                                    "low_confidence": False}]),
     (False, "no_usable_memories", "abstain")),
    ({"results": []}, (False, "unsupported_response", "abstain")),
    (_response("maybe"), (False, "malformed_response", "abstain")),
])
def test_answer_decision_matches_sdk_should_answer(response, expected):
    assert S._sdk_answer_decision(response, rows_key="results", require_ready=False) == expected


@pytest.mark.parametrize("indexing,ready", [
    ({"status": "ready", "answer_risk": "none"}, True),
    ({"status": "ready"}, True),
    ({"status": "ready", "answer_risk": "may_change"}, False),
    ({"status": "incomplete", "answer_risk": "may_change"}, False),
    (None, False),
])
def test_require_ready_matches_sdk(indexing, ready):
    response = _response("answerable", indexing=indexing)
    gate = S._answer_gate(response, rows_key="results", delivered=True,
                          category=None, reason=None)
    assert gate["ready"] is ready
    assert gate["safe_to_answer"] is True
    assert gate["require_ready"]["safe_to_answer"] is ready
    if not ready:
        assert gate["require_ready"] == {
            "safe_to_answer": False, "reason": "index_not_ready", "action": "retry"}


def test_reason_sources_need_only_not_low_confidence():
    response = {"answer_status": "answerable",
                "sources": [{"memory_id": "m1", "revision_status": "current"}]}
    assert S._sdk_answer_decision(response, rows_key="sources", require_ready=False)[0]


def test_gate_is_never_safe_when_the_adapter_withheld():
    gate = S._answer_gate(_response("answerable"), rows_key="results", delivered=False,
                          category="malformed_evidence_receipt", reason="grounding_receipt_missing")
    assert gate["safe_to_answer"] is False
    assert gate["reason"] == "grounding_receipt_missing"
    assert gate["require_ready"]["safe_to_answer"] is False


# ------------------------------------------------------ the isError rule
@pytest.mark.parametrize("result,failure", [
    ({"error": "HTTP 500"}, "error"),
    ({"degraded": True, "results": []}, "service_failure"),
    ({"failure_category": "verification_unavailable"}, "verification_unavailable"),
    ({"failure_category": "quota_exhausted"}, "quota_exhausted"),
    ({"failure_category": "malformed_evidence_receipt"}, "malformed_evidence_receipt"),
    ({"failure_category": "unknown_fact", "no_match": True}, None),
    ({"failure_category": "index_pending", "degraded": False}, None),
    ({"synthesis_status": "retrieval_only", "reasoning_failure_category": "service_failure"}, None),
    ({"results": []}, None),
])
def test_one_operational_failure_rule(result, failure):
    assert S._operational_failure(result) == failure


def test_protocol_promotes_degraded_result_to_tool_error(monkeypatch):
    from mcp.server.fastmcp.exceptions import ToolError

    async def degraded_search(**_kwargs):
        return {"query": "q", "results": [], "degraded": True}

    tool = S.mcp._tool_manager.get_tool("hebbrix_search")  # noqa: SLF001
    monkeypatch.setattr(tool, "fn", degraded_search)
    with pytest.raises(ToolError) as exc:
        asyncio.run(S.mcp.call_tool("hebbrix_search", {"query": "q"}))
    assert '"ok":false' in str(exc.value) and "Operational failure" in str(exc.value)
