"""A small, paging- and throttling-aware Microsoft Graph HTTP client.

Graph throttles aggressively (429) and buries its real error message inside
the response body as JSON-within-JSON - this wraps both so every server's
tool code just calls ``get``/``post``/``patch``/``delete``/``get_all`` and
either gets data back or a ``GraphError`` with an actionable message.
"""

from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .errors import GraphError

GRAPH_V1 = "https://graph.microsoft.com/v1.0"
GRAPH_BETA = "https://graph.microsoft.com/beta"

_MAX_ATTEMPTS = 4
_RETRY_STATUS = {429, 500, 502, 503, 504}


class GraphClient:
    """Wraps an ``httpx.Client``. Pass a zero-arg ``token_provider`` callable -
    normally ``ClientCredentialAuth.get_token`` or ``DeviceCodeAuth.get_token``
    - so the client always sends a fresh (or silently-refreshed) bearer token
    rather than caching one that can expire mid-session.
    """

    def __init__(
        self,
        token_provider: Callable[[], str],
        *,
        base_url: str = GRAPH_V1,
        timeout: float = 30.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._token_provider = token_provider
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "GraphClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token_provider()}",
            "Accept": "application/json",
        }

    def _url(self, path: str) -> str:
        if path.startswith("https://"):
            return path
        return f"{self._base_url}/{path.lstrip('/')}"

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
    ) -> dict[str, Any]:
        url = self._url(path)
        resp: httpx.Response | None = None
        for attempt in range(_MAX_ATTEMPTS):
            resp = self._client.request(
                method, url, params=params, json=json_body, headers=self._headers()
            )
            if resp.status_code in _RETRY_STATUS and attempt < _MAX_ATTEMPTS - 1:
                delay = _retry_delay(resp, attempt)
                time.sleep(delay)
                continue
            break
        assert resp is not None
        if resp.status_code >= 400:
            raise _to_graph_error(resp)
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()

    def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.request("GET", path, params=params)

    def post(self, path: str, *, json_body: Any = None) -> dict[str, Any]:
        return self.request("POST", path, json_body=json_body)

    def patch(self, path: str, *, json_body: Any = None) -> dict[str, Any]:
        return self.request("PATCH", path, json_body=json_body)

    def delete(self, path: str) -> dict[str, Any]:
        return self.request("DELETE", path)

    def get_all(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Follow ``@odata.nextLink`` until exhausted or ``limit`` items collected.

        For a fleet-wide pull of more than a few hundred records, prefer a
        dedicated export/report endpoint where the API offers one - looping
        this over tens of thousands of objects is slow and throttles hard.
        """
        items: list[dict[str, Any]] = []
        next_path: str | None = path
        next_params: dict[str, Any] | None = params
        while next_path:
            page = self.request("GET", next_path, params=next_params)
            items.extend(page.get("value", []))
            if limit is not None and len(items) >= limit:
                return items[:limit]
            next_path = page.get("@odata.nextLink")
            next_params = None  # nextLink is already a full URL with params baked in
        return items


def _retry_delay(resp: httpx.Response, attempt: int) -> float:
    retry_after = resp.headers.get("Retry-After")
    if retry_after is not None:
        try:
            return min(float(retry_after), 30.0)
        except ValueError:
            pass
    return min(2.0**attempt, 30.0)


def _to_graph_error(resp: httpx.Response) -> GraphError:
    request_id = resp.headers.get("request-id") or resp.headers.get("client-request-id")
    code = "unknown"
    message = resp.text[:300]
    try:
        body = resp.json()
        err = body.get("error", {})
        code = err.get("code", code)
        message = err.get("message", message)
    except ValueError:
        pass
    return GraphError(resp.status_code, code, message, request_id=request_id)
