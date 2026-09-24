#!/usr/bin/env python3
"""Sabotage suite for check_instructions.py.

Every case builds a throwaway `plugin/crew`-shaped fixture under a temp
directory and points the checker's ROOT/CREW/ALLOWANCE_PATH at it, the same
isolation pattern `scripts/_test/self-claims.py` uses for check-marketplace.py.
Nothing here touches this repository's own files.

The four cases the ticket names explicitly: a command file over the line
budget, a stale name in a file not on the legacy exemption list, a broken
`${CLAUDE_PLUGIN_ROOT}` path, and an allowance-listed file that grew past its
recorded line count -- each must go red, and each has a must-allow twin so a
future edit that makes the check fail a correct fixture is caught here rather
than in someone else's repo.

Also covered, one case each: an allowance entry naming an agent or skill
(not a command) still fails on growth; a nested `commands/group/x.md` is
still budget- and frontmatter-checked; a ceiling raised without the explicit
"raised: <why>" reason fails against a real throwaway git history, and the
same raise with that reason passes but still prints; reference-style links
and their definitions; and running `main()` itself on a fixture with one
problem of each kind, to prove the wiring in `main()` actually calls every
check (scripts/_test/self-claims.py has the same "main() wiring" case for
check-marketplace.py's own checks).

Run: python3 scripts/_test/instruction-budgets.py
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET = os.path.join(os.path.dirname(HERE), "check_instructions.py")


def load_checker():
    spec = importlib.util.spec_from_file_location("check_instructions", TARGET)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CHECKER = load_checker()


def _write(path: str, body: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(body)


def _root_at(tmp):
    """Point CHECKER's ROOT/CREW/ALLOWANCE_PATH at `tmp` for the duration of
    the `with` block, restoring them afterwards."""
    class _Ctx:
        def __init__(self):
            self.saved = None

        def __enter__(self):
            self.saved = (CHECKER.ROOT, CHECKER.CREW, CHECKER.ALLOWANCE_PATH)
            CHECKER.ROOT = tmp
            CHECKER.CREW = os.path.join(tmp, "plugin", "crew")
            CHECKER.ALLOWANCE_PATH = os.path.join(CHECKER.CREW, ".budget-allowance.json")
            return self

        def __exit__(self, *exc):
            CHECKER.ROOT, CHECKER.CREW, CHECKER.ALLOWANCE_PATH = self.saved
            return False

    return _Ctx()


def _patched(tmp, fn, *args):
    """Run `fn(*args, fail)` with CHECKER's ROOT/CREW/ALLOWANCE_PATH pointed
    at `tmp`, and return the collected failure messages."""
    with _root_at(tmp):
        problems: list[str] = []
        fn(*args, problems.append)
        return problems


def _load_allowance(tmp):
    """Run CHECKER.load_allowance with ROOT/CREW pointed at `tmp`, discarding
    any failure it reports (a malformed-allowance fixture is its own case,
    below) and returning the dict it built."""
    with _root_at(tmp):
        return CHECKER.load_allowance(lambda _msg: None)


FRONTMATTER = (
    "---\n"
    "description: fixture command\n"
    "argument-hint: none\n"
    "allowed-tools: Read\n"
    "---\n\n"
)


def run_command_budget(tmp_lines, allowance, command_path="fixture.md"):
    with tempfile.TemporaryDirectory() as tmp:
        body = FRONTMATTER + "line\n" * tmp_lines
        _write(os.path.join(tmp, "plugin", "crew", "commands", command_path), body)
        if allowance is not None:
            _write(os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
                   json.dumps(allowance))
        loaded = _load_allowance(tmp) if allowance is not None else {}
        return _patched(tmp, CHECKER.check_command_budget, loaded)


def run_frontmatter(body: str, command_path="fixture.md"):
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "plugin", "crew", "commands", command_path), body)
        return _patched(tmp, CHECKER.check_frontmatter)


def run_stale_names(body: str, path_rel: str, legacy: bool = False):
    """``legacy=True`` adds the file to the fixture's legacy exemption list,
    proving an explicitly-listed legacy file is never scanned -- distinct
    from every other case here (the default), which proves what happens to a
    file NOT on the list: scanned, because that is now the default."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, path_rel), body)
        saved_files = CHECKER.LEGACY_STALE_NAME_FILES
        CHECKER.LEGACY_STALE_NAME_FILES = (path_rel,) if legacy else ()
        try:
            return _patched(tmp, CHECKER.check_stale_names)
        finally:
            CHECKER.LEGACY_STALE_NAME_FILES = saved_files


def run_broken_references(body: str):
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "plugin", "crew", "commands", "fixture.md"), body)
        return _patched(tmp, CHECKER.check_broken_references)


def run_allowance_growth(recorded_lines: int, total_lines: int, reason: str,
                          path_rel: str = "plugin/crew/commands/fixture.md"):
    """Mirrors main()'s own sequence: load_allowance then check_command_budget
    and check_allowance_growth against the SAME fail collector, so a
    malformed allowance entry's own message is visible here too, not just a
    downstream growth failure.

    ``total_lines`` is the fixture file's actual total line count (frontmatter
    included, when the fixture is a command); ``recorded_lines`` is what the
    allowance entry claims. ``path_rel`` defaults to a command so the existing
    budget-related cases are unchanged; passing an agent or skill path proves
    growth is caught there too, not just under commands/.
    """
    with tempfile.TemporaryDirectory() as tmp:
        content_lines = max(total_lines - len(FRONTMATTER.splitlines()), 0)
        body = FRONTMATTER + "line\n" * content_lines if "/commands/" in path_rel else \
            "line\n" * total_lines
        _write(os.path.join(tmp, path_rel), body)
        _write(
            os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
            json.dumps({
                path_rel: {"lines": recorded_lines, "reason": reason},
            }),
        )
        with _root_at(tmp):
            problems: list[str] = []
            allowance = CHECKER.load_allowance(problems.append)
            CHECKER.check_command_budget(allowance, problems.append)
            CHECKER.check_allowance_growth(allowance, problems.append)
            return problems


def _git(cwd, *args):
    subprocess.run(["git", "-C", cwd, *args], capture_output=True, text=True, check=True)


def run_ceiling_check(base_lines: int, base_reason: str,
                       head_lines: int, head_reason: str):
    """A real throwaway git history: one commit records `.budget-allowance.json`
    at `base_lines`/`base_reason`; the working tree then holds `head_lines`/
    `head_reason` UNCOMMITTED, the same shape as a ceiling raised in the
    change under review. `base` is passed explicitly rather than exercising
    `_resolve_default_branch`, which depends on this checkout's own remotes
    and branch names, not the fixture's -- that resolution path is covered
    separately, by the "git unavailable" and "no default branch" cases below.
    """
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "plugin", "crew", "commands", "fixture.md"),
               FRONTMATTER + "line\n" * base_lines)
        _write(
            os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
            json.dumps({
                "plugin/crew/commands/fixture.md":
                    {"lines": base_lines, "reason": base_reason},
            }),
        )
        _git(tmp, "init", "-q")
        _git(tmp, "config", "user.email", "test@example.com")
        _git(tmp, "config", "user.name", "test")
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", "base")
        base_sha = subprocess.run(
            ["git", "-C", tmp, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        _write(
            os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
            json.dumps({
                "plugin/crew/commands/fixture.md":
                    {"lines": head_lines, "reason": head_reason},
            }),
        )
        with _root_at(tmp):
            problems: list[str] = []
            allowance = CHECKER.load_allowance(problems.append)
            CHECKER.check_allowance_no_silent_raise(allowance, problems.append, base_sha)
            return problems


def run_ceiling_check_new_entry(head_lines: int, head_reason: str):
    """The base commit has no entry at all for the fixture's path -- a
    brand-new allowance entry, not an existing ceiling being raised."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "plugin", "crew", "commands", "fixture.md"),
               FRONTMATTER + "line\n" * head_lines)
        _write(os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
               json.dumps({}))
        _git(tmp, "init", "-q")
        _git(tmp, "config", "user.email", "test@example.com")
        _git(tmp, "config", "user.name", "test")
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", "base")
        base_sha = subprocess.run(
            ["git", "-C", tmp, "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True,
        ).stdout.strip()
        _write(
            os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
            json.dumps({
                "plugin/crew/commands/fixture.md":
                    {"lines": head_lines, "reason": head_reason},
            }),
        )
        with _root_at(tmp):
            problems: list[str] = []
            allowance = CHECKER.load_allowance(problems.append)
            CHECKER.check_allowance_no_silent_raise(allowance, problems.append, base_sha)
            return problems


def run_ceiling_check_no_git():
    """Not a git working tree at all -- the UNVERIFIED path, not a silent pass."""
    with tempfile.TemporaryDirectory() as tmp:
        _write(os.path.join(tmp, "plugin", "crew", ".budget-allowance.json"),
               json.dumps({"plugin/crew/commands/fixture.md":
                           {"lines": 100, "reason": "T8: to trim"}}))
        with _root_at(tmp):
            problems: list[str] = []
            allowance = CHECKER.load_allowance(problems.append)
            CHECKER.check_allowance_no_silent_raise(allowance, problems.append, None)
            return problems


# The real generator, run the way /crew:onboard and /crew:migrate run it.
GENERATOR = os.path.join(os.path.dirname(os.path.dirname(HERE)), "plugin", "crew",
                         "hooks", "scripts", "crew_instructions.py")


def _rules_fixture(tmp):
    """A consuming repo with one code-map note citing three files, so the
    generator derives `paths: src/alpha/**` for it."""
    for name in ("core.py", "util.py", "io.py"):
        _write(os.path.join(tmp, "src", "alpha", name), "x = 1\n")
    _write(os.path.join(tmp, ".crew", "codemap", "alpha.md"),
           "anchor: repo@abcdef1\n# alpha\n\n## Entry points\n\n"
           "- `src/alpha/core.py:1` - entry.\n- `src/alpha/util.py:1` - util.\n"
           "- `src/alpha/io.py:1` - io.\n\n## Landmines\n\n- the cache is never invalidated.\n")
    _git(tmp, "init", "-q")


def _generate_rules(tmp):
    subprocess.run([sys.executable, GENERATOR, "rules", "--root", tmp],
                   capture_output=True, text=True, check=True)


def run_rules_drift(stage: str) -> list[str]:
    """check_generated_drift on a fixture repo at one stage of the onboard
    loop. ROOT points at the fixture; CREW stays the real plugin, so the
    real crew_instructions.py does the comparing."""
    with tempfile.TemporaryDirectory() as tmp:
        _rules_fixture(tmp)
        note = os.path.join(tmp, ".crew", "codemap", "alpha.md")
        if stage == "none-committed":
            pass
        elif stage == "hand-written-only":
            _write(os.path.join(tmp, ".claude", "rules", "alpha.md"), "mine\n")
        else:
            _generate_rules(tmp)
        if stage in ("edited", "regenerated"):
            with open(note, "a", encoding="utf-8", newline="\n") as fh:
                fh.write("- a second landmine.\n")
        if stage == "regenerated":
            _generate_rules(tmp)
        if stage == "collision":
            _write(os.path.join(tmp, ".crew", "codemap", "beta.md"),
                   "# beta\n\n## Landmines\n\n- `src/alpha/io.py:1` breaks.\n")
            _write(os.path.join(tmp, ".claude", "rules", "beta.md"), "mine\n")
        problems: list[str] = []
        saved = CHECKER.ROOT
        CHECKER.ROOT = tmp
        try:
            CHECKER.check_generated_drift(problems.append)
        finally:
            CHECKER.ROOT = saved
        return problems


def run_main_wiring() -> str:
    """Build one fixture that trips every check `main()` wires up, run
    `main()` itself (not the individual functions the rest of this suite
    calls directly), and return everything it printed. A suite that only
    ever calls `check_command_budget(...)` etc. directly never notices a
    check that main() forgot to call -- see check-marketplace.py's own
    `_test/self-claims.py` "main() wiring" cases for the same gap on that
    checker.
    """
    with tempfile.TemporaryDirectory() as tmp:
        crew = os.path.join(tmp, "plugin", "crew")
        # 1: command over budget, unlisted -> check_command_budget
        _write(os.path.join(crew, "commands", "fixture.md"),
               FRONTMATTER + "line\n" * 150)
        # 2/3: allowance-listed agent, grown, with a ceiling raised in this
        # change and no "raised:" reason -> check_allowance_growth AND
        # check_allowance_no_silent_raise
        _write(os.path.join(crew, "agents", "grown.md"), FRONTMATTER + "line\n" * 90)
        _write(
            os.path.join(crew, ".budget-allowance.json"),
            json.dumps({
                "plugin/crew/agents/grown.md": {"lines": 90, "reason": "T8: to trim"},
                "plugin/crew/agents/gone.md": {"lines": 10, "reason": "T8: to trim"},
            }),
        )
        # git history: base commit records agents/grown.md at 50 lines, so
        # the working tree's 90 is a raise with no "raised:" reason, and
        # agents/gone.md is listed but absent -> check_allowance_paths_exist
        _git(tmp, "init", "-q")
        _git(tmp, "config", "user.email", "test@example.com")
        _git(tmp, "config", "user.name", "test")
        base_allowance = os.path.join(crew, ".budget-allowance.json")
        _write(base_allowance, json.dumps({
            "plugin/crew/agents/grown.md": {"lines": 50, "reason": "T8: to trim"},
        }))
        _git(tmp, "add", "-A")
        _git(tmp, "commit", "-q", "-m", "base")
        _git(tmp, "branch", "-m", "main")
        _write(
            base_allowance,
            json.dumps({
                "plugin/crew/agents/grown.md": {"lines": 90, "reason": "T8: to trim"},
                "plugin/crew/agents/gone.md": {"lines": 10, "reason": "T8: to trim"},
            }),
        )
        # 4: no frontmatter -> check_frontmatter
        _write(os.path.join(crew, "agents", "noheader.md"), "not a frontmatter block\n")
        # 5: stale name, not on the legacy list -> check_stale_names
        _write(os.path.join(crew, "commands", "stale.md"),
               FRONTMATTER + "Dispatch qa-reviewer for the fallback pass.\n")
        # 6: broken relative link -> check_broken_references
        _write(os.path.join(crew, "commands", "brokenlink.md"),
               FRONTMATTER + "See [x](../skills/does-not-exist/SKILL.md).\n")
        # 7: guards.<name> reference -> check_policy_ids; crew_guards.py does
        # not exist in this fixture, so this also proves the "could not
        # import" failure path fires rather than passing silently.
        _write(os.path.join(crew, "commands", "guardref.md"),
               FRONTMATTER + "See guards.notARealGuard for details.\n")
        # 8: a marked AGENTS.md with no crew_instructions.py present in this
        # fixture at all -> check_generated_drift's subprocess call fails,
        # which is itself a form of drift it must report, not swallow.
        _write(os.path.join(tmp, "AGENTS.md"), "<!-- crew:generated -->\nfixture\n")

        saved_argv = sys.argv
        sys.argv = ["check_instructions.py"]
        buf = io.StringIO()
        try:
            with _root_at(tmp), contextlib.redirect_stdout(buf):
                returncode = CHECKER.main()
        finally:
            sys.argv = saved_argv
        output = buf.getvalue()
        assert returncode == 1, f"expected main() to exit 1, got {returncode}: {output}"
        return output


def main() -> int:
    passed = failed = 0

    def check(name, problems, expect_block, needle=""):
        nonlocal passed, failed
        ok = bool(problems) == expect_block
        if ok and needle:
            ok = any(needle in p for p in problems)
        if ok:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")
            print(f"       expected {'a' if expect_block else 'no'} problem"
                  + (f" containing {needle!r}" if needle else ""))
            print(f"       got {problems}")

    def check_true(name, condition):
        nonlocal passed, failed
        if condition:
            passed += 1
            print(f"  ok   {name}")
        else:
            failed += 1
            print(f"  FAIL {name}")

    # --- main() wiring (scripts/_test/instruction-budgets.py:152's own gap) --
    # Runs before anything else in this suite: check_policy_ids's
    # "could not import crew_guards" path only fires the first time
    # `_guard_names` looks for it on a `sys.path` that has never seen the
    # real `plugin/crew/hooks/scripts` -- a later case in this same process
    # (the codex hooks.json marker test) imports crew_instructions using the
    # REAL path on purpose and leaves it on `sys.path` for the rest of the
    # process, which would otherwise let crew_guards resolve from there too
    # and mask this exact gap.
    #
    # Every case elsewhere in this suite calls a check function directly;
    # none of them would notice a check main() forgot to wire in. This runs
    # main() itself on one fixture built to trip all nine, and asserts each
    # one's own message shape is present in what main() actually printed.
    wiring_output = run_main_wiring()
    for label, needle in (
        ("check_command_budget", "budget 120"),
        ("check_allowance_growth", "grew to"),
        ("check_allowance_no_silent_raise", "ceiling raised"),
        ("check_allowance_paths_exist", "no longer exists"),
        ("check_frontmatter", "no frontmatter block"),
        ("check_generated_drift", "generated agents: drift"),
        ("check_stale_names", "stale name"),
        ("check_broken_references", "does not resolve"),
        ("check_policy_ids", "could not import crew_guards"),
    ):
        check_true(f"main() wiring: {label} contributed a failure",
                   needle in wiring_output)

    # --- generated .claude/rules drift (what /crew:onboard and /crew:migrate write) --
    check("rules generated by the onboard call and untouched since pass the drift check",
          run_rules_drift("generated"), False)
    check("a codemap note edited without regenerating its rule FAILS the drift check",
          run_rules_drift("edited"), True, "generated rules: drift - stale: ")
    check("regenerating after the edit passes the drift check again",
          run_rules_drift("regenerated"), False)
    check("no generated rule committed at all is a no-op, not a failure",
          run_rules_drift("none-committed"), False)
    check("a hand-written rule with nothing generated beside it is left to its owner",
          run_rules_drift("hand-written-only"), False)
    collision = run_rules_drift("collision")
    check("a hand-written file at a generated rule's path is reported under its own label",
          collision, True, "hand-written file, not drift - ")
    check_true("that hand-written collision is not also reported as drift",
               not any("generated rules: drift" in p for p in collision))

    # --- command line budget ------------------------------------------
    check(
        "a command file over 120 lines with no allowance entry is red",
        run_command_budget(150, allowance=None),
        True,
        "budget 120",
    )
    check(
        "a command file at exactly 120 lines is allowed",
        run_command_budget(120 - len(FRONTMATTER.splitlines()), allowance=None),
        False,
    )
    check(
        "a command file over 120 lines but listed in the allowance is allowed",
        run_command_budget(150, allowance={
            "plugin/crew/commands/fixture.md":
                {"lines": 150 + len(FRONTMATTER.splitlines()), "reason": "T8: to trim"},
        }),
        False,
    )
    check(
        "an allowance-listed file that grew past its recorded line count is red",
        run_allowance_growth(recorded_lines=150, total_lines=160,
                              reason="T8: to trim"),
        True,
        "grew to",
    )
    check(
        "an allowance-listed file at exactly its recorded line count is allowed",
        run_allowance_growth(recorded_lines=150, total_lines=150,
                              reason="held: awaiting owner decision on T2 deletions"),
        False,
    )
    check(
        "an allowance entry with an unrecognised reason is rejected",
        run_allowance_growth(recorded_lines=150, total_lines=150,
                              reason="because I said so"),
        True,
        "must be",
    )
    check(
        "BLOCK1: an allowance entry naming an AGENT (not a command) still fails on growth",
        run_allowance_growth(recorded_lines=150, total_lines=160,
                              reason="held: awaiting owner decision on T2 deletions",
                              path_rel="plugin/crew/agents/fixture.md"),
        True,
        "grew to",
    )
    check(
        "BLOCK1: same agent entry at exactly its recorded line count is allowed",
        run_allowance_growth(recorded_lines=150, total_lines=150,
                              reason="held: awaiting owner decision on T2 deletions",
                              path_rel="plugin/crew/agents/fixture.md"),
        False,
    )
    check(
        "BLOCK1: an allowance entry naming a SKILL still fails on growth",
        run_allowance_growth(recorded_lines=50, total_lines=60,
                              reason="held: awaiting owner decision on T2 deletions",
                              path_rel="plugin/crew/skills/fixture/SKILL.md"),
        True,
        "grew to",
    )
    check(
        "BLOCK2: a nested commands/group/x.md over budget is still checked",
        run_command_budget(150, allowance=None, command_path=os.path.join("group", "fixture.md")),
        True,
        "budget 120",
    )
    check(
        "BLOCK2: a nested commands/group/x.md missing frontmatter is still checked",
        run_frontmatter("no frontmatter here\n", command_path=os.path.join("group", "fixture.md")),
        True,
        "no frontmatter",
    )
    check(
        "a reason of the explicit raised: form is accepted by load_allowance",
        run_allowance_growth(recorded_lines=150, total_lines=150,
                              reason="raised: BLOCK3 example, approved by owner"),
        False,
    )

    # --- allowance ceiling not silently raised (BLOCK3) ------------------
    check(
        "BLOCK3: a ceiling raised with no reason change fails, comparing to a real base commit",
        run_ceiling_check(base_lines=100, base_reason="T8: to trim",
                           head_lines=150, head_reason="T8: to trim"),
        True,
        "ceiling raised",
    )
    check(
        "BLOCK3: the same raise WITH the explicit 'raised: <why>' reason passes",
        run_ceiling_check(base_lines=100, base_reason="T8: to trim",
                           head_lines=150, head_reason="raised: BLOCK3 needed the room"),
        False,
    )
    check(
        "BLOCK3: a ceiling that did not move is allowed regardless of reason text",
        run_ceiling_check(base_lines=100, base_reason="T8: to trim",
                           head_lines=100, head_reason="T8: to trim"),
        False,
    )
    check(
        "BLOCK3: a brand-new entry absent from the base is not a 'raise'",
        run_ceiling_check_new_entry(head_lines=999, head_reason="T8: to trim"),
        False,
    )
    check(
        "BLOCK3: no git repository at all is UNVERIFIED, not a silent pass",
        run_ceiling_check_no_git(),
        True,
        "UNVERIFIED",
    )

    # --- stale names (BLOCK4: inverted default) --------------------------
    check(
        "a stale name in a file NOT on the legacy exemption list is red by default",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the fallback pass.\n",
            "plugin/crew/commands/newthing.md",
        ),
        True,
        "stale name",
    )
    check(
        "the same stale name marked <!-- deliberate --> in the same paragraph is allowed",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the fallback pass. <!-- deliberate -->\n",
            "plugin/crew/commands/newthing.md",
        ),
        False,
    )
    check(
        "a marker on the NEXT line of the same paragraph still exempts a wrapped sentence",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the\nfallback pass. <!-- deliberate -->\n",
            "plugin/crew/commands/newthing.md",
        ),
        False,
    )
    check(
        "a marker in the NEXT paragraph does not exempt an earlier one",
        run_stale_names(
            FRONTMATTER + "Dispatch qa-reviewer for the fallback pass.\n\n"
            "Unrelated paragraph. <!-- deliberate -->\n",
            "plugin/crew/commands/newthing.md",
        ),
        True,
        "stale name",
    )
    check(
        "a stale name inside frontmatter (a description) is not flagged",
        run_stale_names(
            "---\ndescription: crew 1.0 successor of qa-reviewer\n---\n\nbody text\n",
            "plugin/crew/agents/newagent.md",
        ),
        False,
    )
    check(
        "BLOCK4: the same stale name in a file ON the legacy exemption list is not checked",
        run_stale_names(
            FRONTMATTER + "qa-reviewer\n",
            "plugin/crew/commands/legacy.md",
            legacy=True,
        ),
        False,
    )
    check(
        "BLOCK4: an agent file (not just a command) not on the legacy list is red too",
        run_stale_names(
            FRONTMATTER + "qa-reviewer\n",
            "plugin/crew/agents/newagent2.md",
        ),
        True,
        "stale name",
    )

    # --- frontmatter close (FIX :180) -------------------------------------
    check(
        "a frontmatter block with no closing --- line is flagged",
        run_frontmatter("---\ndescription: x\n"),
        True,
        "no frontmatter",
    )
    check(
        "four dashes is not an exact closing --- line",
        run_frontmatter("---\ndescription: x\n----\n"),
        True,
        "no frontmatter",
    )
    check(
        "--- followed by trailing text on the same line is not a valid close",
        run_frontmatter("---\ndescription: x\n--- oops\n"),
        True,
        "no frontmatter",
    )
    check(
        "an exact closing --- line (with trailing whitespace) is accepted",
        run_frontmatter("---\ndescription: x\n--- \n"),
        False,
    )

    # --- broken references ----------------------------------------------
    check(
        "a ${CLAUDE_PLUGIN_ROOT} path that does not exist is red",
        run_broken_references(
            FRONTMATTER + "Run ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/does_not_exist.py\n"
        ),
        True,
        "names missing",
    )
    check(
        "a ${CLAUDE_PLUGIN_ROOT} path that exists is allowed",
        run_broken_references(
            FRONTMATTER + "Run ${CLAUDE_PLUGIN_ROOT}/commands/fixture.md\n"
        ),
        False,
    )
    check(
        "a relative Markdown link that does not resolve is red",
        run_broken_references(
            FRONTMATTER + "See [the skill](../skills/does-not-exist/SKILL.md).\n"
        ),
        True,
        "does not resolve",
    )
    check(
        "an http(s) link is never checked as a local path",
        run_broken_references(
            FRONTMATTER + "See [docs](https://example.com/does/not/exist).\n"
        ),
        False,
    )

    # --- link parser: angle brackets, titles, query strings, parens (FIX :305) --
    check(
        "an angle-bracket <dest> that does not resolve is red",
        run_broken_references(
            FRONTMATTER + "See [x](<../skills/does-not-exist/SKILL.md>).\n"
        ),
        True,
        "does not resolve",
    )
    check(
        "a bare dest with a title in quotes that does not resolve is red",
        run_broken_references(
            FRONTMATTER + 'See [x](../skills/does-not-exist/SKILL.md "the skill").\n'
        ),
        True,
        "does not resolve",
    )
    check(
        "a dest with a query string strips the query before resolving",
        run_broken_references(
            FRONTMATTER + "See [x](fixture.md?utm_source=x).\n"
        ),
        False,
    )
    check(
        "a bare dest containing one level of balanced parens resolves the whole thing",
        run_broken_references(
            FRONTMATTER + "See [x](does-not-exist(1).md).\n"
        ),
        True,
        "does not resolve: does-not-exist(1).md",
    )

    # --- reference-style links and definitions (FIX :94) -------------------
    check(
        "a full reference link [text][label] resolves against its definition",
        run_broken_references(
            FRONTMATTER + "See [the skill][missing].\n\n"
            "[missing]: ../skills/does-not-exist/SKILL.md\n"
        ),
        True,
        "does not resolve",
    )
    check(
        "a collapsed reference link [text][] uses the text as the label",
        run_broken_references(
            FRONTMATTER + "See [does-not-exist.md][].\n\n"
            "[does-not-exist.md]: does-not-exist.md\n"
        ),
        True,
        "does not resolve",
    )
    check(
        "a reference link resolving to an existing file is allowed",
        run_broken_references(
            FRONTMATTER + "See [it][ok].\n\n"
            "[ok]: fixture.md\n"
        ),
        False,
    )
    check(
        "a [text][label] with no matching definition is not this checker's business",
        run_broken_references(
            FRONTMATTER + "See [text][nowhere-defined].\n"
        ),
        False,
    )

    # --- policy-ID token matching (FIX :95) ---------------------------------
    check_true(
        "guards.<name> is matched to the whole token, underscore included",
        [m.group(1) for m in CHECKER.GUARD_REF_RE.finditer(
            "guards.cloudGuard_extra and guards.forcePush and guards.prod*"
        )] == ["cloudGuard_extra", "forcePush", "prod"],
    )

    # --- .codex/hooks.json generated-marker rule matches crew_instructions.py (FIX :211) --
    generated_hooks_json = json.dumps({"hooks": {"SessionStart": [{"hooks": [{
        "type": "command",
        "command": 'bash "x/hooks/scripts/crew-context.sh" --harness codex',
    }]}]}})
    handwritten_hooks_json = json.dumps({"hooks": {"SessionStart": [{"hooks": [{
        "type": "command", "command": "echo hi",
    }]}]}})
    check_true(
        "a hooks.json shaped like crew_instructions.py's own output is recognised as generated",
        CHECKER._codex_hooks_looks_generated(generated_hooks_json) is True,
    )
    check_true(
        "a hand-written hooks.json (any other shape) is never treated as generated",
        CHECKER._codex_hooks_looks_generated(handwritten_hooks_json) is False,
    )

    print(f"\ninstruction-budgets: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
