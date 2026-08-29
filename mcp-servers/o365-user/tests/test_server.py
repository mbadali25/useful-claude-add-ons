from __future__ import annotations

import mcp_o365_user.server as server


def test_whoami_calls_me(monkeypatch, fake_client):
    fake_client.get_result = {"displayName": "Test User", "userPrincipalName": "test@example.com"}
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_whoami()

    assert result["displayName"] == "Test User"
    assert fake_client.get_calls[0][0] == "me"


def test_list_messages_defaults_to_inbox(monkeypatch, fake_client):
    fake_client.get_all_result = [{"id": "m1"}]
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_list_messages()

    assert result == {"count": 1, "items": [{"id": "m1"}]}
    path, _, _ = fake_client.get_all_calls[0]
    assert path == "me/mailFolders/inbox/messages"


def test_list_messages_honors_folder_arg(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_user_list_messages(folder="sentitems")

    path, _, _ = fake_client.get_all_calls[0]
    assert path == "me/mailFolders/sentitems/messages"


def test_search_messages_wraps_query_in_search_param(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_user_search_messages("invoice")

    _, params, _ = fake_client.get_all_calls[0]
    assert params["$search"] == '"invoice"'


def test_list_calendar_events_passes_range(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_user_list_calendar_events("2026-01-01T00:00:00", "2026-01-02T00:00:00")

    path, params, _ = fake_client.get_all_calls[0]
    assert path == "me/calendarView"
    assert params["startDateTime"] == "2026-01-01T00:00:00"
    assert params["endDateTime"] == "2026-01-02T00:00:00"


def test_list_files_root_path(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_user_list_files()

    path, _, _ = fake_client.get_all_calls[0]
    assert path == "me/drive/root/children"


def test_list_files_subfolder_path(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_user_list_files(path="Documents/Reports")

    path, _, _ = fake_client.get_all_calls[0]
    assert path == "me/drive/root:/Documents/Reports:/children"


def test_send_mail_dry_run_without_confirm(monkeypatch, fake_client):
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_send_mail("a@example.com", "Hi", "body text")

    assert result["wouldExecute"] is False
    assert fake_client.post_calls == []


def test_send_mail_blocked_without_env_flag(monkeypatch, fake_client):
    monkeypatch.delenv(server.ALLOW_WRITES_ENV, raising=False)
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_send_mail("a@example.com", "Hi", "body text", confirm=True)

    assert result["blocked"] is True
    assert fake_client.post_calls == []


def test_send_mail_executes_with_multiple_recipients(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_send_mail("a@example.com, b@example.com", "Hi", "body text", confirm=True)

    assert result["executed"] is True
    path, body = fake_client.post_calls[0]
    assert path == "me/sendMail"
    to_addrs = [r["emailAddress"]["address"] for r in body["message"]["toRecipients"]]
    assert to_addrs == ["a@example.com", "b@example.com"]


def test_create_calendar_event_executes(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_create_calendar_event(
        "Standup", "2026-01-01T09:00:00", "2026-01-01T09:30:00", attendees="a@example.com", confirm=True
    )

    assert result["executed"] is True
    path, body = fake_client.post_calls[0]
    assert path == "me/events"
    assert body["subject"] == "Standup"
    assert body["attendees"][0]["emailAddress"]["address"] == "a@example.com"


def test_create_calendar_event_allows_no_attendees(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    server.o365_user_create_calendar_event(
        "Focus block", "2026-01-01T09:00:00", "2026-01-01T09:30:00", confirm=True
    )

    _, body = fake_client.post_calls[0]
    assert body["attendees"] == []


def test_delete_message_executes(monkeypatch, fake_client):
    monkeypatch.setenv(server.ALLOW_WRITES_ENV, "1")
    monkeypatch.setattr(server, "get_client", lambda: fake_client)

    result = server.o365_user_delete_message("m1", confirm=True)

    assert result["executed"] is True
    assert fake_client.delete_calls == ["me/messages/m1"]
