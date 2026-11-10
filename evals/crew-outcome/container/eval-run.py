#!/usr/bin/env python3
"""Run one command in the eval container, whose only network is a loopback.

The container is started with `--network none`: it has no route to anything,
including the host's own services. The allowlisting proxy is a host process
listening on a unix socket in a directory mounted at /run/proxy. This wrapper
listens on 127.0.0.1:3128 inside the container, forwards each connection to
that socket, sets HTTPS_PROXY to it, and runs the command it was given.

Usage: eval-run <command> [args...]   (exit status is the command's)
"""

import os
import socket
import subprocess
import sys
import threading

SOCKET_PATH = "/run/proxy/proxy.sock"
HOST, PORT = "127.0.0.1", 3128


def pump(source, sink):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            sink.sendall(data)
    except OSError:
        pass
    finally:
        for end in (source, sink):
            try:
                end.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def forward(client):
    upstream = socket.socket(socket.AF_UNIX)
    try:
        upstream.connect(SOCKET_PATH)
    except OSError:
        client.close()
        upstream.close()
        return
    threading.Thread(target=pump, args=(client, upstream), daemon=True).start()
    pump(upstream, client)


def serve(listener):
    while True:
        client, _addr = listener.accept()
        threading.Thread(target=forward, args=(client,), daemon=True).start()


def main(argv):
    if len(argv) < 2:
        print("usage: eval-run <command> [args...]", file=sys.stderr)
        return 2
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind((HOST, PORT))
    listener.listen(64)
    threading.Thread(target=serve, args=(listener,), daemon=True).start()
    env = dict(os.environ, HTTPS_PROXY=f"http://{HOST}:{PORT}")
    code = subprocess.run(argv[1:], env=env, check=False).returncode
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    sys.exit(main(sys.argv))
