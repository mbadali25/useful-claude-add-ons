from __future__ import annotations

import mcp_intune.server as server


def test_list_devices_selects_fields_and_wraps_count(monkeypatch, fake_client):
    fake_client.get_all_result = [{"id": "1"}, {"id": "2"}]
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_list_devices(top=10)

    assert result == {"count": 2, "items": [{"id": "1"}, {"id": "2"}]}
    path, params, limit = fake_client.get_all_calls[0]
    assert path == "deviceManagement/managedDevices"
    assert params["$top"] == 10
    assert "deviceName" in params["$select"]
    assert limit == 10


def test_list_devices_passes_filter_through(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.intune_list_devices(filter="operatingSystem eq 'Windows'")

    _, params, _ = fake_client.get_all_calls[0]
    assert params["$filter"] == "operatingSystem eq 'Windows'"


def test_list_devices_omits_filter_key_when_not_given(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.intune_list_devices()

    _, params, _ = fake_client.get_all_calls[0]
    assert "$filter" not in params


def test_noncompliant_devices_applies_expected_filter(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.intune_list_noncompliant_devices(top=5)

    _, params, limit = fake_client.get_all_calls[0]
    assert params["$filter"] == "complianceState eq 'noncompliant'"
    assert limit == 5


def test_get_device_fetches_single_object(monkeypatch, fake_client):
    fake_client.get_result = {"id": "abc", "deviceName": "LAPTOP-1"}
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_get_device("abc")

    assert result == {"id": "abc", "deviceName": "LAPTOP-1"}
    assert fake_client.get_calls[0][0] == "deviceManagement/managedDevices/abc"


def test_sync_device_dry_run_without_confirm(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_sync_device("device-1")

    assert result["wouldExecute"] is False
    assert fake_client.post_calls == []


def test_sync_device_blocked_when_confirm_but_flag_unset(monkeypatch, fake_client):
    monkeypatch.delenv(server.ALLOW_WRITES_ENV, raising=False)
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_sync_device("device-1", confirm=True)

    assert result["blocked"] is True
    assert fake_client.post_calls == []


def test_sync_device_executes_when_confirmed_and_flag_set(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_sync_device("device-1", confirm=True)

    assert result["executed"] is True
    assert fake_client.post_calls == [("deviceManagement/managedDevices/device-1/syncDevice", None)]


def test_wipe_device_requires_its_own_confirm_and_flag(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_wipe_device("device-9", confirm=True)

    assert result["executed"] is True
    assert fake_client.post_calls == [("deviceManagement/managedDevices/device-9/wipe", None)]


def test_list_compliance_policies_wraps_results(monkeypatch, fake_client):
    fake_client.get_all_result = [{"id": "p1"}]
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_list_compliance_policies()

    assert result == {"count": 1, "items": [{"id": "p1"}]}
    assert fake_client.get_all_calls[0][0] == "deviceManagement/deviceCompliancePolicies"


def test_list_apps_wraps_results(monkeypatch, fake_client):
    fake_client.get_all_result = [{"id": "app1"}]
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.intune_list_apps(top=3)

    assert result == {"count": 1, "items": [{"id": "app1"}]}
    path, params, limit = fake_client.get_all_calls[0]
    assert path == "deviceAppManagement/mobileApps"
    assert params["$top"] == 3
    assert limit == 3
