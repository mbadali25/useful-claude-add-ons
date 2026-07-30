# Playwright recipes

Working patterns for the situations that come up most. Python sync API unless noted; the
async and Node forms are the same shapes with different syntax.

## Contents
- [Skeleton](#skeleton)
- [Authentication and sessions](#authentication-and-sessions)
- [MFA and CAPTCHA](#mfa-and-captcha)
- [Forms](#forms)
- [File uploads and downloads](#file-uploads-and-downloads)
- [Waiting correctly](#waiting-correctly)
- [Visual checks and regression](#visual-checks-and-regression)
- [Network inspection and mocking](#network-inspection-and-mocking)
- [Iframes and shadow DOM](#iframes-and-shadow-dom)
- [Mobile and device emulation](#mobile-and-device-emulation)
- [Accessibility](#accessibility)
- [Tracing and video](#tracing-and-video)
- [Multi-step user journeys](#multi-step-user-journeys)
- [Node test-runner setup](#node-test-runner-setup)

## Skeleton

Every ad-hoc script should look roughly like this — instrumented before navigation, so
nothing that happens during load goes unrecorded.

```python
from playwright.sync_api import sync_playwright, expect

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    context = browser.new_context(viewport={"width": 1280, "height": 800})
    page = context.new_page()

    errors, failures = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.on("requestfailed", lambda r: failures.append(f"{r.method} {r.url} {r.failure}"))

    page.goto("https://example.com", wait_until="load")
    # ... the actual checks ...

    context.close()
    browser.close()

print("JS errors:", errors)
print("Failed requests:", failures)
```

## Authentication and sessions

Log in once, save the session, reuse it everywhere. Logging in before every check is slow
and can trip rate limits or lockout policies.

```python
# Save (scripts/login.py does this for you)
context.storage_state(path="auth.json")

# Reuse
context = browser.new_context(storage_state="auth.json")
```

`storage_state` captures cookies plus localStorage. It does **not** capture sessionStorage
or IndexedDB, so an app that keeps its token in sessionStorage needs it seeded manually:

```python
context.add_init_script("""
  sessionStorage.setItem('token', 'VALUE_FROM_ENV');
""")
```

Sessions expire. If a reused state suddenly redirects to the login page, that's expiry,
not a bug in the app — re-run `login.py`.

**Token/API auth** skips the UI entirely, which is faster and less brittle when the login
form isn't what's being tested:

```python
context = browser.new_context(extra_http_headers={
    "Authorization": f"Bearer {os.environ['API_TOKEN']}"
})
```

**HTTP basic auth**:
```python
context = browser.new_context(http_credentials={
    "username": os.environ["BASIC_USER"], "password": os.environ["BASIC_PASS"]
})
```

**Testing that logout works** matters as much as login: after logging out, request a
protected URL directly and assert you land on the login page. Plenty of apps clear the UI
without invalidating the session.

## MFA and CAPTCHA

Neither can be automated away, and trying is usually a red flag rather than a puzzle.

- **TOTP** in a test account you control: generate the code from the shared secret with
  `pyotp`, storing the secret in an env var. Only valid when the user owns the account and
  gives you the secret.
- **SMS/email codes**: no clean automation. Either use `--headed --pause-for-mfa 60` and
  have a human complete it once, then reuse the saved storage state until it expires, or
  ask whether there's a test account with MFA disabled — most teams have one.
- **CAPTCHA**: don't attempt to solve or bypass it. Ask whether the staging environment
  has a bypass token or a whitelisted test key (reCAPTCHA and hCaptcha both provide test
  keys that always pass). If the answer is no, report the flow as un-automatable past that
  point rather than working around a control that exists specifically to stop automation.

Say clearly in the report which steps were verified and which were blocked.

## Forms

Run `scripts/inspect_forms.py URL` first so the locators come from the real DOM.

```python
page.get_by_label("Email address").fill("someone@example.com")
page.get_by_label("Password").fill(os.environ["APP_PASSWORD"])
page.get_by_label("Remember me").check()
page.get_by_label("Country").select_option("US")          # by value
page.get_by_label("Country").select_option(label="United States")
page.get_by_role("radio", name="Standard shipping").check()
page.get_by_role("button", name="Continue").click()
```

`fill()` clears first and fires the input events frameworks listen for; it's right almost
always. Use `press_sequentially()` (formerly `type()`) only when testing something that
reacts per keystroke, like an autocomplete.

**Testing validation is usually the interesting part.** Check that bad input is rejected,
not just that good input works:

```python
page.get_by_label("Email").fill("not-an-email")
page.get_by_role("button", name="Submit").click()
expect(page.get_by_text("Enter a valid email")).to_be_visible()

# Native HTML5 validity, which never renders as DOM text:
msg = page.get_by_label("Email").evaluate("el => el.validationMessage")

# And confirm nothing was submitted:
expect(page).to_have_url(re.compile(r"/signup"))
```

Worth probing deliberately: empty required fields, whitespace-only input, over-max-length
strings, leading/trailing spaces in emails, unicode and emoji, `<script>` tags and SQL
quotes in free-text fields (the app should escape, not break), and double-clicking submit
(does it create two records?).

**Dynamic and dependent fields** — a select that populates another select — need a wait on
the actual change, not a sleep:

```python
page.get_by_label("Country").select_option("US")
expect(page.get_by_label("State")).to_be_enabled()
expect(page.get_by_label("State").locator("option")).not_to_have_count(1)
```

## File uploads and downloads

```python
page.get_by_label("Attach resume").set_input_files("/path/to/cv.pdf")
page.get_by_label("Photos").set_input_files(["a.png", "b.png"])
page.get_by_label("Attach resume").set_input_files([])          # clear

# Generated on the fly, no temp file needed:
page.get_by_label("Upload").set_input_files({
    "name": "data.csv", "mimeType": "text/csv", "buffer": b"a,b\n1,2\n"
})
```

For a custom drop zone with a hidden input, target the input directly —
`page.locator("input[type=file]")` works even when it's `display:none`, because
`set_input_files` doesn't require visibility.

If the UI only opens a native file chooser:
```python
with page.expect_file_chooser() as fc:
    page.get_by_role("button", name="Browse").click()
fc.value.set_files("/path/to/file.pdf")
```

Downloads:
```python
with page.expect_download() as dl:
    page.get_by_role("link", name="Export CSV").click()
download = dl.value
download.save_as("/tmp/export.csv")
print(download.suggested_filename)
```

Verify the contents, not just that a file arrived — a 0-byte or HTML-error-page download
is a common failure that "it downloaded" would miss.

## Waiting correctly

The rule: wait for the condition you actually care about.

```python
expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
expect(page.get_by_test_id("row")).to_have_count(20)
page.wait_for_url("**/checkout/confirm*")
with page.expect_response(lambda r: "/api/items" in r.url and r.status == 200):
    page.get_by_role("button", name="Load more").click()
page.get_by_test_id("spinner").wait_for(state="hidden")
```

`expect()` retries until the timeout, so it absorbs normal async delay without a fixed
sleep. `page.wait_for_timeout()` exists but should appear only as a deliberate settle
after a resize or animation — never as a substitute for a real condition.

`wait_until="networkidle"` is tempting and often wrong: an app with polling or a websocket
never goes idle, and the wait burns the full timeout. Prefer `"load"` plus an explicit
assertion on something the page renders.

## Visual checks and regression

Screenshots at several widths catch layout breakage that a functional test sails past:

```python
for w, h in [(1920, 1080), (1280, 800), (768, 1024), (390, 844)]:
    page.set_viewport_size({"width": w, "height": h})
    page.wait_for_timeout(300)          # let media queries and resize handlers settle
    page.screenshot(path=f"shot-{w}.png", full_page=True)

page.get_by_test_id("pricing-table").screenshot(path="pricing.png")   # one element
```

`scripts/audit_page.py` does the multi-viewport pass for you.

For real pixel-diff regression, use the Node test runner, which has it built in:

```javascript
await expect(page).toHaveScreenshot('dashboard.png', { maxDiffPixelRatio: 0.01 });
```

First run writes the baseline; later runs diff against it and emit an image showing what
moved. Stabilise the page first or every run will differ:

```python
page.add_style_tag(content="""
  *, *::before, *::after { animation: none !important; transition: none !important; }
  .timestamp, [data-dynamic] { visibility: hidden !important; }
""")
page.emulate_media(reduced_motion="reduce")
context = browser.new_context(timezone_id="UTC", locale="en-US")   # freeze locale drift
```

Fonts render differently across operating systems, so baselines captured on macOS will
fail on a Linux CI runner. Generate baselines in the same environment that will check
them, or accept a small diff ratio.

## Network inspection and mocking

Watch what the page actually asks for:

```python
page.on("request", lambda r: print(">>", r.method, r.url))
page.on("response", lambda r: print("<<", r.status, r.url))
```

Mocking lets you test states that are hard to produce for real — the empty state, the
error state, the slow state:

```python
page.route("**/api/items", lambda route: route.fulfill(
    status=200, content_type="application/json", body='{"items": []}'))

page.route("**/api/items", lambda route: route.fulfill(status=500, body="boom"))

page.route("**/api/items", lambda route: (
    page.wait_for_timeout(5000), route.continue_()))       # simulate a slow endpoint

page.route("**/*.{png,jpg,jpeg,woff2}", lambda route: route.abort())  # speed up a run
```

Offline behaviour:
```python
context.set_offline(True)
```

Route handlers registered on `context` apply to every page in it; on `page`, just that
page. Register them **before** `goto`, or the first load slips past.

Assert on the request the app sends, which catches a whole class of bug the UI hides:

```python
with page.expect_request("**/api/orders") as req:
    page.get_by_role("button", name="Place order").click()
payload = req.value.post_data_json
assert payload["quantity"] == 2
```

## Iframes and shadow DOM

Iframe content is not reachable from `page` locators:

```python
frame = page.frame_locator("iframe[title='Payment']")
frame.get_by_label("Card number").fill("4242424242424242")

# By URL, when the iframe has no stable attribute:
f = page.frame(url=lambda u: "checkout" in u)
```

Payment fields (Stripe, Braintree) are almost always cross-origin iframes — that's the
usual reason "the locator exists in DevTools but Playwright can't find it."

**Shadow DOM needs nothing special**: Playwright's CSS and role locators pierce open shadow
roots automatically. Closed shadow roots are genuinely unreachable, which is worth saying
plainly rather than working at for an hour.

## Mobile and device emulation

```python
iphone = p.devices["iPhone 13"]
context = browser.new_context(**iphone)
```

That sets viewport, user agent, device scale factor, and touch support together. Emulation
tests responsive layout and touch handlers; it does **not** reproduce real mobile Safari
or Android quirks, real network conditions, or real performance. Say which you tested —
"looks correct at 390px in Chromium" is honest; "works on iPhone" isn't.

Touch gestures:
```python
page.get_by_test_id("card").tap()
page.touchscreen.tap(100, 200)
```

## Accessibility

The role-based locators you should already be using double as an a11y check. Beyond that:

```python
print(page.accessibility.snapshot())    # the tree a screen reader sees
```

For a real audit, inject axe-core:

```python
page.add_script_tag(url="https://cdnjs.cloudflare.com/ajax/libs/axe-core/4.10.2/axe.min.js")
results = page.evaluate("async () => await axe.run()")
for v in results["violations"]:
    print(v["impact"], v["id"], v["help"], len(v["nodes"]), "nodes")
```

Automated checks catch maybe a third of real accessibility problems — contrast, missing
labels, bad ARIA. They can't judge whether the reading order or focus management makes
sense. Report findings as a starting point, not a clean bill of health.

## Tracing and video

The single most useful debugging tool Playwright has:

```python
context.tracing.start(screenshots=True, snapshots=True, sources=True)
# ... the run ...
context.tracing.stop(path="trace.zip")
```

```bash
playwright show-trace trace.zip      # or: python -m playwright show-trace trace.zip
```

The viewer gives a timeline of every action with a DOM snapshot before and after, plus
network, console, and the source line that triggered each step. When something fails
intermittently, turn tracing on and let it fail — the trace tells you what the page looked
like at the moment it broke, which no amount of re-running will.

Video, when a trace is overkill:
```python
context = browser.new_context(record_video_dir="videos/",
                              record_video_size={"width": 1280, "height": 720})
```
The file is finalised on `context.close()`, so don't look for it before then.

## Multi-step user journeys

Model the flow the way a user experiences it, asserting at each transition so a failure
points at the step that broke rather than at the end.

```python
def test_checkout(page):
    page.goto(BASE + "/products")
    page.get_by_role("link", name="Blue Widget").click()
    expect(page.get_by_role("heading", name="Blue Widget")).to_be_visible()

    page.get_by_role("button", name="Add to cart").click()
    expect(page.get_by_test_id("cart-count")).to_have_text("1")

    page.get_by_role("link", name="Checkout").click()
    page.get_by_label("Full name").fill("Test User")
    page.get_by_label("Email").fill("test@example.com")

    with page.expect_response(lambda r: "/api/orders" in r.url) as resp:
        page.get_by_role("button", name="Place order").click()
    assert resp.value.status == 201, f"order API returned {resp.value.status}"

    expect(page.get_by_text("Order confirmed")).to_be_visible()
```

Screenshot at each step (`page.screenshot(path=f"step-{n}.png")`) when the run is
exploratory — a visual sequence is the fastest way to show a user where their flow breaks.

## Node test-runner setup

When the user wants tests that persist rather than a one-off answer:

```bash
npm init playwright@latest
npx playwright test
npx playwright test --ui          # interactive mode, watch and time-travel
npx playwright test --headed --debug
npx playwright show-report
npx playwright codegen https://example.com    # records clicks into working code
```

`codegen` is a good way to bootstrap a flow quickly — but always clean up what it emits.
It tends to produce over-specific locators, and its output should be rewritten toward
role and label locators before anyone relies on it.

Useful `playwright.config.ts` defaults:
```typescript
export default defineConfig({
  retries: process.env.CI ? 2 : 0,
  use: {
    baseURL: process.env.BASE_URL ?? 'http://127.0.0.1:3000',
    trace: 'on-first-retry',      // trace only what failed — cheap and high value
    screenshot: 'only-on-failure',
    video: 'retain-on-failure',
  },
  webServer: {                    // starts the app, waits for it, tears it down
    command: 'npm run dev',
    url: 'http://127.0.0.1:3000',
    reuseExistingServer: !process.env.CI,
  },
});
```

Retries hide flakiness as much as they absorb it. If a test only passes on retry, treat
that as a bug to investigate, not a solved problem.
