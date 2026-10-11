# pylint: disable=global-statement,line-too-long,logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""MCP tools of AI-Connect, shared by the STDIO client and the HTTP/SSE server."""

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from bridge_client import get_client  # pylint: disable=import-error
from bridge_time import parse_bridge_timestamp
from peer_name import record_seen, session_pid
from untrusted import frame_message, sanitize  # pylint: disable=import-error

log = logging.getLogger(__name__)

# The session's project: the working directory this MCP server started in
# (for Claude Code, the session's project), unless AI_CONNECT_PROJECT_DIR or
# client.project_dir names one
START_CWD = os.getcwd()
_configured_project_dir = ""
# Largest file peer_send / peer_context share, unless AI_CONNECT_MAX_FILE_BYTES says otherwise
DEFAULT_MAX_FILE_BYTES = 256 * 1024

NOT_CONNECTED = "❌ Not connected to the Bridge Server (peer_status shows why)."


def _format_time(moment: datetime) -> str:
    """Local HH:MM:SS.mmm — milliseconds keep the order of quick exchanges clear."""
    return moment.astimezone().strftime("%H:%M:%S.%f")[:-3]


def _format_bridge_time(timestamp: str) -> str:
    """A Bridge timestamp (UTC, ISO) in local time."""
    return _format_time(parse_bridge_timestamp(timestamp))


class FileRefused(ValueError):
    """A file that may not leave this machine through a peer message."""


def set_project_dir(project_dir: str) -> None:
    """client.project_dir from the config; AI_CONNECT_PROJECT_DIR still wins."""
    global _configured_project_dir
    _configured_project_dir = project_dir
    if project_dir:
        log.info(f"File sharing confined to client.project_dir {Path(project_dir).expanduser().resolve()}")


def project_root() -> Path:
    """The only directory files may be shared from, symlinks resolved."""
    chosen = os.environ.get("AI_CONNECT_PROJECT_DIR") or _configured_project_dir or START_CWD
    return Path(chosen).expanduser().resolve()


def max_file_bytes() -> int:
    return int(os.environ.get("AI_CONNECT_MAX_FILE_BYTES") or DEFAULT_MAX_FILE_BYTES)


def _refuse(file: str, reason: str) -> FileRefused:
    log.warning("peer file share refused: %s (requested %r)", reason, file)
    return FileRefused(reason)


def _shareable_path(file: str) -> Path:
    """The real path of file if it may be shared, else FileRefused.

    Relative paths resolve against the project; the result, with every
    symlink followed, must lie inside it and be a regular file within the
    size cap.
    """
    root = project_root()
    path = Path(file).expanduser()
    if not path.is_absolute():
        path = root / path
    try:
        real = path.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        raise _refuse(file, f"not found ({e.__class__.__name__})") from None
    if not real.is_relative_to(root):
        raise _refuse(file, f"outside the project {root}")
    if not real.is_file():
        raise _refuse(file, "not a regular file")
    size, cap = real.stat().st_size, max_file_bytes()
    if size > cap:
        raise _refuse(file, f"too large ({size} bytes, limit {cap})")
    return real


def _read_excerpt(file: str, lines: str | None) -> str:
    """Read a file inside the project, or the line range "start-end" / "line" of it."""
    text = _shareable_path(file).read_text(encoding="utf-8")
    if not lines:
        return text
    start_text, _, end_text = lines.partition("-")
    start = int(start_text)
    end = int(end_text) if end_text else start
    return "\n".join(text.splitlines()[start - 1:end])


def _build_context(file: str | None, lines: str | None) -> dict | None:
    """Context that travels with a message: path, line range and the text itself."""
    if not file:
        return None
    context = {"file": file, "excerpt": _read_excerpt(file, lines)}
    if lines:
        context["lines"] = lines
    return context


def _format_messages(messages: list[dict], me: str) -> str:
    """Render received messages, each framed as untrusted peer data."""
    rendered = []
    for msg in messages:
        sender = sanitize(msg["from"], single_line=True)
        rendered.append(f"📥 [{_format_bridge_time(msg['timestamp'])}] [{sender} → {me}]:")
        rendered.append(frame_message(msg["from"], msg["content"], msg.get("context")))
    return "\n".join(rendered)


async def peer_list() -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    peers = await client.list_peers()
    lines = ["Online peers:"]
    for peer in peers:
        # Name, state detail and status are set by the peer: one line each, escaped
        line = f"  - {sanitize(peer['name'], True)} [{sanitize(peer['ip'], True)}]"
        if peer["state"]:
            line += f" {sanitize(peer['state'], True)} since {_format_bridge_time(peer['state_since'])}"
            if peer["state_detail"]:
                line += f" ({sanitize(peer['state_detail'], True)})"
        if peer["status"]:
            line += f" - {sanitize(peer['status'], True)}"
        lines.append(line)
    return "\n".join(lines)


async def peer_set_state(state: str, detail: str) -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    if not await client.set_state(state, detail):
        return "❌ Connection to the Bridge lost."
    return f"State: {state}" + (f" ({detail})" if detail else "")


async def peer_set_status(status: str) -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    if not await client.set_status(status):
        return "❌ Connection to the Bridge lost."
    return f"Status: {status}" if status else "Status cleared"


async def peer_notify_when_idle(peer: str) -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    if not await client.notify_when_idle(peer):
        return "❌ Connection to the Bridge lost."
    return f"The Bridge will send you a message once {peer} is done or waits for approval."


async def peer_send(to: str, message: str, file: str | None, lines: str | None) -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    try:
        context = _build_context(file, lines)
    except (OSError, ValueError) as e:
        return f"❌ Cannot read {file}: {e}"
    if not await client.send_message(to, message, context):
        return "❌ Sending failed, connection to the Bridge lost."
    attached = f" (+ {file}{' lines ' + lines if lines else ''})" if file else ""
    return f"📤 [{_format_time(datetime.now(timezone.utc))}] [{client.peer_name} → {to}]: {message}{attached}"


async def peer_read() -> str:
    client = get_client()
    if client and client.standby:
        return "⏸️ This session is on standby: another one holds its name for now. Try again in a few seconds."
    if not client or not client.connected:
        return NOT_CONNECTED
    messages = client.pop_messages()
    if not messages:
        return "📭 No new messages."
    # The watcher started at the next turn end reports only what came later
    from_bridge = [m["timestamp"] for m in messages if "id" in m]
    if from_bridge:
        record_seen(session_pid(), max(from_bridge))
    return _format_messages(messages, client.peer_name)


async def peer_history(peer: str, limit: int) -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    messages = await client.get_history(peer, limit)
    if not messages:
        return f"No conversation with '{peer}'."
    lines = [f"Conversation with {sanitize(peer, True)}:"]
    for msg in messages:
        direction = "📤" if msg["from"] == client.peer_name else "📥"
        lines.append(f"{direction} [{_format_bridge_time(msg['timestamp'])}] {sanitize(msg['from'], True)}:")
        lines.append(frame_message(msg["from"], msg["content"], msg.get("context")))
    return "\n".join(lines)


async def peer_context(file: str, lines: str | None, message: str | None) -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    try:
        context = _build_context(file, lines)
    except (OSError, ValueError) as e:
        return f"❌ Cannot read {file}: {e}"
    content = message or f"Shared {file}" + (f" (lines {lines})" if lines else "")
    if not await client.send_message("*", content, context):
        return "❌ Sharing failed, connection to the Bridge lost."
    return f"📤 [{_format_time(datetime.now(timezone.utc))}] Shared with all online peers: {file}" + (f" lines {lines}" if lines else "")


async def peer_status() -> str:
    client = get_client()
    if not client:
        return "Client not initialised."
    bridge = f"{client.host}:{client.port}"
    if client.connected:
        return f"✅ Connected as '{client.peer_name}' to the Bridge Server {bridge}"
    if client.token_refused:
        return f"❌ The Bridge Server {bridge} refused the token: check client.token in config.yaml"
    if client.standby:
        return f"⏸️ Standby: another session holds the name '{client.peer_name}' on the Bridge Server {bridge}"
    if client.reconnecting:
        return f"🔄 Reconnecting to the Bridge Server {bridge}..."
    return f"❌ Not connected. Bridge Server: {bridge}"
