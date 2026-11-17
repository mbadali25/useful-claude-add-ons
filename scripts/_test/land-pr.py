#!/usr/bin/env python3
"""Suite for scripts/land-pr.py: must-do and must-not-do cases.

Every case builds a throwaway world under a temp directory: a bare repository
standing in for GitHub (`remote.git`, with `refs/pull/<n>/head` refs), a seed
clone the case writes branches from, and a local clone handed to the lander as
--repo. The pull request data comes from a --pr-json file, so `gh` is never
called and nothing leaves the machine. Git's global and system configuration
are switched off for the whole run (GIT_CONFIG_GLOBAL, GIT_CONFIG_NOSYSTEM), so
no real configuration is read or written.

The fixture repository carries small stand-ins at the paths of the real
generators and checks (each reads marker files the case commits), plus the
REAL scripts/check-changelog.py, so the changelog lines the lander writes are
judged by the checker CI runs.

Must-not-do, each held by a case: it never merges the pull request (the
remote base branch never moves), never force-pushes (a branch that moved
rejects the push and keeps the other commit), never commits on or pushes to
main, refuses a dirty tree, and never treats an unreadable open PR head as a
lower version. Mutations at the end prove the suite can go red.

Run: python3 scripts/_test/land-pr.py [case-name-substring]
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
TARGET = os.path.join(SCRIPTS, "land-pr.py")

STUB_CHECK = '''import os, sys
name = {name!r}
hook = os.environ.get("LAND_TEST_HOOK")
if hook and os.path.exists(hook) and name == "check-instructions":
    with open(hook, encoding="utf-8") as fh:
        code = fh.read()
    os.remove(hook)
    exec(compile(code, hook, "exec"))
if os.path.exists("FAIL_" + name):
    print("stub " + name + ": failing")
    sys.exit(1)
if os.path.exists("SKIP_" + name):
    sys.exit(77)
sys.exit(0)
'''
STUB_NOOP = "import sys\nsys.exit(0)\n"
STUB_BUILD = '''import os, sys
if "--check" in sys.argv:
    if os.path.exists("GUIDE_STALE"):
        print("stale: crew-guide.html - rebuild")
        sys.exit(1)
    sys.exit(0)
if os.path.exists("GUIDE_STALE"):
    os.remove("GUIDE_STALE")
    sys.exit(3)
sys.exit(0)
'''
STUB_VERSIONED = '''import json, os, sys
target, template = {target!r}, {template!r}
with open("plugin/crew/.claude-plugin/plugin.json", encoding="utf-8") as fh:
    want = template.format(version=json.load(fh)["version"])
have = open(target, encoding="utf-8").read() if os.path.exists(target) else None
if "--check" in sys.argv:
    if have != want:
        print(target + " is stale")
        sys.exit(1)
    sys.exit(0)
os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
with open(target, "w", encoding="utf-8", newline="\\n") as fh:
    fh.write(want)
'''
STUB_SYNC = '''import sys
begin, end = "<!-- BEGIN CHANGELOG.md -->", "<!-- END CHANGELOG.md -->"
log = open("CHANGELOG.md", encoding="utf-8").read().splitlines()
newest = next((line[4:] for line in log if line.startswith("### ")), "")
text = open("README.md", encoding="utf-8").read()
want = text[:text.index(begin) + len(begin)] + "\\n\\n- " + newest + "\\n\\n" + text[text.index(end):]
if "--check" in sys.argv:
    if want != text:
        print("sync-updates: README.md is stale -- run scripts/sync-updates.py")
        sys.exit(1)
    sys.exit(0)
with open("README.md", "w", encoding="utf-8", newline="\\n") as fh:
    fh.write(want)
'''
RULES_TEMPLATE = "rules for crew {version}\n"
REVIEW_TEMPLATE = "<!-- crew-standards-export start crew={version} -->\nrules\n"
OLD_ENTRY = "### Fixed — crew 1.3.0: the first entry\n\n- **Summary.** old.\n"
CHANGELOG = "# Changelog\n\n## [Unreleased]\n\n" + OLD_ENTRY
README = ("# Repo\n\nHand-written.\n\n<!-- BEGIN CHANGELOG.md -->\n\n- Fixed — crew 1.3.0: the "
          "first entry\n\n<!-- END CHANGELOG.md -->\n\nFooter.\n")
PLUGINS = ("# Plugins\n\n| | |\n|---|---|\n| **Source** | crew |\n"
           "| **Version** | {version}<!-- claim: plugin-version:crew --> |\n")
BUDGETS = ("# Budgets\n\n<!-- claim: crew-markdown-lines -->\n`git ls-files` currently totals 0 "
           "lines across 0 files (including this\nfile).\n")


def load():
    spec = importlib.util.spec_from_file_location("land_pr", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sh(cwd, *args):
    done = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False,
                          encoding="utf-8", stdin=subprocess.DEVNULL)
    if done.returncode != 0:
        raise RuntimeError(f"{args} -> {done.returncode}\n{done.stdout}{done.stderr}")
    return done.stdout.strip()


def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path) or root, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def read(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8", newline="") as fh:
        return fh.read()


def market(root, crew, other="1.0.0"):
    write(root, ".claude-plugin/marketplace.json", json.dumps({"plugins": [
        {"name": "crew", "source": "./plugin/crew", "description": "d", "version": crew},
        {"name": "other", "source": "./plugin/other", "description": "d", "version": other}]},
        indent=2) + "\n")
    write(root, "plugin/crew/.claude-plugin/plugin.json",
          json.dumps({"name": "crew", "version": crew}, indent=2) + "\n")
    write(root, "plugin/PLUGINS.md", PLUGINS.format(version=crew))
    write(root, ".claude/rules/crew.md", RULES_TEMPLATE.format(version=crew))
    write(root, "REVIEW.md", REVIEW_TEMPLATE.format(version=crew))


def commit(root, message):
    sh(root, "git", "add", "-A")
    sh(root, "git", "commit", "-q", "-m", message)
    return sh(root, "git", "rev-parse", "HEAD")


def identify(root):
    sh(root, "git", "config", "user.name", "Land Test")
    sh(root, "git", "config", "user.email", "land@test.invalid")
    sh(root, "git", "config", "core.autocrlf", "false")


class World:
    """remote.git (the hosting side), seed (where cases write), local (--repo)."""

    def __init__(self, tmp, module):
        self.tmp, self.module, self.prs = tmp, module, {}
        self.remote = os.path.join(tmp, "remote.git")
        self.seed = os.path.join(tmp, "seed")
        self.local = os.path.join(tmp, "local")
        sh(tmp, "git", "init", "-q", "--bare", "-b", "main", self.remote)
        sh(tmp, "git", "init", "-q", "-b", "main", self.seed)
        identify(self.seed)
        sh(self.seed, "git", "remote", "add", "origin", self.remote)
        self._seed_files()
        sh(self.seed, "git", "add", "-A")
        module.remeasure_budgets(self.seed)
        commit(self.seed, "base")
        sh(self.seed, "git", "push", "-q", "origin", "main")
        sh(tmp, "git", "clone", "-q", self.remote, self.local)
        identify(self.local)

    def _seed_files(self):
        seed = self.seed
        market(seed, "1.3.0")
        write(seed, "plugin/crew/code.py", "VALUE = 1\n")
        write(seed, "plugin/crew/README.md", "# crew\n\nWhat it does.\n")
        write(seed, "plugin/crew/BUDGETS.md", BUDGETS)
        write(seed, "plugin/other/code.py", "OTHER = 1\n")
        write(seed, "docs/note.md", "# note\n")
        write(seed, "CHANGELOG.md", CHANGELOG)
        write(seed, "README.md", README)
        for name, rel in (("check-instructions", "scripts/check_instructions.py"),
                          ("check-marketplace", "scripts/check-marketplace.py"),
                          ("check-crew-docs", "scripts/check-crew-docs.py"),
                          ("check-tooling-pr", "scripts/check-tooling-pr.py"),
                          ("pylint", "scripts/run-pylint.py")):
            write(seed, rel, STUB_CHECK.format(name=name))
        shutil.copyfile(os.path.join(SCRIPTS, "check-changelog.py"),
                        os.path.join(seed, "scripts", "check-changelog.py"))
        write(seed, "scripts/sync-updates.py", STUB_SYNC)
        write(seed, "docs/guides/crew/src/build.py", STUB_BUILD)
        write(seed, "docs/guides/crew/src/config_reference.py", STUB_NOOP)
        write(seed, "plugin/crew/tests/optin_inventory.py", STUB_NOOP)
        write(seed, "plugin/crew/hooks/scripts/crew_instructions.py",
              STUB_VERSIONED.format(target=".claude/rules/crew.md", template=RULES_TEMPLATE))
        write(seed, "plugin/crew/hooks/scripts/crew_standards.py",
              STUB_VERSIONED.format(target="REVIEW.md", template=REVIEW_TEMPLATE))

    def branch(self, name, number, *edits, title="fix(crew): a change", push=True):
        """A PR branch from main: one commit per edit(seed) callable."""
        sh(self.seed, "git", "checkout", "-q", "-B", name, "main")
        for i, edit in enumerate(edits):
            edit(self.seed)
            commit(self.seed, f"{name} commit {i + 1}")
        head = sh(self.seed, "git", "rev-parse", "HEAD")
        if push:
            sh(self.seed, "git", "push", "-q", "origin", f"HEAD:refs/heads/{name}",
               f"HEAD:refs/pull/{number}/head")
        self.prs[number] = {"number": number, "headRefName": name, "headRefOid": head,
                            "baseRefName": "main", "title": title, "body": "", "isDraft": True,
                            "state": "OPEN", "isCrossRepository": False}
        sh(self.seed, "git", "checkout", "-q", "main")
        return head

    def advance_main(self, edit, message="main moves"):
        sh(self.seed, "git", "checkout", "-q", "main")
        edit(self.seed)
        commit(self.seed, message)
        sh(self.seed, "git", "push", "-q", "origin", "main")

    def sha(self, ref):
        return sh(self.remote, "git", "rev-parse", ref)

    def show(self, ref, rel):
        return sh(self.remote, "git", "show", f"{ref}:{rel}")

    def land(self, number, *extra, pr=None):
        """(exit code, output, report dict) of one lander run."""
        data = {"pr": pr or self.prs[number], "open": list(self.prs.values())}
        pr_json = os.path.join(self.tmp, f"pr-{number}.json")
        report = os.path.join(self.tmp, f"report-{number}.json")
        write(self.tmp, f"pr-{number}.json", json.dumps(data))
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = self.module.main([str(number), "--repo", self.local, "--pr-json", pr_json,
                                     "--report", report, *extra])
        with open(report, encoding="utf-8") as fh:
            return code, out.getvalue(), json.load(fh)


def edit_code(value=2):
    return lambda root: write(root, "plugin/crew/code.py", f"VALUE = {value}\n")


def crew_version(world, ref):
    data = json.loads(world.show(ref, ".claude-plugin/marketplace.json"))
    return next(p["version"] for p in data["plugins"] if p["name"] == "crew")


# ---- cases ---------------------------------------------------------------------------
# Each returns a list of problems; [] is a pass.

def case_dry_run_pushes_nothing(world):
    head = world.branch("feat/a", 10, edit_code())
    main = world.sha("refs/heads/main")
    code, out, report = world.land(10)
    bad = []
    if code != 0:
        bad.append(f"exit {code}, wanted 0\n{out}")
    if world.sha("refs/heads/feat/a") != head:
        bad.append("a dry run moved the PR branch")
    if world.sha("refs/heads/main") != main:
        bad.append("a dry run moved main")
    if report.get("versions") != {"crew": "1.3.1"}:
        bad.append(f"versions {report.get('versions')}, wanted crew 1.3.1")
    for rel in (".claude-plugin/marketplace.json", "plugin/crew/.claude-plugin/plugin.json",
                "plugin/PLUGINS.md", "CHANGELOG.md", "README.md", ".claude/rules/crew.md",
                "REVIEW.md"):
        if rel not in report.get("changed", []):
            bad.append(f"{rel} not in the would-change list {report.get('changed')}")
    if report.get("pushed"):
        bad.append("the report says pushed on a dry run")
    return bad


def case_push_lands_one_commit(world):
    head = world.branch("feat/a", 10, edit_code(), title="fix(crew): the widget turns (1.2.9)")
    main = world.sha("refs/heads/main")
    code, out, report = world.land(10, "--push", "--trailer", "Docs: none - a test")
    bad = []
    new = world.sha("refs/heads/feat/a")
    if code != 0 or not report.get("pushed"):
        return [f"exit {code}, pushed {report.get('pushed')}\n{out}"]
    if world.sha("refs/heads/main") != main:
        bad.append("NEVER MERGES violated: the base branch moved")
    if sh(world.remote, "git", "rev-list", "--count", f"{head}..{new}") != "1":
        bad.append("wanted exactly one new commit on the PR branch")
    if sh(world.remote, "git", "rev-parse", f"{new}^") != head:
        bad.append("the land commit's parent is not the old PR head (not a fast-forward)")
    if crew_version(world, new) != "1.3.1":
        bad.append(f"marketplace crew {crew_version(world, new)}, wanted 1.3.1")
    if json.loads(world.show(new, "plugin/crew/.claude-plugin/plugin.json"))["version"] != "1.3.1":
        bad.append("plugin.json not bumped")
    if "| **Version** | 1.3.1<!--" not in world.show(new, "plugin/PLUGINS.md"):
        bad.append("the PLUGINS.md claim row was not bumped")
    log = world.show(new, "CHANGELOG.md")
    if "### Changed — crew 1.3.1: the widget turns (#10)" not in log:
        bad.append("no changelog entry from the PR title (prefix and version stripped)")
    if log.index("crew 1.3.1") > log.index("crew 1.3.0"):
        bad.append("the new entry is not above the old one")
    if "crew 1.3.1: the widget turns" not in world.show(new, "README.md"):
        bad.append("README's generated block was not rewritten")
    if "Hand-written." not in world.show(new, "README.md"):
        bad.append("README's hand-written text was lost")
    if world.show(new, ".claude/rules/crew.md") != "rules for crew 1.3.1":
        bad.append(".claude/rules/crew.md was not regenerated")
    message = sh(world.remote, "git", "log", "-1", "--format=%B", new)
    if "crew 1.3.1: land #10" not in message or "Docs: none - a test" not in message:
        bad.append(f"commit message: {message!r}")
    if json.loads(world.show(new, ".claude-plugin/marketplace.json"))["plugins"][1]["version"] != "1.0.0":
        bad.append("an entry the PR did not touch was bumped")
    return bad


def case_version_above_every_open_head(world):
    world.branch("feat/b", 11, lambda r: market(r, "1.3.4"))
    world.branch("feat/c", 12, lambda r: market(r, "1.3.7"))
    world.branch("feat/a", 10, edit_code())
    code, out, report = world.land(10)
    if code != 0 or report.get("versions") != {"crew": "1.3.8"}:
        return [f"exit {code}, versions {report.get('versions')}, wanted crew 1.3.8 (above #12's "
                f"1.3.7)\n{out}"]
    return []


def case_second_pr_gets_the_next_number(world):
    world.branch("feat/a", 10, edit_code(2))
    world.branch("feat/d", 14, lambda r: write(r, "plugin/crew/more.py", "MORE = 1\n"))
    code, out, _ = world.land(10, "--push")
    if code != 0:
        return [f"first land exit {code}\n{out}"]
    landed = world.sha("refs/heads/feat/a")
    # The owner's merge, done by the test: the lander never does this.
    sh(world.seed, "git", "fetch", "-q", "origin", "feat/a")
    sh(world.seed, "git", "checkout", "-q", "main")
    sh(world.seed, "git", "merge", "-q", "--no-ff", "-m", "Merge PR 10", landed)
    sh(world.seed, "git", "push", "-q", "origin", "main")
    del world.prs[10]
    code, out, report = world.land(14, "--push")
    new = world.sha("refs/heads/feat/d")
    bad = []
    if code != 0 or report.get("versions") != {"crew": "1.3.2"}:
        bad.append(f"second land exit {code}, versions {report.get('versions')}, wanted 1.3.2\n{out}")
    elif "crew 1.3.2" not in world.show(new, "CHANGELOG.md"):
        bad.append("the second PR has no entry for 1.3.2")
    return bad


def _legacy(world):
    """A branch that bumped twice on its own; main then moved past it."""
    def first(root):
        write(root, "plugin/crew/code.py", "VALUE = 2\n")
        market(root, "1.3.1")
        write(root, "CHANGELOG.md", CHANGELOG.replace(
            OLD_ENTRY, "### Fixed — crew 1.3.1: the widget\n\n- **Summary.** `crew` 1.3.1 fixes it.\n\n"
            + OLD_ENTRY))

    def second(root):
        market(root, "1.3.2")
        text = read(root, "CHANGELOG.md").replace("crew 1.3.1: the widget", "crew 1.3.2: the widget")
        write(root, "CHANGELOG.md", text.replace("`crew` 1.3.1 fixes", "`crew` 1.3.2 fixes"))
        write(root, "plugin/crew/README.md",
              "# crew\n\nWhat it does.\n\n**The widget (crew 1.3.2).** Since crew 1.3.0 it spun.\n")
        write(root, "README.md", README.replace("crew 1.3.0: the first entry", "crew 1.3.2: the widget"))

    head = world.branch("fix/legacy", 20, first, second)

    def main_moves(root):
        market(root, "1.3.5")
        write(root, "plugin/crew/extra.py", "EXTRA = 1\n")
        write(root, "CHANGELOG.md", CHANGELOG.replace(
            OLD_ENTRY, "### Added — crew 1.3.5: extra\n\n- **Summary.** extra.\n\n" + OLD_ENTRY))
        write(root, "README.md", README.replace("crew 1.3.0: the first entry", "crew 1.3.5: extra"))

    world.advance_main(main_moves)
    return head


def case_legacy_branch_conflicts_resolved_by_rule(world):
    head = _legacy(world)
    main = world.sha("refs/heads/main")
    code, out, report = world.land(20, "--push")
    if code != 0:
        return [f"exit {code}\n{out}"]
    new = world.sha("refs/heads/fix/legacy")
    bad = []
    if report.get("versions") != {"crew": "1.3.6"}:
        bad.append(f"versions {report.get('versions')}, wanted crew 1.3.6 (main has 1.3.5)")
    if world.sha("refs/heads/main") != main:
        bad.append("NEVER MERGES violated: the base branch moved")
    if sh(world.remote, "git", "rev-list", "--count", f"{head}..{new}", "--first-parent") != "2":
        bad.append("wanted a merge commit and one land commit above the old head")
    log = world.show(new, "CHANGELOG.md")
    for want in ("### Fixed — crew 1.3.6: the widget", "`crew` 1.3.6 fixes it",
                 "- crew 1.3.1: re-bump only - interim number on the fix/legacy branch (#20)",
                 "- crew 1.3.2: re-bump only - ", "### Added — crew 1.3.5: extra"):
        if want not in log:
            bad.append(f"CHANGELOG.md lacks {want!r}")
    if "crew 1.3.2: the widget" in log:
        bad.append("the branch's stale heading (crew 1.3.2) survived")
    if log.count("### Changed") != 0:
        bad.append("a fallback entry was written although the PR had its own")
    prose = world.show(new, "plugin/crew/README.md")
    if "(crew 1.3.6)" not in prose or "Since crew 1.3.0 it spun" not in prose:
        bad.append(f"prose re-numbering wrong: {prose!r}")
    if "<<<<<<<" in log + world.show(new, "README.md") + world.show(new, ".claude-plugin/marketplace.json"):
        bad.append("a conflict marker was committed")
    if "crew 1.3.6: the widget" not in world.show(new, "README.md"):
        bad.append("README's generated block does not show the landed entry")
    budgets = world.show(new, "plugin/crew/BUDGETS.md")
    files = ("plugin/crew/README.md", "plugin/crew/BUDGETS.md")
    total = sum(len(world.show(new, f).splitlines()) for f in files)
    if f"totals {total} lines across 2 files" not in budgets:
        bad.append(f"BUDGETS.md not re-measured ({total} lines): {budgets!r}")
    states = {name: state for name, state, _ in report.get("checks", [])}
    if states.get("check-changelog") != "PASS":
        bad.append(f"the real check-changelog.py did not pass: {states}")
    return bad


def case_idempotent_rerun(world):
    world.branch("feat/a", 10, edit_code())
    code, out, _ = world.land(10, "--push")
    if code != 0:
        return [f"first run exit {code}\n{out}"]
    landed = world.sha("refs/heads/feat/a")
    world.prs[10]["headRefOid"] = landed
    code, out, report = world.land(10, "--push")
    bad = []
    if code != 0:
        bad.append(f"second run exit {code}\n{out}")
    if world.sha("refs/heads/feat/a") != landed:
        bad.append("a second run moved the branch again")
    if report.get("changed") != [] or report.get("versions") != {}:
        bad.append(f"a second run would change {report.get('changed')} / {report.get('versions')}")
    if "nothing to land" not in out:
        bad.append("the second run did not say there was nothing to land")
    return bad


def _refused(world, number, pr, text, *extra):
    before = {ref: world.sha(ref) for ref in ("refs/heads/main",)}
    code, out, _ = world.land(number, "--push", *extra, pr=pr)
    bad = []
    if code != 2:
        bad.append(f"exit {code}, wanted 2 (refused)\n{out}")
    if text not in out:
        bad.append(f"the refusal does not say {text!r}\n{out}")
    if world.sha("refs/heads/main") != before["refs/heads/main"]:
        bad.append("main moved")
    return bad


def case_refuses_a_pr_whose_head_is_main(world):
    world.branch("feat/a", 10, edit_code())
    pr = dict(world.prs[10], headRefName="main", headRefOid=world.sha("refs/heads/main"))
    return _refused(world, 10, pr, "never commits on or pushes to main")


def case_refuses_closed_and_fork_prs(world):
    world.branch("feat/a", 10, edit_code())
    bad = _refused(world, 10, dict(world.prs[10], state="MERGED"), "not OPEN")
    return bad + _refused(world, 10, dict(world.prs[10], isCrossRepository=True), "fork")


def case_refuses_a_moved_pr_head(world):
    head = world.branch("feat/a", 10, edit_code())
    bad = _refused(world, 10, dict(world.prs[10], headRefOid="0" * 40), "it moved")
    if world.sha("refs/heads/feat/a") != head:
        bad.append("the PR branch moved")
    return bad


def case_unknown_open_head_is_never_lower(world):
    world.branch("feat/a", 10, edit_code())
    world.branch("feat/b", 11, lambda r: market(r, "1.3.9"))
    world.prs[11]["headRefOid"] = "1" * 40  # GitHub reports a head the remote does not serve
    return _refused(world, 10, None, "version there is unknown")


def _in_place(world, branch="feat/a"):
    where = os.path.join(world.tmp, "inplace")
    sh(world.tmp, "git", "clone", "-q", world.remote, where)
    identify(where)
    sh(where, "git", "checkout", "-q", branch)
    return where


def case_in_place_refuses_a_dirty_tree(world):
    world.branch("feat/a", 10, edit_code())
    where = _in_place(world)
    write(where, "scratch.txt", "uncommitted\n")
    head = sh(where, "git", "rev-parse", "HEAD")
    bad = _refused(world, 10, None, "worktree is dirty", "--in-place", where)
    if sh(where, "git", "rev-parse", "HEAD") != head or not os.path.exists(
            os.path.join(where, "scratch.txt")):
        bad.append("a refused run changed the checkout")
    write(where, "plugin/crew/code.py", "VALUE = 99\n")
    os.remove(os.path.join(where, "scratch.txt"))
    return bad + _refused(world, 10, None, "worktree is dirty", "--in-place", where)


def case_in_place_refuses_main_and_crlf(world):
    world.branch("feat/a", 10, edit_code())
    where = _in_place(world, "main")
    bad = _refused(world, 10, None, "never commits there", "--in-place", where)
    sh(where, "git", "checkout", "-q", "feat/a")
    sh(where, "git", "config", "core.autocrlf", "true")
    return bad + _refused(world, 10, None, "core.autocrlf", "--in-place", where)


def case_in_place_clean_checkout_lands_locally(world):
    head = world.branch("feat/a", 10, edit_code())
    where = _in_place(world)
    code, out, report = world.land(10, "--in-place", where)
    bad = []
    if code != 0 or report.get("versions") != {"crew": "1.3.1"}:
        bad.append(f"exit {code}, versions {report.get('versions')}\n{out}")
    if sh(where, "git", "rev-parse", "HEAD^") != head:
        bad.append("the land commit is not on top of the PR head in the checkout")
    if world.sha("refs/heads/feat/a") != head:
        bad.append("a run without --push moved the remote branch")
    if sh(where, "git", "status", "--porcelain"):
        bad.append("the checkout was left dirty")
    return bad


def _hook(world, text):
    path = os.path.join(world.tmp, "hook.py")
    write(world.tmp, "hook.py", text)
    os.environ["LAND_TEST_HOOK"] = path


def case_never_force_pushes_over_a_moved_branch(world):
    world.branch("feat/a", 10, edit_code())
    # Someone else pushes to the PR branch while the checks run.
    sh(world.seed, "git", "checkout", "-q", "feat/a")
    write(world.seed, "docs/note.md", "# note\n\nSomeone else's commit.\n")
    other = commit(world.seed, "someone else's commit")
    sh(world.seed, "git", "checkout", "-q", "main")
    _hook(world, f"import subprocess\nsubprocess.run(['git', '-C', {world.seed!r}, 'push', '-q', "
                 f"'origin', '{other}:refs/heads/feat/a'], check=True)\n")
    code, out, report = world.land(10, "--push")
    bad = []
    if code != 1:
        bad.append(f"exit {code}, wanted 1 (push rejected)\n{out}")
    if world.sha("refs/heads/feat/a") != other:
        bad.append("NEVER FORCES violated: the other commit on the PR branch was overwritten")
    if report.get("pushed"):
        bad.append("the report says pushed")
    argv = world.module.push_argv("origin", "feat/a", "main")
    if argv != ["push", "origin", "HEAD:refs/heads/feat/a"]:
        bad.append(f"push argv is {argv}")
    for branch in ("main", "master", "", "release"):
        try:
            world.module.push_argv("origin", branch, "release" if branch == "release" else "main")
            bad.append(f"push_argv accepted {branch!r}")
        except world.module.Refusal:
            pass
    return bad


def case_refuses_when_main_moved_before_the_push(world):
    head = world.branch("feat/a", 10, edit_code())
    sh(world.seed, "git", "checkout", "-q", "main")
    write(world.seed, "docs/note.md", "# note\n\nMain moved.\n")
    moved = commit(world.seed, "main moves during the checks")
    _hook(world, f"import subprocess\nsubprocess.run(['git', '-C', {world.seed!r}, 'push', '-q', "
                 f"'origin', '{moved}:refs/heads/main'], check=True)\n")
    code, out, _ = world.land(10, "--push")
    bad = []
    if code != 2 or "moved since it was merged" not in out:
        bad.append(f"exit {code}, wanted 2 naming the moved base\n{out}")
    if world.sha("refs/heads/feat/a") != head:
        bad.append("the PR branch was pushed although main had moved")
    return bad


def case_real_conflict_stops(world):
    head = world.branch("feat/a", 10, edit_code(2))
    world.advance_main(edit_code(3))
    code, out, _ = world.land(10, "--push")
    bad = []
    if code != 1 or "plugin/crew/code.py" not in out:
        bad.append(f"exit {code}, wanted 1 naming plugin/crew/code.py\n{out}")
    if world.sha("refs/heads/feat/a") != head:
        bad.append("the PR branch moved despite a real conflict")
    return bad


def _marker(name):
    def edit(root):
        write(root, "plugin/crew/code.py", "VALUE = 2\n")
        write(root, name, "x\n")
    return edit


def case_failed_check_is_not_pushed(world):
    head = world.branch("feat/a", 10, _marker("FAIL_check-marketplace"))
    code, out, _ = world.land(10, "--push", "--accept-skip", "check-marketplace")
    bad = []
    if code != 1 or "check check-marketplace FAILED" not in out:
        bad.append(f"exit {code}, wanted 1\n{out}")
    if world.sha("refs/heads/feat/a") != head:
        bad.append("pushed although a check failed (--accept-skip must not cover a FAIL)")
    return bad


def case_skipped_check_blocks_until_accepted(world):
    head = world.branch("feat/a", 10, _marker("SKIP_pylint"))
    code, out, _ = world.land(10, "--push")
    bad = []
    if code != 3 or world.sha("refs/heads/feat/a") != head:
        bad.append(f"exit {code}, wanted 3 and no push (a skipped check is not a pass)\n{out}")
    code, out, report = world.land(10, "--push", "--accept-skip", "pylint")
    if code != 0 or not report.get("pushed"):
        bad.append(f"with --accept-skip pylint: exit {code}\n{out}")
    return bad


def case_docx_pdf_pass_skipped_is_could_not_tell(world):
    head = world.branch("feat/a", 10, _marker("GUIDE_STALE"))
    code, out, _ = world.land(10, "--push")
    if code != 3 or world.sha("refs/heads/feat/a") != head or "DOCX/PDF NOT rebuilt" not in out:
        return [f"exit {code}, wanted 3, no push, and the DOCX/PDF line\n{out}"]
    return []


def case_missing_generator_fails(world):
    def edit(root):
        write(root, "plugin/crew/code.py", "VALUE = 2\n")
        os.remove(os.path.join(root, "scripts", "sync-updates.py"))
    head = world.branch("feat/a", 10, edit)
    code, out, _ = world.land(10, "--push")
    if code != 1 or "never a skip" not in out or world.sha("refs/heads/feat/a") != head:
        return [f"exit {code}, wanted 1 for a missing generator\n{out}"]
    return []


def case_fragment_and_placeholder(world):
    def edit(root):
        write(root, "plugin/crew/code.py", "VALUE = 2\n")
        write(root, "changelog.d/widget.md",
              "### Fixed — crew NEXT: the widget from a fragment\n\n- **Summary.** `crew` NEXT.\n")
        write(root, "plugin/crew/README.md", "# crew\n\nWhat it does.\n\nNew in crew NEXT.\n")
    world.branch("feat/a", 10, edit)
    code, out, _ = world.land(10, "--push")
    if code != 0:
        return [f"exit {code}\n{out}"]
    new = world.sha("refs/heads/feat/a")
    log, bad = world.show(new, "CHANGELOG.md"), []
    if "### Fixed — crew 1.3.1: the widget from a fragment" not in log or "`crew` 1.3.1." not in log:
        bad.append("the fragment was not folded in with its number")
    if "### Changed" in log:
        bad.append("a fallback entry was written although a fragment gave one")
    if "changelog.d/widget.md" in sh(world.remote, "git", "ls-tree", "-r", "--name-only", new):
        bad.append("the fragment was not removed")
    if "New in crew 1.3.1." not in world.show(new, "plugin/crew/README.md"):
        bad.append("the NEXT placeholder in the PR's prose was not numbered")
    return bad


def case_untouched_plugins_are_not_bumped(world):
    world.branch("docs/only", 30, lambda r: write(r, "docs/note.md", "# note\n\nMore.\n"))
    code, out, report = world.land(30)
    bad = []
    if code != 0 or report.get("versions") != {}:
        bad.append(f"exit {code}, versions {report.get('versions')}, wanted none\n{out}")
    if report.get("changed") != []:
        bad.append(f"a docs-only PR would change {report.get('changed')}")
    return bad


CASES = (
    case_dry_run_pushes_nothing,
    case_push_lands_one_commit,
    case_version_above_every_open_head,
    case_second_pr_gets_the_next_number,
    case_legacy_branch_conflicts_resolved_by_rule,
    case_idempotent_rerun,
    case_refuses_a_pr_whose_head_is_main,
    case_refuses_closed_and_fork_prs,
    case_refuses_a_moved_pr_head,
    case_unknown_open_head_is_never_lower,
    case_in_place_refuses_a_dirty_tree,
    case_in_place_refuses_main_and_crlf,
    case_in_place_clean_checkout_lands_locally,
    case_never_force_pushes_over_a_moved_branch,
    case_refuses_when_main_moved_before_the_push,
    case_real_conflict_stops,
    case_failed_check_is_not_pushed,
    case_skipped_check_blocks_until_accepted,
    case_docx_pdf_pass_skipped_is_could_not_tell,
    case_missing_generator_fails,
    case_fragment_and_placeholder,
    case_untouched_plugins_are_not_bumped,
)


def _rmtree(path):
    for base, _dirs, files in os.walk(path):
        for name in files:
            try:
                os.chmod(os.path.join(base, name), stat.S_IWRITE | stat.S_IREAD)
            except OSError:
                pass
    shutil.rmtree(path)


def run_case(case, module):
    """The case's problems ([] = pass). A crash is a problem, never a pass."""
    tmp = tempfile.mkdtemp(prefix="land-pr-suite-")
    os.environ.pop("LAND_TEST_HOOK", None)
    try:
        return case(World(tmp, module))
    except Exception as exc:  # pylint: disable=broad-exception-caught
        return [f"crashed: {type(exc).__name__}: {exc}"]
    finally:
        os.environ.pop("LAND_TEST_HOOK", None)
        _rmtree(tmp)


def mutations(module):
    """(label, the case that must go red, apply() -> undo())."""
    def swap(name, replacement):
        def apply():
            original = getattr(module, name)
            setattr(module, name, replacement(original))
            return lambda: setattr(module, name, original)
        return apply

    def quiet_status(original):
        def patched(cwd, *args, **kwargs):
            if args[:2] == ("status", "--porcelain"):
                return ""
            return original(cwd, *args, **kwargs)
        return patched

    return (
        ("ignore the other open PR heads", case_version_above_every_open_head,
         swap("next_version", lambda _o: lambda base, own, others: module.bump_patch(
             max([base, own], key=module.parse_version)))),
        ("drop the main/closed/fork refusal", case_refuses_a_pr_whose_head_is_main,
         swap("refuse_unlandable", lambda _o: lambda pr, base: None)),
        ("drop the closed/fork refusal", case_refuses_closed_and_fork_prs,
         swap("refuse_unlandable", lambda _o: lambda pr, base: None)),
        ("see every tree as clean", case_in_place_refuses_a_dirty_tree, swap("git", quiet_status)),
        ("force the push", case_never_force_pushes_over_a_moved_branch,
         swap("push_argv", lambda _o: lambda remote, branch, base: [
             "push", "--force", remote, f"HEAD:refs/heads/{branch}"])),
        ("push whatever the checks said", case_failed_check_is_not_pushed,
         swap("verdict", lambda _o: lambda *_a: (0, []))),
        ("treat a skipped check as a pass", case_skipped_check_blocks_until_accepted,
         swap("classify", lambda o: lambda rc, dnr: "PASS" if rc == 77 else o(rc, dnr))),
        ("read an unreadable open head as no versions", case_unknown_open_head_is_never_lower,
         swap("fetch_open_heads",
              lambda o: lambda *a: {k: (v or {}) for k, v in o(*a).items()})),
        ("resolve every conflict by keeping both sides", case_real_conflict_stops,
         swap("policy_for", lambda _o: lambda rel: ("union", None))),
        ("never re-number the branch's own version", case_legacy_branch_conflicts_resolved_by_rule,
         swap("renumber", lambda _o: lambda *_a: [])),
    )


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    handle, empty = tempfile.mkstemp(prefix="land-pr-gitconfig-")
    os.close(handle)
    os.environ.update(GIT_CONFIG_GLOBAL=empty, GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        os.environ.pop(name, None)
    module = load()
    wanted = [c for c in CASES if not argv or any(a in c.__name__ for a in argv)]
    failed = 0
    try:
        for case in wanted:
            problems = run_case(case, module)
            label = case.__name__[len("case_"):].replace("_", " ")
            print(("ok   " if not problems else "FAIL ") + label, flush=True)
            for problem in problems:
                print("     " + problem.replace("\n", "\n     "), flush=True)
            failed += bool(problems)
        if failed:
            print(f"land-pr: {failed} of {len(wanted)} case(s) failed")
            return 1
        detected = 0
        for label, case, apply in mutations(module):
            if case not in wanted:
                continue
            undo = apply()
            try:
                problems = run_case(case, module)
            finally:
                undo()
            if not problems:
                print(f"SABOTAGE NOT DETECTED: `{label}` left {case.__name__} green")
                return 1
            detected += 1
            print(f"ok   sabotage `{label}`: {case.__name__[len('case_'):]} went red", flush=True)
        print(f"land-pr: all {len(wanted)} cases passed, {detected} mutations detected")
        return 0
    finally:
        os.remove(empty)


if __name__ == "__main__":
    sys.exit(main())
