"""`/crew:init`'s web phase: scaffold Playwright the way crew verifies it.

    python3 webtest_scaffold.py --root .            # dry run (default): writes nothing
    python3 webtest_scaffold.py --root . --apply    # create what is missing
    python3 webtest_scaffold.py --root . --module apps/web [--apply]

Runs only when the repository looks like a web project: a `playwright.config.*`,
an `angular.json`, or a `package.json` naming `@playwright/test` or
`playwright`. Otherwise it prints `n/a`, lists every MODULE below `--root`
that is one (at most `MODULE_DEPTH` levels down, never inside `node_modules`
or a dot-directory, never below a module already found) with the
`--module <dir>` to scaffold it, states the depth searched, and exits 0.

`--module <dir>` (one per run, relative to `--root`) scaffolds that module:
what belongs to the test suite -- reading the existing config, the test
files, the `.gitignore` lines -- lands in the module; what a session loads --
`.mcp.json`, `.codex/config.toml`, `.claude/agents/` -- lands at `--root`,
the directory a session starts in. A value that is absolute, climbs out of
`--root`, does not exist, or is not a web project is refused (exit 1).

NEVER OVERWRITES. Each whole file is created only when absent. Three files are
merged instead, and only by ADDING: `.gitignore` gains missing lines, `.mcp.json`
gains missing `mcpServers` keys, `.codex/config.toml` gains missing
`[mcp_servers.<name>]` tables. An existing key is never touched, and a
`.mcp.json` that does not parse is reported and left alone. Every write is
computed in full first, then staged as a temp and `os.replace`d.

An existing `playwright.config.*` is kept, and READ. Its top-level
`testDir` decides where the three test files go: a string literal, or a name
bound to exactly one; absent means Playwright's default (the config's own
directory), so `tests/` is still collected. Any other value -- a call, an
env lookup, an absolute path, one that leaves the config's directory -- is
"could not tell": no test file is written, the `skip` line says why, and the
run exits 1. When the config lacks the `setup`, `axe` or `visual` project, or
the visual project's gate on the pinned image, each is an advisory `gap`
line followed by a snippet to paste into `projects: [...]` -- the scaffold
never writes into a config it did not create, so a gap is advice and does
not change the exit code. Where `*-snapshots/` baselines under `testDir` are
all named for one declared project (`<arg>-<project>-<platform>.png`, the
default layout), the visual snippet carries a `snapshotPathTemplate` that
keeps finding them; baselines named for no declared project, or for several,
are reported and the template is left out.

Credentials: the auth setup file -- and, in a config this creates, the
`setup` project, `storageState` and `dependencies: ['setup']` -- exist only
when credentials are recorded: `.crew/secrets.md` at `--root`, or a
`storageState` the existing config already declares. Otherwise a `skip` line
says so, `setup` is not reported as a gap, and the exit code is unaffected.

Test Agents: `npx -y --package=@playwright/test@<PINNED_PLAYWRIGHT> playwright
init-agents --loop=claude` and `--loop=codex` run at `--root` (with
`--config=<module>/<config>` for a module, so the seed test lands in the
module's `testDir`) on apply unless every one of
the planner, generator and healer files under `.claude/agents/` exists. The
`--package` pin means npx fetches exactly the release crew verifies, never
whatever is current, even before the pinned `npm i` has run. Every file
already under `.claude/agents/` is snapshotted first and put back
byte-for-byte after, so a customised generator or healer survives; an agent
file still missing afterwards is reported and fails the run. The claude loop
writes its own `.mcp.json`, so the file's bytes are captured before and, if
any server that was there is gone or changed after, the original is put back
with only the NEW servers added.

Exit codes: 0 done, nothing to do, or only advisory `gap`/`skip` lines; 1
something was refused (a `--module`, a `testDir` it could not read, a
`.mcp.json` left alone) or failed; 2 usage.
"""
import argparse
import json
import os
import re
import subprocess
import sys

import webtest_guard

PLAYWRIGHT_MCP = "@playwright/mcp@0.0.82"
DEVTOOLS_MCP = "chrome-devtools-mcp@1.10.1"
AGENTS_DIR = os.path.join(".claude", "agents")
AGENT_FILES = tuple(os.path.join(AGENTS_DIR, f"playwright-test-{role}.md")
                    for role in ("planner", "generator", "healer"))
INIT_AGENTS = ("npx", "-y", f"--package=@playwright/test@{webtest_guard.PINNED_PLAYWRIGHT}",
               "playwright", "init-agents")
REQUIRED_PROJECTS = ("setup", "axe", "visual")
IGNORE_LINES = ("/playwright/.auth/", "/test-results/", "/playwright-report/", "/blob-report/")
MODULE_DEPTH = 3
MODULE_SKIP = ("node_modules",)
MARKERS = "no playwright.config.*, angular.json, or Playwright in package.json"
VALUE_END = frozenset((",", "}", ")", ";"))

CONFIG_TS = """import { defineConfig, devices } from '@playwright/test';

const CI = !!process.env.CI;
const PINNED_IMAGE = '%(image)s';
const inPinnedImage = process.env.%(env)s === PINNED_IMAGE;
%(auth_const)sconst browser = { ...devices['Desktop Chrome']%(state)s };

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
%(setup_project)s    {
      name: 'chromium',
      use: browser,
%(deps_line)s      testIgnore: [/.*\\.axe\\.spec\\.ts/, /.*\\.visual\\.spec\\.ts/],
    },
    { name: 'axe', testMatch: /.*\\.axe\\.spec\\.ts/, use: browser%(deps)s },
    ...(inPinnedImage
      ? [{ name: 'visual', testMatch: /.*\\.visual\\.spec\\.ts/, use: browser%(deps)s }]
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


def find_modules(root, depth=MODULE_DEPTH):
    """[(rel, reason)] for every web project below `root`, at most `depth`
    levels down: never inside `MODULE_SKIP` or a dot-directory, and never
    below a directory that is itself one. `rel` uses forward slashes."""
    found = []

    def walk(path, rel, level):
        try:
            entries = sorted(os.scandir(path), key=lambda e: e.name)
        except OSError:
            return
        for entry in entries:
            if entry.name in MODULE_SKIP or entry.name.startswith("."):
                continue
            if not entry.is_dir(follow_symlinks=False):
                continue
            sub = f"{rel}/{entry.name}" if rel else entry.name
            try:
                reason = detect(entry.path)
            except OSError:
                reason = None
            if reason:
                found.append((sub, reason))
            elif level < depth:
                walk(entry.path, sub, level + 1)

    walk(root, "", 1)
    return sorted(found)


def resolve_module(root, value):
    """(rel, problem): `value` as a forward-slash path under `root`, or why
    it is refused. `rel` None with no problem means `--root` itself."""
    rel = value.replace("\\", "/")
    if os.path.isabs(value) or rel.startswith("/") or re.match(r"^[A-Za-z]:", rel):
        return None, "is absolute"
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if ".." in parts:
        return None, "is not relative to --root"
    if not parts:
        return None, None
    path = os.path.join(root, *parts)
    if not os.path.exists(path):
        return None, "does not exist"
    if not os.path.isdir(path):
        return None, "is not a directory"
    if detect(path) is None:
        return None, f"is not a web project ({MARKERS})"
    return "/".join(parts), None


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


def project_names(text):
    """Every `name: '<literal>'` in a config: its projects, by name."""
    toks = webtest_guard.tokens(text)
    return {toks[i + 2][1] for i in range(len(toks) - 2)
            if toks[i][1] == "name" and toks[i + 1][1] == ":" and toks[i + 2][0] == "str"}


def config_gaps(text, credentials=True):
    """What an existing config lacks of what crew's rules run: each missing
    project by name (`setup` only when credentials are recorded), and
    `gate` when a `visual` project exists without the pinned-image gate."""
    named = project_names(text)
    gaps = [p for p in REQUIRED_PROJECTS if p not in named and (p != "setup" or credentials)]
    if "visual" in named and webtest_guard.PINNED_IMAGE not in text:
        gaps.append("gate")
    return gaps


def _tok(toks, i):
    return toks[i] if 0 <= i < len(toks) else (None, None, None)


def _bindings(toks):
    """{name: [literal or None, ...]} for every `const/let/var NAME = ...`."""
    consts = {}
    for i, (kind, value, _line) in enumerate(toks):
        if kind == "id" and value in ("const", "let", "var") and _tok(toks, i + 2)[1] == "=":
            name, rhs, end = _tok(toks, i + 1)[1], _tok(toks, i + 3), _tok(toks, i + 4)
            literal = rhs[0] == "str" and (end[1] in VALUE_END or end[0] in ("id", None))
            consts.setdefault(name, []).append(rhs[1] if literal else None)
    return consts


def _testdir_exprs(toks):
    """[(depth, expr tokens)] for each `testDir:` / `{ testDir }`; depth
    counts the `{` and `[` around it, so the config object itself is 1."""
    out, depth = [], 0
    for i, (kind, value, _line) in enumerate(toks):
        if kind == "p" and value in ("{", "["):
            depth += 1
        elif kind == "p" and value in ("}", "]"):
            depth -= 1
        if kind not in ("id", "str") or value != "testDir":
            continue
        nxt = _tok(toks, i + 1)
        if nxt[1] == ":":
            j, inner, expr = i + 2, 0, []
            while j < len(toks) and not (inner == 0 and toks[j][1] in VALUE_END):
                inner += {"(": 1, "[": 1, "{": 1, ")": -1, "]": -1, "}": -1}.get(toks[j][1], 0)
                expr.append(toks[j])
                j += 1
            out.append((depth, expr))
        elif kind == "id" and _tok(toks, i - 1)[1] in ("{", ",") and nxt[1] in (",", "}"):
            out.append((depth, [toks[i]]))
    return out


def _testdir_value(expr, consts):
    """(literal, problem) for one `testDir` expression."""
    snippet = " ".join(t[1] for t in expr[:8]) or "(empty)"
    value = None
    if len(expr) == 1 and expr[0][0] == "str" and "${}" not in expr[0][1]:
        value = expr[0][1]
    elif len(expr) == 1 and expr[0][0] == "id":
        bound = consts.get(expr[0][1], [None])
        if None not in bound and len(set(bound)) == 1:
            value = bound[0]
    if value is None:
        return None, f"`{snippet}` is not a string literal or a name bound to exactly one"
    value = re.sub(r"/+", "/", value.replace("\\", "/"))
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        return None, f"`{snippet}` is absolute"
    parts = [p for p in value.split("/") if p not in ("", ".")]
    if ".." in parts:
        return None, f"`{snippet}` leaves the config's directory"
    return "/".join(parts), None


def test_dir(text):
    """(rel, problem) for a config's top-level `testDir`. (None, None) when
    it has none -- or names the config's own directory -- which is
    Playwright's default. `problem` says why the value could not be read;
    it is never replaced by a guess."""
    toks = webtest_guard.tokens(text)
    top = [expr for depth, expr in _testdir_exprs(toks) if depth == 1]
    if not top:
        return None, None
    consts = _bindings(toks)
    values = [_testdir_value(expr, consts) for expr in top]
    problems = [problem for _value, problem in values if problem]
    if problems:
        return None, problems[0]
    found = {value for value, _problem in values}
    if len(found) > 1:
        return None, f"is set {len(top)} times to different values ({', '.join(sorted(found))})"
    return (found.pop() or None), None


def baselines(project, scan, named):
    """(project_name_or_None, sentence_or_None) for the `*-snapshots/`
    baselines under `<project>/<scan>`: the one declared project they are all
    named for, and the sentence the visual gap line carries."""
    top = os.path.join(project, *scan.split("/")) if scan else project
    where = scan or "."
    matched, unmatched = {}, []
    names = sorted(named, key=len, reverse=True)
    for base, dirs, files in os.walk(top):
        dirs[:] = sorted(d for d in dirs if d not in MODULE_SKIP and not d.startswith("."))
        rel = os.path.relpath(base, project).replace(os.sep, "/")
        if not any(seg.endswith("-snapshots") for seg in rel.split("/")):
            continue
        for name in sorted(files):
            path = f"{rel}/{name}"
            stem = os.path.splitext(name)[0]
            owner = next((n for n in names
                          if re.search(rf"-{re.escape(n)}-(?:linux|darwin|win32)$", stem)), None)
            (matched.setdefault(owner, []) if owner else unmatched).append(path)
    unset = "snapshotPathTemplate left unset - check them by hand before adding the project"
    if len(matched) == 1:
        owner, paths = next(iter(matched.items()))
        return owner, (f"{len(paths)} baseline(s) under {where} are named for project '{owner}' "
                       f"(e.g. {paths[0]}); the template keeps them")
    if matched:
        example = sorted(p for paths in matched.values() for p in paths)[0]
        return None, (f"baselines under {where} are named for several projects "
                      f"({', '.join(sorted(matched))}) (e.g. {example}); {unset}")
    if unmatched:
        return None, (f"baselines exist under {where} but none is named for a project this config "
                      f"declares (e.g. {unmatched[0]}); {unset}")
    return None, None


def gap_lines(key, config, named, baseline):
    """(line, snippet lines) for one gap `config_gaps` named."""
    deps = ", dependencies: ['setup']" if "setup" in named else ""
    browser = "use: { ...devices['Desktop Chrome'] }"
    gate = f"...(process.env.{webtest_guard.IMAGE_ENV} === '{webtest_guard.PINNED_IMAGE}'"
    paste = f"{config} lacks the '{key}' project - paste into projects[]"
    if key == "setup":
        return f"{paste}:", ["{ name: 'setup', testMatch: /.*\\.setup\\.ts/ },"]
    if key == "axe":
        return f"{paste}:", [f"{{ name: 'axe', testMatch: /.*\\.axe\\.spec\\.ts/, {browser}{deps} }},"]
    if key == "gate":
        return (f"{config} lacks the visual project's gate on {webtest_guard.PINNED_IMAGE} - wrap "
                "the existing 'visual' entry in:", [f"{gate} ? [", "  <the existing 'visual' entry>",
                                                    "] : []),"])
    owner, sentence = baseline
    template = (f", snapshotPathTemplate: '{{snapshotDir}}/{{testFileDir}}/{{testFileName}}"
                f"-snapshots/{{arg}}-{owner}-{{platform}}{{ext}}'" if owner else "")
    return (f"{paste}{' (' + sentence + ')' if sentence else ''}:",
            [gate, f"  ? [{{ name: 'visual', testMatch: /.*\\.visual\\.spec\\.ts/, {browser}{deps}"
                   f"{template} }}]", "  : []),"])


def credentials_recorded(root, config_text):
    """(recorded, reason): `.crew/secrets.md` at `root`, or a storageState the
    config already declares (a literal or not). Nothing else is inferred."""
    if os.path.isfile(os.path.join(root, ".crew", "secrets.md")):
        return True, f".crew/secrets.md at {root}"
    paths, unresolved = webtest_guard.storage_state_values(config_text or "")
    if paths or unresolved:
        return True, "storageState declared in the config"
    return False, f".crew/secrets.md absent at {root}; no storageState in the config"


def fresh_config(angular, credentials):
    """CONFIG_TS for a repository with no config; the auth pieces only with
    credentials (with them, byte-identical to crew 1.0.59's template)."""
    auth = {"auth_const": "const authFile = 'playwright/.auth/user.json';\n",
            "state": ", storageState: authFile",
            "setup_project": "    { name: 'setup', testMatch: /.*\\.setup\\.ts/ },\n",
            "deps_line": "      dependencies: ['setup'],\n", "deps": ", dependencies: ['setup']"}
    return CONFIG_TS % dict({k: v if credentials else "" for k, v in auth.items()},
                            image=webtest_guard.PINNED_IMAGE, env=webtest_guard.IMAGE_ENV,
                            base_url="http://localhost:4200" if angular else "http://localhost:3000")


def _existing_config(root):
    names = sorted(n for n in os.listdir(root) if n.startswith("playwright.config."))
    return names[0] if names else None


def plan(root, windows, module=None):
    """[(kind, where, rel, text, note)]: kind write/keep/skip/refuse/gap,
    where `module` (the web project) or `root` (what a session loads). A
    gap's rel is its whole line and its text the snippet."""
    project = os.path.join(root, *module.split("/")) if module else root
    angular = os.path.exists(os.path.join(project, "angular.json"))
    existing = _existing_config(project)
    text = _read(os.path.join(project, existing)) if existing else None
    creds, why = credentials_recorded(root, text)
    literal, problem = test_dir(text) if existing else (None, None)
    base = literal or "tests"
    items = []
    if existing:
        items.append(("keep", "module", existing, None, "exists - kept"))
    else:
        items.append(("write", "module", "playwright.config.ts", fresh_config(angular, creds),
                      "create"))
    if problem:
        items.append(("refuse", "module", existing, None,
                      f"testDir {problem} - could not tell where tests are collected; "
                      "auth.setup.ts, fixtures/axe.ts, home.axe.spec.ts not written"))
    else:
        for name, body in (("auth.setup.ts", AUTH_SETUP_TS), ("fixtures/axe.ts", AXE_FIXTURE_TS),
                           ("home.axe.spec.ts", AXE_SPEC_TS)):
            rel = f"{base}/{name}"
            if os.path.exists(os.path.join(project, *rel.split("/"))):
                items.append(("keep", "module", rel, None, "exists - kept"))
            elif name == "auth.setup.ts" and not creds:
                items.append(("skip", "module", rel, None, f"no credentials recorded ({why}) - "
                              "see crew-verification; nothing written"))
            else:
                items.append(("write", "module", rel, body, "create"))
    if existing:
        named = project_names(text or "")
        config = f"{module}/{existing}" if module else existing
        baseline = baselines(project, literal or "", named)
        for key in config_gaps(text or "", creds):
            line, snippet = gap_lines(key, config, named, baseline)
            items.append(("gap", "module", line, "\n".join(snippet), None))
    new, added = merge_ignore(_read(os.path.join(project, ".gitignore")))
    items.append(("write" if new else "keep", "module", ".gitignore", new,
                  f"add {', '.join(added)}" if added else "already ignores"))
    servers = mcp_servers(windows)
    new, added, bad = merge_mcp(_read(os.path.join(root, ".mcp.json")), servers)
    items.append(("write" if new else "keep", "root", ".mcp.json", new,
                  bad or (f"add {', '.join(added)}" if added else "servers present - kept")))
    new, added = merge_codex(_read(os.path.join(root, ".codex", "config.toml")), servers)
    items.append(("write" if new else "keep", "root", ".codex/config.toml", new,
                  f"add {', '.join(added)}" if added else "servers present - kept"))
    return items


def _write(root, rel, text):
    path = os.path.join(root, *rel.split("/"))
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


def missing_agents(root):
    return [a.replace(os.sep, "/") for a in AGENT_FILES if not os.path.exists(os.path.join(root, a))]


def _snapshot_agents(root):
    """{path: bytes} for every file already under `.claude/agents/`."""
    found = {}
    for base, _dirs, files in os.walk(os.path.join(root, AGENTS_DIR)):
        for name in files:
            path = os.path.join(base, name)
            with open(path, "rb") as fh:
                found[path] = fh.read()
    return found


def _restore_agents(root, snapshot):
    """Put back every snapshotted file init-agents changed or removed."""
    out = []
    for path, data in sorted(snapshot.items()):
        try:
            with open(path, "rb") as fh:
                same = fh.read() == data
        except OSError:
            same = False
        if not same:
            tmp = f"{path}.{os.getpid()}.tmp"
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "wb") as fh:
                fh.write(data)
            os.replace(tmp, path)
            out.append(f"  restore {os.path.relpath(path, root).replace(os.sep, '/')} as it was")
    return out


def agent_cmd(loop, config_rel=None):
    """The init-agents command for one loop; `config_rel` (a module's config,
    relative to the root it runs in) puts the seed test in that module."""
    return list(INIT_AGENTS) + [f"--loop={loop}"] + ([f"--config={config_rel}"] if config_rel else [])


def run_agents(root, windows, config_rel=None, runner=subprocess.call):
    """Lines to report. `runner` is injectable so tests never run npx; it
    stays the last keyword so a test's `__defaults__` stub binds it."""
    missing = missing_agents(root)
    if not missing:
        return ["  keep    Test Agents (planner, generator and healer all exist)"], True
    kept = _snapshot_agents(root)
    mcp_path = os.path.join(root, ".mcp.json")
    before = _read(mcp_path)
    out, ok = [f"  missing {', '.join(missing)}"], True
    for loop in ("claude", "codex"):
        cmd = agent_cmd(loop, config_rel)
        rc = runner((["cmd", "/c"] if windows else []) + cmd, cwd=root)
        out.append(f"  {'ran' if rc == 0 else 'FAILED'}     {' '.join(cmd)} (exit {rc})")
        ok = ok and rc == 0
    out += _restore_agents(root, kept)
    still = missing_agents(root)
    if still:
        out.append(f"  FAILED  init-agents left {', '.join(still)} missing")
        ok = False
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
    parser.add_argument("--module", help="a web project below --root; module-scoped files go "
                                         "there, session files stay at --root")
    parser.add_argument("--windows", action="store_true", default=os.name == "nt",
                        help="write cmd /c MCP wrappers (default: this host is Windows)")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    module = None
    if args.module is not None:
        module, problem = resolve_module(root, args.module)
        if problem:
            print(f"webtest scaffold: refused: --module {args.module} {problem}")
            return 1
    project = os.path.join(root, *module.split("/")) if module else root
    reason = detect(project)
    if not reason:
        print(f"webtest scaffold: n/a at {root} - {MARKERS}")
        found = find_modules(root)
        skipped = "node_modules and dot-directories"
        print("\n".join([f"  module  {rel} ({why}) -> --module {rel}" for rel, why in found] + [
            f"  searched {MODULE_DEPTH} directory levels below --root, skipping {skipped}"
            if found else f"  no module found within {MODULE_DEPTH} levels (skipping {skipped})"]))
        return 0
    mode = "apply" if args.apply else "dry run"
    print(f"webtest scaffold ({mode}): web project detected by {reason} in {module or '.'}; "
          f"session files at {root}")
    items = plan(root, args.windows, module)
    ok = True
    for kind, where, rel, text, note in items:
        label = f"{module}/{rel}" if module and where == "module" else rel
        if kind == "gap":
            print("\n".join([f"  gap     {rel}"] + [f"          {s}" for s in text.splitlines()]))
            continue
        if kind in ("skip", "refuse"):
            print(f"  skip    {label}: {note}")
            ok = ok and kind != "refuse"
            continue
        if kind == "keep":
            print(f"  keep    {label}: {note}")
            ok = ok and "left alone" not in note
            continue
        print(f"  write   {label}: {note}")
        if args.apply:
            _write(project if where == "module" else root, rel, text)
    config_rel = f"{module}/{_existing_config(project) or 'playwright.config.ts'}" if module else None
    if args.apply:
        lines, agents_ok = run_agents(root, args.windows, config_rel)
        ok = ok and agents_ok
    elif not missing_agents(root):
        lines = ["  keep    Test Agents (planner, generator and healer all exist)"]
    else:
        lines = [f"  missing {', '.join(missing_agents(root))}"] + [
            f"  run     {' '.join(agent_cmd(loop, config_rel))}" for loop in ("claude", "codex")]
    print("\n".join(lines))
    npm = (f"npm i -D @playwright/test@{webtest_guard.PINNED_PLAYWRIGHT} "
           "@axe-core/playwright@4.13.0 && npx playwright install --with-deps chromium")
    print(f"next: (cd {module} && {npm})" if module else f"next: {npm}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
