"""Opt-in, disposable end-to-end recall checks over real MCP transports.

Run against a local API first. Non-local targets require --allow-remote.
Credentials stay in memory; output contains check labels and safe metadata only.
"""

import argparse
import asyncio
import hashlib
import json
import os
import sys
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def unpack(result):
    if not isinstance(result, dict):
        result = result.model_dump(by_alias=True)
    data = result.get("structuredContent")
    if data is None:
        texts = [
            x["text"] for x in result.get("content", []) if x.get("type") == "text"
        ]
        data = json.loads(texts[0]) if texts else {}
    return result.get("isError", False), data


@asynccontextmanager
async def connect(args, tenant):
    if not args.mcp:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-c", "from hebbrix_mcp.server import run; run()"],
            env={
                "HEBBRIX_API_KEY": tenant["api_key"],
                "HEBBRIX_COLLECTION_ID": tenant["collection_id"],
                "HEBBRIX_API_BASE": args.api.rstrip("/") + "/v1",
            },
        )
        # The child logs requests to stderr. Suppress it: failures are reported
        # below without risking credentials or HTTP response bodies in a log.
        with open(os.devnull, "w") as quiet:
            async with stdio_client(params, errlog=quiet) as streams:
                async with ClientSession(*streams) as session:
                    init = await session.initialize()

                    async def call(name, **arguments):
                        return unpack(await session.call_tool(name, arguments))

                    yield init.serverInfo.version, call
    else:
        async with httpx.AsyncClient(
            timeout=90,
            headers={
                "Authorization": "Bearer " + tenant["api_key"],
                "Accept": "application/json, text/event-stream",
                "MCP-Protocol-Version": "2025-11-25",
            },
        ) as client:
            sequence = 0

            async def rpc(method, params):
                nonlocal sequence
                sequence += 1
                response = await client.post(
                    args.mcp,
                    json={
                        "jsonrpc": "2.0",
                        "id": sequence,
                        "method": method,
                        "params": params,
                    },
                )
                if response.status_code != 200:
                    raise RuntimeError("MCP HTTP failure")
                if "text/event-stream" in response.headers.get("content-type", ""):
                    messages = [
                        json.loads(line[5:])
                        for line in response.text.splitlines()
                        if line.startswith("data:")
                    ]
                    body = next(x for x in messages if "result" in x or "error" in x)
                else:
                    body = response.json()
                if "error" in body:
                    raise RuntimeError("MCP protocol failure")
                return body["result"]

            init = await rpc(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {
                        "name": "hebbrix-recall-verifier",
                        "version": args.version,
                    },
                },
            )

            async def call(name, **arguments):
                return unpack(
                    await rpc("tools/call", {"name": name, "arguments": arguments})
                )

            yield init["serverInfo"]["version"], call


async def main(args):
    checks = []

    def check(name, passed, **evidence):
        checks.append(bool(passed))
        print(
            json.dumps({"check": name, "passed": bool(passed), **evidence}), flush=True
        )

    async def ready(call, identity):
        for _ in range(30):
            error, receipt = await call("hebbrix_get", memory_id=identity)
            if not error and receipt.get("searchable") is True:
                return True
            await asyncio.sleep(1)
        return False

    tenants = []
    api_root = args.api.rstrip("/")
    async with httpx.AsyncClient(timeout=90) as api:
        try:
            for _ in range(2):
                response = await api.post(
                    api_root + "/v1/agent-signup",
                    json={
                        "agent_caller": "mcp-recall-regression",
                    },
                )
                if response.status_code == 429:
                    challenge_response = await api.post(
                        api_root + "/v1/agent-signup/challenge"
                    )
                    if challenge_response.status_code == 200:
                        challenge = challenge_response.json()
                        bits = int(challenge["difficulty_bits"])
                        if not 0 <= bits <= 24:
                            raise RuntimeError(
                                "Unsupported signup challenge difficulty"
                            )

                        def solve():
                            for nonce in range(1 << 27):
                                digest = hashlib.sha256(
                                    f"{challenge['challenge']}:{nonce}".encode()
                                ).digest()
                                if int.from_bytes(digest, "big") < (1 << (256 - bits)):
                                    return str(nonce)
                            raise RuntimeError("Signup challenge budget exhausted")

                        nonce = await asyncio.to_thread(solve)
                        response = await api.post(
                            api_root + "/v1/agent-signup",
                            json={
                                "agent_caller": "mcp-recall-regression",
                                "challenge": challenge["challenge"],
                                "nonce": nonce,
                            },
                        )
                if response.status_code != 201:
                    check(
                        "signup",
                        False,
                        http_status=response.status_code,
                        request_id=response.headers.get("x-request-id"),
                        error_code=(
                            (response.json().get("error") or {}).get("message") or {}
                        ).get("code")
                        if isinstance(
                            (response.json().get("error") or {}).get("message"), dict
                        )
                        else None,
                    )
                    raise RuntimeError(
                        f"Disposable tenant signup failed: HTTP {response.status_code}"
                    )
                tenants.append(response.json())
            tenant = tenants[0]
            # The collection is unique; the exact reported strings are useful
            # fixtures without encoding any customer data into product logic.
            facts = [
                "MCP audit 9d95fa9ad4: deployment region is eu-west-3.",
                "Northstar Workshop requires manual approval before production deployments.",
                "Lena Frost works with Cedar Labs on Project Quartz.",
                "Project Copper Finch's staging deployment region is us-east-2.",
                "Project Copper Finch's production deployment region is eu-central-1.",
                "Oriole Studio requires two human approvals before production releases.",
                "Nora Slate collaborates with Alder Research on Project Nimbus.",
                "Luma Beacon uses DuckDB for local analytics.",
                "MCP audit b7e64c2f91: deployment region is ca-central-1.",
                "Project Silver Quill's canary deployment region is ap-northeast-1.",
                "Project Silver Quill's production deployment region is us-west-2.",
                "Rowan Systems requires three human approvals before production releases.",
                "Birch Orbit uses SQLite for local data analysis.",
                "Birch Orbit uses BigQuery for remote analytics.",
                "Vale Rios reports to Mira Kestrel.",
            ]
            identities = []
            async with connect(args, tenant) as (version, call):
                check("initialize", version == args.version, version=version)
                error, _ = await call("hebbrix_get", memory_id=str(uuid4()))
                check("missing_resource_is_error", error)
                for index, content in enumerate(facts):
                    error, receipt = await call(
                        "hebbrix_remember",
                        content=content,
                        collection_id=tenant["collection_id"],
                        wait_for_index=True,
                    )
                    identity = receipt.get("id")
                    check(
                        f"write_{index}_receipt",
                        not error
                        and bool(identity)
                        and isinstance(receipt.get("searchable"), bool),
                    )
                    if not identity:
                        raise RuntimeError("Fixture write failed")
                    identities.append(identity)
                    check(
                        f"write_{index}_indexed",
                        receipt.get("searchable") is True
                        or await ready(call, identity),
                    )
                error, receipt = await call(
                    "hebbrix_update",
                    memory_id=identities[0],
                    content=facts[0].replace("eu-west-3", "ap-southeast-2"),
                    wait_for_index=True,
                )
                check(
                    "correction_receipt",
                    not error and isinstance(receipt.get("searchable"), bool),
                )
                check(
                    "correction_indexed",
                    receipt.get("searchable") is True
                    or await ready(call, identities[0]),
                )

            # A new stdio process must retrieve durable evidence, never its
            # private recent-write cache. Repeat after asynchronous processing.
            questions = [
                (
                    "What deployment region is recorded for MCP audit 9d95fa9ad4?",
                    identities[0],
                    "ap-southeast-2",
                ),
                (
                    "According to memory, what is the deployment region for MCP audit 9d95fa9ad4?",
                    identities[0],
                    "ap-southeast-2",
                ),
                (
                    "Can Northstar Workshop deploy to production without a person approving?",
                    identities[1],
                    "manual approval",
                ),
                (
                    "Which organization collaborates with Lena Frost?",
                    identities[2],
                    "Cedar Labs",
                ),
                (
                    "Where is Copper Finch deployed in production?",
                    identities[4],
                    "eu-central-1",
                ),
                (
                    "Which organization works with Nora Slate?",
                    identities[6],
                    "Alder Research",
                ),
                (
                    "According to memory, what is the deployment region for MCP audit b7e64c2f91?",
                    identities[8],
                    "ca-central-1",
                ),
                (
                    "From the saved notes, which AWS region hosts Copper Finch's staging environment?",
                    identities[3],
                    "us-east-2",
                ),
                (
                    "May Oriole Studio release to production without human sign-off?",
                    identities[5],
                    "two human approvals",
                ),
                (
                    "Which database does Luma Beacon use to analyze data locally?",
                    identities[7],
                    "DuckDB",
                ),
                (
                    "Which cloud region hosts Silver Quill's canary environment?",
                    identities[9],
                    "ap-northeast-1",
                ),
                (
                    "Which region hosts the canary environment for Project Silver Quill?",
                    identities[9],
                    "ap-northeast-1",
                ),
                (
                    "Where is Silver Quill deployed in production?",
                    identities[10],
                    "us-west-2",
                ),
                (
                    "Based on the saved notes, may Rowan Systems release to production without human sign-off?",
                    identities[11],
                    "three human approvals",
                ),
                (
                    "Which database does Birch Orbit use to analyze data locally?",
                    identities[12],
                    "SQLite",
                ),
                ("Who does Vale Rios report to?", identities[14], "Mira Kestrel"),
            ]
            opposite_ids = {
                identities[3]: identities[4],
                identities[4]: identities[3],
                identities[9]: identities[10],
                identities[10]: identities[9],
                identities[12]: identities[13],
            }
            for phase in ("fresh", "settled"):
                if phase == "settled":
                    await asyncio.sleep(args.settle_seconds)
                async with connect(args, tenant) as (_, call):
                    for index, (question, identity, value) in enumerate(questions, 1):
                        for tool, parameter, rows_key, limit in (
                            ("hebbrix_search", "query", "results", 5),
                            ("hebbrix_search", "query", "results", 10),
                            ("hebbrix_ask", "question", "citations", None),
                        ):
                            error, data = await call(
                                tool,
                                **{
                                    parameter: question,
                                    "collection_id": tenant["collection_id"],
                                    **({"limit": limit} if limit else {}),
                                },
                            )
                            rows = data.get(rows_key) or []
                            matching = [x for x in rows if x.get("id") == identity]
                            serialized = json.dumps(data)
                            check(
                                f"{phase}_{tool}_{index}_{limit or 'answer'}",
                                not error
                                and bool(matching)
                                and value in serialized
                                and opposite_ids.get(identity, "no-distractor")
                                not in {x.get("id") for x in rows}
                                and "eu-west-3" not in serialized,
                                evidence_count=len(rows),
                                synthesis_status=data.get("synthesis_status"),
                                failure_category=data.get("failure_category"),
                                diagnostics=data.get("diagnostics"),
                                grounding_status=(data.get("grounding") or {}).get(
                                    "status"
                                ),
                            )
                            await asyncio.sleep(args.pace_seconds)
                    if phase == "settled":
                        # Keep absence checks separate from the preceding
                        # evidence workload's per-minute reasoning budget.
                        # A rate-limit error is not a factual abstention.
                        await asyncio.sleep(args.unknown_cooldown_seconds)
                        for index, question in enumerate(
                            [
                                "What is Lena Frost's private signing key?",
                                "What is Northstar Workshop's staging deployment region?",
                                "What deployment region is recorded for MCP audit 9d95fa9ad5?",
                                "What is Oriole Studio's annual revenue?",
                                "How old is Nora Slate?",
                                "What is Copper Finch's backup retention period?",
                                "Which region hosts Silver Quill's development environment?",
                                "Does Mira Kestrel report to Vale Rios?",
                            ]
                        ):
                            error, data = await call(
                                "hebbrix_ask",
                                question=question,
                                collection_id=tenant["collection_id"],
                            )
                            check(
                                f"unknown_{index}_abstains",
                                not error
                                and not data.get("citations")
                                and data.get("abstain_recommended") is True,
                                is_error=error,
                                evidence_count=len(data.get("citations") or []),
                                failure_category=data.get("failure_category"),
                                diagnostics=data.get("diagnostics"),
                            )
                            await asyncio.sleep(args.pace_seconds)
                        if args.require_graph:
                            for _ in range(4):
                                error, graph = await call(
                                    "hebbrix_graph_status",
                                    memory_id=identities[2],
                                    wait_seconds=30,
                                )
                                if error or graph.get("ready") or graph.get("terminal"):
                                    break
                            gc = graph.get("graph_check") or {}
                            check(
                                "graph_status_honest",
                                not error
                                and graph.get("status") == "ready"
                                and gc.get("entity_relationship_count") is None
                                and "related_memory_count" in gc
                                and "relationship_count" not in gc,
                            )
                            error, graph = await call(
                                "hebbrix_graph_query",
                                entity="Lena Frost",
                                collection_id=tenant["collection_id"],
                            )
                            check(
                                "graph_edges_extracted",
                                not error
                                and "cedar labs" in json.dumps(graph).casefold(),
                            )
            async with connect(args, tenants[1]) as (_, call):
                error, _ = await call("hebbrix_get", memory_id=identities[0])
                check("foreign_memory_rejected", error)
                error, _ = await call(
                    "hebbrix_search",
                    query=questions[0][0],
                    collection_id=tenant["collection_id"],
                )
                check("foreign_collection_rejected", error)
        except Exception as exc:
            check("runtime", False, error_type=type(exc).__name__)
        finally:
            for index, tenant in enumerate(tenants):
                path = api_root + "/v1/collections/" + tenant["collection_id"]
                headers = {"Authorization": "Bearer " + tenant["api_key"]}
                try:
                    response = await api.delete(path, headers=headers)
                    check(
                        f"cleanup_{index}_first_attempt",
                        response.status_code == 204,
                        http_status=response.status_code,
                    )
                    for _ in range(2):
                        if response.status_code in (204, 404):
                            break
                        await asyncio.sleep(1)
                        response = await api.delete(path, headers=headers)
                    response = await api.get(path, headers=headers)
                    check(f"cleanup_{index}_inaccessible", response.status_code == 404)
                except Exception as exc:
                    check(f"cleanup_{index}", False, error_type=type(exc).__name__)
    print(json.dumps({"passed": sum(checks), "total": len(checks)}), flush=True)
    return 0 if checks and all(checks) else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api", default="http://localhost:8000")
    parser.add_argument(
        "--mcp", help="Optional hosted MCP URL; defaults to local stdio"
    )
    parser.add_argument("--version", default="0.5.11")
    parser.add_argument("--settle-seconds", type=float, default=30)
    parser.add_argument("--pace-seconds", type=float, default=2.1)
    parser.add_argument("--unknown-cooldown-seconds", type=float, default=61)
    parser.add_argument("--require-graph", action="store_true")
    parser.add_argument("--allow-remote", action="store_true")
    args = parser.parse_args()
    if (
        any(
            urlparse(url).hostname not in ("localhost", "127.0.0.1", "::1")
            for url in (args.api, args.mcp)
            if url
        )
        and not args.allow_remote
    ):
        parser.error("Remote disposable writes require --allow-remote")
    sys.exit(asyncio.run(main(args)))
