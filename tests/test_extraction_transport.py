"""Canonical extraction polling and fail-closed transport parsing."""
import asyncio
import os

import httpx
import pytest

os.environ.setdefault("HEBBRIX_API_KEY", "mem_sk_synthetic")
from hebbrix_mcp import server as S


@pytest.mark.parametrize("url", [None, "/v1/memory-jobs/job-1", "/v1/memories/jobs/job-1"])
def test_polling_uses_canonical_endpoint_without_redirect(monkeypatch, url):
    seen = []
    async def run():
        async def handler(request):
            seen.append(request.url.path)
            if "/memories/jobs/" in request.url.path:
                return httpx.Response(308, headers={"Location": "/v1/memory-jobs/job-1"})
            return httpx.Response(200, json={"status": "completed", "result": {
                "searchable": True, "created_count": 1, "results": [{"id": "memory-1"}],
            }})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monkeypatch.setattr(S, "_client", lambda: client)
            return await S._memory_job_status("job-1", url)
    result = asyncio.run(run())
    assert seen == ["/v1/memory-jobs/job-1"]
    assert result["status"] == "completed"
    assert result["searchable"] is True


@pytest.mark.parametrize("url", ["https://foreign.invalid/v1/memory-jobs/job-1",
                                 "/v1/auth/api-keys", "/v1/memory-jobs/another-job"])
def test_untrusted_poll_urls_cannot_redirect_credentials_or_change_job(monkeypatch, url):
    async def forbidden(*args, **kwargs):
        raise AssertionError("invalid poll URL must not make a request")
    monkeypatch.setattr(S, "_get", forbidden)
    result = asyncio.run(S._memory_job_status("job-1", url))
    assert result["ok"] is False
    assert result["error"]


@pytest.mark.parametrize("method", ["get", "post", "patch", "delete"])
def test_empty_redirect_is_error_not_json_exception_or_success(monkeypatch, method):
    seen = []
    async def run():
        async def handler(request):
            seen.append(request.url.host)
            return httpx.Response(308, headers={"Location": "https://foreign.invalid/secret"})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            monkeypatch.setattr(S, "_client", lambda: client)
            helper = getattr(S, "_" + method)
            return await helper("/synthetic", {}) if method in {"post", "patch"} else await helper("/synthetic")
    result = asyncio.run(run())
    assert len(seen) == 1
    assert result["status"] == 308
    assert result["ok"] is False
    assert result["error"]
    assert "secret" not in str(result)


@pytest.mark.parametrize("body", [b"", b"<html>private gateway content</html>"])
def test_non_json_success_is_structured_payload_free_error(body):
    result = S._json_response(httpx.Response(200, content=body))
    assert result["ok"] is False
    assert "private" not in str(result)
