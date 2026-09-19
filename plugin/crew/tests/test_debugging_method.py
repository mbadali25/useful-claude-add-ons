"""Crew ships a debugging method, and something dispatches it.

Before crew 0.19.66 this plugin had 27 commands and 19 skills and no method
for finding a cause. The gap was not subtle -- no command named diagnosis, no
skill described one, no role's job was to establish why something broke -- and
what fills that gap by default is fixing where the error surfaced, which is the
defect that comes back wearing a different symptom.

The method itself is `superpowers:systematic-debugging` by Jesse Vincent, MIT,
copied under `skills/crew-debugging/`. So these assertions cover three distinct
things that regress differently:

1. **The copy is complete.** Specifically the four adversarial pressure tests,
   which are the part most likely to be dropped as "not documentation" -- and
   they are exactly what makes the method hold in the situation that motivated
   it, where a deadline makes guessing tempting.
2. **The attribution survives.** MIT's one substantive condition is that the
   notice travel with the copy. A copy whose notice was edited away is a
   licence violation that no test but this one would notice.
3. **Something dispatches it.** A skill nothing routes to is a file. The
   routing lives in `commands/work.md` and `agents/developer.md`, and it is
   prose in a subagent prompt, so -- exactly as in test_codemap_read_path.py
   and test_scope_discipline.py -- there is nothing executable to run and the
   only mechanical regression is the instruction going missing. That is the
   state the feature would have been in from birth without this file.

Assertions run through `_norm`, so they survive a rewrap and fail only on the
sentence actually being removed.

**0.19.67 adds a fourth thing**, five Codex (gpt-6-astra) findings against
0.19.66: `commands/debug.md` overclaimed what the missing `Write`/`Edit` grant
enforces (`Bash` can write a file as readily as `Edit` can), `find-polluter.sh`
shipped at file mode `100644` so upstream's documented invocation fails with
"permission denied" on Linux, and the script inherited three upstream
defects -- unquoted word-splitting on a test filename containing whitespace,
a discarded runner exit status, and a false-clean verdict when zero tests
actually ran. The four behavioural tests below run the real script against a
fake `npm` on `PATH` rather than asserting on its source text, because these
are exactly the shape of bug a source-text assertion cannot catch: the code
can *look* like it checks something while still discarding the result.
"""
import os
import pathlib
import re
import subprocess
import tempfile

import pytest

import crew_fixtures

import context  # noqa: F401  pylint: disable=unused-import

PLUGIN = pathlib.Path(__file__).resolve().parents[1]
SKILL_DIR = PLUGIN / "skills" / "crew-debugging"

# For the two behavioural find-polluter.sh tests below. Resolved once at
# import time and proved by actually running a probe script, the same
# safeguard test_verify_gate_lock_sh.py uses -- a plausible-looking bash on
# PATH that cannot open a Windows path is a documented failure mode here.
_BASH = crew_fixtures.resolve_bash()

# Upstream's adversarial scenarios plus the no-pressure control. The control
# matters: a model that answers test-academic correctly and then folds under
# test-pressure-1 has shown it knows the method and abandons it, which is a
# different and worse finding than not knowing it.
PRESSURE_TESTS = (
    "test-pressure-1.md",
    "test-pressure-2.md",
    "test-pressure-3.md",
    "test-academic.md",
)

# The supporting techniques SKILL.md points at by name. A pointer to a file
# that is not there is worse than no pointer: it reads as an available
# technique right up to the moment somebody needs it.
TECHNIQUES = (
    "root-cause-tracing.md",
    "defense-in-depth.md",
    "condition-based-waiting.md",
    "find-polluter.sh",
)


def _norm(text):
    """Collapse runs of whitespace so an assertion survives a rewrap."""
    return re.sub(r"\s+", " ", text)


def _skill():
    return _norm((SKILL_DIR / "SKILL.md").read_text(encoding="utf-8"))


def _agent(name):
    return _norm((PLUGIN / "agents" / f"{name}.md").read_text(encoding="utf-8"))


def _command(name):
    return _norm((PLUGIN / "commands" / f"{name}.md").read_text(encoding="utf-8"))


def test_the_skill_exists_with_its_entry_point():
    assert (SKILL_DIR / "SKILL.md").is_file(), (
        "skills/crew-debugging/SKILL.md is gone, so crew has no debugging "
        "method again -- the exact gap 0.19.66 was written to close"
    )


def test_the_pressure_tests_ship():
    """These are the first thing a tidy-up deletes, and the reason the method
    holds under the conditions that break it."""
    for name in PRESSURE_TESTS:
        assert (SKILL_DIR / name).is_file(), (
            f"{name} is missing. The pressure tests are not examples and not "
            "documentation -- they are the check on whether the Iron Law "
            "survives a deadline, sunk cost, or a senior engineer who is "
            "certain. Dropping them drops the part that works in exactly the "
            "situation the skill was added for"
        )
    body = _skill()
    for name in PRESSURE_TESTS:
        assert name in body, (
            f"SKILL.md no longer names {name}, so the file ships but nothing "
            "tells a reader it exists or what it is for"
        )


def test_the_supporting_techniques_ship_and_are_named():
    for name in TECHNIQUES:
        assert (SKILL_DIR / name).is_file(), f"{name} is missing from the skill"
        assert name in _skill(), (
            f"SKILL.md no longer names {name}; a technique nothing points at "
            "is a file nobody opens"
        )


def test_find_polluter_is_not_crlf():
    """`pathlib.write_text` is text mode on Windows, so a rewrite of this file
    through the obvious call turns every \\n into \\r\\n and bash dies on the
    shebang as `bad interpreter: ...^M`. The repo's .gitattributes governs
    what git stores, not what sits in the worktree bash executes -- so this
    asserts the bytes on disk, which is the thing that actually breaks."""
    raw = (SKILL_DIR / "find-polluter.sh").read_bytes()
    assert b"\r\n" not in raw, (
        "find-polluter.sh has CRLF line endings in the worktree. It will fail "
        "on its shebang as 'bad interpreter'. Rewrite it with newline='\\n' "
        "or restore with `git checkout -- <path>`"
    )
    assert raw.startswith(b"#!/usr/bin/env bash"), "shebang lost"


def test_the_attribution_survives():
    """MIT's one substantive condition. A copy that loses the notice is a
    licence violation, and nothing else in this repo would report it."""
    body = _skill()
    assert "Jesse Vincent" in body, (
        "SKILL.md dropped the author attribution for a method it copied "
        "wholesale from superpowers:systematic-debugging"
    )
    assert "MIT" in body, "SKILL.md no longer states the licence of what it copied"
    assert "plugin/crew/NOTICE.md" in body, (
        "SKILL.md no longer points at the notice file carrying the full "
        "copyright and permission text, so the attribution chain is broken "
        "at the only place a reader would follow it"
    )

    notice = PLUGIN / "NOTICE.md"
    assert notice.is_file(), (
        "plugin/crew/NOTICE.md is gone. It is the only place this plugin "
        "carries the MIT copyright and permission notice it is obliged to "
        "reproduce"
    )
    notice_body = _norm(notice.read_text(encoding="utf-8"))
    assert "Copyright (c) 2025 Jesse Vincent" in notice_body
    assert "Permission is hereby granted, free of charge" in notice_body, (
        "NOTICE.md no longer contains the MIT permission notice. The "
        "copyright line alone does not satisfy the licence -- it requires "
        "both, verbatim"
    )
    assert "crew-debugging" in notice_body, (
        "NOTICE.md no longer says WHICH files the notice covers, which makes "
        "it unattributable to anything in the next reader's tree"
    )


def test_the_iron_law_is_intact():
    """The whole method reduces to this one line under pressure. Softening it
    -- to 'should', or 'where time allows' -- is the failure it exists to
    prevent, and it would not fail any other check."""
    body = _skill()
    assert "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST" in body, (
        "SKILL.md lost or reworded the Iron Law. Every pressure test in this "
        "directory is a test of that one sentence"
    )


def test_phase_one_reads_crews_own_artifacts():
    """This is the adaptation -- the reason crew has a copy rather than a
    dependency. Lose it and the file is a duplicate of upstream."""
    body = _skill()
    for source, why in (
        ("## Landmines", "the per-repo record of what already broke here"),
        (".crew/codemap/INDEX.md", "the entry point into the map"),
        (".crew/codemap/schema-<datasource>.md", "the schema note for data defects"),
        ("graphify-out/graph.json", "the code graph, for a cross-file backward trace"),
        (".crew/verify.json", "the command the gate will actually run"),
    ):
        assert source in body, (
            f"SKILL.md's Phase 1 no longer names {source} ({why}). Without "
            "it the method re-derives this repo's failure modes from the diff "
            "in an empty context, every time, which is what crew already "
            "fixed once for the reviewer"
        )
    assert "git diff --name-only" in body, (
        "SKILL.md dropped the anchor re-check. Without it a note whose anchor "
        "is behind HEAD reads as 'wrong' rather than 'check it', so a current "
        "note gets discarded and the evidence source stops being used"
    )


def test_the_upstream_skill_is_preferred_when_present():
    body = _skill()
    assert "Invoke `superpowers:systematic-debugging` with the `Skill` tool" in body, (
        "SKILL.md no longer instructs an invocation of the upstream skill, so "
        "a session with the maintained original installed reads crew's "
        "snapshot instead. Asserting the NAME is not enough -- it appears "
        "several times in this file in sentences about provenance, so the "
        "routing step can be deleted while every mention survives. That is "
        "not hypothetical: it is the miss this suite's own sabotage run "
        "found, and the reason this assertion names the instruction"
    )
    assert "`Skill` tool" in body, (
        "the availability check must be a real Skill invocation. Prose asking "
        "the model to consider whether something is installed is not "
        "harness-enforced; an invocation of an absent skill errors, which is"
    )
    assert "absent from this session" in body or "absent **from this session**" in body, (
        "SKILL.md dropped the honest limit on the availability check. A "
        "failed invocation proves the skill is missing from THIS SESSION, "
        "not from the machine -- a disabled-but-installed plugin looks "
        "identical. Reporting it as 'not installed' is the unknown "
        "collapsing into a definite-sounding value, which is this repo's "
        "named recurring defect"
    )


def test_the_command_exists_and_cannot_edit_the_tree():
    """'Diagnosis does not patch' is enforced by the tool grant, not by the
    prose. A Write or Edit in allowed-tools silently converts this command
    into one that can fix what it was supposed to only explain."""
    path = PLUGIN / "commands" / "debug.md"
    assert path.is_file(), "commands/debug.md is gone; /crew:debug no longer exists"
    raw = path.read_text(encoding="utf-8")
    front = raw.split("---")[1]
    tools = [t.strip() for t in front.split("allowed-tools:")[1].split("\n")[0].split(",")]
    for forbidden in ("Write", "Edit"):
        assert forbidden not in tools, (
            f"/crew:debug was granted {forbidden}. The command's contract is "
            "that it ends with a cause and evidence and does not touch the "
            "tree; that separation is what makes the evidence auditable "
            "apart from the patch"
        )
    assert "Skill" in tools, (
        "/crew:debug lost the Skill tool, so it cannot load the method it "
        "exists to run, nor probe for the upstream skill"
    )


def test_the_command_carries_the_deferred_contract():
    """Composes with the scope discipline 0.19.62 gave the roles. Debugging
    finds unrelated problems more reliably than anything else the crew does,
    because tracing a data flow means reading code nobody was looking at."""
    body = _command("debug")
    assert "## Deferred — and where it went" in body, (
        "debug.md lost its Deferred section, so an investigation that turned "
        "up three unrelated defects reports identically to one that found "
        "none"
    )
    assert "Nothing deferred." in body, (
        "the empty case must be spelled. An absent section reads the same "
        "whether nothing was found or something was found and quietly fixed"
    )
    assert "TODO.md" in body, (
        "debug.md no longer says where a deferred finding goes, which makes "
        "the instruction unactionable and the queue unwritten"
    )


def test_work_routes_a_defect_to_the_debug_command():
    """A copy nobody dispatches is a file, not an integration."""
    body = _command("work")
    assert "run `/crew:debug` before you plan" in body, (
        "work.md no longer routes a defect to /crew:debug before planning, so "
        "a defect ticket goes straight to plan-and-fix and the method ships "
        "unreachable. The bare string `/crew:debug` also appears in the "
        "paragraph explaining what the command returns, so asserting only "
        "the name passes while the routing step is gone -- a miss this "
        "suite's sabotage run actually produced"
    )
    assert "defect rather than a feature" in body, (
        "work.md dropped the condition that decides when to debug. 'Run "
        "/crew:debug' with no trigger is either always or never, and in "
        "practice never"
    )


def test_developer_debugs_before_proposing_a_fix():
    body = _agent("developer")
    assert "run `/crew:debug` **before** you write the fix" in body, (
        "developer.md no longer runs /crew:debug before a fix, so the role "
        "that actually writes the diff is the one role not using the method. "
        "The bare name appears again further down, in the paragraph about a "
        "brief that already carries a debug report, so a presence check on "
        "it alone passes with the instruction deleted"
    )
    assert "NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST" in body, (
        "developer.md dropped the Iron Law. Pointing at a command without "
        "stating the rule it enforces leaves the obvious fix looking "
        "reasonable, which is the whole failure mode"
    )
    assert "follow the `crew-debugging` skill it loads" in body, (
        "developer.md no longer sends the role into the crew-debugging skill, "
        "so it reaches the command but not the method behind it. Asserting "
        "the bare skill name passes on the mention in the reporting "
        "requirement below, which is about provenance rather than method"
    )


def test_debug_md_no_longer_overclaims_tool_grant_as_enforcement():
    """0.19.67, Codex finding #1. The absence of Write/Edit does not stop a
    fix landing -- `Bash` can write a file as readily as `Edit` can -- so
    claiming it "is the enforcement" is false, and false in the direction
    that matters: it tells a reader the Iron Law is mechanically guaranteed
    when it is a rule the role has to actually follow."""
    body = _command("debug")
    assert "the absence of an editing tool is not" not in body, (
        "debug.md still claims the missing Write/Edit grant is the "
        "enforcement for the Iron Law. Bash can write a file, so nothing in "
        "the tool grant actually prevents a patch landing without root-cause "
        "investigation first -- the passage overclaims a guarantee the grant "
        "does not provide"
    )
    assert "removes the" in body and "convenient" in body and "path to a fix" in body, (
        "debug.md dropped the corrected framing -- the tool grant removes "
        "the convenient path to a fix, not the possibility of one -- so the "
        "distinction this fix exists to draw is gone along with the "
        "overclaim it replaced"
    )


def test_find_polluter_is_executable_in_the_index():
    """0.19.67, Codex finding #2. `find-polluter.sh` shipped at file mode
    `100644`, so upstream's own documented invocation
    (`./find-polluter.sh ...`) fails with "permission denied" on Linux and
    every Windows checkout that respects the index bit. The worktree bit on
    Windows is meaningless -- this has to check the INDEX mode, which is
    what a Linux checkout actually gets, via `git ls-files -s` rather than
    `os.access` or `pathlib.Path.stat()` on the local file."""
    done = subprocess.run(
        ["git", "ls-files", "-s", "skills/crew-debugging/find-polluter.sh"],
        cwd=str(PLUGIN), capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL, check=False,
    )
    assert done.returncode == 0, (
        f"git ls-files -s failed (exit {done.returncode}): {done.stderr}"
    )
    mode = done.stdout.split()[0] if done.stdout.split() else ""
    assert mode == "100755", (
        f"find-polluter.sh is tracked at mode {mode!r}, not 100755. Fix with "
        "`git update-index --chmod=+x "
        "plugin/crew/skills/crew-debugging/find-polluter.sh` -- a worktree "
        "chmod alone does not change what a fresh Linux clone gets, only the "
        "index bit does"
    )


def _write_fake_npm(bin_dir, exit_code):
    """A stand-in test runner on PATH, minimal enough that its only job is to
    exit with a chosen code -- never mistaken for a real npm.
    `newline='\\n'`: this repo's own landmine list warns that `write_text`'s
    default text mode turns a `.sh` into CRLF on Windows, which dies on the
    shebang as `bad interpreter: ...^M`."""
    npm_path = bin_dir / "npm"
    npm_path.write_text(f"#!/usr/bin/env bash\nexit {exit_code}\n",
                         encoding="utf-8", newline="\n")
    npm_path.chmod(0o755)
    return npm_path


def _run_find_polluter(tmp_path, pollution_check, pattern, npm_exit=0):
    """Runs the real (fixed) find-polluter.sh against a throwaway repo with
    one matching test file and a fake `npm` standing in for the real runner,
    and returns the CompletedProcess."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "sample.test.ts").write_text("// fixture\n", encoding="utf-8")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _write_fake_npm(bin_dir, npm_exit)

    script = str(SKILL_DIR / "find-polluter.sh").replace("\\", "/")
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
    # encoding="utf-8": the script's own output has emoji in it, and
    # subprocess.run's text-mode default on Windows is the console codepage
    # (cp1252 here), which raises UnicodeDecodeError on those bytes rather
    # than on anything this fix touches.
    return subprocess.run(
        [_BASH, script, pollution_check, pattern],
        cwd=str(repo), capture_output=True, text=True, timeout=30,
        stdin=subprocess.DEVNULL, env=env, check=False,
        encoding="utf-8", errors="replace",
    )


def _write_logging_fake_npm(bin_dir, log_path):
    """A stand-in npm that records each invocation's argument count and the
    exact bytes of every argument, one line per call. The defect this backs
    (0.19.67, Codex finding #3) is about what gets exec'd, not what gets
    printed, so `_write_fake_npm`'s plain exit code is not enough here --
    the log has to distinguish one call with one argument from two calls
    each with half of it."""
    npm_path = bin_dir / "npm"
    log = str(log_path).replace("\\", "/")
    script = (
        "#!/usr/bin/env bash\n"
        '{ printf "argc=%d" "$#"; for a in "$@"; do printf " [%s]" "$a"; '
        f'done; printf "\\n"; }} >> "{log}"\n'
        "exit 0\n"
    )
    npm_path.write_text(script, encoding="utf-8", newline="\n")
    npm_path.chmod(0o755)
    return npm_path


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_keeps_a_whitespace_filename_as_one_argument():
    """0.19.67, Codex finding #3. The original loop was
    `for TEST_FILE in $TEST_FILES`, which word-splits on IFS -- a test file
    named `has space.test.ts` became two runner invocations, `./src/has`
    and `space.test.ts`, neither of which is the real file. Fixed with a
    `while IFS= read -r` loop, which reads one line (one matched path) per
    iteration regardless of what it contains."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "has space.test.ts").write_text(
            "// fixture\n", encoding="utf-8")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        log_path = tmp_path / "npm-calls.log"
        _write_logging_fake_npm(bin_dir, log_path)

        script = str(SKILL_DIR / "find-polluter.sh").replace("\\", "/")
        env = dict(os.environ)
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            [_BASH, script, ".nonexistent-pollution-marker", "src/**/*.test.ts"],
            cwd=str(repo), capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL, env=env, check=False,
            encoding="utf-8", errors="replace",
        )
        calls = (log_path.read_text(encoding="utf-8").splitlines()
                 if log_path.exists() else [])

    assert result.returncode == 0, (
        "find-polluter.sh did not exit clean against a single passing test "
        f"whose filename contains a space.\nstdout:\n{result.stdout}\n"
        f"stderr:\n{result.stderr}"
    )
    assert len(calls) == 1, (
        f"expected exactly one npm invocation, got {len(calls)}: {calls!r}. "
        "More than one call means the filename was split into fragments and "
        "run as separate, invalid invocations -- this is the miss a plain "
        "exit-code check on find-polluter.sh's own stdout would not catch, "
        "because the sabotaged version still prints 'all tests clean'"
    )
    assert calls[0] == "argc=2 [test] [./src/has space.test.ts]", (
        f"npm was not invoked with the full path as one argument: {calls[0]!r}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_reports_runner_failure_instead_of_clean():
    """0.19.67, Codex finding #4. A runner that cannot even execute (exit
    127, command not found) was previously discarded by `|| true` and read
    as "ran clean". A runner failure and a passing test are different
    findings and must not collapse into the same exit code."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_find_polluter(
            pathlib.Path(tmp), ".nonexistent-pollution-marker",
            "src/**/*.test.ts", npm_exit=127,
        )
    assert result.returncode != 0, (
        "find-polluter.sh exited 0 against a runner that exits 127 -- a "
        "broken runner is being reported as a clean investigation.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "RUNNER FAILED" in result.stdout, (
        "find-polluter.sh did not name the runner failure in its output.\n"
        f"stdout:\n{result.stdout}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_reports_no_tests_ran_instead_of_clean():
    """0.19.67, Codex finding #5. An unmatched pattern executes zero tests,
    and zero tests run is not evidence of a clean investigation -- it is no
    evidence at all. Runs against a real fixture repo with an unmatched
    pattern, so no test file is ever found or executed."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_find_polluter(
            pathlib.Path(tmp), ".nonexistent-pollution-marker",
            "nomatch/**/*.spec.ts", npm_exit=0,
        )
    assert result.returncode != 0, (
        "find-polluter.sh exited 0 with an unmatched pattern -- zero tests "
        "executed is being reported as a clean investigation.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "NO TESTS RAN" in result.stdout, (
        "find-polluter.sh did not report that no tests ran.\n"
        f"stdout:\n{result.stdout}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_runner_does_not_drain_the_test_list_stdin():
    """0.19.69, Codex finding #1 on the 0.19.67 fix. The `while IFS= read
    -r TEST_FILE; do ... done <<< "$TEST_FILES"` loop drives `read` off
    the here-string on fd 0. Without its own stdin the runner inherits
    that fd, and a runner that reads stdin to EOF (some do) drains the
    rest of the test list before the next `read` can see it -- the loop
    silently ends after one file. This is the same landmine
    `verify-gate.sh` documents for its own `while read` loop over a
    here-string. Fixed by giving the runner `< /dev/null`.

    Reproduction: two fixture files. The fake npm drains stdin for the
    first (`a`) and would create pollution for the second (`b`) -- so a
    clean verdict here means `b` was never run, not that it is clean."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.test.ts").write_text("// fixture a\n", encoding="utf-8")
        (repo / "src" / "b.test.ts").write_text("// fixture b\n", encoding="utf-8")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker = str(tmp_path / ".pollution-marker").replace("\\", "/")
        npm_path = bin_dir / "npm"
        npm_path.write_text(
            "#!/usr/bin/env bash\n"
            'case "$2" in\n'
            "  *a.test.ts) cat > /dev/null; exit 0 ;;\n"
            f'  *b.test.ts) touch "{marker}"; exit 0 ;;\n'
            "esac\n"
            "exit 0\n",
            encoding="utf-8", newline="\n",
        )
        npm_path.chmod(0o755)

        script = str(SKILL_DIR / "find-polluter.sh").replace("\\", "/")
        env = dict(os.environ)
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            [_BASH, script, marker, "src/**/*.test.ts"],
            cwd=str(repo), capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL, env=env, check=False,
            encoding="utf-8", errors="replace",
        )

    assert "[2/2]" in result.stdout, (
        "the second test file never ran. A runner that drains the loop's "
        "stdin consumes the rest of the test list before `read` sees it, "
        f"which reads identically to 'only one test matched'.\nstdout:\n"
        f"{result.stdout}"
    )
    assert result.returncode != 0 and "FOUND POLLUTER" in result.stdout, (
        "b.test.ts's pollution was not reported -- a drained stdin ends "
        "the loop after the first file and reports a false clean verdict "
        f"instead.\nstdout:\n{result.stdout}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_reports_the_polluter_even_when_it_also_exits_nonzero():
    """0.19.69, Codex finding #2 on the 0.19.67 fix. Finding pollution IS a
    test exiting non-zero in the common case -- a leaked file plus a failed
    assertion in the same test. Treating every non-zero exit as a runner
    failure reported FOUND POLLUTER as RUNNER FAILED and aborted before the
    pollution check ever ran. Fixed by checking pollution unconditionally
    and reserving RUNNER FAILED for exit 126/127 (runner could not
    execute), not for the test's own exit code."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.test.ts").write_text("// fixture\n", encoding="utf-8")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker = str(tmp_path / ".pollution-marker").replace("\\", "/")
        npm_path = bin_dir / "npm"
        npm_path.write_text(
            f'#!/usr/bin/env bash\ntouch "{marker}"\nexit 1\n',
            encoding="utf-8", newline="\n",
        )
        npm_path.chmod(0o755)

        script = str(SKILL_DIR / "find-polluter.sh").replace("\\", "/")
        env = dict(os.environ)
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            [_BASH, script, marker, "src/**/*.test.ts"],
            cwd=str(repo), capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL, env=env, check=False,
            encoding="utf-8", errors="replace",
        )

    assert result.returncode != 0, (
        f"find-polluter.sh exited 0 against a test that polluted and "
        f"failed.\nstdout:\n{result.stdout}"
    )
    assert "FOUND POLLUTER" in result.stdout, (
        "the polluter was not reported.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "RUNNER FAILED" not in result.stdout, (
        "an ordinary non-zero test exit (1) was reported as RUNNER FAILED, "
        "which means the pollution check never ran for a test that "
        f"actually polluted.\nstdout:\n{result.stdout}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_continues_past_an_ordinary_failure_without_pollution():
    """0.19.69, Codex finding #2 on the 0.19.67 fix, second half. A test
    that fails on its own (no pollution, no runner crash) is not evidence
    the investigation is broken -- it should be recorded and bisection
    should continue, not abort the whole run."""
    with tempfile.TemporaryDirectory() as tmp:
        result = _run_find_polluter(
            pathlib.Path(tmp), ".nonexistent-pollution-marker",
            "src/**/*.test.ts", npm_exit=1,
        )
    assert result.returncode != 0, (
        "find-polluter.sh exited 0 with a failing test and no pollution -- "
        "a clean verdict requires every test that ran to have passed.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "RUNNER FAILED" not in result.stdout, (
        "an ordinary exit-1 test failure was reported as RUNNER FAILED "
        f"instead of continuing the bisection.\nstdout:\n{result.stdout}"
    )
    assert "failed without producing pollution" in result.stdout, (
        "the summary did not name the failed-without-pollution test.\n"
        f"stdout:\n{result.stdout}"
    )
    assert "sample.test.ts" in result.stdout, (
        "the summary did not name which file failed.\n"
        f"stdout:\n{result.stdout}"
    )


@pytest.mark.skipif(_BASH is None, reason="needs bash")
def test_find_polluter_reports_the_polluter_even_when_the_runner_could_not_execute():
    """0.19.70, Codex finding on the 0.19.69 fix. Moving the pollution check
    ahead of the ordinary-failure branch still left it BEHIND the 126/127
    "RUNNER FAILED" branch, so a test that touches the pollution marker and
    then hits a missing or non-executable runner command (exit 127) was
    still reported as RUNNER FAILED, hiding the polluter it had already
    created. The pollution check now runs first, before any exit-code
    classification at all -- a marker on disk is a polluter found
    regardless of what the runner's exit code was."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = pathlib.Path(tmp)
        repo = tmp_path / "repo"
        (repo / "src").mkdir(parents=True)
        (repo / "src" / "a.test.ts").write_text("// fixture\n", encoding="utf-8")

        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        marker = str(tmp_path / ".pollution-marker").replace("\\", "/")
        npm_path = bin_dir / "npm"
        npm_path.write_text(
            f'#!/usr/bin/env bash\ntouch "{marker}"\nexit 127\n',
            encoding="utf-8", newline="\n",
        )
        npm_path.chmod(0o755)

        script = str(SKILL_DIR / "find-polluter.sh").replace("\\", "/")
        env = dict(os.environ)
        env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
        result = subprocess.run(
            [_BASH, script, marker, "src/**/*.test.ts"],
            cwd=str(repo), capture_output=True, text=True, timeout=30,
            stdin=subprocess.DEVNULL, env=env, check=False,
            encoding="utf-8", errors="replace",
        )

    assert result.returncode != 0, (
        f"find-polluter.sh exited 0 against a test that polluted and hit a "
        f"missing runner command.\nstdout:\n{result.stdout}"
    )
    assert "FOUND POLLUTER" in result.stdout, (
        "the polluter was not reported even though the marker was created "
        f"before the runner exited 127.\nstdout:\n{result.stdout}"
    )
    assert "RUNNER FAILED" not in result.stdout, (
        "exit 127 was reported as RUNNER FAILED despite the pollution "
        "marker existing, hiding a real polluter behind a runner-failure "
        f"report.\nstdout:\n{result.stdout}"
    )
