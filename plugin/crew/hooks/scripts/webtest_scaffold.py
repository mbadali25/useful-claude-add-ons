"""`/crew:init`'s web phase: scaffold Playwright the way crew verifies it.

    python3 webtest_scaffold.py --root .            # dry run (default): writes nothing
    python3 webtest_scaffold.py --root . --apply    # create what is missing

Runs only when the repository looks like a web project: a `playwright.config.*`,
an `angular.json`, or a `package.json` naming `@playwright/test` or
`playwright`. Otherwise it prints `n/a` and exits 0.

NEVER OVERWRITES. Each whole file is created only when absent. Three files are
merged instead, and only by ADDING: `.gitignore` gains missing lines, `.mcp.json`
gains missing `mcpServers` keys, `.codex/config.toml` gains missing
`[mcp_servers.<name>]` tables. An existing key is never touched, and a
`.mcp.json` that does not parse is reported and left alone. Every write is
computed in full first, then staged as a temp and `os.replace`d.

`npx playwright init-agents --loop=claude` and `--loop=codex` run on apply
unless `.claude/agents/playwright-test-planner.md` already exists. The claude
loop writes its own `.mcp.json`, so the file's bytes are captured before and,
if any server that was there is gone or changed after, the original is put
back with only the NEW servers added.

Exit codes: 0 done (or nothing to do); 1 something was refused or failed; 2 usage.
"""
import argparse
import json
import os
import subprocess
import sys

import webtest_guard

PLAYWRIGHT_MCP = "@playwright/mcp@0.0.82"
DEVTOOLS_MCP = "chrome-devtools-mcp@1.10.1"
AGENT_MARKER = os.path.join(".claude", "agents", "playwright-test-planner.md")
IGNORE_LINES = ("/playwright/.auth/", "/test-results/", "/playwright-report/", "/blob-report/")

CONFIG_TS = """import { defineConfig, devices } from '@playwright/test';

const CI = !!process.env.CI;
const PINNED_IMAGE = '%(image)s';
const inPinnedImage = process.env.%(env)s === PINNED_IMAGE;
const authFile = 'playwright/.auth/user.json';
const browser = { ...devices['Desktop Chrome'], storageState: authFile };

export default defineConfig({
  testDir: './tests',
  fullyParallel: true,
  forbidOnly: CI,
  retries: CI ? 2 : 0,
  reporter: CI ? 'blob' : 'html',
  snapshotPathTemplate: '{testDir}/__screenshots__/{projectName}/{platform}/{testFilePath}/{arg}{ext}',
  expect: { toHaveScreenshot: { animations: 'disabled', maxDiffPixelRatio: 0.01 } },
  use: {
    baseURL: process.env.BASE_URL ?? '%(base_url)s',
    trace: 'on-first-retry',
    testIdAttribute: 'data-testid',
  },
  projects: [
    { name: 'setup', testMatch: /.*\\.setup\\.ts/ },
    {
      name: 'chromium',
      use: browser,
      dependencies: ['setup'],
      testIgnore: [/.*\\.axe\\.spec\\.ts/, /.*\\.visual\\.spec\\.ts/],
    },
    { name: 'axe', testMatch: /.*\\.axe\\.spec\\.ts/, use: browser, dependencies: ['setup'] },
    ...(inPinnedImage
      ? [{ name: 'visual', testMatch: /.*\\.visual\\.spec\\.ts/, use: browser, dependencies: ['setup'] }]
      : []),
  ],
});
"""

AUTH_SETUP_TS = """import { test as setup, expect } from '@playwright/test';

const authFile = 'playwright/.auth/user.json';

setup('authenticate', async ({ page }) => {
  await page.goto('/login');
  await page.getByLabel('Username').fill(process.env.E2E_USER ?? '');
  await page.getByLabel('Password').fill(process.env.E2E_PASSWORD ?? '');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('navigation')).toBeVisible();
  await page.context().storageState({ path: authFile });
});
"""

AXE_FIXTURE_TS = """import { writeFile } from 'node:fs/promises';
import { test as base, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

type AxeFixtures = { checkA11y: () => Promise<void> };

export const test = base.extend<AxeFixtures>({
  checkA11y: async ({ page }, use, testInfo) => {
    await use(async () => {
      const results = await new AxeBuilder({ page })
        .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
        .analyze();
      const file = testInfo.outputPath('axe-results.json');
      await writeFile(file, JSON.stringify(results, null, 2));
      await testInfo.attach('axe-results', { path: file, contentType: 'application/json' });
      expect(results.violations).toEqual([]);
    });
  },
});

export { expect };
"""

AXE_SPEC_TS = """import { test } from './fixtures/axe';

test('home page has no WCAG A/AA violations', async ({ page, checkA11y }) => {
  await page.goto('/');
  await checkA11y();
});
"""


def detect(root):
    """The reason this is a web project, or None."""
    names = os.listdir(root)
    config = sorted(n for n in names if n.startswith("playwright.config."))
    if config:
        return config[0]
    if "angular.json" in names:
        return "angular.json"
    try:
        with open(os.path.join(root, "package.json"), encoding="utf-8-sig") as fh:
            pkg = json.load(fh)
    except (OSError, ValueError):
        return None
    deps = {}
    for key in ("dependencies", "devDependencies"):
        if isinstance(pkg.get(key), dict):
            deps.update(pkg[key])
    for name in ("@playwright/test", "playwright"):
        if name in deps:
            return f"package.json ({name})"
    return None


def _npx(windows, *args):
    return ({"command": "cmd", "args": ["/c", "npx"] + list(args)} if windows
            else {"command": "npx", "args": list(args)})


def mcp_servers(windows):
    return {"playwright": _npx(windows, PLAYWRIGHT_MCP, "--isolated", "--headless",
                               "--caps", "testing"),
            "chrome-devtools": _npx(windows, DEVTOOLS_MCP)}


def _codex_table(name, server):
    args = ", ".join(json.dumps(a) for a in server["args"])
    return (f"[mcp_servers.{name}]\ncommand = {json.dumps(server['command'])}\n"
            f"args = [{args}]\n")


def _read(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            return fh.read()
    except FileNotFoundError:
        return None


def merge_mcp(text, servers):
    """(new_text_or_None, added, problem). None text means nothing to write."""
    data = {} if text is None else None
    if text is not None:
        try:
            data = json.loads(text)
        except ValueError:
            return None, [], ".mcp.json does not parse; left alone"
        if not isinstance(data, dict) or not isinstance(data.get("mcpServers", {}), dict):
            return None, [], ".mcp.json has no mcpServers object; left alone"
    existing = data.setdefault("mcpServers", {})
    added = [n for n in servers if n not in existing]
    for name in added:
        existing[name] = servers[name]
    return (json.dumps(data, indent=2) + "\n" if added else None), added, None


def merge_codex(text, servers):
    text = text or ""
    added = [n for n in servers if f"[mcp_servers.{n}]" not in text]
    if not added:
        return None, []
    tables = "\n".join(_codex_table(n, servers[n]) for n in added)
    sep = "" if not text else ("\n" if text.endswith("\n") else "\n\n")
    return text + sep + tables, added


def merge_ignore(text):
    lines = (text or "").splitlines()
    added = [line for line in IGNORE_LINES if line not in lines]
    if not added:
        return None, []
    sep = "" if not text or text.endswith("\n") else "\n"
    return (text or "") + sep + "\n".join(added) + "\n", added


def plan(root, windows):
    """[(rel, new_text_or_None, note)]. None text = nothing to write."""
    angular = os.path.exists(os.path.join(root, "angular.json"))
    has_config = any(n.startswith("playwright.config.") for n in os.listdir(root))
    config = CONFIG_TS % {"image": webtest_guard.PINNED_IMAGE, "env": webtest_guard.IMAGE_ENV,
                          "base_url": "http://localhost:4200" if angular else "http://localhost:3000"}
    items = []
    whole = (("playwright.config.ts", config, has_config),
             ("tests/auth.setup.ts", AUTH_SETUP_TS, False),
             ("tests/fixtures/axe.ts", AXE_FIXTURE_TS, False),
             ("tests/home.axe.spec.ts", AXE_SPEC_TS, False))
    for rel, text, skip in whole:
        if skip or os.path.exists(os.path.join(root, rel)):
            items.append((rel, None, "exists - kept"))
        else:
            items.append((rel, text, "create"))
    text, added = merge_ignore(_read(os.path.join(root, ".gitignore")))
    items.append((".gitignore", text, f"add {', '.join(added)}" if added else "already ignores"))
    servers = mcp_servers(windows)
    text, added, problem = merge_mcp(_read(os.path.join(root, ".mcp.json")), servers)
    items.append((".mcp.json", text, problem or (f"add {', '.join(added)}" if added
                                                  else "servers present - kept")))
    text, added = merge_codex(_read(os.path.join(root, ".codex", "config.toml")), servers)
    items.append((".codex/config.toml", text, f"add {', '.join(added)}" if added
                  else "servers present - kept"))
    return items


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def run_agents(root, windows, runner=subprocess.call):
    """Lines to report. `runner` is injectable so tests never run npx."""
    if os.path.exists(os.path.join(root, AGENT_MARKER)):
        return [f"  keep    Test Agents ({AGENT_MARKER.replace(os.sep, '/')} exists)"], True
    mcp_path = os.path.join(root, ".mcp.json")
    before = _read(mcp_path)
    out, ok = [], True
    for loop in ("claude", "codex"):
        cmd = ["npx", "playwright", "init-agents", f"--loop={loop}"]
        rc = runner((["cmd", "/c"] if windows else []) + cmd, cwd=root)
        out.append(f"  {'ran' if rc == 0 else 'FAILED'}     {' '.join(cmd)} (exit {rc})")
        ok = ok and rc == 0
    after = _read(mcp_path)
    if before is not None and after != before:
        try:
            new = json.loads(after or "{}").get("mcpServers", {})
        except (ValueError, AttributeError):
            new = {}
        text, added, problem = merge_mcp(before, new if isinstance(new, dict) else {})
        _write(root, ".mcp.json", text or before)
        out.append(f"  restore .mcp.json as it was{', plus ' + ', '.join(added) if added else ''}"
                   f"{' (' + problem + ')' if problem else ''}")
    return out, ok


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--windows", action="store_true", default=os.name == "nt",
                        help="write cmd /c MCP wrappers (default: this host is Windows)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    reason = detect(root)
    if not reason:
        print("webtest scaffold: n/a - no playwright.config.*, angular.json, or Playwright "
              "in package.json")
        return 0
    mode = "apply" if args.apply else "dry run"
    print(f"webtest scaffold ({mode}): web project detected by {reason}")
    items = plan(root, args.windows)
    ok = True
    for rel, text, note in items:
        if text is None:
            print(f"  keep    {rel}: {note}")
            ok = ok and "left alone" not in note
            continue
        print(f"  write   {rel}: {note}")
        if args.apply:
            _write(root, rel, text)
    if args.apply:
        lines, agents_ok = run_agents(root, args.windows)
        ok = ok and agents_ok
    elif os.path.exists(os.path.join(root, AGENT_MARKER)):
        lines = [f"  keep    Test Agents ({AGENT_MARKER.replace(os.sep, '/')} exists)"]
    else:
        lines = ["  run     npx playwright init-agents --loop=claude",
                 "  run     npx playwright init-agents --loop=codex"]
    print("\n".join(lines))
    print(f"next: npm i -D @playwright/test@{webtest_guard.PINNED_PLAYWRIGHT} "
          "@axe-core/playwright@4.13.0 && npx playwright install --with-deps chromium")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
