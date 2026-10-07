#!/usr/bin/env python3
"""Suite for scripts/check-crew-docs.py -- a crew code change touches a
narrative crew doc, or declares `Docs: none - <reason>` (T-0055).

Every case builds a throwaway git repository in a temp directory with a fake
`refs/remotes/origin/main` and runs the checker's `check()` against it.
Nothing touches this repository's own files or refs.

Must-fail cases are what the rule is for: crew code with no doc and no valid
declaration. Must-pass cases keep it honest. Could-not-tell cases exit 77,
never 0. The mutation cases patch the loaded checker one way each and assert
that a named case flips; a mutation that flips nothing fails the suite.

Run: python3 scripts/_test/crew-docs.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check-crew-docs.py")

HOOK = "plugin/crew/hooks/scripts/crew_status.py"
README = "plugin/crew/README.md"


def load_checker():
    spec = importlib.util.spec_from_file_location("check_crew_docs", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root: str, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=root, check=True, capture_output=True,
                          text=True, stdin=subprocess.DEVNULL).stdout.strip()


def write(root: str, rel: str, text: str = "x\n") -> None:
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def commit(root: str, paths: list[str], message: str) -> None:
    for rel in paths:
        write(root, rel, f"{message}\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", message)


def repo(tmp: str, origin: bool = True) -> str:
    root = os.path.join(tmp, "repo")
    os.makedirs(root)
    git(root, "init", "-q", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "config", "core.autocrlf", "false")
    commit(root, ["README.md", HOOK, "plugin/crew/hooks/scripts/old_name.py"], "seed")
    if origin:
        git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-qb", "lane")
    return root


def body_file(tmp: str, text: str) -> str:
    path = os.path.join(tmp, "body.md")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    return path


def event_file(tmp: str, payload) -> str:
    path = os.path.join(tmp, "event.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(payload if isinstance(payload, str) else json.dumps(payload))
    return path


# Each case returns (root, pr_body_file, environ).
NO_ENV: dict = {}


def fail_hook_only(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook change")
    return root, None, NO_ENV


def fail_hook_plus_mechanical(tmp):
    root = repo(tmp)
    commit(root, [HOOK, "plugin/PLUGINS.md", "CHANGELOG.md", "plugin/crew/BUDGETS.md",
                  ".crew/codemap/hooks.md", "docs/diagrams/crew.mmd"], "mechanical only")
    return root, None, NO_ENV


def fail_hook_untracked(tmp):
    root = repo(tmp)
    write(root, "plugin/crew/hooks/scripts/new_hook.py")
    return root, None, NO_ENV


def fail_skill_script_plus_reference(tmp):
    root = repo(tmp)
    commit(root, ["plugin/crew/skills/crew-setup/scripts/detect.sh",
                  "plugin/crew/skills/crew-setup/platform.md"], "skill script and reference")
    return root, None, NO_ENV


def fail_trailer_without_reason(tmp):
    root = repo(tmp)
    write(root, HOOK, "changed\n")
    git(root, "commit", "-qam", "hook\n\nDocs: none")
    return root, None, NO_ENV


def fail_trailer_placeholder(tmp):
    root = repo(tmp)
    write(root, HOOK, "changed\n")
    git(root, "commit", "-qam", "hook\n\nDocs: none - <why>")
    return root, None, NO_ENV


def fail_body_blank_reason(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    return root, body_file(tmp, "Summary\n\nDocs: none -    \n"), NO_ENV


def fail_body_mid_sentence(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    return root, body_file(tmp, "We could say Docs: none - nothing changed here.\n"), NO_ENV


def fail_trailer_only_on_main(tmp):
    root = repo(tmp)
    git(root, "checkout", "-q", "main")
    write(root, "other.txt")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "main work\n\nDocs: none - main's own reason")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "lane")
    commit(root, [HOOK], "hook")
    git(root, "merge", "-q", "--no-edit", "main")
    return root, None, NO_ENV


def pass_no_crew(tmp):
    root = repo(tmp)
    commit(root, ["scripts/x.py", "skills/notify/SKILL.md"], "not crew")
    return root, None, NO_ENV


def pass_tests_evals_manifest(tmp):
    root = repo(tmp)
    commit(root, ["plugin/crew/tests/test_x.py", "plugin/crew/evals/e/case.json",
                  "plugin/crew/hooks/scripts/_test/t.sh",
                  "plugin/crew/.claude-plugin/plugin.json"], "tests only")
    return root, None, NO_ENV


def pass_command_md(tmp):
    root = repo(tmp)
    commit(root, ["plugin/crew/commands/x.md"], "prompt only")
    return root, None, NO_ENV


def pass_hook_plus_readme(tmp):
    root = repo(tmp)
    commit(root, [HOOK, README], "hook and readme")
    return root, None, NO_ENV


def pass_hook_plus_guide_source(tmp):
    root = repo(tmp)
    commit(root, [HOOK, "docs/guides/crew/src/quickstart.md"], "hook and guide")
    return root, None, NO_ENV


def pass_rename_plus_skill(tmp):
    root = repo(tmp)
    git(root, "mv", "plugin/crew/hooks/scripts/old_name.py", "plugin/crew/hooks/scripts/new_name.py")
    write(root, "plugin/crew/skills/crew-setup/SKILL.md", "doc\n")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "rename and skill")
    return root, None, NO_ENV


def pass_trailer_with_reason(tmp):
    root = repo(tmp)
    write(root, HOOK, "changed\n")
    git(root, "commit", "-qam", "hook\n\nDocs: none - internal rename, no behaviour change")
    return root, None, NO_ENV


def _body_case(dash):
    def case(tmp):
        root = repo(tmp)
        commit(root, [HOOK], "hook")
        return root, body_file(tmp, f"Summary.\n\n  Docs: none {dash} refactor only\n"), NO_ENV
    case.__name__ = f"pass_body_dash_{ord(dash):x}"
    return case


def pass_event_body(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    path = event_file(tmp, {"pull_request": {"body": "x\nDocs: none - log text only\n"}})
    return root, None, {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": path}


def pass_merge_ref_shape(tmp):
    root = repo(tmp)
    commit(root, [HOOK, README], "branch work")
    branch = git(root, "rev-parse", "HEAD")
    git(root, "checkout", "-q", "main")
    commit(root, ["main.txt"], "main moved")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "--detach", "main")
    git(root, "merge", "-q", "--no-ff", "--no-edit", branch)
    return root, None, NO_ENV


def pass_main_merged_in(tmp):
    root = repo(tmp)
    commit(root, ["scripts/lane.py"], "lane, not crew")
    git(root, "checkout", "-q", "main")
    commit(root, [HOOK], "main changed crew")
    git(root, "update-ref", "refs/remotes/origin/main", "HEAD")
    git(root, "checkout", "-q", "lane")
    git(root, "merge", "-q", "--no-edit", "main")
    return root, None, NO_ENV


def _release_repo(tmp):
    """origin/main at the seed; origin/release/9.9 adds a crew README change
    on top; the lane branches from the release and changes a hook only."""
    root = repo(tmp)
    git(root, "checkout", "-qb", "release/9.9", "main")
    commit(root, ["plugin/crew/README.md"], "release-branch doc work")
    git(root, "update-ref", "refs/remotes/origin/release/9.9", "HEAD")
    git(root, "checkout", "-qB", "lane", "release/9.9")
    commit(root, [HOOK], "lane hook change")
    return root


def fail_release_base_doc_not_this_prs(tmp):
    root = _release_repo(tmp)
    return root, None, {"GITHUB_BASE_REF": "release/9.9"}


def unknown_base_not_a_ref(tmp):
    root = repo(tmp)
    commit(root, [HOOK, "plugin/crew/README.md"], "hook and doc")
    return root, None, {"GITHUB_BASE_REF": "release/missing"}


def unknown_no_origin(tmp):
    root = repo(tmp, origin=False)
    commit(root, [HOOK], "hook")
    return root, None, NO_ENV


def unknown_event_missing(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    return root, None, {"GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": os.path.join(tmp, "nope.json")}


def unknown_event_not_json(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    return root, None, {"GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": event_file(tmp, "{not json")}


def unknown_body_file_missing(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    return root, os.path.join(tmp, "missing-body.md"), NO_ENV


def pass_docs_with_unreadable_event(tmp):
    root = repo(tmp)
    commit(root, [HOOK, README], "hook and readme")
    return root, None, {"GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": os.path.join(tmp, "nope.json")}


def pass_trailer_with_unreadable_event(tmp):
    root = repo(tmp)
    write(root, HOOK, "changed\n")
    git(root, "commit", "-qam", "hook\n\nDocs: none - comment only")
    return root, None, {"GITHUB_EVENT_NAME": "pull_request",
                        "GITHUB_EVENT_PATH": os.path.join(tmp, "nope.json")}


def unknown_git_cannot_start(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    empty = os.path.join(tmp, "empty-path")
    os.makedirs(empty)
    return root, None, {"PATH": empty}


def unknown_event_body_not_text(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    path = event_file(tmp, {"pull_request": {"body": 42}})
    return root, None, {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": path}


def fail_event_body_null(tmp):
    root = repo(tmp)
    commit(root, [HOOK], "hook")
    path = event_file(tmp, {"pull_request": {"body": None}})
    return root, None, {"GITHUB_EVENT_NAME": "pull_request", "GITHUB_EVENT_PATH": path}


CASES = [
    (fail_hook_only, 1), (fail_hook_plus_mechanical, 1), (fail_hook_untracked, 1),
    (fail_skill_script_plus_reference, 1), (fail_trailer_without_reason, 1),
    (fail_trailer_placeholder, 1), (fail_body_blank_reason, 1), (fail_body_mid_sentence, 1),
    (fail_trailer_only_on_main, 1), (fail_release_base_doc_not_this_prs, 1),
    (pass_no_crew, 0), (pass_tests_evals_manifest, 0), (pass_command_md, 0),
    (pass_hook_plus_readme, 0), (pass_hook_plus_guide_source, 0), (pass_rename_plus_skill, 0),
    (pass_trailer_with_reason, 0), (_body_case("-"), 0), (_body_case("–"), 0),
    (_body_case("—"), 0), (pass_event_body, 0), (pass_merge_ref_shape, 0),
    (pass_main_merged_in, 0), (pass_docs_with_unreadable_event, 0),
    (pass_trailer_with_unreadable_event, 0),
    (unknown_no_origin, 77), (unknown_event_missing, 77), (unknown_event_not_json, 77),
    (unknown_body_file_missing, 77), (unknown_git_cannot_start, 77),
    (unknown_event_body_not_text, 77), (fail_event_body_null, 1),
    (unknown_base_not_a_ref, 77),
]


def run_case(checker, case):
    with tempfile.TemporaryDirectory() as tmp:
        root, body, environ = case(tmp)
        # A case's PATH is applied to the process for the check alone (git is
        # started through it), after its fixture repo was built.
        saved = os.environ.get("PATH")
        if "PATH" in environ:
            os.environ["PATH"] = environ["PATH"]
        try:
            return checker.check(root, body, environ)
        finally:
            if saved is not None:
                os.environ["PATH"] = saved


def output_checks(checker) -> list[str]:
    """The exit-1 and exit-0-by-declaration messages say what they must."""
    problems = []
    code, lines = run_case(checker, fail_hook_only)
    text = "\n".join(lines)
    if code == 1:
        for need in (HOOK, "plugin/crew/README.md", "docs/guides/crew/src/*.md",
                     "Docs: none - <the reason>", "commit trailer", "PR body"):
            if need not in text:
                problems.append(f"exit-1 output does not name {need!r}")
    code, lines = run_case(checker, pass_trailer_with_reason)
    text = "\n".join(lines)
    if "internal rename, no behaviour change" not in text or "commit trailer" not in text:
        problems.append(f"exit-0 declaration output lacks the reason or source: {text!r}")
    code, lines = run_case(checker, fail_trailer_placeholder)
    if "not valid" not in "\n".join(lines):
        problems.append("an invalid declaration is not named as such")
    return problems


def mutations(checker):
    """(label, patch(module), a case that must flip)."""
    def docs_plus_plugins(m):
        m.DOCS = m.DOCS + ("plugin/PLUGINS.md",)

    def empty_reason_ok(m):
        orig = m.declaration

        def patched(value):
            match = m._VALUE.match(value.strip())  # pylint: disable=protected-access
            if match:
                return True, match.group(1).strip()
            return orig(value)
        m.declaration = patched

    def placeholder_ok(m):
        def patched(value):
            match = m._VALUE.match(value.strip())  # pylint: disable=protected-access
            if not match:
                return False, ""
            reason = match.group(1).strip()
            return bool(reason), reason
        m.declaration = patched

    def missing_ref_passes(m):
        orig = m.check

        def patched(root, body=None, environ=None):
            code, lines = orig(root, body, environ)
            return (0, lines) if code == m.EXIT_MISSING else (code, lines)
        m.check = patched

    def trailers_from_head(m):
        def patched(root, base="origin/main"):  # pylint: disable=unused-argument
            log = m._git(root, "log", "--format=%(trailers:key=Docs,valueonly)", "HEAD")  # pylint: disable=protected-access
            return [ln.strip() for ln in log.stdout.splitlines() if ln.strip()]
        m.trailer_values = patched

    def drop_status(m):
        def patched(root, base="origin/main"):
            diff = m._git(root, "diff", "--name-only", f"{base}...HEAD")  # pylint: disable=protected-access
            return sorted(p for p in diff.stdout.splitlines() if p)
        m.changed_paths = patched

    def unreadable_body_is_empty(m):
        orig = m.pr_body

        def patched(pr_body_file, environ):
            try:
                return orig(pr_body_file, environ)
            except m.CouldNotTell:
                return ""
        m.pr_body = patched

    def base_always_main(m):
        m.base_ref = lambda environ, base=None: "origin/main"

    return [
        ("PR base ignored, main used", base_always_main, fail_release_base_doc_not_this_prs),
        ("PLUGINS.md counted as a doc", docs_plus_plugins, fail_hook_plus_mechanical),
        ("empty reason accepted", empty_reason_ok, fail_body_blank_reason),
        ("placeholder reason accepted", placeholder_ok, fail_trailer_placeholder),
        ("missing ref returns 0", missing_ref_passes, unknown_no_origin),
        ("trailers read from HEAD", trailers_from_head, fail_trailer_only_on_main),
        ("git status paths dropped", drop_status, fail_hook_untracked),
        ("unreadable body read as empty", unreadable_body_is_empty, unknown_event_missing),
    ]


def main() -> int:
    checker = load_checker()
    failures = 0
    for case, want in CASES:
        code, lines = run_case(checker, case)
        ok = code == want
        failures += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {case.__name__}: exit {code} (want {want})")
        if not ok:
            for line in lines:
                print(f"       {line}")
    for problem in output_checks(checker):
        failures += 1
        print(f"FAIL output: {problem}")
    for label, patch, case in mutations(checker):
        before, _ = run_case(checker, case)
        mutant = load_checker()
        patch(mutant)
        after, _ = run_case(mutant, case)
        flipped = after != before
        failures += not flipped
        print(f"{'ok  ' if flipped else 'FAIL'} mutation '{label}': {case.__name__} "
              f"{before} -> {after}")
    total = len(CASES) + len(mutations(checker))
    print(f"\ncrew-docs: {total - failures} passed, {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
