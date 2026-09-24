"""The canonical `verify.json` rules for a Playwright web project.

    python3 webtest_rules.py [--paths GLOB ...]

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
  4. `webtest_guard.py skips` -- no skip added since the ticket's base that
     the spec's Exclusions do not name.
  5. `webtest_guard.py visual` -- runs the visual project inside
     `PINNED_IMAGE`, exits 77 (SKIP, reported UNVERIFIED, never PASS) anywhere
     else.

Guard commands name `${CLAUDE_PLUGIN_ROOT:?...}`: the verify gate runs as a
plugin hook, which has it set; anywhere it is unset the command fails with
that message rather than resolving to `/hooks/scripts/...` and failing
obscurely.
"""
import argparse
import json
import sys

import webtest_guard

DEFAULT_PATHS = ("playwright.config.*", "package.json", "package-lock.json",
                 "src/**", "tests/**", "e2e/**", "specs/**", "angular.json")
SPEC_PATHS = ("**/*.spec.ts", "**/*.spec.js", "**/*.spec.tsx", "**/*.spec.mjs",
              "**/*.test.ts", "**/*.test.js", "**/*.test.tsx", "**/*.test.mjs")
AUTH_PATHS = ("playwright/**", "playwright.config.*", ".gitignore", "**/.auth/**")
GUARD = ('python3 "${CLAUDE_PLUGIN_ROOT:?crew plugin root not set - run from the '
         'crew verify gate}/hooks/scripts/webtest_guard.py"')


def rules(paths=DEFAULT_PATHS):
    paths = list(paths)
    return [
        {"paths": paths, "reach": "local",
         "run": ["npx playwright test --reporter=blob",
                 "npx playwright merge-reports --reporter html ./blob-report"],
         "why": "The suite's exit code, then one HTML report from the blob shards. "
                "Visual diffs are not in it off the pinned image; rule 5 owns them."},
        {"paths": paths, "reach": "local",
         "run": ["npx playwright test --project=axe --reporter=line"],
         "why": "Zero axe violations (wcag2a/aa, wcag21a/aa), asserted by the axe "
                "fixture. Also inside rule 1; separate so the failure names itself."},
        {"paths": list(AUTH_PATHS), "reach": "local",
         "run": [f"{GUARD} auth-leak --root ."],
         "why": "playwright/.auth holds live session state; git ls-files of it, and of "
                "any storageState path in playwright.config, must be empty."},
        {"paths": list(SPEC_PATHS), "reach": "local",
         "run": [f"{GUARD} skips --root ."],
         "why": "A healer skip is a finding, never accepted: any .skip/.fixme/test.fail "
                "added since the ticket's base fails unless the spec's Exclusions name it."},
        {"paths": paths + ["**/__screenshots__/**"], "reach": "local",
         "run": [f"{GUARD} visual --root ."],
         "why": f"Screenshot diffs compare only inside {webtest_guard.PINNED_IMAGE}; "
                "anywhere else this exits 77 and reads UNVERIFIED, never PASS."},
    ]


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--paths", nargs="+", default=list(DEFAULT_PATHS))
    args = parser.parse_args(argv)
    print(json.dumps({"rules": rules(args.paths)}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
