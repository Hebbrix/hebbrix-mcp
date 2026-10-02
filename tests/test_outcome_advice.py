import asyncio
from unittest.mock import AsyncMock
from hebbrix_mcp import server as S


def test_confidence_preserves_advice_not_authorization(monkeypatch):
    read = AsyncMock(return_value=dict(confidence=.9, memory_support=.9,
        action_confidence=.676, advisory_decision="ACT", decision_count=8,
        safety_reasons=[], authorization_granted=False, autonomy_evidence={"risk_tier": "low"}))
    monkeypatch.setattr(S, "_get", read)
    result = asyncio.run(S.hebbrix_confidence("Restart sandbox", "c", "alice", "p", "a", {"issue": "slow"}))
    assert read.call_args.args[1]["end_user_id"] == "alice"
    assert result["action_confidence"] == .676 and result["advisory_decision"] == "ACT"
    assert not result["authorization_granted"]


def test_policy_configuration_is_explicit_revision_checked_write(monkeypatch):
    write = AsyncMock(return_value={"revision": 2, "authorization_granted": False})
    monkeypatch.setattr(S, "_put", write)
    config = {"strategy": "posterior_sampling", "actions": {"a": {"target": "sandbox"}}}
    result = asyncio.run(S.hebbrix_configure_policy("p:key", config, 1, "alice", "c"))
    assert write.call_args.args == ("/learning/policies/p%3Akey/configuration", dict(
        configuration=config, expected_revision=1, collection_id="c", user_id="alice"))
    assert result["revision"] == 2


def test_adaptive_choice_fails_without_configuration_then_logs_exact_mode(monkeypatch):
    read = AsyncMock(return_value={"configuration": None})
    write = AsyncMock(return_value={"decision_id": "d", "behavior_probabilities": {"a": .5, "b": .5}})
    monkeypatch.setattr(S, "_get", read)
    monkeypatch.setattr(S, "_post", write)
    assert "error" in asyncio.run(S.hebbrix_choose_action("p", ["a", "b"], adaptive_exploration=True))
    write.assert_not_called()
    read.return_value = {"configuration": {"strategy": "posterior_sampling"}}
    result = asyncio.run(S.hebbrix_choose_action("p", ["a", "b"], adaptive_exploration=True))
    assert write.call_args.args[1]["mode"] == "explore"
    assert write.call_args.args[1]["exploration_rate"] == 0
    assert result["behavior_probabilities"] == {"a": .5, "b": .5}


def test_search_keeps_final_api_outcome_order_at_saturated_scores(monkeypatch):
    from tests.test_server import _fake, FakeResponse
    monkeypatch.setattr(S, "_LOCAL_CACHE", False)
    _fake(monkeypatch, FakeResponse(200, {"results": [
        dict(memory_id="b", content="Enable pooling", score=.9999, rank=1,
            score_calibrated=True, metadata={"outcome_evidence": {"successes": 6, "failures": 0}}),
        dict(memory_id="a", content="Raise timeout", score=1., rank=2,
            score_calibrated=True, metadata={"outcome_evidence": {"successes": 0, "failures": 6}}),
    ], "scores_calibrated": True}))
    result = asyncio.run(S.hebbrix_search("Fix slow requests", collection_id="c", min_score=0))
    assert [r["id"] for r in result["results"]] == ["b", "a"]
    assert result["results"][1]["outcome_evidence"]["failures"] == 6


def test_new_setup_report_and_auto_prior_wire(monkeypatch):
    write=AsyncMock(return_value={"decision_id":"d", "revision":1})
    read=AsyncMock(return_value={"authorization_granted":False})
    monkeypatch.setattr(S,"_post",write)
    monkeypatch.setattr(S,"_get",read)
    asyncio.run(S.hebbrix_setup_policy("p",{"version":"v1","fields":{}},{"a":{"risk_tier":"low"}},"u","c"))
    assert write.call_args.args[0]=="/learning/policies/p/setup"
    asyncio.run(S.hebbrix_learning_report("p",7,"u","c"))
    assert read.call_args.args==( "/learning/policies/p/report",dict(days=7,collection_id="c",user_id="u"))
    asyncio.run(S.hebbrix_choose_action("p",["a","b"],prior_action="b",prior_strength=4))
    assert write.call_args.args[1]["mode"]=="auto"
    assert write.call_args.args[1]["prior_action"]=="b"
    before=write.call_count
    assert "error" in asyncio.run(S.hebbrix_choose_action("p",["a","b"],prior_action="x",prior_strength=4))
    assert write.call_count==before
