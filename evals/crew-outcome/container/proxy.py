#!/usr/bin/env python3
"""Allowlisting CONNECT proxy for the L-0728 outcome eval arms.

Usage: proxy.py <allowlist-file> <log-file> <bind-address> [port]

It runs on the HOST, bound to the arm network's gateway address only (the arm
network is `--internal`: containers have no route out but can reach that
address). A host process needs no container egress, which this host
(net.ipv4.ip_forward = 0) does not give.

Only `CONNECT host:443` to an allowlisted host is tunnelled. Plain HTTP and any
other CONNECT is answered 403. Every decision is appended to <log-file> as one
JSON line, so the grader can see which hosts an arm tried to reach.
"""

import asyncio
import json
import sys
import time


def load_allowlist(path):
    hosts = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.split("#", 1)[0].strip().lower()
            if line:
                hosts.append(line)
    return hosts


def allowed(host, hosts):
    host = host.lower().rstrip(".")
    return any(host == h or (h.startswith(".") and host.endswith(h)) for h in hosts)


async def pipe(reader, writer):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionError, OSError):
        pass
    finally:
        try:
            writer.close()
        except OSError:
            pass


def make_handler(hosts, log_path):
    def log(**fields):
        fields["time"] = time.time()
        with open(log_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(fields) + "\n")

    async def handle(reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 30)
        except (asyncio.TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            writer.close()
            return
        first = head.split(b"\r\n", 1)[0].decode("latin-1")
        parts = first.split()
        if len(parts) != 3 or parts[0] != "CONNECT":
            log(request=first[:200], decision="deny", reason="not CONNECT")
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        host, _, port = parts[1].rpartition(":")
        if port != "443" or not allowed(host, hosts):
            log(host=host, port=port, decision="deny")
            writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        try:
            up_reader, up_writer = await asyncio.wait_for(asyncio.open_connection(host, 443), 20)
        except (OSError, asyncio.TimeoutError) as exc:
            log(host=host, port=port, decision="error", error=type(exc).__name__)
            writer.write(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            await writer.drain()
            writer.close()
            return
        log(host=host, port=port, decision="allow")
        writer.write(b"HTTP/1.1 200 Connection established\r\n\r\n")
        await writer.drain()
        await asyncio.gather(pipe(reader, up_writer), pipe(up_reader, writer))

    return handle


async def main(argv):
    hosts = load_allowlist(argv[1])
    port = int(argv[4]) if len(argv) > 4 else 3128
    server = await asyncio.start_server(make_handler(hosts, argv[2]), argv[3], port)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main(sys.argv))
