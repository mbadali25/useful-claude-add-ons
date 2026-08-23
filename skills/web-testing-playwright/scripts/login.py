#!/usr/bin/env python3
"""Log in to a site and save the authenticated session for reuse.

Credentials come from environment variables only - never from arguments, which
would land in shell history and process listings. The saved storage-state file
lets every later run start already logged in, which is both faster and kinder
to the login endpoint.

    export APP_USER='someone@example.com'
    export APP_PASSWORD='...'
    python3 login.py --url https://app.example.com/login \
        --success-url "**/dashboard" --save-state ./auth.json

If field auto-detection picks the wrong control, name them explicitly:

    python3 login.py --url ... --user-selector "#username" \
        --password-selector "#pass" --submit-selector "button[type=submit]"

Then reuse the session:

    python3 audit_page.py https://app.example.com/settings --storage-state ./auth.json

The state file contains live session cookies - treat it like a password.
Add it to .gitignore and delete it when you're done.
"""

import argparse
import os
import sys
from urllib.parse import quote_plus as quote_plus_safe

try:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright is not installed. Run: python3 scripts/check_env.py")

# Tried in order. Label/role lookups first because they match what a user sees.
USER_CANDIDATES = [
    ("label", r"(?i)^(email|e-mail|username|user name|user|login|account)"),
    ("css", "input[autocomplete='username']"),
    ("css", "input[type='email']"),
    ("css", "input[name*='user' i], input[name*='email' i], input[name='login' i]"),
    ("css", "input[id*='user' i], input[id*='email' i]"),
    ("placeholder", r"(?i)(email|username)"),
]
PASSWORD_CANDIDATES = [
    ("css", "input[type='password']"),
    ("label", r"(?i)^password"),
    ("css", "input[autocomplete='current-password']"),
]
SUBMIT_CANDIDATES = [
    ("role", r"(?i)^(log ?in|sign ?in|continue|submit|enter)"),
    ("css", "button[type='submit']"),
    ("css", "input[type='submit']"),
]


def make_redactor(*secrets):
    """Scrub credential values out of anything we print.

    A GET-method login form puts the password straight into the URL query
    string, and error banners sometimes echo the username back. Neither should
    ever reach stdout, a log file, or a screenshot filename.
    """
    from urllib.parse import quote

    variants = set()
    for s in secrets:
        if not s:
            continue
        variants.update({s, quote(s), quote_plus_safe(s), quote(s, safe="")})
    variants = sorted(variants, key=len, reverse=True)

    def redact(text):
        text = str(text)
        for v in variants:
            if v:
                text = text.replace(v, "<redacted>")
        return text

    return redact


def resolve(page, candidates, explicit, what):
    """Find a control, preferring an explicit selector if one was given."""
    if explicit:
        loc = page.locator(explicit).first
        if loc.count() == 0:
            sys.exit(f"--{what}-selector matched nothing: {explicit}")
        return loc

    import re as _re
    for kind, pattern in candidates:
        try:
            if kind == "label":
                loc = page.get_by_label(_re.compile(pattern)).first
            elif kind == "placeholder":
                loc = page.get_by_placeholder(_re.compile(pattern)).first
            elif kind == "role":
                loc = page.get_by_role("button", name=_re.compile(pattern)).first
            else:
                loc = page.locator(pattern).first
            if loc.count() > 0 and loc.is_visible():
                return loc
        except PWError:
            continue
    return None


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--url", required=True, help="the login page URL")
    ap.add_argument("--user-env", default="APP_USER",
                    help="env var holding the username (default: APP_USER)")
    ap.add_argument("--password-env", default="APP_PASSWORD",
                    help="env var holding the password (default: APP_PASSWORD)")
    ap.add_argument("--user-selector", help="override username field detection")
    ap.add_argument("--password-selector", help="override password field detection")
    ap.add_argument("--submit-selector", help="override submit button detection")
    ap.add_argument("--next-selector",
                    help="selector for the first-screen Next button on a "
                         "two-step login; falls back to --submit-selector")
    ap.add_argument("--success-url", help="URL glob expected after login, e.g. '**/dashboard'")
    ap.add_argument("--success-selector",
                    help="selector that only exists when logged in, e.g. '[data-testid=avatar]'")
    ap.add_argument("--save-state", default="./auth.json",
                    help="where to write the session (default: ./auth.json)")
    ap.add_argument("--screenshot", help="save a post-login screenshot here")
    ap.add_argument("--two-step", action="store_true",
                    help="username and password are on separate screens")
    ap.add_argument("--browser", default="chromium",
                    choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--headed", action="store_true",
                    help="watch it happen - useful when detection misfires")
    ap.add_argument("--pause-for-mfa", type=int, default=0, metavar="SECONDS",
                    help="hold the browser open this long so a human can complete MFA "
                         "(requires --headed)")
    ap.add_argument("--timeout", type=int, default=30000)
    ap.add_argument("--ignore-https-errors", action="store_true")
    args = ap.parse_args()

    username = os.environ.get(args.user_env)
    password = os.environ.get(args.password_env)
    missing = [n for n, v in ((args.user_env, username),
                              (args.password_env, password)) if not v]
    if missing:
        sys.exit(
            "Missing credentials in the environment: " + ", ".join(missing)
            + f"\n  bash       : export {args.user_env}='...' {args.password_env}='...'"
            + f"\n  PowerShell : $env:{args.user_env}='...'; $env:{args.password_env}='...'"
        )

    if not (args.success_url or args.success_selector):
        print("WARNING: no --success-url or --success-selector given, so this can only "
              "guess whether login worked. A failed login often still returns HTTP 200.",
              file=sys.stderr)

    if args.pause_for_mfa and not args.headed:
        sys.exit("--pause-for-mfa needs --headed so a human can actually see the prompt.")

    redact = make_redactor(username, password)

    console_errors = []

    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch(headless=not args.headed)
        context = browser.new_context(ignore_https_errors=args.ignore_https_errors)
        page = context.new_page()
        page.set_default_timeout(args.timeout)
        page.on("console",
                lambda m: console_errors.append(m.text[:300]) if m.type == "error" else None)

        print(f"-> {args.url}")
        page.goto(args.url, wait_until="load")

        user_field = resolve(page, USER_CANDIDATES, args.user_selector, "user")
        if user_field is None:
            sys.exit("Could not find a username field. Run inspect_forms.py on this URL "
                     "and pass --user-selector explicitly.")
        user_field.fill(username)
        print(f"   filled username from ${args.user_env}")

        if args.two_step:
            # --next-selector, not --submit-selector: on a real two-screen login
            # the "Next" and "Sign in" buttons rarely share markup, and reusing
            # one selector for both means either the first click misses or the
            # second one does.
            nxt = resolve(page, SUBMIT_CANDIDATES,
                          args.next_selector or args.submit_selector, "next")
            if nxt:
                nxt.click()
                page.wait_for_load_state("domcontentloaded")

        pw_field = resolve(page, PASSWORD_CANDIDATES, args.password_selector, "password")
        if pw_field is None:
            sys.exit("Could not find a password field. If this is a two-screen login, "
                     "add --two-step; otherwise pass --password-selector.")
        pw_field.fill(password)
        print(f"   filled password from ${args.password_env} (value not logged)")

        submit = resolve(page, SUBMIT_CANDIDATES, args.submit_selector, "submit")
        if submit is None:
            print("   no submit button found - pressing Enter instead")
            pw_field.press("Enter")
        else:
            submit.click()

        if args.pause_for_mfa:
            print(f"   waiting {args.pause_for_mfa}s for you to complete MFA in the browser...")
            page.wait_for_timeout(args.pause_for_mfa * 1000)

        ok = True
        detail = []
        try:
            page.wait_for_load_state("networkidle", timeout=args.timeout)
        except PWTimeout:
            detail.append("page never reached network idle")

        if args.success_url:
            try:
                page.wait_for_url(args.success_url, timeout=args.timeout)
                detail.append(f"reached {args.success_url}")
            except PWTimeout:
                ok = False
                detail.append(
                    f"never reached the glob {args.success_url} "
                    f"(still at {redact(page.url)}). If the real URL looks right, the glob "
                    "may be too strict - a query string needs a trailing '*'."
                )

        if args.success_selector:
            try:
                page.locator(args.success_selector).first.wait_for(
                    state="visible", timeout=args.timeout)
                detail.append(f"found {args.success_selector}")
            except (PWTimeout, PWError):
                ok = False
                detail.append(f"never saw {args.success_selector}")

        if not (args.success_url or args.success_selector):
            # Weak heuristic: a visible password field usually means we're still stuck.
            still_there = page.locator("input[type='password']").count() > 0
            ok = not still_there
            detail.append("password field still on screen - probably rejected"
                          if still_there else "password field gone - probably accepted")

        print(f"   final URL: {redact(page.url)}")
        for d in detail:
            print(f"   {d}")

        if password in page.url or quote_plus_safe(password) in page.url:
            print("   WARNING: the password appears in the URL - this login form uses "
                  "method=GET, which writes credentials into browser history, server "
                  "logs, and Referer headers. Worth reporting as a security bug.")

        if args.screenshot:
            page.screenshot(path=args.screenshot, full_page=True)
            print(f"   screenshot: {args.screenshot}")

        if ok:
            context.storage_state(path=args.save_state)
            try:
                os.chmod(args.save_state, 0o600)
            except OSError:
                pass
            print(f"\nLOGIN OK - session saved to {args.save_state}")
            print("Reuse it with:  --storage-state " + args.save_state)
            print("This file holds live session cookies. Gitignore it; delete when done.")
        else:
            print("\nLOGIN FAILED")
            # Surface the visible error message rather than making the user guess.
            for sel in ("[role=alert]", ".error", ".alert", "[class*='error' i]"):
                try:
                    loc = page.locator(sel).first
                    if loc.count() and loc.is_visible():
                        text = redact(" ".join(loc.inner_text().split())[:300])
                        if text:
                            print(f"Page says: {text}")
                            break
                except PWError:
                    continue
            if console_errors:
                print("Console errors:")
                for c in console_errors[:5]:
                    print(f"  - {redact(c)}")

        context.close()
        browser.close()

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
