"""Test network guard: no socket a test opens may leave this machine.

An audit hook refuses a connect, sendto or bind to anything but loopback and a name lookup
of anything but localhost, and notes each in the file $AI_CONNECT_NETGUARD names; the
conftest fixture fails the test that caused it. Both conftest.py files load it in the pytest
process, and sitecustomize.py beside it (on PYTHONPATH) loads it in every Python a test starts.
Stdlib only, and nothing imported until a socket event needs it: it runs in every fake tool.
"""
import errno
import os
import sys
from pathlib import Path

MARK_ENV = "AI_CONNECT_NETGUARD"
HERE = Path(__file__).resolve().parent
_installed = [False]
_proactor_patched = [False]


def _loopback(host, lookup: bool = False) -> bool:
    """host is this machine. For a lookup any address literal passes too: resolving one asks nobody."""
    import ipaddress  # pylint: disable=import-outside-toplevel
    import socket  # pylint: disable=import-outside-toplevel
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host.lower().rstrip(".") in ("localhost", socket.gethostname().lower()):
        return True
    try:
        return ipaddress.ip_address(host.split("%")[0]).is_loopback or lookup
    except ValueError:
        return False


def _refuse(what: str) -> None:
    mark = os.environ.get(MARK_ENV)
    if mark:
        with open(mark, "a", encoding="utf-8") as fh:
            fh.write(what + "\n")
    raise OSError(errno.ENETUNREACH, f"test network guard: {what} is not loopback")


def _check_address(action: str, sock, address) -> None:
    import socket  # pylint: disable=import-outside-toplevel
    if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple) and address \
            and not _loopback(address[0]):
        _refuse(f"{action} {address[0]}:{address[1] if len(address) > 1 else ''}")


def _patch_proactor() -> None:
    """Windows: asyncio's proactor connects through ConnectEx, which raises no audit event."""
    events = sys.modules.get("asyncio.windows_events")
    if events is None or _proactor_patched[0]:
        return
    _proactor_patched[0] = True
    connect = events.IocpProactor.connect

    def guarded(self, conn, address):
        _check_address("connect", conn, address)
        return connect(self, conn, address)

    events.IocpProactor.connect = guarded


def _hook(event: str, args: tuple) -> None:
    if not event.startswith("socket."):
        return
    if event == "socket.__new__":
        _patch_proactor()
    elif event in ("socket.connect", "socket.sendto", "socket.bind"):
        _check_address(event[len("socket."):], args[0], args[1])
    elif event in ("socket.getaddrinfo", "socket.gethostbyname"):
        if args[0] is not None and not _loopback(args[0], lookup=True):
            name = args[0].decode("ascii", "replace") if isinstance(args[0], bytes) else args[0]
            _refuse(f"lookup {name}")


def install() -> None:
    if not _installed[0]:
        _installed[0] = True
        sys.addaudithook(_hook)


def guard(mark: Path) -> None:
    """Guard this process and, through the environment, every Python it starts."""
    os.environ[MARK_ENV] = str(mark)
    inherited = os.environ.get("PYTHONPATH")
    if str(HERE) not in (inherited or "").split(os.pathsep):
        os.environ["PYTHONPATH"] = os.pathsep.join([str(HERE)] + ([inherited] if inherited else []))
    install()


def take() -> str:
    """What was refused since the last call, one line each; the note is cleared."""
    mark = os.environ.get(MARK_ENV)
    if not mark or not os.path.exists(mark):
        return ""
    with open(mark, encoding="utf-8") as fh:
        opened = fh.read()
    os.unlink(mark)
    return opened
