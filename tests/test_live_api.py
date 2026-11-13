"""Opt-in live API compatibility test over the real stdio protocol.

Offline mocks encode what we believe the API accepts; this test checks it. It is
skipped unless HEBBRIX_LIVE_API_URL is set, e.g.:

    HEBBRIX_LIVE_API_URL=http://localhost:8000 \\
    HEBBRIX_LIVE_API_KEY_FILE=/path/to/key.json \\
    uv run --frozen pytest tests/test_live_api.py -q

The key comes from HEBBRIX_LIVE_API_KEY or the ``api_key`` field of the JSON file
named by HEBBRIX_LIVE_API_KEY_FILE; it is never printed. Every run writes only to
fresh disposable collections and deletes them afterwards. A non-local API is
refused unless HEBBRIX_LIVE_ALLOW_REMOTE=1.
"""

from __future__ import annotations

import json
import os
import random
import string
import time
from urllib.parse import urlparse

import httpx
import pytest

from conftest import StdioMCP, server_env

LIVE_URL = os.environ.get("HEBBRIX_LIVE_API_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(
    not LIVE_URL, reason="set HEBBRIX_LIVE_API_URL to run the live API compatibility test"
)
ANSWER_STATUSES = {
    "answerable", "conflicting", "superseded", "unverified", "indexing", "no_relevant_memory",
}
# A pronounceable, letters-only codename keeps each run's facts unique without
# turning the subject into an opaque identifier for the API's claim grounding.
RUN = "".join(random.SystemRandom().choice(string.ascii_lowercase) for _ in range(6))
CODENAME = f"Tallis{RUN}"
PLAIN_FACT = f"Project {CODENAME}'s database is PostgreSQL 16."
FILLER = (
    f"The quarterly operations review for the {CODENAME} freight account covered "
    "routine items: warehouse staffing stayed stable across the three regional hubs, "
    "the driver onboarding checklist needed no changes, and fuel costs were reviewed "
    "without action items. "
)
ESCALATION = f"Finally, the team confirmed that the {CODENAME} escalation contact is Priya Venkataraman."
LONG_FACT = (FILLER * 8)[: 1534 - len(ESCALATION) - 1] + " " + ESCALATION
MESSY = (
    f"Notes from today: the {CODENAME} staging cluster runs Kubernetes 1.31, and the "
    "on-call rotation for it changes every Monday."
)


def _key() -> str:
    if os.environ.get("HEBBRIX_LIVE_API_KEY"):
        return os.environ["HEBBRIX_LIVE_API_KEY"]
    path = os.environ.get("HEBBRIX_LIVE_API_KEY_FILE", "")
    if not path:
        pytest.fail("set HEBBRIX_LIVE_API_KEY or HEBBRIX_LIVE_API_KEY_FILE")
    with open(os.path.expanduser(path)) as handle:
        return json.load(handle)["api_key"]


@pytest.fixture(scope="module")
def live(tmp_path_factory):
    host = urlparse(LIVE_URL).hostname
    if host not in ("localhost", "127.0.0.1", "::1") and os.environ.get(
        "HEBBRIX_LIVE_ALLOW_REMOTE"
    ) != "1":
        pytest.fail("refusing disposable writes to a non-local API without HEBBRIX_LIVE_ALLOW_REMOTE=1")
    key = _key()
    api = httpx.Client(
        base_url=LIVE_URL + "/v1", headers={"Authorization": f"Bearer {key}"}, timeout=120
    )
    created: list[str] = []
    servers: list[StdioMCP] = []

    def connect(label: str) -> tuple[str, StdioMCP]:
        response = api.post("/collections", json={
            "name": f"zz-mcp-live-{label}-{RUN}",
            "description": "hebbrix-mcp live compatibility test - safe to delete",
        })
        assert response.status_code in (200, 201), response.status_code
        collection_id = response.json()["id"]
        created.append(collection_id)
        server = StdioMCP(server_env(
            LIVE_URL + "/v1", str(tmp_path_factory.mktemp(label)),
            HEBBRIX_API_KEY=key, HEBBRIX_COLLECTION_ID=collection_id,
            HEBBRIX_EXTRACTION_POLL_SECONDS="25",
        ))
        servers.append(server)
        return collection_id, server

    yield connect
    for server in servers:
        server.close()
    for collection_id in created:
        api.delete(f"/collections/{collection_id}")
    api.close()


def _searchable(server: StdioMCP, memory_id: str, **scope: str) -> bool:
    for _ in range(45):
        is_error, receipt = server.call("hebbrix_get", memory_id=memory_id, **scope)
        if not is_error and receipt.get("searchable") is True:
            return True
        time.sleep(1)
    return False


def _readiness_contract(payload: dict) -> None:
    assert payload["answer_status"] in ANSWER_STATUSES
    assert isinstance(payload["indexing"], dict) and payload["indexing"]["status"]
    gate = payload["answer_gate"]
    assert isinstance(gate["ready"], bool) and isinstance(gate["safe_to_answer"], bool)
    assert isinstance(gate["require_ready"]["safe_to_answer"], bool)
    assert gate["require_ready"]["safe_to_answer"] <= gate["safe_to_answer"]
    assert payload["evidence_withheld"] is (payload["failure_category"] is not None)


def test_live_remember_extract_search_ask_get(live):
    _, server = live("shared")

    is_error, plain = server.call("hebbrix_remember", content=PLAIN_FACT)
    assert is_error is False, plain
    assert plain["id"] and isinstance(plain["searchable"], bool)

    is_error, long_memory = server.call("hebbrix_remember", content=LONG_FACT)
    assert is_error is False, long_memory

    # The advertised smart path with its defaults (0.5.14 failed with HTTP 422).
    is_error, extracted = server.call("hebbrix_remember", content=MESSY, extract=True)
    assert is_error is False, extracted
    assert extracted["job_id"]
    assert extracted["status"] in {"completed", "indexing_pending", "processing", "queued"}
    if extracted["status"] == "completed":
        assert extracted["memories"], extracted
        assert isinstance(extracted["searchable"], bool)

    assert _searchable(server, plain["id"]) and _searchable(server, long_memory["id"])

    is_error, found = server.call(
        "hebbrix_search", query=f"What database does Project {CODENAME} use?"
    )
    assert is_error is False, found
    _readiness_contract(found)
    assert plain["id"] in [row["id"] for row in found["results"]], found

    is_error, answer = server.call(
        "hebbrix_ask", question=f"Who is the {CODENAME} escalation contact?"
    )
    assert is_error is False, answer
    _readiness_contract(answer)
    cited = [c for c in answer["citations"] if c["id"] == long_memory["id"]]
    assert cited, answer
    # The supporting fact sits at the very end of a 1,534-character memory.
    assert "Priya Venkataraman" in cited[0]["content"], cited[0]
    assert isinstance(cited[0]["truncated"], bool)
    assert cited[0]["content_length"] == len(LONG_FACT)

    is_error, got = server.call("hebbrix_get", memory_id=long_memory["id"])
    assert is_error is False and got["content"] == LONG_FACT


def test_live_end_user_scope(live):
    _, server = live("scoped")
    fact = f"The {CODENAME} customer is billed in euros."
    is_error, write = server.call("hebbrix_remember", content=fact, user_id="live-user-a")
    assert is_error is False, write
    assert _searchable(server, write["id"], user_id="live-user-a")

    # A collection holding end-user data is not a user boundary: the API refuses
    # an unscoped read, and the adapter surfaces that as an MCP error.
    question = f"Which currency is the {CODENAME} customer billed in?"
    for tool, argument in (("hebbrix_search", "query"), ("hebbrix_ask", "question")):
        is_error, refused = server.call(tool, **{argument: question})
        assert is_error is True, (tool, refused)
        assert "user_id" in refused["error"], (tool, refused)

    is_error, found = server.call("hebbrix_search", query=question, user_id="live-user-a")
    assert is_error is False, found
    assert write["id"] in [row["id"] for row in found["results"]], found

    is_error, other = server.call("hebbrix_search", query=question, user_id="live-user-b")
    assert is_error is False, other
    assert write["id"] not in [row["id"] for row in other["results"]]

    is_error, answered = server.call("hebbrix_ask", question=question, user_id="live-user-a")
    assert is_error is False, answered

    assert server.call("hebbrix_get", memory_id=write["id"], user_id="live-user-a")[0] is False
    is_error, foreign = server.call("hebbrix_get", memory_id=write["id"], user_id="live-user-b")
    assert is_error is True, foreign
