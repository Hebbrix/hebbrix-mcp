"""Protocol regressions through the REAL stdio transport and a mock REST backend.

Every case spawns nothing new: one hebbrix-mcp child (plus one with a pinned
scope) serves the module. Each test programs the loopback backend, calls a tool
over JSON-RPC and asserts what an MCP client receives (``isError`` and the
payload) and what the adapter sent upstream.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from conftest import MockBackend, StdioMCP, server_env

SEARCH = ("POST", "/v1/search")
REASON = ("POST", "/v1/search/reason")
READY = {
    "status": "ready",
    "pending_memories": 0,
    "keyword_only_memories": 0,
    "failed_memories": 0,
    "capped": False,
    "answer_risk": "none",
}
PENDING_MAY_CHANGE = READY | {"status": "incomplete", "pending_memories": 2,
                              "answer_risk": "may_change"}
SUPPORTED = {"applied": True, "status": "supported", "contract_version": "claim-grounding-v58"}
NO_GROUNDED_MATCH = {"applied": True, "status": "no_grounded_match", "reason": "claim_not_grounded"}
ROW = {
    "memory_id": "m1",
    "id": "m1",
    "content": "Project Atlas uses PostgreSQL 16.",
    "score": 0.93,
    "low_confidence": False,
    "revision_status": "current",
    "is_current": True,
    "evidence_role": "answer",
}


def search_envelope(**changes: Any) -> dict[str, Any]:
    """A current, well-formed /v1/search response (search-safety-v1)."""
    body = {
        "query": "q",
        "results": [dict(ROW)],
        "total": 1,
        "search_type": "hybrid",
        "processing_time_ms": 12.0,
        "degraded": False,
        "degraded_sources": [],
        "indexing": dict(READY),
        "scores_calibrated": True,
        "no_match": False,
        "answer_status": "answerable",
        "abstain_recommended": False,
        "confidence_reason": "calibrated_match",
        "query_confidence": 0.93,
        "grounding": dict(SUPPORTED),
        "safety_contract_version": "search-safety-v1",
        "evidence_ids": ["m1"],
        "evidence_claims": [{"memory_id": "m1", "status": "supported"}],
    }
    body.update(copy.deepcopy(changes))
    return body


def reason_envelope(**changes: Any) -> dict[str, Any]:
    """A current, well-formed /v1/search/reason response."""
    source = {k: v for k, v in ROW.items() if k != "id"} | {"score": 1.4}
    body = {
        "answer": "Project Atlas uses PostgreSQL 16. [1]",
        "sources": [source],
        "metadata": {},
        "answer_status": "answerable",
        "indexing": dict(READY),
        "no_match": False,
        "abstain_recommended": False,
        "query_confidence": 1.0,
        "grounding": dict(SUPPORTED),
        "evidence_ids": ["m1"],
        "evidence_claims": [{"memory_id": "m1", "status": "supported"}],
        "safety_contract_version": "search-safety-v1",
        "degraded": False,
        "decision_abstained": False,
        "abstain_reason": None,
        "reasoning_status": "completed",
    }
    body.update(copy.deepcopy(changes))
    return body


NO_MATCH = dict(
    results=[], total=0, evidence_ids=[], evidence_claims=[], no_match=True,
    abstain_recommended=True, query_confidence=0.0, grounding=NO_GROUNDED_MATCH,
    answer_status="no_relevant_memory", confidence_reason="no_relevant_memory",
)
REASON_NO_MATCH = dict(
    answer=None, sources=[], evidence_ids=[], evidence_claims=[], no_match=True,
    abstain_recommended=True, query_confidence=0.0, grounding=NO_GROUNDED_MATCH,
    answer_status="no_relevant_memory", decision_abstained=True,
    abstain_reason="no_retrievable_evidence",
)


@pytest.fixture(scope="module")
def backend():
    mock = MockBackend()
    yield mock
    mock.close()


@pytest.fixture(scope="module")
def mcp_server(backend, tmp_path_factory):
    server = StdioMCP(server_env(backend.base, str(tmp_path_factory.mktemp("mcp"))))
    yield server
    server.close()


@pytest.fixture(scope="module")
def pinned_server(backend, tmp_path_factory):
    server = StdioMCP(server_env(
        backend.base, str(tmp_path_factory.mktemp("pinned")),
        HEBBRIX_USER_ID="end-user-a", HEBBRIX_AGENT_ID="support-agent",
    ))
    yield server
    server.close()


def _no_evidence(payload: dict[str, Any]) -> None:
    assert payload.get("results", []) == []
    assert payload.get("citations", []) == []
    assert payload["evidence_ids"] == []
    assert payload["evidence_claims"] == []
    assert payload["no_match"] is True and payload["abstain_recommended"] is True
    assert payload["evidence_withheld"] is True
    assert payload["answer_gate"]["safe_to_answer"] is False
    assert payload["answer_gate"]["require_ready"]["safe_to_answer"] is False


# ----------------------------------------------------------------------------
# Defect 13 + 12: one fail-closed envelope verdict, one isError rule.
# (name, envelope changes, isError, failure_category, safety_reason)
# ----------------------------------------------------------------------------
CONTRADICTORY_SEARCH = [
    ("ungrounded_receipt_with_flags_and_evidence_ids",
     dict(results=[], grounding={"status": "no_grounded_match", "grounded": False},
          no_match=True, abstain_recommended=True, answer_status="no_relevant_memory"),
     "no_match_contains_evidence"),
    ("ungrounded_receipt_with_clear_flags_and_rows",
     dict(grounding={"status": "no_grounded_match", "grounded": False}),
     "grounding_contradicts_evidence"),
    ("ungrounded_receipt_with_abstention_and_rows",
     dict(grounding={"status": "no_grounded_match", "grounded": False},
          abstain_recommended=True, answer_status="unverified"),
     "grounding_contradicts_evidence"),
    ("supported_status_marked_not_grounded",
     dict(grounding=SUPPORTED | {"grounded": False}), "grounding_contradicts_evidence"),
    ("empty_grounding_object", dict(grounding={}), "grounding_receipt_missing"),
    ("grounding_without_status", dict(grounding={"applied": True}), "grounding_status_missing"),
    ("unknown_grounding_status", dict(grounding={"status": "probably"}),
     "unsupported_grounding_status"),
    ("null_safety_contract_version", dict(safety_contract_version=None),
     "unsupported_safety_contract_version"),
    ("unsupported_safety_contract_version", dict(safety_contract_version="search-safety-v0"),
     "unsupported_safety_contract_version"),
    ("no_match_with_rows", dict(no_match=True), "no_match_contains_evidence"),
    ("rows_not_bound_to_evidence_ids", dict(evidence_ids=["other"]),
     "evidence_ids_not_bound_to_rows"),
    ("duplicate_evidence_ids", dict(evidence_ids=["m1", "m1"]), "duplicate_evidence_ids"),
    ("answerable_status_with_abstention", dict(abstain_recommended=True),
     "answerable_status_contradicts_abstention"),
    ("unknown_answer_status", dict(answer_status="maybe"), "unsupported_answer_status"),
    ("string_abstention_flag", dict(no_match="false"), "invalid_abstention_fields"),
    ("confidence_out_of_range", dict(query_confidence=1.7), "invalid_query_confidence"),
    ("rows_without_identity", dict(results=[ROW | {"memory_id": "", "id": ""}]),
     "invalid_evidence_row_identity"),
    ("not_abstaining_without_rows", dict(results=[], evidence_ids=[], evidence_claims=[]),
     "no_evidence_rows"),
]


@pytest.mark.parametrize("name,changes,reason", CONTRADICTORY_SEARCH,
                         ids=[case[0] for case in CONTRADICTORY_SEARCH])
def test_search_contradictory_envelope_withholds_evidence_and_is_error(
    backend, mcp_server, name, changes, reason
):
    backend.reset({SEARCH: (200, search_envelope(**changes))})
    is_error, payload = mcp_server.call("hebbrix_search", query="Which database does Atlas use?")
    assert is_error is True, name
    _no_evidence(payload)
    assert payload["failure_category"] == "malformed_evidence_receipt"
    assert payload["safety_reason"] == reason


def test_search_missing_safety_version_is_malformed(backend, mcp_server):
    envelope = search_envelope()
    envelope.pop("safety_contract_version")
    backend.reset({SEARCH: (200, envelope)})
    is_error, payload = mcp_server.call("hebbrix_search", query="Which database does Atlas use?")
    assert is_error is True
    _no_evidence(payload)
    assert payload["safety_reason"] == "missing_safety_fields:safety_contract_version"


@pytest.mark.parametrize("changes,category", [
    # The customer report: degraded + service failure + abstention was isError false.
    (dict(NO_MATCH, degraded=True, degraded_sources=["vector_search"],
          grounding={"status": "no_grounded_match", "reason": "evidence_pipeline_degraded"}),
     "service_failure"),
    (dict(degraded=True), "service_failure"),  # degraded without named sources
    (dict(NO_MATCH, grounding={"status": "verification_unavailable",
                                "reason": "claim_verifier_unavailable"}),
     "verification_unavailable"),
])
def test_search_operational_failures_are_mcp_errors(backend, mcp_server, changes, category):
    backend.reset({SEARCH: (200, search_envelope(**changes))})
    is_error, payload = mcp_server.call("hebbrix_search", query="Which database does Atlas use?")
    assert is_error is True
    _no_evidence(payload)
    assert payload["failure_category"] == category
    assert payload["ok"] is False and payload["error"]


def test_search_upstream_http_failure_is_mcp_error(backend, mcp_server):
    backend.reset({SEARCH: (503, {"detail": "search temporarily unavailable"})})
    is_error, payload = mcp_server.call("hebbrix_search", query="anything")
    assert is_error is True
    assert payload["failure_category"] == "service_failure"
    assert "HTTP 503" in payload["error"]


def test_ordinary_no_match_is_not_an_error(backend, mcp_server):
    backend.reset({SEARCH: (200, search_envelope(**NO_MATCH))})
    is_error, payload = mcp_server.call("hebbrix_search", query="What is my blood type?")
    assert is_error is False
    _no_evidence(payload)
    assert payload["failure_category"] == "unknown_fact"
    assert payload["answer_status"] == "no_relevant_memory"
    assert payload["answer_gate"]["action"] == "say_unknown"
    assert payload["degraded"] is False


def test_abstention_with_rows_withholds_them_without_error(backend, mcp_server):
    backend.reset({SEARCH: (200, search_envelope(
        abstain_recommended=True, answer_status="unverified",
        confidence_reason="authorization_not_verifiable",
    ))})
    is_error, payload = mcp_server.call("hebbrix_search", query="May I deploy on Friday?")
    assert is_error is False
    _no_evidence(payload)
    assert payload["safety_reason"] == "abstain_recommended"
    assert payload["answer_gate"]["action"] == "verify_authorization"


def test_index_pending_is_readiness_not_error(backend, mcp_server):
    backend.reset({SEARCH: (200, search_envelope(
        **NO_MATCH | dict(answer_status="indexing", confidence_reason="index_pending"),
        degraded=True, degraded_sources=["index_pending"],
        indexing=PENDING_MAY_CHANGE | {"answer_risk": "incomplete_set"},
    ))})
    is_error, payload = mcp_server.call("hebbrix_search", query="How many vendors do we use?")
    assert is_error is False
    _no_evidence(payload)
    assert payload["failure_category"] == "index_pending"
    assert payload["degraded"] is False and payload["degraded_sources"] == ["index_pending"]
    assert payload["answer_gate"]["ready"] is False
    assert payload["answer_gate"]["action"] == "retry"
    assert payload["indexing"]["answer_risk"] == "incomplete_set"


# ----------------------------------------------------------------------------
# Defect 9: readiness for strict gating (SDK should_answer equivalence).
# ----------------------------------------------------------------------------
def test_ready_supported_search_is_safe_in_strict_mode(backend, mcp_server):
    backend.reset({SEARCH: (200, search_envelope())})
    is_error, payload = mcp_server.call("hebbrix_search", query="Which database does Atlas use?")
    assert is_error is False
    assert [row["id"] for row in payload["results"]] == ["m1"]
    assert payload["evidence_ids"] == ["m1"]
    assert payload["evidence_withheld"] is False and payload["failure_category"] is None
    assert payload["answer_status"] == "answerable"
    assert payload["indexing"] == READY
    gate = payload["answer_gate"]
    assert gate == {
        "ready": True, "safe_to_answer": True, "reason": "answerable", "action": "answer",
        "require_ready": {"safe_to_answer": True, "reason": "answerable", "action": "answer"},
    }
    assert payload["results"][0]["revision_status"] == "current"


def test_answer_that_may_change_is_returned_but_held_in_strict_mode(backend, mcp_server):
    backend.reset({SEARCH: (200, search_envelope(
        degraded=True, degraded_sources=["index_pending"], indexing=PENDING_MAY_CHANGE,
    ))})
    is_error, payload = mcp_server.call("hebbrix_search", query="Which database does Atlas use?")
    assert is_error is False  # coverage-only degradation keeps evidence (API contract)
    assert [row["id"] for row in payload["results"]] == ["m1"]
    gate = payload["answer_gate"]
    assert gate["safe_to_answer"] is True and gate["ready"] is False
    assert gate["require_ready"] == {
        "safe_to_answer": False, "reason": "index_not_ready", "action": "retry"
    }
    assert payload["indexing"]["pending_memories"] == 2


def test_ask_exposes_reason_readiness_fields(backend, mcp_server):
    backend.reset({REASON: (200, reason_envelope(indexing=PENDING_MAY_CHANGE))})
    is_error, payload = mcp_server.call("hebbrix_ask", question="Which database does Atlas use?")
    assert is_error is False
    assert payload["synthesis_status"] == "synthesized"
    assert payload["answer_status"] == "answerable"
    assert payload["decision_abstained"] is False
    assert payload["reasoning_status"] == "completed"
    assert payload["answer_gate"]["safe_to_answer"] is True
    assert payload["answer_gate"]["require_ready"]["action"] == "retry"


# ----------------------------------------------------------------------------
# Defect 13 on ask: answers are withheld by the same verdict.
# ----------------------------------------------------------------------------
CONTRADICTORY_REASON = [
    ("abstained_decision_with_answer",
     dict(decision_abstained=True, abstain_recommended=False),
     "abstained_decision_contains_answer"),
    ("empty_grounding_object", dict(grounding={}), "grounding_receipt_missing"),
    ("null_safety_contract_version", dict(safety_contract_version=None),
     "unsupported_safety_contract_version"),
    ("ungrounded_receipt_with_flags_and_evidence_ids",
     dict(grounding={"status": "no_grounded_match", "grounded": False}, no_match=True,
          abstain_recommended=True, sources=[]),
     "no_match_contains_evidence"),
    ("ungrounded_receipt_with_answer",
     dict(grounding={"status": "no_grounded_match", "grounded": False}),
     "grounding_contradicts_evidence"),
    ("answer_beside_no_match", dict(sources=[], evidence_ids=[], evidence_claims=[],
                                    no_match=True, abstain_recommended=True,
                                    answer_status="no_relevant_memory"),
     "no_match_contains_evidence"),
    ("not_abstaining_without_sources", dict(sources=[], evidence_ids=[], evidence_claims=[]),
     "no_evidence_rows"),
    ("answerable_status_with_abstention", dict(abstain_recommended=True),
     "answerable_status_contradicts_abstention"),
]


@pytest.mark.parametrize("name,changes,reason", CONTRADICTORY_REASON,
                         ids=[case[0] for case in CONTRADICTORY_REASON])
def test_ask_contradictory_envelope_withholds_answer(backend, mcp_server, name, changes, reason):
    backend.reset({
        REASON: (200, reason_envelope(**changes)),
        SEARCH: (200, search_envelope(**NO_MATCH)),
    })
    is_error, payload = mcp_server.call("hebbrix_ask", question="Which database does Atlas use?")
    assert is_error is True, name
    assert payload["answer"] is None
    _no_evidence(payload)
    assert payload["failure_category"] == "malformed_evidence_receipt"
    assert payload["safety_reason"] == reason
    assert payload["synthesis_status"] == "abstained"


def test_ask_contradictory_fallback_search_also_withheld(backend, mcp_server):
    backend.reset({
        REASON: (200, reason_envelope(decision_abstained=True)),
        SEARCH: (200, search_envelope(grounding={})),
    })
    is_error, payload = mcp_server.call("hebbrix_ask", question="Which database does Atlas use?")
    assert is_error is True
    assert payload["answer"] is None
    _no_evidence(payload)


def test_ask_retrieval_only_fallback_uses_valid_search_evidence(backend, mcp_server):
    backend.reset({
        REASON: (200, reason_envelope(safety_contract_version=None)),
        SEARCH: (200, search_envelope()),
    })
    is_error, payload = mcp_server.call("hebbrix_ask", question="Which database does Atlas use?")
    assert is_error is False
    assert payload["synthesis_status"] == "retrieval_only"
    assert payload["reasoning_failure_category"] == "malformed_evidence_receipt"
    assert [c["id"] for c in payload["citations"]] == ["m1"]
    assert payload["answer_gate"]["safe_to_answer"] is True


def test_ask_unknown_fact_is_not_an_error(backend, mcp_server):
    backend.reset({
        REASON: (200, reason_envelope(**REASON_NO_MATCH)),
        SEARCH: (200, search_envelope(**NO_MATCH)),
    })
    is_error, payload = mcp_server.call("hebbrix_ask", question="What is my blood type?")
    assert is_error is False
    assert payload["answer"] is None
    _no_evidence(payload)
    assert payload["failure_category"] == "unknown_fact"
    assert payload["decision_abstained"] is True


def test_ask_degraded_reasoning_is_error(backend, mcp_server):
    backend.reset({
        REASON: (200, reason_envelope(**REASON_NO_MATCH | dict(
            degraded=True, abstain_reason="evidence_pipeline_degraded"))),
        SEARCH: (200, search_envelope(**NO_MATCH)),
    })
    is_error, payload = mcp_server.call("hebbrix_ask", question="Which database does Atlas use?")
    assert is_error is True
    assert payload["failure_category"] == "service_failure"
    assert payload["answer"] is None


# ----------------------------------------------------------------------------
# Defect 10: citations carry the supporting passage, never a silent cut.
# ----------------------------------------------------------------------------
FILLER = ("The weekly operations review covered staffing, the shared calendar and "
          "routine vendor updates; nothing changed. ")


def _long_memory(fact: str, position: str, repeats: int = 9) -> str:
    before = {"beginning": 0, "middle": repeats // 2, "end": repeats}[position]
    return FILLER * before + fact + " " + FILLER * (repeats - before)


@pytest.mark.parametrize("position", ["beginning", "middle", "end"])
def test_ask_citation_is_the_supporting_span_wherever_it_is(backend, mcp_server, position):
    fact = "The Halvard escalation contact is Priya Venkataraman"
    content = _long_memory(fact + ".", position)
    assert len(content) > 900
    source = {"memory_id": "long-1", "content": content, "score": 1.1,
              "revision_status": "current", "is_current": True}
    metadata = {"evidence_contract": {"propositions": [{"supporting_spans": [
        {"memory_id": "long-1", "span": fact, "signals": ["verified_answer_span"]}]}]}}
    backend.reset({REASON: (200, reason_envelope(
        answer=f"{fact}. [1]", sources=[source], evidence_ids=["long-1"],
        evidence_claims=[], metadata=metadata,
    ))})
    is_error, payload = mcp_server.call(
        "hebbrix_ask", question="Who is the Halvard escalation contact?", user_id="end-user-a"
    )
    assert is_error is False
    (citation,) = payload["citations"]
    assert citation["content"] == fact
    assert citation["passage"] == "supporting_span"
    assert citation["truncated"] is True
    assert citation["content_length"] == len(content)
    assert citation["fetch_full_content"] == {
        "tool": "hebbrix_get", "arguments": {"memory_id": "long-1", "user_id": "end-user-a"}
    }


def test_ask_without_span_returns_the_whole_memory(backend, mcp_server):
    """The reported case: a 1,534-character memory whose fact sits at the end."""
    fact = "Finally, the escalation contact is Priya Venkataraman."
    content = (FILLER * 20)[: 1534 - len(fact)] + fact
    assert len(content) == 1534
    source = {"memory_id": "long-2", "content": content, "score": 1.0,
              "revision_status": "current", "is_current": True}
    backend.reset({REASON: (200, reason_envelope(
        answer="Priya Venkataraman. [1]", sources=[source], evidence_ids=["long-2"],
        evidence_claims=[],
    ))})
    is_error, payload = mcp_server.call("hebbrix_ask", question="Who is the escalation contact?")
    assert is_error is False
    (citation,) = payload["citations"]
    assert citation["content"] == content and fact in citation["content"]
    assert citation["passage"] == "full_content" and citation["truncated"] is False
    assert "fetch_full_content" not in citation


def test_ask_oversized_memory_without_span_marks_truncation(backend, mcp_server):
    content = FILLER * 60 + "The fact is at the very end."
    source = {"memory_id": "huge", "content": content, "score": 1.0,
              "revision_status": "current", "is_current": True}
    backend.reset({REASON: (200, reason_envelope(
        sources=[source], evidence_ids=["huge"], evidence_claims=[]))})
    is_error, payload = mcp_server.call("hebbrix_ask", question="Where is the fact?")
    assert is_error is False
    (citation,) = payload["citations"]
    assert citation["passage"] == "leading_characters"
    assert citation["truncated"] is True
    assert len(citation["content"]) < citation["content_length"] == len(content)
    assert citation["fetch_full_content"]["arguments"] == {"memory_id": "huge"}


def test_ask_multi_source_answer_cites_each_source(backend, mcp_server):
    sources = [
        {"memory_id": "kestrel-region", "content": "Project Kestrel's region is eu-north-1.",
         "score": 1.0, "revision_status": "current", "is_current": True},
        {"memory_id": "kestrel-db", "content": FILLER * 6 + "Project Kestrel's database is "
         "CockroachDB.", "score": 0.9, "revision_status": "current", "is_current": True},
    ]
    metadata = {"evidence_selection": {"obligations": [
        {"supporting_spans": [{"memory_id": "kestrel-db",
                               "span": "Project Kestrel's database is CockroachDB"}]},
        # A span that is not verbatim in its memory is never used as a citation.
        {"supporting_spans": [{"memory_id": "kestrel-region", "span": "Kestrel runs in Ohio"}]},
    ]}}
    backend.reset({REASON: (200, reason_envelope(
        answer="eu-north-1 [1] and CockroachDB [2].", sources=sources,
        evidence_ids=["kestrel-region", "kestrel-db"], evidence_claims=[], metadata=metadata,
    ))})
    is_error, payload = mcp_server.call(
        "hebbrix_ask", question="Which region and database does Project Kestrel use?"
    )
    assert is_error is False
    region, database = payload["citations"]
    assert region["content"] == sources[0]["content"] and region["truncated"] is False
    assert database["content"] == "Project Kestrel's database is CockroachDB"
    assert database["passage"] == "supporting_span" and database["truncated"] is True


# ----------------------------------------------------------------------------
# Defect 7: explicit, validated end-user / agent / run scope.
# ----------------------------------------------------------------------------
def test_search_and_ask_forward_end_user_scope(backend, mcp_server):
    backend.reset({SEARCH: (200, search_envelope()), REASON: (200, reason_envelope())})
    is_error, payload = mcp_server.call(
        "hebbrix_search", query="Which database?", user_id="end-user-a",
        agent_id="support-agent", run_id="run-7",
    )
    assert is_error is False and payload["scope"]["user_id"] == "end-user-a"
    (sent,) = backend.sent(*SEARCH)
    assert {k: sent["json"][k] for k in ("user_id", "agent_id", "run_id")} == {
        "user_id": "end-user-a", "agent_id": "support-agent", "run_id": "run-7"}
    is_error, _ = mcp_server.call("hebbrix_ask", question="Which database?", user_id="end-user-a")
    assert is_error is False
    assert backend.sent(*REASON)[0]["json"]["user_id"] == "end-user-a"


def test_ask_fallback_search_keeps_the_scope(backend, mcp_server):
    backend.reset({REASON: (200, reason_envelope(**REASON_NO_MATCH)),
                   SEARCH: (200, search_envelope())})
    mcp_server.call("hebbrix_ask", question="Which database?", user_id="end-user-b")
    assert backend.sent(*SEARCH)[0]["json"]["user_id"] == "end-user-b"


def test_missing_end_user_scope_surfaces_api_guidance(backend, mcp_server):
    detail = {"error": "end_user_scope_required",
              "message": "Provide user_id to read a collection containing end-user data. "
                         "A collection alone is not a user boundary.",
              "required_scope": ["user_id"]}
    backend.reset({SEARCH: (400, {"detail": detail}), REASON: (400, {"detail": detail})})
    for tool, arg in (("hebbrix_search", "query"), ("hebbrix_ask", "question")):
        is_error, payload = mcp_server.call(tool, **{arg: "Which database?"})
        assert is_error is True, tool
        assert "Provide user_id" in payload["error"], tool


def test_id_addressed_tools_forward_scope_as_query_constraints(backend, mcp_server):
    memory = {"id": "m1", "content": "fact", "searchable": True, "end_user_id": "end-user-a"}
    backend.reset({
        ("GET", "/v1/memories/m1"): (200, memory),
        ("PATCH", "/v1/memories/m1"): (200, memory),
        ("GET", "/v1/memories/m1/history"): (200, {"history": []}),
        ("GET", "/v1/memories"): (200, {"items": [memory]}),
        ("DELETE", "/v1/memories/m1"): (204, None),
    })
    assert mcp_server.call("hebbrix_get", memory_id="m1", user_id="end-user-a")[1]["user_id"] \
        == "end-user-a"
    mcp_server.call("hebbrix_update", memory_id="m1", content="fact", user_id="end-user-a")
    mcp_server.call("hebbrix_history", memory_id="m1", user_id="end-user-a")
    mcp_server.call("hebbrix_list", user_id="end-user-a", run_id="run-7")
    is_error, deleted = mcp_server.call("hebbrix_forget", memory_id="m1", user_id="end-user-a")
    assert is_error is False and deleted["deleted"] is True
    for request in backend.requests:
        assert request["query"]["user_id"] == "end-user-a", request["path"]
    assert backend.sent("GET", "/v1/memories")[0]["query"]["run_id"] == "run-7"


def test_scoped_get_miss_is_an_error_and_not_served_from_cache(backend, mcp_server):
    backend.reset({
        ("POST", "/v1/memories/raw"): (201, {"id": "m-scoped", "searchable": False,
                                             "processing_status": "pending"}),
        ("GET", "/v1/memories/m-scoped"): (404, {"detail": "Memory not found"}),
    })
    is_error, _ = mcp_server.call("hebbrix_remember", content="Alice prefers tea.",
                                  user_id="alice", wait_for_index=False)
    assert is_error is False
    assert backend.sent("POST", "/v1/memories/raw")[0]["json"]["user_id"] == "alice"
    # Another end user must never see Alice's write from the local cache.
    is_error, payload = mcp_server.call("hebbrix_get", memory_id="m-scoped", user_id="bob")
    assert is_error is True and "HTTP 404" in payload["error"]
    # The writer's own scope still gets read-after-write.
    is_error, payload = mcp_server.call("hebbrix_get", memory_id="m-scoped", user_id="alice")
    assert is_error is False and payload["pending_index"] is True


@pytest.mark.parametrize("value", ["", "   ", "x" * 256, "bad\nid"])
def test_invalid_scope_is_rejected_before_any_request(backend, mcp_server, value):
    backend.reset({SEARCH: (200, search_envelope())})
    is_error, payload = mcp_server.call("hebbrix_search", query="q", user_id=value)
    assert is_error is True
    assert payload["error_code"] == "invalid_scope"
    assert backend.requests == []


def test_writes_forward_scope(backend, mcp_server):
    backend.reset({
        ("POST", "/v1/memories/batch"): (201, {"created": 1, "memory_ids": ["b1"]}),
        ("POST", "/v1/knowledge-graph/query"): (200, {"results": []}),
    })
    mcp_server.call("hebbrix_remember_many", facts=["one"], user_id="end-user-a",
                    agent_id="support-agent")
    (batch,) = backend.sent("POST", "/v1/memories/batch")
    assert batch["json"]["user_id"] == "end-user-a"
    assert batch["json"]["agent_id"] == "support-agent"
    mcp_server.call("hebbrix_graph_query", entity="Atlas", user_id="end-user-a")
    assert backend.sent("POST", "/v1/knowledge-graph/query")[0]["json"]["user_id"] == "end-user-a"


def test_pinned_scope_is_applied_and_cannot_be_overridden(backend, pinned_server):
    backend.reset({SEARCH: (200, search_envelope())})
    is_error, payload = pinned_server.call("hebbrix_search", query="Which database?")
    assert is_error is False
    sent = backend.sent(*SEARCH)[0]["json"]
    assert sent["user_id"] == "end-user-a" and sent["agent_id"] == "support-agent"
    is_error, payload = pinned_server.call("hebbrix_search", query="q", user_id="end-user-b")
    assert is_error is True and payload["error_code"] == "scope_pinned"
    assert len(backend.requests) == 1
    # Graph data is attributed to end users only: an agent-pinned session must
    # not silently read the whole user's graph.
    is_error, payload = pinned_server.call("hebbrix_graph_query", entity="Atlas")
    assert is_error is True and payload["error_code"] == "unsupported_scope"
    assert len(backend.requests) == 1


# ----------------------------------------------------------------------------
# Defect 8: the advertised extraction path (extract=True with defaults).
# ----------------------------------------------------------------------------
def _memories_endpoint(request: dict[str, Any]):
    """Mirror the API's MemoryAdd contract, including the reported 422."""
    body = request["json"] or {}
    if body.get("infer") and body.get("wait_for_index") and body.get("async_dispatch") is True:
        return 422, {"error": {"type": "validation_error", "message": (
            "Invalid request: Value error, wait_for_index conflicts with "
            "async_dispatch=true; omit async_dispatch to wait, or poll the returned "
            "job when using background extraction")}}
    if body.get("async_dispatch") is True:
        return 202, {"job_id": "job-1", "status": "queued", "poll_url": "/v1/memory-jobs/job-1"}
    return 200, {"results": [], "searchable": False}


def _extraction_routes(readiness_sequence: list[bool]) -> dict:
    job_states = iter(["processing", "completed"])
    readiness = iter(readiness_sequence)

    def job(_request):
        state = next(job_states, "completed")
        payload = {"job_id": "job-1", "status": state, "error": None}
        if state == "completed":
            payload |= {
                "outbox_event_id": "11111111-2222-3333-4444-555555555555",
                "readiness_url": "/v1/memories/batches/11111111-2222-3333-4444-555555555555",
                "result": {"facts_extracted": 2, "memories_created": 2, "searchable": None,
                           "events": [
                               {"event": "ADD", "memory_id": "x1", "content": "Staging runs K8s 1.31."},
                               {"event": "ADD", "memory_id": "x2", "content": "On-call changes Mondays."},
                           ]},
            }
        return 200, payload

    def report(_request):
        return 200, {"searchable": next(readiness, True), "complete": False}

    return {
        ("POST", "/v1/memories"): _memories_endpoint,
        ("GET", "/v1/memory-jobs/job-1"): job,
        ("GET", "/v1/memories/batches/11111111-2222-3333-4444-555555555555"): report,
    }


def test_extract_with_default_wait_completes_and_confirms_readiness(backend, mcp_server):
    backend.reset(_extraction_routes([False, True]))
    is_error, payload = mcp_server.call(
        "hebbrix_remember", content="Staging runs K8s 1.31 and on-call changes Mondays.",
        extract=True, user_id="end-user-a",
    )
    assert is_error is False, payload
    (write,) = backend.sent("POST", "/v1/memories")
    assert write["json"]["async_dispatch"] is True and "wait_for_index" not in write["json"]
    assert write["json"]["user_id"] == "end-user-a"
    assert payload["status"] == "completed"
    assert payload["searchable"] is True
    assert payload["index_wait_outcome"] == "satisfied"
    assert [m["id"] for m in payload["memories"]] == ["x1", "x2"]


def test_extract_without_index_wait_reports_readiness_truthfully(backend, mcp_server):
    backend.reset(_extraction_routes([False]))
    is_error, payload = mcp_server.call(
        "hebbrix_remember", content="Staging runs K8s 1.31.", extract=True,
        wait_for_index=False,
    )
    assert is_error is False
    assert payload["status"] == "completed" and payload["searchable"] is False
    assert "hebbrix_extraction_status" in payload["next_action"]
    assert len(backend.sent("GET", "/v1/memories/batches/11111111-2222-3333-4444-555555555555")) == 1


def test_isolation_rule_applies_to_non_search_tools(backend, mcp_server):
    backend.reset({("GET", "/v1/memories/m404"): (404, {"detail": "Memory not found"}),
                   ("GET", "/v1/collections"): (200, {"items": []})})
    assert mcp_server.call("hebbrix_get", memory_id="m404")[0] is True
    assert mcp_server.call("hebbrix_list_collections")[0] is False
