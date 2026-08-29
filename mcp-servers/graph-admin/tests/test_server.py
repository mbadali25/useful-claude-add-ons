from __future__ import annotations

import mcp_graph_admin.server as server


def test_list_users_selects_fields(monkeypatch, fake_client):
    fake_client.get_all_result = [{"id": "1"}]
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_list_users(top=10)

    assert result == {"count": 1, "items": [{"id": "1"}]}
    path, params, limit = fake_client.get_all_calls[0]
    assert path == "users"
    assert "userPrincipalName" in params["$select"]
    assert limit == 10


def test_list_users_filter_passthrough(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.graph_admin_list_users(filter="accountEnabled eq false")

    _, params, _ = fake_client.get_all_calls[0]
    assert params["$filter"] == "accountEnabled eq false"


def test_get_user_fetches_by_id(monkeypatch, fake_client):
    fake_client.get_result = {"id": "u1"}
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    assert server.graph_admin_get_user("u1") == {"id": "u1"}
    assert fake_client.get_calls[0][0] == "users/u1"


def test_conditional_access_uses_beta_endpoint(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.graph_admin_list_conditional_access_policies()

    path = fake_client.get_all_calls[0][0]
    assert path.startswith("https://graph.microsoft.com/beta/")


def test_add_group_member_dry_run_without_confirm(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_add_group_member("g1", "u1")

    assert result["wouldExecute"] is False
    assert fake_client.post_calls == []


def test_add_group_member_blocked_without_env_flag(monkeypatch, fake_client):
    monkeypatch.delenv(server.ALLOW_WRITES_ENV, raising=False)
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_add_group_member("g1", "u1", confirm=True)

    assert result["blocked"] is True
    assert fake_client.post_calls == []


def test_add_group_member_executes_when_allowed(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_add_group_member("g1", "u1", confirm=True)

    assert result["executed"] is True
    path, body = fake_client.post_calls[0]
    assert path == "groups/g1/members/$ref"
    assert body["@odata.id"].endswith("/directoryObjects/u1")


def test_remove_group_member_executes_via_delete(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_remove_group_member("g1", "u1", confirm=True)

    assert result["executed"] is True
    assert fake_client.delete_calls == ["groups/g1/members/u1/$ref"]


def test_disable_user_patches_account_enabled_false(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_disable_user("u1", confirm=True)

    assert result["executed"] is True
    path, body = fake_client.patch_calls[0]
    assert path == "users/u1"
    assert body == {"accountEnabled": False}


def test_delete_user_blocked_without_confirm(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_delete_user("u1")

    assert result["wouldExecute"] is False
    assert fake_client.delete_calls == []


def test_delete_user_executes_when_confirmed_and_allowed(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.graph_admin_delete_user("u1", confirm=True)

    assert result["executed"] is True
    assert fake_client.delete_calls == ["users/u1"]
