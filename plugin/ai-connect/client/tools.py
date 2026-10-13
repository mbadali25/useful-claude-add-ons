# pylint: disable=global-statement,line-too-long,logging-fstring-interpolation  # upstream AI-Connect style, kept to minimise the fork's diff
"""MCP tools of AI-Connect, shared by the STDIO client and the HTTP/SSE server."""

import logging
import os
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from bridge_client import MessageTooLarge, get_client  # pylint: disable=import-error
from bridge_time import parse_bridge_timestamp
from peer_name import record_seen, session_pid
from untrusted import frame_lines, frame_message, sanitize  # pylint: disable=import-error

log = logging.getLogger(__name__)

# The session's project: the working directory this MCP server started in
# (for Claude Code, the session's project), unless AI_CONNECT_PROJECT_DIR or
# client.project_dir names one
START_CWD = os.getcwd()
_configured_project_dir = ""
# Largest file peer_send / peer_context share, unless AI_CONNECT_MAX_FILE_BYTES says otherwise.
# Below the Bridge's default message limit (64 KiB): a bigger file could never be sent.
# JSON escaping can still push a smaller one over; send_message checks the frame itself
DEFAULT_MAX_FILE_BYTES = 48 * 1024
TOO_LARGE = "❌ Not sent: {error}. Share fewer lines (lines=\"10-80\") or a smaller file."
# The Bridge's HISTORY_MAX_LIMIT (server/websocket_server.py); the client imports nothing from server/
HISTORY_MAX_LIMIT = 1000

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


def _handle_path(fd: int) -> Path:
    """The path an open handle really refers to, every link and junction resolved.

    Asked of the handle, not the name, so a swap after the open cannot change it.
    """
    if sys.platform == "win32":
        import ctypes  # pylint: disable=import-outside-toplevel
        import msvcrt  # pylint: disable=import-outside-toplevel,import-error
        from ctypes import wintypes  # pylint: disable=import-outside-toplevel

        final_path = ctypes.WinDLL("kernel32", use_last_error=True).GetFinalPathNameByHandleW
        final_path.argtypes = [wintypes.HANDLE, wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD]
        final_path.restype = wintypes.DWORD
        handle, size = msvcrt.get_osfhandle(fd), 512
        while True:
            buf = ctypes.create_unicode_buffer(size)
            needed = final_path(handle, buf, size, 0)
            if not needed:
                raise ctypes.WinError(ctypes.get_last_error())
            if needed < size:
                break
            size = needed + 1
        text = buf.value
        if text.startswith("\\\\?\\UNC\\"):
            text = "\\\\" + text[8:]
        elif text.startswith("\\\\?\\"):
            text = text[4:]
        return Path(text)
    if os.path.isdir("/proc/self/fd"):
        return Path(os.readlink(f"/proc/self/fd/{fd}"))
    if sys.platform == "darwin":
        import fcntl  # pylint: disable=import-outside-toplevel,import-error
        raw = fcntl.fcntl(fd, fcntl.F_GETPATH, b"\0" * 1024)
        return Path(raw.split(b"\0", 1)[0].decode())
    raise OSError("this platform cannot tell which file an open handle refers to")


_OPEN_FLAGS = os.O_RDONLY
for _flag in ("O_BINARY", "O_NOINHERIT", "O_CLOEXEC", "O_NOFOLLOW"):
    _OPEN_FLAGS |= getattr(os, _flag, 0)


def _read_shareable(file: str) -> str:
    """The text of file if it may be shared, else FileRefused.

    _shareable_path checks the name; the name can then be swapped for a link
    (the file or any directory above it) or the file can grow. So the checks
    that decide are made again on the open handle: a regular file, its final
    path inside the project, and no more than the cap read from it.
    """
    real = _shareable_path(file)
    root, cap = project_root(), max_file_bytes()
    try:
        fd = os.open(real, _OPEN_FLAGS)
    except OSError as e:
        raise _refuse(file, f"cannot open ({e.__class__.__name__})") from None
    with os.fdopen(fd, "rb") as fh:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise _refuse(file, "not a regular file")
        try:
            final = _handle_path(fd)
        except OSError as e:
            raise _refuse(file, f"cannot verify where it lives ({e.__class__.__name__})") from None
        if not final.is_relative_to(root):
            raise _refuse(file, f"outside the project {root} once opened")
        data = fh.read(cap + 1)
    if len(data) > cap:
        raise _refuse(file, f"too large (over {cap} bytes)")
    # Universal newlines, as read_text gave them
    return data.decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def _read_excerpt(file: str, lines: str | None) -> str:
    """Read a file inside the project, or the line range "start-end" / "line" of it."""
    text = _read_shareable(file)
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


def _safe_bridge_time(timestamp: object) -> str:
    """A Bridge timestamp in local time; one that does not parse is shown escaped."""
    try:
        return _format_bridge_time(timestamp)  # type: ignore[arg-type]
    except (TypeError, ValueError, AttributeError):
        return sanitize(repr(timestamp), single_line=True)


def _message_fields(msg: object) -> tuple[object, object, object, object]:
    """(sender, content, context, timestamp) of a message, whatever its shape."""
    if not isinstance(msg, dict):
        return "?", f"malformed message: {msg!r}", None, None
    return msg.get("from", "?"), msg.get("content", ""), msg.get("context"), msg.get("timestamp")


def _format_messages(messages: list, me: str) -> str:
    """Render received messages, each framed as untrusted peer data."""
    rendered = []
    for msg in messages:
        sender, content, context, timestamp = _message_fields(msg)
        header = f"📥 [{_safe_bridge_time(timestamp)}] [{sender} → {me}]:"
        rendered.append(frame_message(sender, content, context, header))
    return "\n".join(rendered)


async def peer_list() -> str:
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    peers = await client.list_peers()
    if not peers:
        return "Online peers: none"
    # Name, state, state detail and status are set by the peers: every line
    # goes inside one untrusted block, escaped by frame_lines
    return "Online peers:\n" + frame_lines("the Bridge's peer list", [_peer_line(peer) for peer in peers])


def _peer_line(peer: object) -> str:
    if not isinstance(peer, dict):
        return f"- malformed peer entry: {peer!r}"
    line = f"- {peer.get('name', '?')} [{peer.get('ip', '?')}]"
    if peer.get("state"):
        line += f" {peer['state']} since {_safe_bridge_time(peer.get('state_since'))}"
        if peer.get("state_detail"):
            line += f" ({peer['state_detail']})"
    if peer.get("status"):
        line += f" - {peer['status']}"
    return line


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
    try:
        if not await client.send_message(to, message, context):
            return "❌ Sending failed, connection to the Bridge lost."
    except MessageTooLarge as e:
        return TOO_LARGE.format(error=e)
    attached = f" (+ {file}{' lines ' + lines if lines else ''})" if file else ""
    return f"📤 [{_format_time(datetime.now(timezone.utc))}] [{client.peer_name} → {to}]: {message}{attached}"


async def peer_read() -> str:
    client = get_client()
    if client and client.standby:
        return "⏸️ This session is on standby: another one holds its name for now. Try again in a few seconds."
    if not client or not client.connected:
        return NOT_CONNECTED
    # Read without clearing: a message that fails to render stays queued
    messages = client.peek_messages()
    if not messages:
        return "📭 No new messages."
    rendered = _format_messages(messages, client.peer_name)
    # The watcher started at the next turn end reports only what came later
    from_bridge = [m["timestamp"] for m in messages
                   if isinstance(m, dict) and "id" in m and _is_bridge_time(m.get("timestamp"))]
    if from_bridge:
        record_seen(session_pid(), max(from_bridge))
    client.drop_messages(len(messages))
    return rendered


def _is_bridge_time(timestamp: object) -> bool:
    try:
        parse_bridge_timestamp(timestamp)  # type: ignore[arg-type]
    except (TypeError, ValueError, AttributeError):
        return False
    return True


async def peer_history(peer: str, limit: int) -> str:
    # Checked here as well as on the Bridge: the Bridge refuses a bad limit
    # with an error frame, and get_history would wait that out to its timeout
    if isinstance(limit, bool) or not isinstance(limit, int) or not 0 < limit <= HISTORY_MAX_LIMIT:
        return f"❌ limit must be a whole number from 1 to {HISTORY_MAX_LIMIT}, got {limit!r}"
    client = get_client()
    if not client or not client.connected:
        return NOT_CONNECTED
    messages = await client.get_history(peer, limit)
    if not messages:
        return f"No conversation with '{peer}'."
    lines = [f"Conversation with {sanitize(peer, True)}:"]
    for msg in messages:
        sender, content, context, timestamp = _message_fields(msg)
        direction = "📤" if sender == client.peer_name else "📥"
        header = f"{direction} [{_safe_bridge_time(timestamp)}] {sender}:"
        lines.append(frame_message(sender, content, context, header))
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
    try:
        if not await client.send_message("*", content, context):
            return "❌ Sharing failed, connection to the Bridge lost."
    except MessageTooLarge as e:
        return TOO_LARGE.format(error=e)
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
