#!/usr/bin/env python3
"""
labtarget - a deliberately vulnerable, localhost-only web app.

Purpose: give the gizmoduck security-scanning package a real target so its
scanner output parsers (sqlmap, Nikto, ZAP, Nuclei, Nmap, ...) can be built
and tested against actual tool output instead of hand-built fixtures.

THIS APP IS INTENTIONALLY VULNERABLE.
It must NEVER be bound to anything other than 127.0.0.1 (loopback).
It is a test harness only - not shipped functionality, not packaged,
not referenced from any plugin manifest.

Usage:
    python server.py [--port 8899]

The app creates a throwaway SQLite database in a temp file on startup and
deletes it on shutdown (Ctrl+C / SIGTERM / normal exit). No persistent data,
no real credentials, nothing sensitive is stored.
"""

import argparse
import atexit
import os
import signal
import sqlite3
import sys
import tempfile
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlsplit, parse_qs, unquote

HOST = "127.0.0.1"  # hard-coded - never change to "0.0.0.0" or ""
STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

BANNER = r"""
==================================================================
  labtarget - INTENTIONALLY VULNERABLE TEST WEB APP
  ------------------------------------------------------------
  * Bound to 127.0.0.1 ONLY - not reachable from the network.
  * Contains a deliberate SQL injection endpoint (/item?id=).
  * Contains missing security headers, an exposed /admin/ path,
    and a directory listing under /files/ - all on purpose.
  * Backing data lives in a throwaway SQLite temp file that is
    deleted when this process exits.
  * This is a scanner fixture-capture harness for gizmoduck.
    It is never packaged, never shipped, never pointed at anything
    but this local process.
  ==================================================================
"""

_db_path = None
_db_conn = None


def _init_db():
    global _db_path, _db_conn
    fd, _db_path = tempfile.mkstemp(prefix="labtarget_", suffix=".sqlite3")
    os.close(fd)
    _db_conn = sqlite3.connect(_db_path, check_same_thread=False)
    cur = _db_conn.cursor()
    cur.execute(
        """
        CREATE TABLE items (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            price TEXT NOT NULL
        )
        """
    )
    cur.executemany(
        "INSERT INTO items (id, name, description, price) VALUES (?, ?, ?, ?)",
        [
            (1, "Pallet Jack", "Manual pallet jack, salvage lot", "45.00"),
            (2, "Shelving Unit", "Steel shelving, 5 shelves", "120.00"),
            (3, "Forklift Tire", "Solid rubber forklift tire", "80.00"),
            (4, "Extension Cord", "50ft heavy duty cord", "15.00"),
            (5, "Pressure Washer", "Gas pressure washer, 3000psi", "210.00"),
        ],
    )
    # A second table with values an injected UNION query could pull,
    # to give sqlmap something to actually extract (--dump).
    cur.execute(
        """
        CREATE TABLE secrets (
            id INTEGER PRIMARY KEY,
            note TEXT NOT NULL
        )
        """
    )
    cur.executemany(
        "INSERT INTO secrets (id, note) VALUES (?, ?)",
        [(1, "fixture-only value, not a real secret")],
    )
    _db_conn.commit()
    print(f"[labtarget] SQLite temp DB created at {_db_path}")


def _cleanup_db():
    global _db_conn, _db_path
    try:
        if _db_conn is not None:
            _db_conn.close()
    except Exception:
        pass
    if _db_path and os.path.exists(_db_path):
        os.remove(_db_path)
        print(f"[labtarget] SQLite temp DB removed: {_db_path}")


def _page(title, body):
    return f"""<!doctype html>
<html>
<head><title>{title}</title></head>
<body>
<h1>{title}</h1>
{body}
<hr>
<p><a href="/">Home</a> | <a href="/about">About</a> | <a href="/contact">Contact</a> | <a href="/files/">Files</a></p>
</body>
</html>"""


class LabTargetHandler(BaseHTTPRequestHandler):
    # Deliberately reports a stale, vulnerable-looking server banner so
    # Nikto/Nuclei have something obvious to flag - this is one of the
    # "obvious findings" the harness exists to produce.
    server_version = "Apache/2.2.3"
    sys_version = "(Unix) mod_ssl/2.2.3 OpenSSL/0.9.8e-fips-rc1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[labtarget] %s - %s\n" % (self.address_string(), fmt % args))

    # No security headers are ever added here (no CSP, no
    # X-Frame-Options, no X-Content-Type-Options) - that omission is
    # intentional so passive scanners (Nuclei, ZAP) have findings.
    def _send(self, status, content_type, body_bytes):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        self.wfile.write(body_bytes)

    def _send_html(self, status, html):
        self._send(status, "text/html; charset=utf-8", html.encode("utf-8"))

    def do_GET(self):
        parts = urlsplit(self.path)
        path = parts.path
        query = parse_qs(parts.query)

        if path == "/":
            self._index()
        elif path == "/about":
            self._about()
        elif path == "/contact":
            self._contact()
        elif path == "/item":
            self._item(query)
        elif path in ("/admin", "/admin/"):
            self._admin()
        elif path in ("/files", "/files/"):
            self._files_index()
        elif path.startswith("/files/"):
            self._files_serve(path[len("/files/"):])
        elif path == "/robots.txt":
            self._send(200, "text/plain", b"User-agent: *\nDisallow: /admin/\n")
        else:
            self._send_html(404, _page("Not Found", "<p>No such page.</p>"))

    def _index(self):
        body = """
        <p>Welcome to the Salvage Lot Browser (test fixture).</p>
        <ul>
          <li><a href="/item?id=1">Item 1</a></li>
          <li><a href="/item?id=2">Item 2</a></li>
          <li><a href="/item?id=3">Item 3</a></li>
          <li><a href="/about">About this lot</a></li>
          <li><a href="/contact">Contact the seller</a></li>
          <li><a href="/files/">Browse uploaded files</a></li>
        </ul>
        """
        self._send_html(200, _page("Salvage Lot Browser", body))

    def _about(self):
        body = "<p>This is a fixture storefront used only for local scanner testing.</p>"
        self._send_html(200, _page("About", body))

    def _contact(self):
        body = "<p>Contact: not a real address, this is a test fixture.</p>"
        self._send_html(200, _page("Contact", body))

    def _admin(self):
        # An obvious, unauthenticated "admin" surface for Nikto/dirbusting
        # style checks to find and report.
        body = """
        <p>Admin Panel (test fixture - no real auth behind this).</p>
        <form>
          <label>Username: <input name="user"></label><br>
          <label>Password: <input name="pass" type="password"></label><br>
          <input type="submit" value="Login">
        </form>
        """
        self._send_html(200, _page("Admin Panel", body))

    def _files_index(self):
        # Deliberate directory listing for Nikto's directory-indexing check.
        try:
            entries = sorted(os.listdir(STATIC_DIR))
        except FileNotFoundError:
            entries = []
        items = "".join(f'<li><a href="/files/{e}">{e}</a></li>' for e in entries)
        body = f"<h2>Index of /files/</h2><ul>{items}</ul>"
        self._send_html(200, _page("Index of /files/", body))

    def _files_serve(self, name):
        name = unquote(name)
        # No path traversal hardening beyond basename - this is a fixture,
        # not a hardening exercise, but we still stay inside STATIC_DIR
        # so the harness itself can't be used to read the rest of the disk.
        safe_name = os.path.basename(name)
        full = os.path.join(STATIC_DIR, safe_name)
        if not os.path.isfile(full):
            self._send_html(404, _page("Not Found", "<p>No such file.</p>"))
            return
        with open(full, "rb") as f:
            data = f.read()
        self._send(200, "text/plain; charset=utf-8", data)

    def _item(self, query):
        raw_id = query.get("id", ["1"])[0]
        # THE deliberate vulnerability: raw_id is interpolated straight
        # into the SQL text with no parameterization and no quoting,
        # in a numeric context - the classic sqlmap target shape.
        sql = f"SELECT id, name, description, price FROM items WHERE id = {raw_id}"
        rows = []
        error_text = None
        try:
            cur = _db_conn.cursor()
            cur.execute(sql)
            rows = cur.fetchall()
        except sqlite3.Error as exc:
            # Surface the raw DB error in the response body on purpose -
            # this is what makes error-based injection detectable.
            error_text = str(exc)

        body = f"<p><code>Query: {sql}</code></p>"
        if error_text:
            body += f"<p style='color:red'>SQL error: {error_text}</p>"
        elif rows:
            body += "<table border='1'><tr><th>id</th><th>name</th><th>description</th><th>price</th></tr>"
            for r in rows:
                body += "<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>"
            body += "</table>"
        else:
            body += "<p>No items found.</p>"
        self._send_html(200, _page("Item Lookup", body))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8899, help="port to bind on 127.0.0.1 (default: 8899)")
    args = parser.parse_args()

    print(BANNER)
    _init_db()
    atexit.register(_cleanup_db)

    def _handle_sigterm(signum, frame):
        _cleanup_db()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _handle_sigterm)

    server = HTTPServer((HOST, args.port), LabTargetHandler)
    print(f"[labtarget] listening on http://{HOST}:{args.port}/ (Ctrl+C to stop)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        _cleanup_db()


if __name__ == "__main__":
    main()
