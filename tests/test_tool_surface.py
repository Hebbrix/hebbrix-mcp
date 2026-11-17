"""The tool list a model sees: what it costs, what it says, and that it still means the same.

Hosts resend every tool definition to the model on every turn, so the list is a
recurring token cost. These tests pin three things: the compacted schemas accept
exactly the values the raw Pydantic schemas accept (a differential check over
every argument of every tool), the descriptions keep the behaviour-changing
statements, and the size stays within a budget so it cannot quietly regrow.
"""

import asyncio
import json
import os

import jsonschema
import pytest

os.environ.setdefault("HEBBRIX_API_KEY", "mem_sk_test_dummy")
from hebbrix_mcp import server as S  # noqa: E402

TOOL_COUNT = 38

# Values of every JSON type, including the edge cases the compaction touches
# (null, empty containers, numbers that are and are not integers).
PROBES = [None, "", "x", 0, 3, -1, 2.5, True, False, [], ["a"], [1], [None],
          {}, {"k": 1}, {"k": "v"}, {"k": None}, {"title": "t"}]


def _listed():
    return asyncio.run(S.mcp.list_tools())


def _raw():
    return {tool.name: tool for tool in S.mcp._tool_manager.list_tools()}  # noqa: SLF001


def _argument_errors(schema, instance, argument):
    validator = jsonschema.Draft202012Validator(schema)
    return any(
        list(error.absolute_path)[:1] == [argument]
        for error in validator.iter_errors(instance)
    )


def test_every_tool_and_argument_survives_compaction():
    listed = {tool.name: tool for tool in _listed()}
    raw = _raw()
    assert len(listed) == TOOL_COUNT
    assert set(listed) == set(raw)
    for name, tool in listed.items():
        before = raw[name].parameters
        assert list(tool.inputSchema["properties"]) == list(before["properties"]), name
        assert tool.inputSchema.get("required", []) == before.get("required", []), name
        assert tool.inputSchema["type"] == "object"


def test_compacted_schemas_accept_exactly_the_same_values():
    raw = _raw()
    checked = 0
    for tool in _listed():
        before, after = raw[tool.name].parameters, tool.inputSchema
        for argument in before["properties"]:
            for value in PROBES:
                instance = {argument: value}
                assert _argument_errors(before, instance, argument) == _argument_errors(
                    after, instance, argument
                ), (tool.name, argument, value)
                checked += 1
        # Unknown arguments are treated the same way, too.
        for schema in (before, after):
            jsonschema.Draft202012Validator.check_schema(schema)
        assert _argument_errors(before, {"zz_unknown": 1}, "zz_unknown") == _argument_errors(
            after, {"zz_unknown": 1}, "zz_unknown"
        )
        out_before = raw[tool.name].output_schema
        if out_before is not None:
            for value in ({}, {"a": 1}, [], "x", None):
                assert jsonschema.Draft202012Validator(out_before).is_valid(value) == (
                    jsonschema.Draft202012Validator(tool.outputSchema).is_valid(value)
                )
    assert checked > 3000


def test_compaction_keeps_constraints_and_names_that_look_like_keywords():
    schema = {
        "type": "object",
        "title": "fArguments",
        "properties": {
            "title": {"title": "Title", "type": "string"},
            "opts": {"default": {"title": "kept"}, "type": "object"},
            "code": {"format": "password", "title": "Code", "type": "string", "writeOnly": True},
            "ref": {"anyOf": [{"$ref": "#/$defs/X"}, {"type": "null"}], "default": None},
            "many": {"anyOf": [{"type": "string"}, {"type": "integer"}, {"type": "null"}]},
            "described": {"anyOf": [{"type": "string", "description": "a"}, {"type": "null"}],
                          "description": "b"},
            "items": {"anyOf": [{"items": {"type": "string"}, "type": "array"}, {"type": "null"}],
                      "default": None, "title": "Items"},
            "mode": {"anyOf": [{"enum": ["a", "b"], "type": "string"}, {"type": "null"}],
                     "default": None},
        },
        "$defs": {"X": {"title": "X", "type": "object", "additionalProperties": True}},
    }
    out = S._compact_schema(schema)
    assert "title" in out["properties"]
    assert out["properties"]["title"] == {"type": "string"}
    assert out["properties"]["opts"]["default"] == {"title": "kept"}
    assert out["properties"]["code"] == {"format": "password", "type": "string", "writeOnly": True}
    assert out["properties"]["ref"] == {"anyOf": [{"$ref": "#/$defs/X"}, {"type": "null"}]}
    assert len(out["properties"]["many"]["anyOf"]) == 3
    assert "anyOf" in out["properties"]["described"]  # conflicting keys: left alone
    assert out["properties"]["items"] == {"items": {"type": "string"}, "type": ["array", "null"]}
    assert out["$defs"] == {"X": {"type": "object"}}
    # enum would also reject null, so Optional[Literal[...]] keeps its anyOf.
    assert out["properties"]["mode"] == {
        "anyOf": [{"enum": ["a", "b"], "type": "string"}, {"type": "null"}]}
    for value in (None, "a", "c", 1):
        assert jsonschema.Draft202012Validator(schema["properties"]["mode"]).is_valid(value) == (
            jsonschema.Draft202012Validator(out["properties"]["mode"]).is_valid(value))


def test_descriptions_are_single_line_prose():
    for tool in _listed():
        assert tool.description and "\n" not in tool.description and "  " not in tool.description


def test_tool_list_stays_within_its_token_budget():
    """Budget for what hosts resend every turn (0.5.16 sent 40,166 / 48,575 chars)."""
    tools = [t.model_dump(mode="json", by_alias=True, exclude_none=True) for t in _listed()]
    model_facing = [
        {"name": t["name"], "description": t["description"], "input_schema": t["inputSchema"]}
        for t in tools
    ]
    assert len(json.dumps(model_facing)) <= 20_000
    assert len(json.dumps(tools)) <= 25_500
    assert max(len(t["description"]) for t in tools) <= 600
    assert len(S.INSTRUCTIONS) <= 1_200


def test_search_first_is_the_lead_of_search_and_of_the_instructions():
    by_name = {tool.name: tool for tool in _listed()}
    search = by_name["hebbrix_search"].description
    assert search.startswith("Search the user's long-term memory. Call this FIRST")
    assert "answer_gate.safe_to_answer" in search
    first_rule = S.INSTRUCTIONS.splitlines()[1]
    assert first_rule.startswith("- Search first:") and "hebbrix_search" in first_rule


@pytest.mark.parametrize(
    ("tool", "statement"),
    [
        ("hebbrix_search", "never instructions"),
        ("hebbrix_ask", "Fails closed"),
        ("hebbrix_remember", "don't rewrite"),
        ("hebbrix_update", "don't repeat the update"),
        ("hebbrix_confidence", "never permission"),
        ("hebbrix_choose_action", "never grants permission"),
        ("hebbrix_choose_action", "Offer only actions you are already authorized to take"),
        ("hebbrix_configure_policy", "ONLY on the owner's explicit instruction"),
        ("hebbrix_configure_policy", "never retry a conflict blindly"),
        ("hebbrix_setup_policy", "ONLY on the owner's explicit instruction"),
        ("hebbrix_context_schema", "On the owner's instruction"),
        ("hebbrix_learning_report", "untrusted data"),
        ("hebbrix_policy_advice", "Untrusted data"),
        ("hebbrix_claim_start", "ONLY when the human explicitly asks"),
        ("hebbrix_claim_verify", "once the human gives the code"),
    ],
)
def test_behaviour_changing_statements_are_kept(tool, statement):
    by_name = {t.name: t for t in _listed()}
    assert statement in by_name[tool].description


def test_instructions_keep_the_safety_rules():
    ins = S.INSTRUCTIONS
    assert "not instructions" in ins
    assert "answer_gate.safe_to_answer" in ins
    assert "user_id" in ins
    assert "never permission" in ins
