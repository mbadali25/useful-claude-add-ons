from __future__ import annotations

import mcp_o365_admin.server as server


def test_list_sharepoint_sites_default_search(monkeypatch, fake_client):
    fake_client.get_all_result = [{"id": "s1"}]
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_list_sharepoint_sites()

    assert result == {"count": 1, "items": [{"id": "s1"}]}
    path, params, _ = fake_client.get_all_calls[0]
    assert path == "sites"
    assert params["search"] == "*"


def test_list_site_drive_items_root(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_admin_list_site_drive_items("site1")

    path, _, _ = fake_client.get_all_calls[0]
    assert path == "sites/site1/drive/root/children"


def test_list_site_drive_items_subfolder(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_admin_list_site_drive_items("site1", path="Shared/Reports")

    path, _, _ = fake_client.get_all_calls[0]
    assert path == "sites/site1/drive/root:/Shared/Reports:/children"


def test_list_teams_filters_on_resource_provisioning(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_admin_list_teams()

    _, params, _ = fake_client.get_all_calls[0]
    assert "resourceProvisioningOptions" in params["$filter"]


def test_search_mailbox_scoped_to_one_user(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_admin_search_mailbox("user1", "invoice")

    path, params, _ = fake_client.get_all_calls[0]
    assert path == "users/user1/messages"
    assert params["$search"] == '"invoice"'


def test_assign_license_dry_run_without_confirm(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_assign_license("user1", "sku1")

    assert result["wouldExecute"] is False
    assert fake_client.post_calls == []


def test_assign_license_blocked_without_env_flag(monkeypatch, fake_client):
    monkeypatch.delenv(server.ALLOW_WRITES_ENV, raising=False)
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_assign_license("user1", "sku1", confirm=True)

    assert result["blocked"] is True
    assert fake_client.post_calls == []


def test_assign_license_executes_when_allowed(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_assign_license("user1", "sku1", confirm=True)

    assert result["executed"] is True
    path, body = fake_client.post_calls[0]
    assert path == "users/user1/assignLicense"
    assert body["addLicenses"] == [{"skuId": "sku1"}]
    assert body["removeLicenses"] == []


def test_remove_license_executes_when_allowed(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_remove_license("user1", "sku1", confirm=True)

    assert result["executed"] is True
    path, body = fake_client.post_calls[0]
    assert path == "users/user1/assignLicense"
    assert body["removeLicenses"] == ["sku1"]


def test_remove_team_member_executes_via_delete(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_remove_team_member("team1", "member1", confirm=True)

    assert result["executed"] is True
    assert fake_client.delete_calls == ["teams/team1/members/member1"]


def test_delete_drive_item_blocked_without_confirm(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_delete_drive_item("site1", "item1")

    assert result["wouldExecute"] is False
    assert fake_client.delete_calls == []


def test_delete_drive_item_executes_when_confirmed_and_allowed(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_admin_delete_drive_item("site1", "item1", confirm=True)

    assert result["executed"] is True
    assert fake_client.delete_calls == ["sites/site1/drive/items/item1"]
