"""Failure categories and diagnostics must not weaken evidence validation."""

import asyncio
import os

import httpx
import pytest

os.environ.setdefault("HEBBRIX_API_KEY", "mem_sk_test_dummy")
from hebbrix_mcp import server as S


def empty(**changes):
    return {
        "no_match": True,
        "abstain_recommended": True,
        "query_confidence": 0.0,
        "grounding": {"status": "no_grounded_match"},
        "evidence_ids": [],
        "results": [],
        "sources": [],
        "answer": None,
        "safety_contract_version": "search-safety-v1",
        **changes,
    }


@pytest.mark.parametrize(
    "response,expected",
    [
        (empty(), "unknown_fact"),
        (
            empty(
                grounding={
                    "status": "verification_unavailable",
                    "reason": "claim_verifier_unavailable",
                }
            ),
            "verification_unavailable",
        ),
        ({"error": "unavailable", "status": 503}, "service_failure"),
        ({"error": "budget exhausted", "status": 402}, "quota_exhausted"),
        ({"answer": "untrusted"}, "malformed_evidence_receipt"),
        ([], "malformed_evidence_receipt"),
    ],
)
def test_ask_distinguishes_unknown_from_operational_failure(
    monkeypatch, response, expected
):
    async def post(path, body):
        return response

    monkeypatch.setattr(S, "_cid", lambda _: "test-scope")
    monkeypatch.setattr(S, "_post", post)
    result = asyncio.run(S.hebbrix_ask("Which database is configured?"))
    assert result["failure_category"] == expected
    assert result["answer"] is None
    assert result["citations"] == []
    assert result["abstain_recommended"] is True
    assert bool(result.get("error")) == (
        expected
        in {"service_failure", "verification_unavailable", "malformed_evidence_receipt"}
    )


def test_retrieval_only_keeps_both_request_traces(monkeypatch):
    async def post(path, body):
        if path.endswith("reason"):
            return empty(
                _request_diagnostics={"request_id": "reason-1", "build": "r-test"}
            )
        return empty(
            no_match=False,
            abstain_recommended=False,
            query_confidence=0.9,
            grounding={
                "status": "supported",
                "contract_version": "claim-grounding-v28",
            },
            evidence_ids=["memory-1"],
            results=[
                {"memory_id": "memory-1", "score": 0.9, "content": "Synthetic evidence"}
            ],
            _request_diagnostics={"request_id": "search-2", "build": "r-test"},
        )

    monkeypatch.setattr(S, "_cid", lambda _: "test-scope")
    monkeypatch.setattr(S, "_post", post)
    result = asyncio.run(S.hebbrix_ask("Which database is configured?"))
    assert result["synthesis_status"] == "retrieval_only"
    assert result["reasoning_failure_category"] == "synthesis_abstention"
    assert result["citations"][0]["id"] == "memory-1"
    assert result["diagnostics"]["reasoning"]["request_id"] == "reason-1"
    assert result["diagnostics"]["retrieval"]["request_id"] == "search-2"


def test_http_diagnostics_are_response_local_and_redacted(monkeypatch):
    async def run():
        async def handler(request):
            key = request.url.path.rsplit("/", 1)[-1]
            return httpx.Response(
                200,
                json=empty(),
                headers={
                    "x-request-id": key + "-request",
                    "x-hebbrix-build": "test-build",
                    "authorization": "must-not-appear",
                    "set-cookie": "must-not-appear",
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monkeypatch.setattr(S, "_client", lambda: client)
            return await asyncio.gather(
                S._post("/search", {}), S._post("/search/reason", {})
            )

    first, second = asyncio.run(run())
    assert S._evidence_diagnostics(first) == {
        "http_status": 200,
        "request_id": "search-request",
        "build": "test-build",
        "safety_version": "search-safety-v1",
        "grounding_status": "no_grounded_match",
    }
    assert S._evidence_diagnostics(second)["request_id"] == "reason-request"
    assert "must-not-appear" not in str(first) + str(second)
