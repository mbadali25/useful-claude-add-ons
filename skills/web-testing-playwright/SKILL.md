---
name: web-testing-playwright
description: Drive a real browser with Playwright to test and debug websites — load pages, screenshot how they look at different viewports, capture console errors and failed network requests, inspect and fill web forms, log in with credentials, and reproduce UI bugs. Includes environment setup for Windows (winget or Chocolatey) and Linux, so use this whenever Playwright, browser automation, or a browser install is involved. Trigger it whenever the user wants something checked *in a browser* rather than in source code — "is my site up", "does the login flow work", "why is this page blank", "check the form validation", "the layout breaks on mobile", "take a screenshot of", "click through the checkout", "test the signup page", "there is a JS error somewhere", "walk through the site as a user", or any request to verify, exercise, or debug a live or locally-running web app. Prefer this over reading source code when the question is about actual runtime behavior.
---

# Web Testing & Debugging with Playwright

Answer questions about a website by *observing the real thing* in a real browser. Source
code tells you what should happen; a Playwright run tells you what does. When someone
reports a bug, reproduce it and bring back evidence — a screenshot, a console error, a
failing request — not a theory.

## Ground rules before touching a site

**Authorization.** Only exercise sites the user owns, operates, or is clearly authorized
to test — their own app, their staging environment, `localhost`. If they point at a
third-party site and want you to log in, brute-force, scrape at volume, or bypass a
CAPTCHA or bot check, stop and ask what their relationship to that site is. Read-only
navigation of a public page is fine; credential and load-generating activity is not,
absent authorization.

**Credentials.** Never inline a password into a script, a log line, or a filename. Read
them from environment variables and reference the variable name in code. Before showing
a script back to the user, scan it for anything that looks like a secret. Screenshots of
a filled login form can capture a password in a visible field or an autofilled value —
mask the field or screenshot after navigation. If the user pastes a credential into chat,
use it, but write it into the script as `os.environ["APP_PASSWORD"]` and tell them which
variable to set.

## Step 0 — Check the environment, then ask before installing

Always start here. Do not assume Playwright is present or that a previous session's
install persisted.

```bash
python3 scripts/check_env.py          # add --json for machine-readable output
```

It reports OS, Python/Node versions, whether the Playwright package and browser binaries
are installed, and — on Windows — whether `winget` and `choco` are available. It ends
with the exact commands to run for whatever is missing.

**Installing software needs the user's consent.** Show the specific commands, say roughly
how big the download is (browser binaries are a few hundred MB), note if it needs
administrator/sudo, and wait for a yes. Then follow the matching guide:

- Windows → `references/setup-windows.md` (winget vs. Chocolatey decision, elevation, PATH refresh, proxies)
- Linux / WSL / containers → `references/setup-linux.md` (system libraries, headless servers, Docker)

## Choosing the shape of the work

| Situation | Use |
|---|---|
| "Is this broken?", one-off investigation, reproducing a bug | Python Playwright script, or the bundled scripts below |
| Durable suite the team reruns, CI, retries, HTML report | `@playwright/test` (Node) — `npm init playwright@latest` |
| User already has a test suite | Match whatever it uses; don't introduce a second framework |

Python is the faster path to a first answer and matches the bundled scripts. Node's
`@playwright/test` is the better home for tests that outlive the conversation — it gives
retries, parallelism, an HTML report, and per-test traces for free.

## Bundled scripts

All live in `scripts/`, take `--help`, and write structured JSON alongside human-readable
output. They are starting points — read one before adapting it rather than rewriting from
scratch.

**`check_env.py`** — environment and install readiness (above).

**`audit_page.py URL`** — the default first move for "something's wrong with this page."
Loads the URL, records HTTP status, title, console messages, uncaught page errors, and
failed/slow requests, then screenshots at desktop, tablet, and mobile widths.

```bash
python3 scripts/audit_page.py https://example.com --out ./audit
python3 scripts/audit_page.py http://localhost:3000/dashboard \
    --storage-state ./auth.json --wait-for "[data-testid=chart]"
```

**`inspect_forms.py URL`** — enumerates every form on the page: each field's name, type,
required flag, current value, associated label, and a suggested Playwright locator, plus
the submit controls. Use this before writing form-filling code so the selectors are
grounded in the real DOM instead of guessed.

**`login.py`** — logs in using credentials from environment variables, verifies success,
and saves the authenticated session to a storage-state file that every later run can
reuse. This is how you avoid re-logging-in on every check.

```bash
export APP_USER='someone@example.com' APP_PASSWORD='...'
python3 scripts/login.py --url https://app.example.com/login \
    --success-url "**/dashboard" --save-state ./auth.json
```

## How to write the checks

**Locators, best to worst.** `get_by_role("button", name="Save")` → `get_by_label("Email")`
→ `get_by_test_id(...)` → `get_by_text(...)` → CSS/XPath. Role and label locators mirror
how a user and a screen reader find things, so they survive restyling and they double as
an accessibility signal — if you can't find a control by role or label, that's often a
real bug worth mentioning. Never write `div > div:nth-child(3) > span`.

**Never sleep.** Playwright auto-waits on actions and on `expect()` assertions. If
something needs settling, wait on the actual condition — `expect(locator).to_be_visible()`,
`page.wait_for_url(...)`, `page.wait_for_response(lambda r: "/api/items" in r.url)`. A
`time.sleep(3)` is the single biggest source of flaky tests and it hides the real timing
bug rather than finding it.

**Instrument every run.** Attach console, `pageerror`, and `requestfailed` handlers before
navigating. Half of "the page looks fine but doesn't work" turns out to be a 500 on an
XHR or an uncaught TypeError that nobody was watching for.

**Turn on tracing when you're stuck.** A trace records DOM snapshots, actions, network,
and console for the whole run, and `playwright show-trace trace.zip` gives you a
time-travel debugger. Details and more patterns — auth, file uploads, downloads, iframes,
shadow DOM, network mocking, visual regression, mobile emulation — are in
`references/recipes.md`. Read that file whenever the task goes past "load page, look at it."

## Debugging loop

1. **Reproduce headlessly first.** Fast, and it's how CI will see it.
2. **If it only fails headless, that's a finding**, not an obstacle — see the headless
   section in `references/troubleshooting.md` before reaching for `headless=False`.
3. **Watch it happen** when the failure is unclear: `headless=False, slow_mo=300`, or
   `PWDEBUG=1` for the inspector. On a headless Linux box, use `xvfb-run` or record video
   instead.
4. **Narrow it down.** Bisect the flow, screenshot before and after the suspect step, dump
   `page.content()` when a locator resolves to nothing.
5. **Confirm the fix** by rerunning the exact same script.

When a locator times out, the error already tells you whether zero or many elements
matched — read it before changing anything. `references/troubleshooting.md` maps the
common Playwright errors to their actual causes.

## Reporting back

Lead with the verdict, then the evidence. Something like:

```
**Login flow: fails at the 2nd step.**

- POST /api/session → 500 (response body: "db timeout")
- Console: Uncaught TypeError: Cannot read properties of null (reading 'token') — app.js:412
- Screenshot: audit/login-failure-1280x800.png (spinner never resolves)
- Reproduced 3/3 times, headless and headed, Chromium 127.

Likely cause: the session endpoint is erroring and the client doesn't handle a
non-200, so it dereferences a null body. Fix the 500 first; the client-side
null check is a separate hardening item.
```

Attach the screenshots and the JSON report. Say plainly what you could not check —
"I couldn't get past the MFA prompt, so everything after login is unverified" — rather
than implying broader coverage than you have. If a check passed, say what specifically
was asserted, since "looks fine" from a browser that never waited for the data to load
is worse than no answer.

## Reference files

Read these as needed rather than upfront:

- `references/setup-windows.md` — winget vs. Chocolatey, admin elevation, PATH, corporate proxies, WSL
- `references/setup-linux.md` — distro packages, `--with-deps`, headless servers, Docker, CI
- `references/recipes.md` — auth/storage state, MFA, forms and uploads, visual regression, network mocking, iframes, downloads, mobile emulation, tracing
- `references/troubleshooting.md` — error-to-cause table for timeouts, strict-mode violations, headless-only failures, missing libraries
