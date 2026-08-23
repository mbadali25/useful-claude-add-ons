#!/usr/bin/env python3
"""Load a page in a real browser and report everything that went wrong.

Captures HTTP status, title, console messages, uncaught page errors, failed and
slow requests, then screenshots the page at several viewport widths. Writes a
JSON report plus PNGs to the output directory and prints a summary.

    python3 audit_page.py https://example.com
    python3 audit_page.py http://localhost:3000/app --storage-state ./auth.json
    python3 audit_page.py https://example.com --wait-for "[data-testid=chart]" --trace

Exit code is 1 if any error-level problem was found, 0 otherwise, so it can be
used as a smoke check in a shell pipeline.
"""

import argparse
import json
import re
import sys
import time
from pathlib import Path

try:
    from playwright.sync_api import Error as PWError
    from playwright.sync_api import TimeoutError as PWTimeout
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("Playwright is not installed. Run: python3 scripts/check_env.py")

DEFAULT_VIEWPORTS = "1280x800,768x1024,390x844"
# Console noise that is almost never the bug being chased.
IGNORABLE = re.compile(
    r"(favicon\.ico|Download the React DevTools|\[HMR\]|webpack-dev-server|"
    r"DevTools failed to load source map)",
    re.I,
)


def parse_viewports(spec):
    out = []
    for chunk in spec.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            w, h = chunk.lower().split("x")
            out.append({"width": int(w), "height": int(h)})
        except ValueError:
            sys.exit(f"Bad viewport {chunk!r} - expected WIDTHxHEIGHT, e.g. 1280x800")
    return out


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("url")
    ap.add_argument("--out", default="./audit", help="output directory (default: ./audit)")
    ap.add_argument("--viewports", default=DEFAULT_VIEWPORTS,
                    help=f"comma-separated WxH (default: {DEFAULT_VIEWPORTS})")
    ap.add_argument("--browser", default="chromium",
                    choices=["chromium", "firefox", "webkit"])
    ap.add_argument("--storage-state", help="auth JSON saved by login.py")
    ap.add_argument("--wait-for", help="CSS selector that must appear before screenshotting")
    ap.add_argument("--wait-until", default="load",
                    choices=["commit", "domcontentloaded", "load", "networkidle"])
    ap.add_argument("--timeout", type=int, default=30000, help="navigation timeout in ms")
    ap.add_argument("--settle", type=float, default=0.4,
                    help="seconds to let async paint finish after load (default: 0.4)")
    ap.add_argument("--full-page", action="store_true", help="capture entire scroll height")
    ap.add_argument("--headed", action="store_true", help="show the browser window")
    ap.add_argument("--trace", action="store_true",
                    help="record a trace.zip (view with: playwright show-trace)")
    ap.add_argument("--slow-request-ms", type=int, default=3000,
                    help="flag requests slower than this (default: 3000)")
    ap.add_argument("--ignore-https-errors", action="store_true",
                    help="accept self-signed certs (staging/local only)")
    ap.add_argument("--all-console", action="store_true",
                    help="keep log/info/debug messages too, not just warnings and errors")
    args = ap.parse_args()

    outdir = Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)
    viewports = parse_viewports(args.viewports)

    report = {
        "url": args.url,
        "browser": args.browser,
        "status": None,
        "final_url": None,
        "title": None,
        "load_ms": None,
        "console": [],
        "page_errors": [],
        "failed_requests": [],
        "slow_requests": [],
        "bad_responses": [],
        "screenshots": [],
        "navigation_error": None,
    }

    with sync_playwright() as p:
        browser = getattr(p, args.browser).launch(headless=not args.headed)
        ctx_args = {
            "viewport": viewports[0],
            "ignore_https_errors": args.ignore_https_errors,
        }
        if args.storage_state:
            ctx_args["storage_state"] = args.storage_state
        context = browser.new_context(**ctx_args)
        if args.trace:
            context.tracing.start(screenshots=True, snapshots=True, sources=True)

        page = context.new_page()
        page.set_default_timeout(args.timeout)
        timings = {}

        def on_console(msg):
            if msg.type not in ("error", "warning") and not args.all_console:
                return
            text = msg.text
            if IGNORABLE.search(text):
                return
            loc = msg.location or {}
            report["console"].append({
                "type": msg.type,
                "text": text[:2000],
                "source": f"{loc.get('url', '')}:{loc.get('lineNumber', '')}".strip(":"),
            })

        def on_request(req):
            timings[req] = time.time()

        def on_finished(req):
            started = timings.pop(req, None)
            if started is None:
                return
            elapsed = (time.time() - started) * 1000
            if elapsed >= args.slow_request_ms:
                report["slow_requests"].append({
                    "url": req.url[:500], "method": req.method, "ms": round(elapsed)
                })

        def on_failed(req):
            timings.pop(req, None)
            report["failed_requests"].append({
                "url": req.url[:500],
                "method": req.method,
                "resource_type": req.resource_type,
                "failure": (req.failure or "unknown"),
            })

        def on_response(resp):
            if resp.status >= 400:
                report["bad_responses"].append({
                    "url": resp.url[:500],
                    "status": resp.status,
                    "resource_type": resp.request.resource_type,
                })

        page.on("console", on_console)
        page.on("pageerror", lambda e: report["page_errors"].append(str(e)[:2000]))
        page.on("request", on_request)
        page.on("requestfinished", on_finished)
        page.on("requestfailed", on_failed)
        page.on("response", on_response)

        started = time.time()
        try:
            resp = page.goto(args.url, wait_until=args.wait_until, timeout=args.timeout)
            report["status"] = resp.status if resp else None
        except (PWTimeout, PWError) as exc:
            report["navigation_error"] = str(exc).splitlines()[0]

        if args.wait_for and not report["navigation_error"]:
            try:
                page.locator(args.wait_for).first.wait_for(state="visible",
                                                           timeout=args.timeout)
            except (PWTimeout, PWError):
                report["navigation_error"] = (
                    f"--wait-for selector never became visible: {args.wait_for}"
                )

        report["load_ms"] = round((time.time() - started) * 1000)
        if args.settle:
            page.wait_for_timeout(args.settle * 1000)

        try:
            report["final_url"] = page.url
            report["title"] = page.title()
        except PWError:
            pass

        slug = re.sub(r"[^a-z0-9]+", "-", args.url.lower()).strip("-")[:60] or "page"
        for vp in viewports:
            page.set_viewport_size(vp)
            page.wait_for_timeout(250)  # let CSS media queries and resize handlers run
            name = f"{slug}-{vp['width']}x{vp['height']}.png"
            path = outdir / name
            try:
                page.screenshot(path=str(path), full_page=args.full_page)
                report["screenshots"].append(str(path))
            except PWError as exc:
                report["screenshots"].append(f"FAILED {name}: {exc}")

        if args.trace:
            trace_path = outdir / "trace.zip"
            context.tracing.stop(path=str(trace_path))
            report["trace"] = str(trace_path)

        context.close()
        browser.close()

    report_path = outdir / "report.json"
    report_path.write_text(json.dumps(report, indent=2))

    errors = [c for c in report["console"] if c["type"] == "error"]
    warnings = [c for c in report["console"] if c["type"] == "warning"]

    print(f"\nURL      : {report['url']}")
    if report["final_url"] and report["final_url"] != report["url"]:
        print(f"Redirect : {report['final_url']}")
    print(f"Status   : {report['status']}   Load: {report['load_ms']} ms")
    print(f"Title    : {report['title']!r}")
    if report["navigation_error"]:
        print(f"NAV ERROR: {report['navigation_error']}")

    def section(label, items, fmt):
        if not items:
            return
        print(f"\n{label} ({len(items)}):")
        for item in items[:10]:
            print("  - " + fmt(item))
        if len(items) > 10:
            print(f"  ... {len(items) - 10} more in report.json")

    section("Uncaught page errors", report["page_errors"], lambda e: e.splitlines()[0])
    section("Console errors", errors,
            lambda c: f"{c['text'][:180]}  [{c['source']}]")
    section("Console warnings", warnings, lambda c: c["text"][:180])
    section("Failed requests", report["failed_requests"],
            lambda r: f"{r['method']} {r['url'][:140]} - {r['failure']}")
    section("HTTP >= 400", report["bad_responses"],
            lambda r: f"{r['status']} {r['url'][:140]}")
    section("Slow requests", report["slow_requests"],
            lambda r: f"{r['ms']} ms  {r['url'][:140]}")

    print(f"\nScreenshots: {len(report['screenshots'])} -> {outdir}")
    for shot in report["screenshots"]:
        print(f"  {shot}")
    print(f"Report     : {report_path}")

    problems = (
        bool(report["navigation_error"])
        or bool(report["page_errors"])
        or bool(errors)
        or bool(report["failed_requests"])
        or bool(report["bad_responses"])
        or (report["status"] or 200) >= 400
    )
    print("\nRESULT: " + ("PROBLEMS FOUND" if problems else "clean"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
