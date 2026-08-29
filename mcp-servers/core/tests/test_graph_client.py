from __future__ import annotations

import httpx
import pytest

from mcp_ms_core.errors import GraphError
from mcp_ms_core.graph_client import GraphClient


def _client(handler) -> GraphClient:
    transport = httpx.MockTransport(handler)
    return GraphClient(lambda: "fake-token", transport=transport)


def test_get_sends_bearer_token_and_returns_json():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"displayName": "Test User"})

    client = _client(handler)
    result = client.get("me")

    assert seen["auth"] == "Bearer fake-token"
    assert seen["url"] == "https://graph.microsoft.com/v1.0/me"
    assert result == {"displayName": "Test User"}


def test_get_all_follows_next_link():
    pages = [
        {"value": [{"id": "1"}, {"id": "2"}], "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2"},
        {"value": [{"id": "3"}]},
    ]
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        page = pages[calls["n"]]
        calls["n"] += 1
        return httpx.Response(200, json=page)

    client = _client(handler)
    items = client.get_all("users")

    assert [item["id"] for item in items] == ["1", "2", "3"]
    assert calls["n"] == 2


def test_get_all_respects_limit_without_extra_page_fetch():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "value": [{"id": "1"}, {"id": "2"}, {"id": "3"}],
                "@odata.nextLink": "https://graph.microsoft.com/v1.0/users?page=2",
            },
        )

    client = _client(handler)
    items = client.get_all("users", limit=2)

    assert [item["id"] for item in items] == ["1", "2"]


def test_error_response_raises_graph_error_with_nested_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404,
            json={"error": {"code": "Request_ResourceNotFound", "message": "Resource not found."}},
            headers={"request-id": "abc-123"},
        )

    client = _client(handler)
    with pytest.raises(GraphError) as excinfo:
        client.get("users/does-not-exist")

    err = excinfo.value
    assert err.status_code == 404
    assert err.code == "Request_ResourceNotFound"
    assert "Resource not found" in str(err)
    assert "abc-123" in str(err)


def test_401_error_message_points_at_doctor():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"code": "InvalidAuthenticationToken", "message": "Token expired."}})

    client = _client(handler)
    with pytest.raises(GraphError, match="doctor"):
        client.get("me")


def test_429_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr("mcp_ms_core.graph_client.time.sleep", lambda _seconds: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "TooManyRequests", "message": "throttled"}})
        return httpx.Response(200, json={"value": []})

    client = _client(handler)
    result = client.get("me")

    assert calls["n"] == 2
    assert result == {"value": []}


def test_429_exhausts_retries_and_raises(monkeypatch):
    monkeypatch.setattr("mcp_ms_core.graph_client.time.sleep", lambda _seconds: None)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"Retry-After": "0"}, json={"error": {"code": "TooManyRequests", "message": "throttled"}})

    client = _client(handler)
    with pytest.raises(GraphError) as excinfo:
        client.get("me")

    assert excinfo.value.status_code == 429


def test_204_returns_empty_dict():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    client = _client(handler)
    assert client.delete("me/messages/1") == {}


def test_post_sends_json_body():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.content
        return httpx.Response(201, json={"id": "new"})

    client = _client(handler)
    result = client.post("me/sendMail", json_body={"subject": "hi"})

    assert b'"subject":"hi"' in seen["body"] or b'"subject": "hi"' in seen["body"]
    assert result == {"id": "new"}
