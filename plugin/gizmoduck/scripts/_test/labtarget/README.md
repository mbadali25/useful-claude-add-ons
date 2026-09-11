# labtarget - local scan target

A small, self-contained, **intentionally vulnerable** web app used only to
capture real scanner output (sqlmap, Nikto, ZAP, Nuclei, Nmap, ...) so the
gizmoduck parsers can be built and tested against genuine tool output instead
of hand-built fixtures.

**It must never be bound to anything but 127.0.0.1.** It is a test harness,
not shipped functionality - it is not referenced from any plugin manifest or
packaging step, and it must stay that way.

## Start / stop

```
python server.py [--port 8899]
```

- Binds to `127.0.0.1:8899` by default (the host is hard-coded in
  `server.py` and is not configurable from the CLI - only the port is).
- Prints a startup banner confirming it is intentionally vulnerable and
  loopback-only.
- Creates a throwaway SQLite database in a temp file (`labtarget_*.sqlite3`
  under the OS temp dir) on startup.
- Stop with **Ctrl+C in the same foreground terminal** - this is the
  reliable path: Python catches it as `KeyboardInterrupt` and deletes the
  temp SQLite file before exiting. `server.py` also installs a `SIGTERM`
  handler for the same cleanup on Unix.
  On Windows, a *forced* stop of a backgrounded/non-console process (Task
  Manager "End task", `taskkill /F`, or a background job killed from a
  different shell) bypasses Python's signal handling entirely - Windows has
  no message loop to deliver a graceful close to a plain console app in
  that state, so no handler runs and the temp `labtarget_*.sqlite3` file is
  left behind. That leftover file holds only fixture data (never anything
  real) and is safe to delete by hand, or will disappear with the OS's
  normal temp-directory cleanup. Prefer running it in the foreground and
  stopping with Ctrl+C.

## Endpoints

| Path | Purpose |
|---|---|
| `/` | Index page with links, for crawler/spider targets (ZAP baseline scan). |
| `/about`, `/contact` | Plain crawlable HTML pages, linked from `/`. |
| `/item?id=1` | **SQL-injectable** endpoint - the `id` value is interpolated directly into a SQLite query with no parameterization, in a numeric context. This is the sqlmap target. DB errors are echoed into the response body on purpose, to support error-based detection. |
| `/admin/` | Unauthenticated fake admin login form - an obvious finding for Nikto/dirbusting-style checks. |
| `/files/` | Directory listing of `static/` (no index file) - Nikto's directory-indexing check. |
| `/robots.txt` | Present, disallows `/admin/` (which is otherwise reachable) - a common passive-scan signal. |

No response anywhere sets `Content-Security-Policy`, `X-Frame-Options`,
`X-Content-Type-Options`, or similar security headers - that omission is
deliberate so Nuclei/ZAP passive checks have something to report. The
`Server` header is also deliberately spoofed to an old, vulnerable-looking
Apache/mod_ssl/OpenSSL string.

## Safety

- Hard-coded to `127.0.0.1` in `server.py` - do not add a `--host` flag or
  change the bind address.
- Backing store is a SQLite file in the OS temp directory, created fresh on
  each start and deleted on exit (normal exit, Ctrl+C, or SIGTERM). No
  persistent data, no real credentials, nothing sensitive.
- This directory is a test fixture. It is not part of any package build,
  plugin manifest, or install path, and must never be added to one.
- Never point a scanner at this app from anywhere other than the machine
  it's running on, and never expose the port beyond loopback (no SSH
  tunnels, no port-forwarding, no reverse proxy).
