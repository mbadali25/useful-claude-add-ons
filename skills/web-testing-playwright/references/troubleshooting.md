# Troubleshooting

Read the Playwright error text before changing anything — it's unusually informative. A
locator timeout tells you whether zero elements or several matched, and that distinction
points at two completely different fixes.

## Contents
- [Install and launch](#install-and-launch)
- [Locator problems](#locator-problems)
- [Timeouts](#timeouts)
- [Works headed, fails headless](#works-headed-fails-headless)
- [Local development servers](#local-development-servers)
- [Flakiness](#flakiness)
- [Screenshot problems](#screenshot-problems)
- [Auth problems](#auth-problems)
- [Diagnostic escalation](#diagnostic-escalation)

## Install and launch

| Error | Cause | Fix |
|---|---|---|
| `Executable doesn't exist at .../chrome-linux/chrome` | Package installed, browser binaries not downloaded — or the package was upgraded and now wants a different browser revision | `playwright install chromium`. After any Playwright version bump, re-run it. |
| `error while loading shared libraries: libnss3.so` | Linux system libraries missing | `sudo playwright install-deps chromium` |
| `externally-managed-environment` | PEP 668 on Debian/Ubuntu/Fedora | Use a venv, `--user`, or `--break-system-packages` — see setup-linux.md |
| `'playwright' is not recognized` (Windows) | PATH not refreshed since install | New terminal, or `refreshenv`; use `python -m playwright` rather than the bare command |
| Browser download hangs or TLS-errors | Corporate proxy | Set `HTTPS_PROXY`, or fall back to `channel="msedge"` — see setup-windows.md |
| `Target page, context or browser has been closed` | Using `page` after its context closed, or the `with sync_playwright()` block exited | Keep all page work inside the block |
| Chromium crashes on heavy pages in Docker | 64 MB default `/dev/shm` | `docker run --shm-size=1g` |
| Works on your machine, fails on Alpine | musl isn't supported | Use the official Playwright image or a glibc distro |

## Locator problems

**`strict mode violation: locator resolved to 3 elements`** — Playwright refuses ambiguous
locators on purpose, because silently acting on the first match is how tests end up
asserting the wrong thing. Narrow it rather than reaching for `.first`:

```python
page.get_by_role("button", name="Delete")                      # ambiguous
page.get_by_role("row", name="Invoice 42").get_by_role("button", name="Delete")  # scoped
page.get_by_role("button", name="Save", exact=True)            # exact match
```

`.first` is fine when the duplication is genuinely irrelevant, but check that it is — the
duplication is sometimes itself the bug (a component rendered twice).

**Resolved to 0 elements.** Work through these in order:

1. Is it in an iframe? `page.frame_locator("iframe[...]")`. This is the most common cause
   for payment and embedded widgets.
2. Is it rendered yet? Add `expect(...).to_be_visible()` on a parent, or wait for the API
   response that populates it.
3. Is the accessible name what you think? Run `scripts/inspect_forms.py`, or
   `print(page.accessibility.snapshot())`, or `print(page.content())` and grep.
4. Is it behind a cookie banner or modal? Dismiss it first — a modal overlay also causes
   click timeouts on elements that are visible but covered.
5. Is the text split across elements? `get_by_text("Hello world")` fails when the DOM is
   `<span>Hello</span> <span>world</span>`. Use a regex or target the parent.

**`element is not visible` / `element is outside of the viewport`** — Playwright
auto-scrolls, so this usually means zero-size, `display:none`, `visibility:hidden`, or
`opacity:0`, not that you need to scroll. Check with:

```python
print(page.locator("#thing").evaluate("el => getComputedStyle(el).display"))
print(page.locator("#thing").bounding_box())
```

**`element is not stable`** — it's still animating. Wait for the animation to finish, or
disable animations with the `add_style_tag` snippet in recipes.md.

**`element intercepts pointer events`** — something is on top of it. The error names the
intercepting element; usually a cookie banner, a sticky header, or a toast. Dismiss it.
`force=True` bypasses the check but also bypasses a real usability bug, so use it only
after you understand what's covering the element.

## Timeouts

Default is 30s for actions and navigation, 5s for `expect()`. Raising the timeout is
almost never the fix — it just makes you wait longer for the same failure.

| Symptom | Likely cause |
|---|---|
| `page.goto` times out | Server not running, wrong port, firewall, or `networkidle` on a polling app |
| Times out only in CI | Slower machine, cold cache, or a missing service dependency |
| Action times out but the element is clearly there | Covered by an overlay, or inside an iframe |
| Everything times out after a code change | An unhandled dialog (`alert`/`confirm`) is blocking the page — add `page.on("dialog", lambda d: d.accept())` |

Set per-call timeouts where a genuinely slow operation is expected, rather than raising
the global default and losing fast feedback everywhere else.

## Works headed, fails headless

Treat this as a finding, not just an obstacle — CI runs headless, so a headless-only
failure is a real failure. Common causes:

- **Timing.** Headed is slower, which accidentally papers over a missing wait. This is the
  most common cause by far. Find the race; don't add a sleep.
- **Viewport.** Headless defaults to 1280x720. A headed window may be larger, so a
  responsive layout is showing a different breakpoint. Set the viewport explicitly.
- **Fonts.** Server images often lack fonts, changing text metrics and wrapping.
  `sudo apt-get install fonts-liberation fonts-noto-color-emoji`.
- **Bot detection.** Some sites fingerprint headless Chromium. If it's the user's own app
  doing this, that's useful to know; if it's a third party, that's a signal you shouldn't
  be automating it.
- **Media codecs.** The default Chromium build lacks proprietary codecs; use
  `channel="chrome"` if video playback matters.

To compare, run the same script both ways and diff the screenshots:
`--headed` vs default in `audit_page.py`.

## Local development servers

**`net::ERR_CONNECTION_REFUSED` on `localhost` when the server is clearly running.** This
one is genuinely confusing and it happens often. Chromium may resolve `localhost` to
`::1` (IPv6) while the dev server bound only `0.0.0.0` (IPv4), or vice versa. Fix by using
the explicit address on both sides:

```bash
python3 -m http.server 8000 --bind 127.0.0.1
# then target http://127.0.0.1:8000, not http://localhost:8000
```

Node servers: check whether it printed `localhost`, `127.0.0.1`, or `[::]`, and match it.

Other local-server issues:

- **Self-signed HTTPS** → `browser.new_context(ignore_https_errors=True)`. Only for local
  and staging; ignoring cert errors against production hides real problems.
- **Server not started yet** → in the Node runner use the `webServer` config block, which
  starts it and waits for the URL to respond. In a script, poll the URL before proceeding
  rather than sleeping.
- **Docker → host** → `localhost` inside a container is the container. Use
  `host.docker.internal` (Docker Desktop) or `--network host` (Linux).
- **WSL → Windows host** → not the same `localhost` under WSL2; use the host IP from
  `/etc/resolv.conf`, or run the server inside WSL.

## Flakiness

A test that passes 9 times in 10 is giving you information: something in the app has a
real race. Diagnose it rather than adding retries.

Reproduce it deliberately:
```bash
npx playwright test --repeat-each=20 path/to/test.spec.ts
python3 -c "..."   # or just loop the script 20 times
```

Then look for the usual causes:

- A fixed `sleep` that's usually long enough. Replace with a real wait.
- Asserting immediately after an action instead of using `expect()`, which retries.
- Tests sharing state — the same user account, the same record — and racing each other.
  Give each test its own fixture data.
- Time-dependent assertions that break near midnight, at month boundaries, or across
  timezones. Pin `timezone_id` in the context.
- Animations mid-flight when the screenshot fires.
- Real backend flakiness, which is the most valuable finding of all and the one most often
  mislabelled as a "flaky test."

Set `trace: 'on-first-retry'` and read the trace from the failed attempt. That's the
fastest route to the answer.

## Screenshot problems

| Symptom | Fix |
|---|---|
| Blank or white image | Screenshot fired before render — wait for a real element first |
| Images missing | Lazy-loaded below the fold; scroll first or use `full_page=True` |
| `full_page` cuts off | Page uses an internal scroll container, not the document. Screenshot that element instead |
| Fonts differ from expected | Fonts not installed in the environment (see headless section) |
| Diff noise on every run | Animations, timestamps, carousels, ads — hide them with `add_style_tag` |
| Huge file / very tall image | Infinite scroll kept loading; cap the viewport and skip `full_page` |

## Auth problems

- **Redirected to login despite `storage_state`** — the session expired, the app binds the
  session to a fingerprint or IP, or the token lives in sessionStorage (which
  `storage_state` doesn't capture). Re-run `login.py`; if that works and the reuse doesn't,
  it's one of the latter two.
- **Login succeeds manually, fails in automation** — often a hidden CSRF field or a bot
  check. `inspect_forms.py` lists hidden fields; if there's a CSRF token, make sure you're
  submitting the form rather than POSTing directly.
- **`login.py` can't find the fields** — the login form may be inside an iframe (SSO
  providers frequently are), or rendered after load. Pass `--user-selector` and
  `--password-selector` explicitly, and check the SSO provider's origin — if login
  redirects to a different domain, that's an OAuth flow and the field detection is looking
  at the wrong page.
- **Password appears in the URL** — the form uses `method=GET`. That's a genuine security
  bug worth reporting to the user; credentials end up in browser history, server access
  logs, and `Referer` headers.

## Diagnostic escalation

When you're stuck, in increasing order of effort:

```bash
DEBUG=pw:api python3 script.py           # log every Playwright call — find where it hangs
DEBUG=pw:browser python3 script.py       # browser process output — for launch failures
PWDEBUG=1 python3 script.py              # Inspector: step through, timeouts disabled
```

In code:
```python
page.pause()                             # opens the Inspector at this exact point
print(page.content())                    # what the DOM actually is
page.screenshot(path="where-am-i.png")   # what it actually looks like
print(page.url)                          # are you even where you think you are?
```

And the one that solves the most cases: turn on tracing, let it fail, then
`playwright show-trace trace.zip`. Guessing at a failure you can't see is slower than
recording it once.
