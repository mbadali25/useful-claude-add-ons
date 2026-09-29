"""The canonical `verify.json` rules for a Playwright web project.

    python3 webtest_rules.py [--root .] [--module DIR] [--paths GLOB ...]

Prints `{"rules": [...]}` for `/crew:verify` or `stack-web` to merge into a
repository's `.crew/verify.json`. This file is the one place the rule shapes
live; anything that proposes them quotes this output rather than restating it.

Five rules, each with `"reach": "local"` (the tests drive a local server
started by the project's own `webServer`) and no `seconds` -- nobody has timed
them in the target repository, and a guessed cost is the fiction that field
exists to replace:

  1. `npx playwright test --reporter=blob`, then `merge-reports` into HTML.
     The exit code is the check. The `visual` project only exists inside the
     pinned image (the scaffolded config gates it), so on a host this rule
     runs everything except visual diffs.
  2. The `axe` project alone, whose fixture asserts zero violations. It also
     ran inside rule 1; it is its own rule so an accessibility failure is
     named as one.
  3. `webtest_guard.py auth-leak` -- no tracked `.auth` or storageState file.
     Watches `.auth/**` at any depth, `**/*storage*state*.json` in either
     case, `.crew/config.json` (where `webtest.storageState` is declared), and
     every storageState path `--root`'s config names or declares, so adding
     the session file itself re-runs the check.
  4. `webtest_guard.py skips` -- no skip added since the ticket's base that
     the spec's Exclusions do not name. Watches every JS/TS extension the
     guard reads (`JS_EXTS`) anywhere in the tree: a helper imported by a spec
     can live outside any test directory, and a skip in it counts.
  5. `webtest_guard.py visual` -- runs the visual project inside
     `PINNED_IMAGE`, exits 77 (SKIP, reported UNVERIFIED, never PASS) anywhere
     else.

`--module DIR` scopes the set to a web project below `--root` (what
`webtest_scaffold.py --module` scaffolds): every watched path is prefixed
`DIR/` (`.crew/config.json` stays at the root, and the skip rule stays
repo-wide, since `skips` reads the whole tree), each `npx` command runs from
the module in a subshell, `(cd DIR && ...)`, and `auth-leak` and `visual`
get `--module DIR`. Rules the module's `playwright.config.*` cannot run are
left out and named on stderr: rule 2 without an `axe` project, rule 5
without a `visual` one (`webtest rules: omitted the <axe|visual> rule - ...`).
The same holds at the root without `--module` when a root config exists. No
config at all omits nothing: the scaffold creates one with every project.

Guard commands name `${CLAUDE_PLUGIN_ROOT:?...}`: the verify gate runs as a
plugin hook, which has it set; anywhere it is unset the command fails with
that message rather than resolving to `/hooks/scripts/...` and failing
obscurely.
"""
import argparse
import json
import os
import shlex
import sys

import crew_common
import webtest_guard

DEFAULT_PATHS = ("playwright.config.*", "package.json", "package-lock.json",
                 "src/**", "tests/**", "e2e/**", "specs/**", "angular.json")
SPEC_PATHS = tuple(f"**/*{ext}" for ext in webtest_guard.JS_EXTS)
AUTH_PATHS = ("playwright/**", "playwright.config.*", ".gitignore", ".auth/**", "**/.auth/**",
              "**/*storage*state*.json", "**/*storage*State*.json", ".crew/config.json")
GUARD = ('python3 "${CLAUDE_PLUGIN_ROOT:?crew plugin root not set - run from the '
         'crew verify gate}/hooks/scripts/webtest_guard.py"')


def _prefix(module, path):
    return f"{module}/{path}" if module else path


def auth_paths(root=None, module=None):
    """AUTH_PATHS plus every storageState path the (module's) playwright
    config names or the root's crew config declares; with `module`, every
    path but `.crew/config.json` is prefixed with it."""
    extra = []
    if root:
        project = webtest_guard.module_dir(root, module)
        found = webtest_guard.config_auth_paths(project)[0] if project else []
        extra = [_prefix(module, p) for p in found] + webtest_guard.declared_storage_state(root)
    base = [p if p == ".crew/config.json" else _prefix(module, p) for p in AUTH_PATHS]
    return base + [p for p in sorted(set(extra)) if p not in base]


def omitted(root, module=None):
    """[(rule, line)] for the axe and visual rules the config cannot run:
    no `axe` / `visual` project named in the (module's) `playwright.config.*`.
    No root, or no config there, omits nothing."""
    project = webtest_guard.module_dir(root, module) if root else None
    if not project:
        return []
    names = sorted(n for n in os.listdir(project) if n.startswith("playwright.config."))
    if not names:
        return []
    toks = webtest_guard.tokens(crew_common.read_text(
        os.path.join(project, names[0])) or "")
    named = {toks[i + 2][1] for i in range(len(toks) - 2)
             if toks[i][1] == "name" and toks[i + 1][1] == ":" and toks[i + 2][0] == "str"}
    scaffold = f"webtest_scaffold.py --module {module}" if module else "webtest_scaffold.py"
    return [(rule, (f"webtest rules: omitted the {rule} rule - no '{rule}' project in "
                    f"{_prefix(module, names[0])} ({scaffold} prints the gap)"))
            for rule in ("axe", "visual") if rule not in named]


def rules(paths=DEFAULT_PATHS, root=None, module=None):
    paths = [_prefix(module, p) for p in paths]
    here = (lambda c: f"(cd {shlex.quote(module)} && {c})") if module else (lambda c: c)
    flag = f" --module {shlex.quote(module)}" if module else ""
    every = [
        ("suite", {"paths": paths, "reach": "local",
                   "run": [here("npx playwright test --reporter=blob"),
                           here("npx playwright merge-reports --reporter html ./blob-report")],
                   "why": "The suite's exit code, then one HTML report from the blob shards. "
                          "Visual diffs are not in it off the pinned image; rule 5 owns them."}),
        ("axe", {"paths": paths, "reach": "local",
                 "run": [here("npx playwright test --project=axe --reporter=line")],
                 "why": "Zero axe violations (wcag2a/aa, wcag21a/aa), asserted by the axe "
                        "fixture. Also inside rule 1; separate so the failure names itself."}),
        ("auth", {"paths": auth_paths(root, module), "reach": "local",
                  "run": [f"{GUARD} auth-leak --root .{flag}"],
                  "why": "playwright/.auth holds live session state; git ls-files of it, and of "
                         "any storageState path in playwright.config, must be empty."}),
        ("skips", {"paths": list(SPEC_PATHS), "reach": "local",
                   "run": [f"{GUARD} skips --root ."],
                   "why": "A healer skip is a finding, never accepted: any .skip/.fixme/test.fail "
                          "added since the ticket's base fails unless the spec's Exclusions name "
                          "it."}),
        ("visual", {"paths": paths + [_prefix(module, "**/__screenshots__/**")], "reach": "local",
                    "run": [f"{GUARD} visual --root .{flag}"],
                    "why": f"Screenshot diffs compare only inside {webtest_guard.PINNED_IMAGE}; "
                           "anywhere else this exits 77 and reads UNVERIFIED, never PASS."}),
    ]
    left_out = {rule for rule, _line in omitted(root, module)}
    return [rule for key, rule in every if key not in left_out]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", nargs="+", default=list(DEFAULT_PATHS))
    parser.add_argument("--root", default=".",
                        help="repository whose storageState paths the auth rule watches")
    parser.add_argument("--module", help="scope the rules to a web project below --root")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root)
    for _rule, line in omitted(root, args.module):
        print(line, file=sys.stderr)
    print(json.dumps({"rules": rules(args.paths, root, args.module)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
