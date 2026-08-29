"""MCP tool definitions for the signed-in user's own mail, calendar, and
OneDrive files. Everything here is scoped to /me - there is no tenant-wide
tool in this server by design; that boundary is what makes this the
user-scope server rather than the admin-scope one. Every tool here is
read-only except the three at the bottom, gated by mcp_ms_core.write_gate.gate.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from mcp_ms_core import gate

from .client import ALLOW_WRITES_ENV, get_client

mcp = FastMCP("mcp-o365-user")


@mcp.tool()
def o365_user_whoami() -> dict:
    """Return the signed-in user's own profile (GET /me) - the quickest way
    to confirm which account this server is authenticated as."""
    return get_client().get("me")


@mcp.tool()
def o365_user_list_messages(folder: str = "inbox", top: int = 25) -> dict:
    """List messages in one of the signed-in user's own mail folders
    (default 'inbox'; also accepts 'sentitems', 'drafts', 'deleteditems',
    or any other well-known folder name)."""
    items = get_client().get_all(
        f"me/mailFolders/{folder}/messages",
        params={"$top": top, "$select": "id,subject,from,receivedDateTime,isRead,bodyPreview"},
        limit=top,
    )
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_user_get_message(message_id: str) -> dict:
    """Get one message by id, full content included."""
    return get_client().get(f"me/messages/{message_id}")


@mcp.tool()
def o365_user_search_messages(query: str, top: int = 25) -> dict:
    """Full-text search across the signed-in user's own mail
    ($search, e.g. "subject:invoice" or a bare keyword)."""
    items = get_client().get_all("me/messages", params={"$search": f'"{query}"', "$top": top}, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_user_list_calendar_events(start: str, end: str, top: int = 25) -> dict:
    """List the signed-in user's own calendar events between ``start`` and
    ``end`` (ISO 8601 date-times, e.g. "2026-08-01T00:00:00")."""
    items = get_client().get_all(
        "me/calendarView",
        params={"startDateTime": start, "endDateTime": end, "$top": top},
        limit=top,
    )
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_user_list_files(path: str = "/", top: int = 50) -> dict:
    """List files/folders in the signed-in user's own OneDrive at ``path``
    (default the drive root)."""
    client = get_client()
    root = "me/drive/root" if path in ("/", "") else f"me/drive/root:/{path.strip('/')}:"
    items = client.get_all(f"{root}/children", params={"$top": top}, limit=top)
    return {"count": len(items), "items": items}


@mcp.tool()
def o365_user_send_mail(to: str, subject: str, body: str, confirm: bool = False) -> dict:
    """Send an email as the signed-in user. ``to`` is a comma-separated list
    of addresses. Dry-run unless confirm=true AND MS_O365_USER_ALLOW_WRITES=1
    is set on the server."""
    recipients = [{"emailAddress": {"address": addr.strip()}} for addr in to.split(",") if addr.strip()]
    target = f"to:{to} subject:{subject!r}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="send_mail", targets=[target])
    if blocked is not None:
        return blocked
    get_client().post(
        "me/sendMail",
        json_body={
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": recipients,
            }
        },
    )
    return {"wouldExecute": True, "executed": True, "action": "send_mail", "target": target}


@mcp.tool()
def o365_user_create_calendar_event(
    subject: str, start: str, end: str, attendees: str = "", confirm: bool = False
) -> dict:
    """Create a calendar event on the signed-in user's own calendar.
    ``attendees`` is a comma-separated list of addresses (may be empty).
    Dry-run unless confirm=true AND MS_O365_USER_ALLOW_WRITES=1 is set on
    the server."""
    attendee_list = [
        {"emailAddress": {"address": addr.strip()}, "type": "required"}
        for addr in attendees.split(",")
        if addr.strip()
    ]
    target = f"subject:{subject!r} start:{start} end:{end}"
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="create_calendar_event", targets=[target])
    if blocked is not None:
        return blocked
    result = get_client().post(
        "me/events",
        json_body={
            "subject": subject,
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"},
            "attendees": attendee_list,
        },
    )
    return {"wouldExecute": True, "executed": True, "action": "create_calendar_event", "event": result}


@mcp.tool()
def o365_user_delete_message(message_id: str, confirm: bool = False) -> dict:
    """Delete one message from the signed-in user's own mailbox
    (moves to Deleted Items; permanent only once that folder is emptied).
    Dry-run unless confirm=true AND MS_O365_USER_ALLOW_WRITES=1 is set on
    the server."""
    blocked = gate(ALLOW_WRITES_ENV, confirm=confirm, action="delete_message", targets=[message_id])
    if blocked is not None:
        return blocked
    get_client().delete(f"me/messages/{message_id}")
    return {"wouldExecute": True, "executed": True, "action": "delete_message", "messageId": message_id}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
