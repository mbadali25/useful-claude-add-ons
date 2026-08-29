from __future__ import annotations

from typing import Any

import pytest


class FakeGraphClient:
    """Records calls and returns canned responses - no network, no msal."""

    def __init__(self) -> None:
        self.get_all_calls: list[tuple[str, dict | None, int | None]] = []
        self.get_calls: list[tuple[str, dict | None]] = []
        self.post_calls: list[tuple[str, Any]] = []
        self.get_all_result: list[dict] = []
        self.get_result: dict = {}
        self.post_result: dict = {}

    def get_all(self, path: str, *, params: dict | None = None, limit: int | None = None) -> list[dict]:
        self.get_all_calls.append((path, params, limit))
        return self.get_all_result

    def get(self, path: str, *, params: dict | None = None) -> dict:
        self.get_calls.append((path, params))
        return self.get_result

    def post(self, path: str, *, json_body: Any = None) -> dict:
        self.post_calls.append((path, json_body))
        return self.post_result


@pytest.fixture
def fake_client() -> FakeGraphClient:
    return FakeGraphClient()
