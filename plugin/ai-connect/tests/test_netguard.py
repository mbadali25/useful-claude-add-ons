"""The network guard itself: it refuses and reports what leaves this machine, here and in a child Python."""
import asyncio
import socket
import subprocess
import sys

import pytest

import netguard

OUTSIDE = "192.0.2.1"  # TEST-NET-1: never routed, and the guard refuses before a packet is made


def test_a_non_loopback_connect_is_refused_and_reported():
    with pytest.raises(OSError, match="test network guard"):
        socket.create_connection((OUTSIDE, 9), timeout=1)
    assert f"connect {OUTSIDE}:9" in netguard.take()


def test_an_asyncio_connect_is_refused_and_reported():
    """Its own case: on Windows asyncio connects through ConnectEx, past socket.connect."""
    async def dial():
        await asyncio.wait_for(asyncio.open_connection(OUTSIDE, 9), 5)

    with pytest.raises(OSError, match="test network guard"):
        asyncio.run(dial())
    assert f"connect {OUTSIDE}:9" in netguard.take()


def test_a_name_lookup_and_a_wildcard_bind_are_refused_and_reported():
    with pytest.raises(OSError, match="test network guard"):
        socket.getaddrinfo("bridge.example.com", 9999)
    with socket.socket() as sock, pytest.raises(OSError, match="test network guard"):
        sock.bind(("0.0.0.0", 0))
    assert netguard.take().splitlines() == ["lookup bridge.example.com", "bind 0.0.0.0:0"]


def test_a_python_the_test_starts_is_guarded_too(box):
    """deploy and every fake tool run as child processes: the guard reaches them through the Box's environment."""
    dial = f"import socket; socket.create_connection(({OUTSIDE!r}, 9), timeout=1)"
    res = subprocess.run([sys.executable, "-c", dial], env=box.env, capture_output=True, text=True, check=False,
                         stdin=subprocess.DEVNULL, timeout=60)
    assert res.returncode != 0 and "test network guard" in res.stderr
    assert f"connect {OUTSIDE}:9" in netguard.take()


def test_loopback_is_left_alone():
    with socket.socket() as server:
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        socket.create_connection(server.getsockname(), timeout=5).close()
    assert socket.getaddrinfo("localhost", 80) and netguard.take() == ""
