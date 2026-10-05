#!/usr/bin/env python3
"""Which heavy Linux CI suites a pull request has to run (C-0001).

    python3 scripts/ci-select.py --event <github.event_name> [--output "$GITHUB_OUTPUT"]
                                 [--base HEAD^1] [--head HEAD] [--paths-from FILE]

Owner, 2026-10-05: "if only a document was changed, none of these checks will
run ... just like the other ones that check for different plugins", then "each
plugin/skill suite should skip when that component did not change". The four
workflows that call this -- pytest-crew.yml, pylint.yml, shell-suites.yml and
mcp-servers.yml -- read their decision from this ONE script, so the rule cannot
drift between them. marketplace.yml, instruction-budgets.yml, verify-gate.yml
and plugin-evals.yml never call it and always run.

Not an `on: pull_request: paths:` filter: that drops the whole workflow and
leaves its required checks pending. Every job still runs and reports its
required check name; its suite steps are gated on these outputs, and a skipped
suite prints a `::notice::` saying SKIPPED, not passed.

THE RULE. Only a `pull_request` is ever narrowed; push, schedule and
workflow_dispatch select everything. On a pull request the changed paths are
`git diff --name-only --no-renames HEAD^1 HEAD` on the PR merge commit (a rename
is its old path AND its new path, so moving a file out of a component still
runs that component). Each path then selects:

  * inside a COMPONENT (one row of COMPONENTS): that component's suites, plus
    every READER whose glob it matches, plus every combined component when
    it can change the combined pytest session (PYTEST_CONFIGS), plus `lint`
    when it is Python or lint configuration;
  * inside any other `plugin/<name>/` or `skills/<name>/` (a marketplace entry
    no skippable suite tests): only the READERS whose glob it matches, plus
    `lint` when it is Python or lint configuration;
  * a PLAIN DOCUMENT (is_plain_doc): only the READERS whose glob it matches --
    for most documents the two crew files that scan every document;
  * anything else (scripts/, .github/, .crew/, .claude/, root files, a doc a
    suite is known to read but that is not mapped, this script): EVERYTHING.

Everything is also the answer whenever the answer is not known: the diff fails,
the PR head is not a merge commit, the diff is empty, or this script raises.
An unknown must not read as "nothing changed".

READERS are suites that read files outside their own component. They were
found on 2026-10-05 by running every skippable suite under
`strace -f -e openat,execve` (what each opened under the checkout, child
processes included), attributing crew's reads to its test files with a
per-test audit hook, then reading each reading test to turn the paths into
globs that also cover files that do not exist yet. Reads of paths outside
every component (.crew/verify.json, scripts/, .github/, _verify/, .gitignore,
docs/ non-Markdown) need no row: those paths select everything anyway.
scripts/_test/ci-select.py pins the rows.

Outputs (one `key=value` line each, appended to --output; printed when none):
  combined         true|false: whether pytest-crew.yml's combined run runs
  pytest_combined  space-separated pytest paths for that run (COMBINED order,
                   then single crew files); the workflow falls back to the
                   whole COMBINED list when this is missing
  crew             true|false: crew's whole suite (wallclock run, the slow
                   hook matrix in crew-shell-matrix)
  <component>      true|false for every other COMPONENTS key
  lint             true|false: pylint and ruff
  all              true when everything was selected

Exit 0 with outputs written; exit 1 only when the outputs could not be written
(the calling step then fails, which is red, not skipped). Exit 2: usage.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import subprocess
import sys

# (output key, component root, its directory in pytest-crew.yml's combined run
# or None). The non-combined suites are gated on the key by name: cisco_meraki
# and wazuh_onprem are their own pytest processes in pytest-crew.yml,
# bitbucket, doc_builder, jira_manager and obsidian_vault are shell-suites.yml
# steps (doc_builder is also in the combined run), mcp_servers is
# mcp-servers.yml.
COMPONENTS = (
    ("crew", "plugin/crew/", "plugin/crew/tests/"),
    ("gizmoduck", "plugin/gizmoduck/", "plugin/gizmoduck/scripts/_test/"),
    ("mermaid_svg_bitbucket", "skills/mermaid-svg-bitbucket/", "skills/mermaid-svg-bitbucket/tests/"),
    ("notify", "skills/notify/", "skills/notify/tests/"),
    ("doc_builder", "skills/doc-builder/", "skills/doc-builder/scripts/_test/"),
    ("intune_graph", "skills/intune-graph/", "skills/intune-graph/scripts/_test/"),
    ("cisco_meraki", "skills/cisco-meraki/", None),
    ("wazuh_onprem", "skills/wazuh-onprem/", None),
    ("bitbucket", "skills/bitbucket/", None),
    ("jira_manager", "skills/jira-manager/", None),
    ("obsidian_vault", "plugin/obsidian-vault/", None),
    ("mcp_servers", "mcp-servers/", None),
)
KEYS = tuple(key for key, _root, _dir in COMPONENTS)
COMBINED_KEYS = frozenset(key for key, _root, d in COMPONENTS if d)
# pytest-crew.yml's combined run, in the order it has always listed them;
# scripts/gate-runner.py's COMBINED_DIRS is the same list (the suite checks).
COMBINED = tuple(d for _key, _root, d in COMPONENTS if d)

# (glob, target). A changed path matching the glob selects the target: a
# COMPONENTS key (that component's whole suite) or one crew test file (only
# that file, in the combined run). A file is named instead of all of crew only
# when it has no `slow` or `wallclock` test, since the combined run deselects
# both. Globs use fnmatch, so `*` crosses `/`.
CREW = "plugin/crew/tests/"
READERS = (
    # Repo-wide scans inside crew's suite. Every path selects the first: it
    # reads EVERY tracked file (`git ls-files`) for a SendWait call outside
    # auto-clear.ps1's gated child, documents included.
    ("*", CREW + "test_sendkeys_structural_gate.py"),
    # Walks the checkout for .md and .html and fails on a runnable
    # `codex exec --profile review|work`.
    ("*.md", CREW + "test_crew_instructions.py"),
    ("*.html", CREW + "test_crew_instructions.py"),
    # Scans every .py under plugin/ and skills/ for bare tool names.
    ("plugin/*.py", CREW + "test_tool_resolution.py"),
    ("skills/*.py", CREW + "test_tool_resolution.py"),
    # Scans every tracked .py and .sh under a tests/ or _test/ directory for
    # a pwsh spawn without its own cache directory.
    ("*/tests/*.py", CREW + "test_pwsh_cache_isolation.py"),
    ("*/tests/*.sh", CREW + "test_pwsh_cache_isolation.py"),
    ("*/_test/*.py", CREW + "test_pwsh_cache_isolation.py"),
    ("*/_test/*.sh", CREW + "test_pwsh_cache_isolation.py"),
    # The crew user guides' sources, which these quote or check against.
    ("docs/guides/crew/*.md", CREW + "test_crew_autopilot_policy.py"),
    ("docs/guides/crew/*.md", CREW + "test_crew_resume.py"),
    ("docs/guides/crew/*.md", CREW + "test_crew_train.py"),
    ("docs/guides/crew/*.md", CREW + "test_status_vocabulary.py"),
    ("docs/guides/crew/*.md", CREW + "test_troubleshooting_guide.py"),
    # doc-builder's scripts, which crew's docs routing imports and runs.
    ("skills/doc-builder/scripts/*", CREW + "test_docs_routing.py"),
    ("skills/doc-builder/scripts/*", CREW + "test_sabotage_harness.py"),
    # The bitbucket and github merge gates crew's promote step drives.
    ("skills/bitbucket/scripts/*", CREW + "test_gate_command.py"),
    ("skills/bitbucket/scripts/*", CREW + "test_promote_merge_gate.py"),
    ("skills/bitbucket/scripts/*", CREW + "test_sabotage_harness.py"),
    ("skills/github/scripts/*", CREW + "test_gate_command.py"),
    # doc-builder discovers brand packs (any */assets/brand.json) and its
    # suites build with solomon-doc-builder's brand, logos and template.
    ("*assets/brand.json", "doc_builder"),
    ("skills/solomon-doc-builder/*", "doc_builder"),
    # obsidian-vault's probe test compares its resolver with crew's.
    ("plugin/crew/hooks/scripts/role-write-guard.ps1", "obsidian_vault"),
)

LINT_SUFFIXES = (".py", ".pyi", ".ipynb")
# Lint configuration: ruff and pylint read the nearest one, so one inside a
# plugin or skill changes what lint reports there (plugin/localgpu ships a
# pyproject.toml today).
LINT_CONFIGS = ("ruff.toml", ".ruff.toml", "pyproject.toml", ".pylintrc", "pylintrc")

# The combined run is ONE pytest session, and a subset of it is not the same
# session: test modules have no __init__.py, so two test dirs holding the same
# module basename collide ("import file mismatch") only when both are
# collected, and a conftest or pytest config in one dir can change the whole
# session. So a change to any of these inside a combined component selects
# every combined component (COMBINED_KEYS):
#   * any .py under that component's combined test directory;
#   * a test module anywhere in it (test_*.py, *_test.py);
#   * a conftest.py or a pytest configuration file anywhere in it.
# pytest-crew.yml also pins the session's configuration for every subset
# (`-c plugin/gizmoduck/pytest.ini --rootdir plugin/gizmoduck`, what pytest
# resolves on its own for the full list), and scripts/_test/ci-select.py
# fails when two combined test dirs already share a module basename.
PYTEST_CONFIGS = ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini")

# Documents that are never "plain", wherever a suite stands: the repo's own
# instructions, its release notes, and the catalog/mirror documents that the
# registration and sync checks treat as data.
NOT_PLAIN_NAMES = ("README.md", "CHANGELOG.md", "CLAUDE.md", "AGENTS.md", "UPDATE.md")
NOT_PLAIN_ROOTS = ("plugin/", "skills/", "mcp-servers/", ".claude/", ".crew/", ".github/")
# Plain-looking documents a skippable suite reads but READERS cannot map: a
# change to one selects everything. Empty: the documents the 2026-10-05 trace
# found suites reading by name (docs/guides/crew/**) are mapped in READERS.
READ_DOCS = ()


def is_plain_doc(path: str) -> bool:
    """A Markdown file no skippable suite treats as input."""
    if not path.endswith(".md") or path.startswith(NOT_PLAIN_ROOTS):
        return False
    if path.rsplit("/", 1)[-1] in NOT_PLAIN_NAMES:
        return False
    return not any(path == doc or fnmatch.fnmatchcase(path, doc) for doc in READ_DOCS)


def component_of(path: str):
    """(key or None, inside_a_marketplace_entry)."""
    for key, root, _dir in COMPONENTS:
        if path.startswith(root):
            return key, True
    parts = path.split("/")
    if len(parts) >= 3 and parts[0] in ("plugin", "skills"):
        return None, True
    return None, False


def touches_combined_session(key, path: str) -> bool:
    """True when `path`, inside component `key`, can change the combined
    pytest session as a whole (see PYTEST_CONFIGS)."""
    if key not in COMBINED_KEYS:
        return False
    test_dir = next(d for k, _root, d in COMPONENTS if k == key)
    name = path.rsplit("/", 1)[-1]
    return ((path.startswith(test_dir) and path.endswith(".py"))
            or fnmatch.fnmatchcase(name, "test_*.py") or fnmatch.fnmatchcase(name, "*_test.py")
            or name in PYTEST_CONFIGS)


def everything() -> dict:
    return {"keys": set(KEYS), "crew_files": set(), "lint": True, "all": True}


def select(paths) -> tuple[dict, list]:
    """The selection for these changed paths, and one reason line per path
    that selected everything."""
    paths = [p for p in paths if p]
    if not paths:
        return everything(), ["the diff is empty, so what changed is unknown"]
    keys, files, lint, why_all = set(), set(), False, []
    for path in paths:
        targets = {t for glob, t in READERS if fnmatch.fnmatchcase(path, glob)}
        key, in_entry = component_of(path)
        if key:
            targets.add(key)
            if touches_combined_session(key, path):
                targets |= COMBINED_KEYS
        elif not in_entry and not is_plain_doc(path):
            why_all.append(path)
            continue
        if in_entry and (path.endswith(LINT_SUFFIXES) or path.rsplit("/", 1)[-1] in LINT_CONFIGS):
            lint = True
        for target in targets:
            (files if target.startswith("plugin/crew/tests/") else keys).add(target)
    if why_all:
        return everything(), [f"{p} is outside every component and not a plain document"
                              for p in why_all]
    if "crew" in keys:
        files = set()
    return {"keys": keys, "crew_files": files, "lint": lint, "all": False}, []


def outputs(sel: dict) -> list:
    combined = [d for key, _root, d in COMPONENTS if d and key in sel["keys"]]
    combined += sorted(sel["crew_files"])
    lines = [f"combined={'true' if combined else 'false'}", f"pytest_combined={' '.join(combined)}"]
    lines += [f"{key}={'true' if key in sel['keys'] else 'false'}" for key in KEYS]
    lines.append(f"lint={'true' if sel['lint'] else 'false'}")
    lines.append(f"all={'true' if sel['all'] else 'false'}")
    return lines


def changed_paths(base: str, head: str):
    """The PR's changed paths, or (None, reason) when they cannot be known."""
    def git(*args):
        return subprocess.run(["git", "-c", "core.quotePath=false", *args], capture_output=True,
                              check=False, stdin=subprocess.DEVNULL, timeout=60)
    second = git("rev-parse", "--verify", "--quiet", f"{head}^2")
    if second.returncode != 0:
        return None, f"{head} is not a merge commit, so it is not the PR merge result"
    done = git("diff", "--name-only", "--no-renames", "-z", base, head)
    if done.returncode != 0:
        err = done.stderr.decode("utf-8", "replace").strip()
        return None, f"git diff {base} {head} failed (exit {done.returncode}): {err}"
    return [p for p in done.stdout.decode("utf-8", "replace").split("\0") if p], None


def decide(args) -> tuple[dict, list]:
    if args.event != "pull_request":
        return everything(), [f"event {args.event!r} always runs everything"]
    if args.paths_from:
        with open(args.paths_from, encoding="utf-8") as fh:
            paths = [line.rstrip("\n") for line in fh]
    else:
        paths, err = changed_paths(args.base, args.head)
        if paths is None:
            print(f"::warning::ci-select: {err}; every suite runs.")
            return everything(), [err]
    return select(paths)


def describe(sel: dict) -> str:
    names = sorted(sel["keys"]) + sorted(os.path.basename(f) for f in sel["crew_files"])
    names += ["lint"] if sel["lint"] else []
    return ", ".join(names) or "nothing"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--event", required=True)
    ap.add_argument("--output", help="file to append key=value lines to ($GITHUB_OUTPUT)")
    ap.add_argument("--base", default="HEAD^1")
    ap.add_argument("--head", default="HEAD")
    ap.add_argument("--paths-from", help="read changed paths from this file (tests)")
    args = ap.parse_args(argv)
    try:
        sel, reasons = decide(args)
    except Exception as exc:  # pylint: disable=broad-exception-caught
        # Fail closed: any error at all selects everything.
        print(f"::warning::ci-select raised {type(exc).__name__}: {exc}; every suite runs.")
        sel, reasons = everything(), [f"ci-select raised {type(exc).__name__}"]
    lines = outputs(sel)
    if sel["all"]:
        print(f"ci-select: everything runs ({'; '.join(reasons[:5])})")
    else:
        skipped = [k for k in KEYS if k not in sel["keys"]] + ([] if sel["lint"] else ["lint"])
        print(f"::notice::ci-select: this PR selects {describe(sel)}. SKIPPED, not passed: "
              f"{', '.join(skipped) or 'nothing'}. Every suite runs on push to main, "
              "workflow_dispatch and any schedule.")
    text = "\n".join(lines) + "\n"
    if not args.output:
        sys.stdout.write(text)
        return 0
    try:
        with open(args.output, "a", encoding="utf-8") as fh:
            fh.write(text)
    except OSError as exc:
        print(f"::error::ci-select could not write {args.output}: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
