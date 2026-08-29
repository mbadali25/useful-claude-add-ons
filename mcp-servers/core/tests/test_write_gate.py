from __future__ import annotations

from mcp_ms_core.write_gate import gate, writes_enabled

ENV_FLAG = "MCP_TEST_ALLOW_WRITES"


def test_writes_enabled_recognizes_truthy_values(monkeypatch):
    for value in ("1", "true", "True", "yes", "YES"):
        monkeypatch.setenv(ENV_FLAG, value)
        assert writes_enabled(ENV_FLAG) is True


def test_writes_enabled_false_when_unset(monkeypatch):
    monkeypatch.delenv(ENV_FLAG, raising=False)
    assert writes_enabled(ENV_FLAG) is False


def test_writes_enabled_false_for_garbage_value(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "0")
    assert writes_enabled(ENV_FLAG) is False


def test_gate_blocks_without_confirm_regardless_of_env(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    result = gate(ENV_FLAG, confirm=False, action="wipe", targets=["device-1"])
    assert result is not None
    assert result["wouldExecute"] is False
    assert "blocked" not in result
    assert result["affectedCount"] == 1


def test_gate_blocks_with_confirm_but_flag_unset(monkeypatch):
    monkeypatch.delenv(ENV_FLAG, raising=False)
    result = gate(ENV_FLAG, confirm=True, action="wipe", targets=["device-1"])
    assert result is not None
    assert result["blocked"] is True
    assert ENV_FLAG in result["note"]


def test_gate_allows_when_both_confirm_and_flag_set(monkeypatch):
    monkeypatch.setenv(ENV_FLAG, "1")
    result = gate(ENV_FLAG, confirm=True, action="wipe", targets=["device-1"])
    assert result is None
