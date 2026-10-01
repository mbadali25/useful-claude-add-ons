"""T-0110: a test that hands an MSYS child TMP/TEMP pointing at a FILE must
not turn `/tmp` into that file for every other Git-Bash process on the host.

Git for Windows mounts `/tmp` as `usertemp` (its etc/fstab), resolved from
the TMP/TEMP of whichever process CREATES the MSYS runtime's per-user,
per-installation shared mount table; every MSYS process started while that
region lives shares the answer. Under pytest-xdist on an otherwise idle
runner, `test_34d_ps1_a_temp_dir_failure_falls_back_to_crew_not_a_pipe`
(test_verify_gate_stop_gate_record.py) could be that creator, and other
workers' `sh`-flavour gates then failed with `bash.exe: warning: /tmp must
be a valid directory name` / `VERIFY GATE: cannot create temp file` - CI
jobs 109709668000 and 109307433677, each within ~2 s of that test passing
on another worker.

`crew_fixtures.msys_tmp_pinned` is the guard. Two checks here:

- behavioural, on a PRIVATE copy of Git's MSYS runtime (its own install
  path, so its own shared region, with no other process in it - on a dev
  box the real install always has long-lived bash processes holding the
  region, so the race cannot be staged against it): the hazard is live
  without the pin and gone with it;
- structural: every crew test that puts TMP/TEMP into a child environment
  does so inside `msys_tmp_pinned`.
"""
import ast
import os
import pathlib
import shutil
import subprocess
import sys
import threading
import time

import pytest

import crew_fixtures

_TESTS = pathlib.Path(__file__).resolve().parent
_BASH = crew_fixtures.resolve_bash()
_PROBE = "if [ -d /tmp ]; then echo tmp-is-dir; else echo tmp-not-dir; fi"


def _private_msys(tmp_path):
    """A copy of the MSYS runtime `_BASH` belongs to, at a new path: bash,
    its DLLs and etc/fstab (which holds the `/tmp usertemp` line). Returns
    the copy's raw bash.exe."""
    git_root = pathlib.Path(_BASH).resolve().parents[1]
    src_bin = git_root / "usr" / "bin"
    fstab = git_root / "etc" / "fstab"
    if not (src_bin / "msys-2.0.dll").is_file() or not fstab.is_file():
        pytest.skip(f"{_BASH} is not a Git-for-Windows MSYS layout this test can copy")
    dst_bin = tmp_path / "msys" / "usr" / "bin"
    dst_bin.mkdir(parents=True)
    for entry in src_bin.iterdir():
        if entry.suffix.lower() == ".dll" or entry.name.lower() == "bash.exe":
            shutil.copy2(entry, dst_bin / entry.name)
    (tmp_path / "msys" / "etc").mkdir()
    shutil.copy2(fstab, tmp_path / "msys" / "etc" / "fstab")
    return str(dst_bin / "bash.exe")


def _poisoned_env(tmp_path):
    bogus = tmp_path / "not-a-directory"
    bogus.write_text("blocking TMP/TEMP", encoding="utf-8")
    return dict(os.environ, TMP=str(bogus), TEMP=str(bogus))


# `_hold`'s holder script and startup bound; module globals so a test can
# swap in a holder that starts but never announces.
_HOLD_SCRIPT = "echo up; read -r _"
_HOLD_STARTUP_TIMEOUT_S = 30


def _hold(bash, env):
    """Start an MSYS process under `env` and return once its runtime is up
    (so it has created or joined the shared region). Exits on stdin EOF.
    A holder that never announces is killed and raised within the bound."""
    # Outlives this function by design; `_release` closes and reaps it.
    proc = subprocess.Popen(  # pylint: disable=consider-using-with
        [bash, "-c", _HOLD_SCRIPT], env=env,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
    line = crew_fixtures.first_line_within(
        proc, _HOLD_STARTUP_TIMEOUT_S, f"_hold: holder {bash!r}")
    assert line.strip() == "up", f"holder {bash} did not start"
    return proc


def _release(proc):
    proc.stdin.close()
    try:
        proc.wait(timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
        raise


def _probe(bash, env=None):
    done = subprocess.run([bash, "-c", _PROBE], env=env or dict(os.environ),
                          capture_output=True, text=True, encoding="utf-8",
                          check=False,
                          timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    return done.stdout.strip(), done.stderr.strip()


_WINDOWS_ONLY = pytest.mark.skipif(
    not sys.platform.startswith("win") or _BASH is None,
    reason="`/tmp usertemp` and the shared MSYS mount table are Git for "
           "Windows behaviour; elsewhere /tmp is a real directory")


@_WINDOWS_ONLY
def test_unpinned_a_bogus_tmp_child_poisons_tmp_for_its_neighbours(tmp_path):
    """The premise the pin exists for. If this ever stops reproducing, the
    pinned test below passes vacuously - so this fails rather than skips."""
    bash = _private_msys(tmp_path)
    assert _probe(bash)[0] == "tmp-is-dir", "the private copy must start sane"

    poisoner = _hold(bash, _poisoned_env(tmp_path))
    try:
        out, err = _probe(bash)
    finally:
        _release(poisoner)

    assert out == "tmp-not-dir", (
        "a neighbour started while the bogus-TMP process held the region no "
        f"longer sees /tmp as a file (out={out!r} err={err!r}); re-check "
        "whether msys_tmp_pinned is still needed before trusting its test")
    assert "/tmp must be a valid directory name" in err
    assert _probe(bash)[0] == "tmp-is-dir", "the poison must end with its region"


@_WINDOWS_ONLY
def test_pinned_a_bogus_tmp_child_leaves_tmp_alone(tmp_path):
    bash = _private_msys(tmp_path)
    poisoned = _poisoned_env(tmp_path)

    with crew_fixtures.msys_tmp_pinned(bash, poisoned):
        poisoner = _hold(bash, poisoned)
        try:
            neighbour = _probe(bash)
            itself = _probe(bash, poisoned)
        finally:
            _release(poisoner)

    assert neighbour == ("tmp-is-dir", ""), neighbour
    assert itself == ("tmp-is-dir", ""), itself


def _assert_a_stalled_start_fails_fast(monkeypatch, start):
    """Run `start()` - which launches ONE holder that never announces itself
    under a 1 s bound - and assert it turns into a named error within the
    bound, not a readline() that blocks until the CI job's 60-minute limit,
    with the holder killed and its reader thread gone. Returns `start`'s
    outcome dict."""
    launched = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)  # pylint: disable=consider-using-with
        launched.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", recording_popen)
    # The threads alive now, by identity - not a count, which a thread an
    # EARLIER test left behind can lower by exiting meanwhile (seen when this
    # ran after test_verify_gate_stop_gate_record.py: `assert 1 == 2`).
    threads_before = set(threading.enumerate())
    outcome = {}

    def run():
        try:
            start(outcome)
        except RuntimeError as exc:
            outcome["error"] = str(exc)

    runner = threading.Thread(target=run, daemon=True)
    started = time.monotonic()
    runner.start()
    runner.join(timeout=30)
    try:
        assert not runner.is_alive(), (
            "still blocked reading the holder's startup line 30 s after a "
            "1 s bound")
        assert "did not announce" in outcome.get("error", ""), outcome
        assert time.monotonic() - started < 25
        assert len(launched) == 1 and launched[0].poll() is not None, (
            "the stalled holder was left running")

        def started_here():
            return [t for t in threading.enumerate()
                    if t not in threads_before and t is not runner]

        deadline = time.monotonic() + 10
        while started_here() and time.monotonic() < deadline:
            time.sleep(0.05)
        assert started_here() == [], (
            "the holder's reader thread outlived the timeout")
    finally:
        for proc in launched:
            if proc.poll() is None:
                proc.kill()
                proc.wait(timeout=crew_fixtures.GATE_SUBPROCESS_TIMEOUT_S)
    return outcome


@_WINDOWS_ONLY
def test_a_holder_that_never_announces_fails_fast_instead_of_hanging(
        tmp_path, monkeypatch):
    """msys_tmp_pinned's holder: on a stalled start the block is never
    entered, so nothing runs unpinned."""
    monkeypatch.setattr(crew_fixtures, "_PIN_HOLDER_SCRIPT", "read -r _")
    monkeypatch.setattr(crew_fixtures, "PIN_STARTUP_TIMEOUT_S", 1)

    def enter_the_pin(outcome):
        with crew_fixtures.msys_tmp_pinned(_BASH, _poisoned_env(tmp_path)):
            outcome["entered"] = True

    outcome = _assert_a_stalled_start_fails_fast(monkeypatch, enter_the_pin)
    assert "entered" not in outcome, "the block ran without a pin"


@_WINDOWS_ONLY
def test_hold_fails_fast_when_its_holder_never_announces(monkeypatch):
    """T-0110 review round 2, FIX 3: this module's own `_hold` read its
    holder's "up" line with a bare readline() too."""
    monkeypatch.setitem(globals(), "_HOLD_SCRIPT", "read -r _")
    monkeypatch.setitem(globals(), "_HOLD_STARTUP_TIMEOUT_S", 1)

    def hold(outcome):
        outcome["held"] = _hold(_BASH, dict(os.environ))

    outcome = _assert_a_stalled_start_fails_fast(monkeypatch, hold)
    assert "held" not in outcome, outcome


# --- structural: every TMP/TEMP override runs inside the pin -----------------

_OVERRIDDEN = {"TMP", "TEMP"}


# Calls that only BUILD or copy an environment; anything else handed a
# poisoned env is treated as a launch.
_ENV_BUILDERS = {"dict", "copy", "deepcopy"}
_ENV_MUTATORS = {"update", "setdefault"}
# These put TMP/TEMP into THIS process' environment, which every later child
# inherits - including ones started after the pin's block has ended.
_PROCESS_ENV_SETTERS = {"setenv", "putenv"}


def _callee(call):
    func = call.func
    return getattr(func, "attr", None) or getattr(func, "id", None)


def _is_os_environ(node):
    return isinstance(node, ast.Attribute) and node.attr == "environ"


def _names_a_tmp_key(node):
    return isinstance(node, ast.Constant) and node.value in _OVERRIDDEN


def _is_override(node):
    """`f(..., TMP=...)` or a `{"TMP": ...}` literal."""
    if isinstance(node, ast.Call):
        return any(kw.arg in _OVERRIDDEN for kw in node.keywords)
    return isinstance(node, ast.Dict) and any(
        _names_a_tmp_key(key) for key in node.keys)


def _hands_over(arg, tainted):
    """A pin argument that only names or builds an env - `env`,
    `dict(os.environ, TMP=p)`, `{"TMP": p}` - with no launch inside it."""
    if isinstance(arg, ast.Name):
        return True
    if not (isinstance(arg, ast.Dict) or (
            isinstance(arg, ast.Call) and _callee(arg) in _ENV_BUILDERS)):
        return False
    return not any(
        isinstance(sub, ast.Call) and _callee(sub) not in _ENV_BUILDERS
        and any(_poisoned(value, tainted) for value in
                [*sub.args, *(kw.value for kw in sub.keywords)])
        for sub in ast.walk(arg))


def _pinned_nodes(func, tainted):
    """ids of every node that runs while a `with ...msys_tmp_pinned(...)`
    holds the pin: its body and the items AFTER the pin. The pin's own
    arguments and any item before it are evaluated before the pin is entered
    (T-0110 review round 2), so of those only an argument that merely hands
    the env over (`_hands_over`) counts - `with pin(B, env)` reads env there,
    `with pin(B, run(env))` launches with it."""
    inside = set()
    for node in ast.walk(func):
        if not isinstance(node, (ast.With, ast.AsyncWith)):
            continue
        at = next((i for i, item in enumerate(node.items)
                   if isinstance(item.context_expr, ast.Call)
                   and _callee(item.context_expr) == "msys_tmp_pinned"), None)
        if at is None:
            continue
        pin = node.items[at].context_expr
        for arg in [*pin.args, *(kw.value for kw in pin.keywords)]:
            if _hands_over(arg, tainted):
                inside.update(id(sub) for sub in ast.walk(arg))
        for part in [*node.items[at + 1:], *node.body]:
            inside.update(id(sub) for sub in ast.walk(part))
    return inside


def _mutation_receiver(node):
    """The object a node writes TMP/TEMP INTO, if any: `X["TMP"] = v`,
    `X.update(TMP=v)` / `X.update({"TMP": v})`, `X.setdefault("TMP", v)`."""
    if isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Store):
        return node.value if _names_a_tmp_key(node.slice) else None
    if not (isinstance(node, ast.Call) and _callee(node) in _ENV_MUTATORS
            and isinstance(node.func, ast.Attribute)):
        return None
    writes = _is_override(node) or any(
        _is_override(arg) or _names_a_tmp_key(arg) for arg in node.args[:1])
    return node.func.value if writes else None


def _mutated_name(node):
    """The LOCAL name a node writes TMP/TEMP into, if any."""
    receiver = _mutation_receiver(node)
    return receiver.id if isinstance(receiver, ast.Name) else None


def _sets_process_env(node):
    """`os.environ["TMP"] = x`, `os.environ.update(TMP=x)`,
    `monkeypatch.setenv("TMP", x)`, `os.putenv("TEMP", x)`."""
    if (isinstance(node, ast.Call) and _callee(node) in _PROCESS_ENV_SETTERS
            and node.args and _names_a_tmp_key(node.args[0])):
        return True
    return _is_os_environ(_mutation_receiver(node))


def _poisoned(expr, tainted):
    """Does `expr` evaluate to an env carrying a TMP/TEMP override: the
    override itself, a tainted name, or a copy of either."""
    if _is_override(expr):
        return True
    if isinstance(expr, ast.Name):
        return expr.id in tainted
    if isinstance(expr, ast.Dict):
        return any(key is None and _poisoned(value, tainted)
                   for key, value in zip(expr.keys, expr.values))
    if isinstance(expr, ast.Call) and _callee(expr) in _ENV_BUILDERS:
        receiver = ([expr.func.value]
                    if isinstance(expr.func, ast.Attribute) else [])
        return any(_poisoned(arg, tainted) for arg in
                   [*receiver, *expr.args, *(kw.value for kw in expr.keywords)])
    return False


def _assigned_names(stmt):
    targets = stmt.targets if isinstance(stmt, ast.Assign) else [stmt.target]
    return [node.id for target in targets for node in ast.walk(target)
            if isinstance(node, ast.Name)]


def _taint(func):
    """Local names that hold a poisoned env anywhere in `func` (flow-
    insensitive on purpose: a later override taints an earlier read too,
    which can only over-report), and the ids of nodes that merely build or
    copy one - so `env2 = dict(env)` is not itself a launch."""
    tainted, building = set(), set()
    nodes = list(ast.walk(func))
    changed = True
    while changed:
        changed = False
        for node in nodes:
            fresh = []
            mutated = _mutated_name(node)
            if mutated:
                fresh.append(mutated)
                if isinstance(node, ast.Subscript):
                    building.add(id(node.value))
                else:
                    building.update(id(sub) for sub in ast.walk(node))
            if (isinstance(node, (ast.Assign, ast.AnnAssign))
                    and node.value is not None
                    and _poisoned(node.value, tainted)):
                fresh.extend(_assigned_names(node))
                if not (isinstance(node.value, ast.Call)
                        and _callee(node.value) not in _ENV_BUILDERS):
                    building.update(id(sub) for sub in ast.walk(node.value))
            for name in fresh:
                if name not in tainted:
                    tainted.add(name)
                    changed = True
    return tainted, building


def _tmp_sites(source):
    """{function name: [line of each unpinned use]} for every function in
    `source` that puts TMP or TEMP into an environment.

    A use is pinned only if it sits lexically inside a `with
    ...msys_tmp_pinned(...)` while it holds the pin (`_pinned_nodes`) - NOT
    merely somewhere in a
    function that also contains one. A use is: any read of a local name
    holding a poisoned env, other than building or copying one; an inline
    override (`run({"TMP": p})`, `run(env=dict(os.environ, TMP=p))`,
    `return dict(..., TMP=p)`) that is not simply assigned to a name; or
    any write of TMP/TEMP into this process' own environment, which is
    flagged even inside the pin because it outlives the block."""
    sites = {}
    for func in ast.walk(ast.parse(source)):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tainted, building = _taint(func)
        inside = _pinned_nodes(func, tainted)
        assigned = {id(node.value) for node in ast.walk(func)
                    if isinstance(node, (ast.Assign, ast.AnnAssign))}
        overrides, unpinned = False, []
        for node in ast.walk(func):
            if _sets_process_env(node):
                overrides = True
                unpinned.append(node.lineno)
                continue
            if _is_override(node) or _mutated_name(node):
                overrides = True
            if id(node) in building:
                continue
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                use = node.id in tainted
            elif _is_override(node) and _mutated_name(node) is None:
                use = (id(node) not in assigned
                       or _callee(node) not in _ENV_BUILDERS | {None})
            else:
                use = False
            if use and id(node) not in inside:
                unpinned.append(node.lineno)
        if overrides:
            # Merged, not assigned: two functions may share a name (methods,
            # nested helpers), and the clean one must not hide the other.
            sites[func.name] = sorted(set(sites.get(func.name, [])) | set(unpinned))
    return sites


def _unpinned_overrides(source):
    """Names of functions in `source` that put TMP or TEMP into an
    environment and use it anywhere outside a `with msys_tmp_pinned(...)`
    block (see `_tmp_sites`)."""
    return [name for name, lines in _tmp_sites(source).items() if lines]


def test_the_override_detector_sees_both_spellings_and_the_pin():
    unpinned = (
        "def a(p):\n    env = dict(os.environ, TMP=p)\n    run(env)\n"
        "def b(p):\n    run({'TEMP': p})\n"
        "def c(p):\n    run(dict(os.environ, PATH=p))\n"
    )
    pinned = (
        "def d(p):\n    env = dict(os.environ, TMP=p, TEMP=p)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, env):\n        run(env)\n"
    )
    assert _unpinned_overrides(unpinned) == ["a", "b"]
    assert _unpinned_overrides(pinned) == []


# T-0110 review round 1: a function used to count as pinned if it merely
# CONTAINED a `with msys_tmp_pinned(...)`, wherever the launch was. Each of
# these launches (or leaks) a poisoned env outside the block.
_MUST_FLAG = {
    "set_by_subscript_after_the_pin_ended": (
        "def f(p):\n"
        "    env = dict(os.environ)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, env):\n"
        "        pass\n"
        "    env['TMP'] = p\n"
        "    run(env)\n"),
    "launched_before_a_later_pin": (
        "def f(p):\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    run(env)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, env):\n"
        "        run(env)\n"),
    "launched_again_after_the_pin": (
        "def f(p):\n"
        "    env = dict(os.environ, TEMP=p)\n"
        "    with msys_tmp_pinned(B, env):\n"
        "        run(env)\n"
        "    run(env)\n"),
    "set_by_subscript_with_no_pin": (
        "def f(p):\n"
        "    env = {}\n"
        "    env['TEMP'] = p\n"
        "    run(env)\n"),
    "set_by_update": (
        "def f(p):\n"
        "    env = dict(os.environ)\n"
        "    env.update(TMP=p)\n"
        "    run(env)\n"),
    "copied_then_launched_outside": (
        "def f(p):\n"
        "    base = dict(os.environ, TMP=p)\n"
        "    env = dict(base, X='1')\n"
        "    with crew_fixtures.msys_tmp_pinned(B, base):\n"
        "        pass\n"
        "    run(env)\n"),
    "inline_launch_beside_a_pin": (
        "def f(p):\n"
        "    with crew_fixtures.msys_tmp_pinned(B, {}):\n"
        "        pass\n"
        "    run(env=dict(os.environ, TMP=p))\n"),
    "returned_to_an_unknown_caller": (
        "def f(p):\n"
        "    return dict(os.environ, TMP=p)\n"),
    "this_process_env_via_setenv": (
        "def f(p, monkeypatch):\n"
        "    with crew_fixtures.msys_tmp_pinned(B, {}):\n"
        "        monkeypatch.setenv('TMP', p)\n"
        "        run()\n"),
    # T-0110 review round 2, FIX 2: the pin's own arguments are evaluated
    # BEFORE it is entered, and so is any item ahead of it.
    "launched_in_the_pins_own_arguments": (
        "def f(p):\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, run(env)):\n"
        "        pass\n"),
    "launched_to_resolve_the_pins_bash": (
        "def f(p):\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    with crew_fixtures.msys_tmp_pinned(gate_bash(env), env):\n"
        "        run(env)\n"),
    "launched_inside_a_copy_handed_to_the_pin": (
        "def f(p):\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, dict(run(env))):\n"
        "        pass\n"),
    "launched_in_an_item_before_the_pin": (
        "def f(p):\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    with Popen(cmd, env=env) as proc, msys_tmp_pinned(B, env):\n"
        "        pass\n"),
    "hidden_by_a_clean_namesake_after_it": (
        "def f(p):\n"
        "    run({'TMP': p})\n"
        "class C:\n"
        "    def f(self, p):\n"
        "        env = dict(os.environ, TMP=p)\n"
        "        with crew_fixtures.msys_tmp_pinned(B, env):\n"
        "            run(env)\n"),
    "this_process_env_via_os_environ": (
        "def f(p):\n"
        "    with crew_fixtures.msys_tmp_pinned(B, {}):\n"
        "        os.environ['TEMP'] = p\n"
        "        run()\n"),
}

_MUST_PASS = {
    # The real test_34d_ps1 shape: env built BEFORE the pin, used only in
    # the pin's own items and inside its body; the result read afterwards.
    "built_before_launched_inside": (
        "def f(tmp_path):\n"
        "    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root),\n"
        "               TMP=str(bogus), TEMP=str(bogus))\n"
        "    with crew_fixtures.msys_tmp_pinned(\n"
        "            crew_fixtures.resolve_bash(), env):\n"
        "        result = crew_fixtures.run_gate(\n"
        "            [PWSH, '-File', PS1], input='{}', env=env, check=False)\n"
        "    assert result.returncode != 0, result.stderr\n"
        "    assert 'x' in result.stderr, f'stderr: {result.stderr}'\n"),
    "set_by_subscript_inside_the_pin": (
        "def f(p):\n"
        "    env = dict(os.environ)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, env):\n"
        "        env['TMP'] = p\n"
        "        run(env)\n"),
    "launched_unpoisoned_before_the_override": (
        "def f(p):\n"
        "    other = dict(os.environ)\n"
        "    run(other)\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    with crew_fixtures.msys_tmp_pinned(B, env), open(p) as fh:\n"
        "        run(env, fh)\n"),
    "launched_in_an_item_after_the_pin": (
        "def f(p):\n"
        "    env = dict(os.environ, TMP=p)\n"
        "    with msys_tmp_pinned(B, env), Popen(cmd, env=env) as proc:\n"
        "        proc.wait()\n"),
    "built_inline_as_the_pins_argument": (
        "def f(p):\n"
        "    with crew_fixtures.msys_tmp_pinned(B, dict(os.environ, TMP=p)):\n"
        "        pass\n"),
    "reads_tmp_without_setting_it": (
        "def f():\n"
        "    run(os.environ.get('TMP'), os.environ['TEMP'])\n"),
}


@pytest.mark.parametrize("case", sorted(_MUST_FLAG))
def test_the_override_detector_flags_a_launch_outside_the_pin(case):
    assert _unpinned_overrides(_MUST_FLAG[case]) == ["f"], case


@pytest.mark.parametrize("case", sorted(_MUST_PASS))
def test_the_override_detector_passes_a_launch_inside_the_pin(case):
    assert _unpinned_overrides(_MUST_PASS[case]) == [], case


def test_the_real_test_34d_ps1_overrides_tmp_and_launches_inside_the_pin():
    """Not vacuous: the detector must SEE test_34d_ps1's override (else its
    clean result in the whole-tree check below proves nothing)."""
    source = (_TESTS / "test_verify_gate_stop_gate_record.py").read_text(
        encoding="utf-8")
    sites = _tmp_sites(source)
    name = "test_34d_ps1_a_temp_dir_failure_falls_back_to_crew_not_a_pipe"
    assert name in sites, "the detector no longer sees test_34d_ps1's override"
    assert sites[name] == [], sites[name]


# --- the pin must hold the MSYS install the gate's own bash belongs to -------

_PWSH = shutil.which("pwsh")
_GATE_PS1 = str(_TESTS.parent / "hooks" / "scripts" / "verify-gate.ps1")


def _stub(path):
    """A file Get-Command resolves; `-PrintBash` never executes it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("rem stub, never executed\n", encoding="ascii")
    return path


@pytest.mark.skipif(not sys.platform.startswith("win") or _PWSH is None,
                    reason="Resolve-CrewBash is verify-gate.ps1's, native Windows")
def test_gate_bash_follows_resolve_crewbash_not_path_order(tmp_path):
    """T-0110 review round 2, FIX 1: with Git A's bash first on PATH and Git
    B's git first, PATH order (what `resolve_bash` starts from) says A while
    the gate's Resolve-CrewBash walks up from git.exe to B. Pinning A would
    leave B's shared region - the one the gate's children join - unpinned."""
    git_a, git_b = tmp_path / "GitA", tmp_path / "GitB"
    _stub(git_a / "bin" / "bash.exe")
    _stub(git_b / "cmd" / "git.exe")
    b_bash = _stub(git_b / "bin" / "bash.exe")
    path = os.pathsep.join([str(git_a / "bin"), str(git_b / "cmd")])

    by_path_order = shutil.which("bash", path=path)
    assert by_path_order and pathlib.Path(by_path_order).parent == git_a / "bin", (
        "premise: PATH order alone picks Git A's bash")
    env = dict(os.environ, PATH=path)
    assert crew_fixtures.gate_bash(_PWSH, _GATE_PS1, env) == str(b_bash)


def _assigned_from(func, name):
    """The callee names of every `name = <call>(...)` in `func`."""
    return {getattr(node.value.func, "attr", None)
            or getattr(node.value.func, "id", None)
            for node in ast.walk(func)
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call)
            and any(isinstance(t, ast.Name) and t.id == name
                    for t in node.targets)}


def test_test_34d_ps1_pins_the_bash_the_gate_resolves():
    """test_34d_ps1 runs verify-gate.ps1, whose rules run under the bash
    Resolve-CrewBash picks, so its pin must take that bash from
    `crew_fixtures.gate_bash` rather than `resolve_bash`."""
    tree = ast.parse((_TESTS / "test_verify_gate_stop_gate_record.py")
                     .read_text(encoding="utf-8"))
    func = next(node for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef) and node.name ==
                "test_34d_ps1_a_temp_dir_failure_falls_back_to_crew_not_a_pipe")
    pins = [node for node in ast.walk(func) if isinstance(node, ast.Call)
            and _callee(node) == "msys_tmp_pinned"]
    assert len(pins) == 1, pins
    bash = pins[0].args[0]
    callees = ({_callee(bash)} if isinstance(bash, ast.Call)
               else _assigned_from(func, bash.id) if isinstance(bash, ast.Name)
               else set())
    assert callees == {"gate_bash"}, (
        f"test_34d_ps1 pins a bash from {callees or ast.dump(bash)}, not "
        "crew_fixtures.gate_bash")


# Exempt by exact name, with the reason: this module's own helper poisons
# only the PRIVATE MSYS copy above, whose shared region no other process on
# the host can join.
_EXEMPT = {"test_msys_tmp_pin.py::_poisoned_env"}


def test_every_crew_test_that_overrides_tmp_does_it_inside_the_pin():
    found = [
        f"{path.name}::{name}"
        for path in sorted(_TESTS.glob("*.py"))
        for name in _unpinned_overrides(path.read_text(encoding="utf-8"))
    ]
    assert _EXEMPT <= set(found), "stale exemption: " + repr(_EXEMPT - set(found))
    offenders = [name for name in found if name not in _EXEMPT]
    assert offenders == [], (
        "these tests hand a child TMP/TEMP; on Windows that child can decide "
        "/tmp for every Git-Bash process on the host (see this module's "
        "docstring). Run the child inside crew_fixtures.msys_tmp_pinned: "
        + ", ".join(offenders))
