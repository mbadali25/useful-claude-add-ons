"""Every pwsh the test suites spawn runs with an XDG_CACHE_HOME of its own (L-0557).

PowerShell keeps a multicore-JIT startup profile at
`$XDG_CACHE_HOME/powershell/StartupProfileData-NonInteractive` (default
`~/.cache/powershell`). Every pwsh reads it at start-up and rewrites it at
exit, so concurrent pwsh processes race on one file, and a reader that catches
it half-written dies before running a statement: "Stack overflow." (-6) or
SIGSEGV (-11). Isolating the cache per test removes the race at the source.
There is deliberately no retry and no crash-signature matching.

Three guards, each with must-pass and must-fail fixtures:

- `scan_python`: a static AST rule over every tracked `*.py` under a `tests`
  or `_test` directory. Inside `plugin/crew/tests` an inherited environment is
  enough, because conftest's autouse fixture sets the variable per test;
  everywhere else, and for any environment built from scratch, the spawn site
  must set it itself.
- `scan_shell`: every tracked `*.sh` suite that runs a real pwsh exports
  XDG_CACHE_HOME into its own mktemp directory before the first invocation.
- `crew_fixtures.pwsh_cache_violation`: the runtime half, which conftest
  installs as an audit hook so a spawn path the static rule cannot model is
  still refused.
"""
import ast
import os
import pathlib
import re
import subprocess

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures

REPO = pathlib.Path(__file__).resolve().parents[3]
CREW_TESTS = "plugin/crew/tests/"
KEY = "XDG_CACHE_HOME"

SPAWN_NAMES = frozenset(
    ("run", "Popen", "check_output", "check_call", "call", "run_gate", "popen_gate"))
PWSH_RE = re.compile(r"pwsh|powershell", re.IGNORECASE)


# --- the static Python rule ----------------------------------------------------


def _suite_files(suffix):
    """Tracked files with `suffix` under any `tests` or `_test` directory.

    From `git ls-files`, so generated trees (graphify-out, node_modules) are
    never read. Outside a git checkout -- an installed plugin -- the tree
    checks skip visibly rather than pass on an empty list."""
    try:
        out = subprocess.run(
            ["git", "-C", str(REPO), "ls-files", "-z"], capture_output=True,
            check=True, stdin=subprocess.DEVNULL, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        pytest.skip("not a git checkout - the tree scan was NOT run")
    found = []
    for raw in out.split(b"\0"):
        rel = raw.decode("utf-8", "replace")
        parts = rel.split("/")
        if rel.endswith(suffix) and any(p in ("tests", "_test") for p in parts[:-1]):
            found.append(rel)
    return found


def _func_name(node):
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def _first_arg(call):
    if call.args:
        return call.args[0]
    for kw in call.keywords:
        if kw.arg == "args":
            return kw.value
    return None


def _argv0_texts(src, expr, scope):
    """Source of argv[0] for `expr`. A bare name gets one level of lookup to
    its assignments in the enclosing scope (every branch's, so a helper that
    picks python, bash or pwsh by flavour is still seen)."""
    if isinstance(expr, (ast.List, ast.Tuple)):
        if not expr.elts:
            return []
        return [ast.get_source_segment(src, expr.elts[0]) or ""]
    if isinstance(expr, ast.Name) and scope is not None:
        texts = []
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == expr.id for t in node.targets):
                if isinstance(node.value, (ast.List, ast.Tuple)) and node.value.elts:
                    texts.append(ast.get_source_segment(src, node.value.elts[0]) or "")
        return texts
    return [ast.get_source_segment(src, expr) or ""]


def _env_value(call):
    """(present, expr): `present` is False when no `env=` is passed and no
    `**kwargs` could carry one."""
    for kw in call.keywords:
        if kw.arg == "env":
            return True, kw.value
    for kw in call.keywords:
        if kw.arg is None:
            return True, kw.value
    return False, None


def _reads_environ(node):
    """True when code under `node` reads `os.environ` (or a bare `environ`)."""
    return any((isinstance(n, ast.Attribute) and n.attr == "environ")
               or (isinstance(n, ast.Name) and n.id == "environ")
               for n in ast.walk(node))


def _own_nodes(func):
    """Nodes under `func`, not descending into nested functions or classes."""
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        yield node
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda,
                                 ast.ClassDef)):
            stack.extend(ast.iter_child_nodes(node))


def _is_key(node):
    return isinstance(node, ast.Constant) and node.value == KEY


def _top_level_value(expr):
    """The value an environment EXPRESSION gives XDG_CACHE_HOME at its own top
    level -- a dict display's key or a `dict(...)` keyword -- else None. A key
    nested in some other dict inside it is not the environment's."""
    if isinstance(expr, ast.Dict):
        for key, value in zip(expr.keys, expr.values):
            if _is_key(key):
                return value
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id == "dict":
        for kw in expr.keywords:
            if kw.arg == KEY:
                return kw.value
    return None


_SETDEFAULT = object()


def _name_state(name, scope):
    """What straight-line code in `scope`'s own body last did to `name`'s key:
    (value node | _SETDEFAULT | None, the last value assigned to `name`).

    Only statements DIRECTLY in the body count. A set inside an `if`, a loop or
    a `try` may not run, so it is not proof; a later rebinding of `name`
    discards an earlier set."""
    state, assigned = None, None
    for stmt in scope.body:
        if isinstance(stmt, ast.Assign):
            for target in stmt.targets:
                if isinstance(target, ast.Name) and target.id == name:
                    state, assigned = _top_level_value(stmt.value), stmt.value
                elif (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                      and target.value.id == name and _is_key(target.slice)):
                    state = stmt.value
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            call = stmt.value
            func = call.func
            if not (isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name)
                    and func.value.id == name):
                continue
            if func.attr == "update":
                found = [kw.value for kw in call.keywords if kw.arg == KEY]
                found += [v for v in (_top_level_value(a) for a in call.args) if v is not None]
                if found:
                    state = found[-1]
            elif func.attr == "setdefault" and call.args and _is_key(call.args[0]):
                state = state if state is not None else _SETDEFAULT
    return state, assigned


def _assigned_values(name, scope, module):
    """Every value bound to `name` in `scope` (any branch), else at module top."""
    found = []
    if scope is not None:
        for node in _own_nodes(scope):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == name for t in node.targets):
                found.append(node.value)
    if not found:
        for stmt in module.body:
            if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == name for t in stmt.targets):
                found.append(stmt.value)
    return found


_HOME_ATTRS = frozenset(("expanduser", "home"))


def _value_problem(value, scope, ctx, depth=0):
    """None when `value`, given to XDG_CACHE_HOME, names a directory of the
    spawn's own; else a reason. Empty, None and anything derived from the home
    directory or `~` are the user default under another name, and so is an
    ambient XDG_CACHE_HOME copied back outside crew's conftest. A bare name is
    followed to every value bound to it; one it cannot resolve is a reason."""
    if isinstance(value, ast.Constant) and value.value in (None, ""):
        return f"sets {KEY} empty, so pwsh falls back to the user default ~/.cache"
    if isinstance(value, ast.Name):
        bound = _assigned_values(value.id, scope, ctx["module"]) if depth < 3 else []
        if not bound:
            return f"sets {KEY} from {value.id}, which the scan cannot resolve"
        for item in bound:
            reason = _value_problem(item, scope, ctx, depth + 1)
            if reason:
                return reason
        return None
    for node in ast.walk(value):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value.rstrip("/\\")
            if text.startswith("~") or text.endswith(".cache") or node.value == "HOME":
                return f"sets {KEY} to the user default ~/.cache (or from HOME)"
            if node.value == KEY and not ctx["in_crew"]:
                return (f"copies the ambient {KEY} back, which outside crew's conftest "
                        "is the user's own")
        if isinstance(node, ast.Attribute) and node.attr in _HOME_ATTRS:
            return f"sets {KEY} from the home directory - the user default"
    return None


def _judge_helper(name, ctx, depth):
    helper = ctx["helpers"][name]
    returns = [n for n in _own_nodes(helper) if isinstance(n, ast.Return)]
    if not returns:
        return f"helper {name}() returns no environment"
    for ret in returns:
        reason = _judge_env(ret.value, ctx, helper, depth + 1)
        if reason:
            return f"helper {name}(): {reason}"
    return None


def _judge_env(expr, ctx, scope, depth=0):
    """None when the spawn's environment provably carries a key of its own,
    else a one-line reason. Anything the rule cannot classify is a reason,
    never a pass (outside crew's conftest, where nothing else would set it).
    Only the expression itself, the statements that build the name it is, and
    a same-module helper's RETURNED values count: a mention of the key in a
    branch, an unused dict or a comment proves nothing."""
    in_crew = ctx["in_crew"]
    if expr is None or (isinstance(expr, ast.Constant) and expr.value is None):
        return None if in_crew else "inherits the environment, and no conftest sets " + KEY
    text = ast.get_source_segment(ctx["src"], expr) or ""
    value = _top_level_value(expr)
    if value is not None:
        return _value_problem(value, scope, ctx)
    if isinstance(expr, ast.Name) and scope is not None and depth < 4:
        state, assigned = _name_state(expr.id, scope)
        if state is _SETDEFAULT:
            return None if in_crew else (
                f"setdefault keeps an ambient {KEY}, which outside crew's conftest is the "
                "user's own")
        if state is not None:
            return _value_problem(state, scope, ctx)
        if assigned is not None:
            return _judge_env(assigned, ctx, scope, depth + 1)
        return None if in_crew else (
            f"env={text} - its enclosing function never sets {KEY} on it unconditionally")
    if (isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id in ctx["helpers"] and depth < 4):
        return _judge_helper(expr.func.id, ctx, depth)
    if _reads_environ(expr):
        return None if in_crew else f"copies the environment but sets no {KEY}"
    if isinstance(expr, ast.Dict) or (
            isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id == "dict"):
        return f"builds the environment from scratch without {KEY}"
    return None if in_crew else f"env={text} - the scan cannot tell that it sets {KEY}"


def _scopes(tree):
    """{call node: innermost enclosing function (or None)}."""
    owner = {}

    def visit(node, scope):
        for child in ast.iter_child_nodes(node):
            inner = child if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)) else scope
            if isinstance(child, ast.Call):
                owner[child] = scope
            visit(child, inner)

    visit(tree, None)
    return owner


def scan_python(rel, src, crew_covered=True):
    """[(rel, line, function, reason-or-None)] for every pwsh spawn in `src`.

    `crew_covered` says whether crew's conftest really sets the key per test;
    only then does an inherited environment under `plugin/crew/tests` pass."""
    tree = ast.parse(src)
    ctx = {"src": src, "module": tree,
           "in_crew": crew_covered and rel.startswith(CREW_TESTS),
           "helpers": {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}}
    sites = []
    for call, scope in _scopes(tree).items():
        if _func_name(call) not in SPAWN_NAMES:
            continue
        first = _first_arg(call)
        if first is None or not any(PWSH_RE.search(t) for t in _argv0_texts(src, first, scope)):
            continue
        _present, env = _env_value(call)
        reason = _judge_env(env, ctx, scope)
        sites.append((rel, call.lineno, scope.name if scope is not None else "<module>",
                      reason))
    return sorted(sites, key=lambda s: s[1])


def _scan_fixture(tmp_path, rel, body):
    path = tmp_path / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return scan_python(rel, path.read_text(encoding="utf-8"))


_HEAD = "import os\nimport subprocess\nPWSH = 'pwsh'\n\n"


def test_static_scan_flags_from_scratch_env_without_key(tmp_path):
    sites = _scan_fixture(tmp_path, CREW_TESTS + "test_x.py", _HEAD + (
        "def test_a():\n"
        "    subprocess.run([PWSH, '-NoProfile'], env={'PATH': '/bin'})\n"))

    assert [(s[0], s[1], s[3] is not None) for s in sites] == [
        (CREW_TESTS + "test_x.py", 6, True)]


def test_static_scan_flags_inherited_env_outside_crew_conftest(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_y.py", _HEAD + (
        "def pwsh(command):\n"
        "    return subprocess.run([PWSH, '-Command', command], capture_output=True)\n"))

    assert [(s[1], s[2], s[3] is not None) for s in sites] == [(6, "pwsh", True)]


def test_static_scan_flags_helper_env_without_key(tmp_path):
    sites = _scan_fixture(tmp_path, CREW_TESTS + "test_z.py", _HEAD + (
        "def _env(root):\n"
        "    return {'PATH': '/bin', 'HOME': str(root)}\n\n"
        "def test_b(tmp_path):\n"
        "    subprocess.run([PWSH, '-File', 'x.ps1'], env=_env(tmp_path))\n"))

    assert len(sites) == 1 and "_env()" in sites[0][3]


def test_static_scan_flags_a_key_named_only_in_a_comment(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_c.py", _HEAD + (
        "def _env():\n"
        "    # XDG_CACHE_HOME is not set here\n"
        "    return {'PATH': '/bin'}\n\n"
        "def pwsh(command, env=None):\n"
        "    env = dict(os.environ if env is None else env)\n"
        "    # an ambient XDG_CACHE_HOME would be the shared one\n"
        "    return subprocess.run([PWSH, '-Command', command], env=env)\n\n"
        "def other():\n"
        "    subprocess.run([PWSH, '-c', '1'], env=_env())  # XDG_CACHE_HOME\n"))

    assert [s[3] is not None for s in sites] == [True, True]


def test_static_scan_flags_a_bare_name_argv(tmp_path):
    sites = _scan_fixture(tmp_path, "skills/s/scripts/_test/test_w.py", _HEAD + (
        "def go(env):\n"
        "    cmd = [PWSH, '-NoProfile']\n"
        "    return subprocess.run(cmd, env=env)\n"))

    assert [(s[1], s[3] is not None) for s in sites] == [(7, True)]


def test_static_scan_accepts_inherited_env_in_crew_tests(tmp_path):
    sites = _scan_fixture(tmp_path, CREW_TESTS + "test_v.py", _HEAD + (
        "def test_c():\n"
        "    subprocess.run([PWSH, '-NoProfile'], check=False)\n"
        "    subprocess.run([PWSH, '-NoProfile'], env=None, check=False)\n"))

    assert [s[3] for s in sites] == [None, None]


def test_static_scan_accepts_os_environ_derived_env(tmp_path):
    sites = _scan_fixture(tmp_path, CREW_TESTS + "test_u.py", _HEAD + (
        "def _env():\n"
        "    env = os.environ.copy()\n"
        "    env['OS'] = 'Windows_NT'\n"
        "    return env\n\n"
        "def test_d():\n"
        "    subprocess.run([PWSH, '-c', '1'], env=dict(os.environ, OS='x'))\n"
        "    subprocess.run([PWSH, '-c', '1'], env={**os.environ, 'OS': 'x'})\n"
        "    subprocess.run([PWSH, '-c', '1'], env=_env())\n"))

    assert [s[3] for s in sites] == [None, None, None]


def test_static_scan_accepts_explicit_key(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_t.py", _HEAD + (
        "XDG = '/tmp/x'\n\n"
        "def _env():\n"
        "    return {'PATH': '/bin', 'XDG_CACHE_HOME': XDG}\n\n"
        "def pwsh(command, env=None):\n"
        "    env = dict(os.environ if env is None else env)\n"
        "    env['XDG_CACHE_HOME'] = XDG\n"
        "    return subprocess.run([PWSH, '-Command', command], env=env)\n\n"
        "def other():\n"
        "    subprocess.run([PWSH, '-c', '1'], env=dict(os.environ, XDG_CACHE_HOME=XDG))\n"
        "    subprocess.run([PWSH, '-c', '1'], env=_env())\n"))

    assert [s[3] for s in sites] == [None, None, None]


def test_static_scan_flags_crew_tests_when_conftest_does_not_cover(tmp_path):
    path = tmp_path / "t.py"
    path.write_text(_HEAD + "def test_e():\n    subprocess.run([PWSH, '-c', '1'])\n",
                    encoding="utf-8")

    sites = scan_python(CREW_TESTS + "t.py", path.read_text(encoding="utf-8"),
                        crew_covered=False)

    assert [s[3] is not None for s in sites] == [True]


def test_static_scan_ignores_non_pwsh_spawns(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_s.py", _HEAD + (
        "import sys\n"
        "def go():\n"
        "    subprocess.run([sys.executable, '-c', 'print(\"pwsh\")'])\n"
        "    subprocess.run(['bash', 'pwsh-wrapper.sh'])\n"))

    assert sites == []


# An XDG_CACHE_HOME that is empty, or that is the user's own ~/.cache, is the
# shared startup profile under another name: naming the key is not enough.
_BAD_VALUES = (
    "''",
    "None",
    "'~/.cache'",
    "os.path.expanduser('~/.cache')",
    "str(pathlib.Path.home() / '.cache')",
    "str(pathlib.Path.home() / 'shared')",
    "os.path.join(os.environ['HOME'], '.cache')",
    "os.environ.get('XDG_CACHE_HOME', '')",
)
_SET_FORMS = (
    "    subprocess.run([PWSH, '-c', '1'], env={{'PATH': '/bin', 'XDG_CACHE_HOME': {v}}})\n",
    "    subprocess.run([PWSH, '-c', '1'], env=dict(os.environ, XDG_CACHE_HOME={v}))\n",
    "    env = dict(os.environ)\n    env['XDG_CACHE_HOME'] = {v}\n"
    "    subprocess.run([PWSH, '-c', '1'], env=env)\n",
)


@pytest.mark.parametrize("form", range(len(_SET_FORMS)))
@pytest.mark.parametrize("value", _BAD_VALUES)
def test_static_scan_flags_empty_or_user_default_value(tmp_path, value, form):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_bad.py", _HEAD + (
        "import pathlib\n\ndef go():\n" + _SET_FORMS[form].format(v=value)))

    assert [s[3] is not None for s in sites] == [True]


def test_static_scan_flags_setdefault_outside_crew_conftest(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_sd.py", _HEAD + (
        "def go():\n"
        "    env = dict(os.environ)\n"
        "    env.setdefault('XDG_CACHE_HOME', '/tmp/x')\n"
        "    subprocess.run([PWSH, '-c', '1'], env=env)\n"))

    assert [s[3] is not None for s in sites] == [True]


def test_static_scan_flags_helper_whose_return_lacks_key(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_dead.py", _HEAD + (
        "def _env(flag=False):\n"
        "    if flag:\n"
        "        unused = {'XDG_CACHE_HOME': '/tmp/x'}\n"
        "        del unused\n"
        "    return {'PATH': '/bin'}\n\n"
        "def go():\n"
        "    subprocess.run([PWSH, '-c', '1'], env=_env())\n"))

    assert [s[3] is not None for s in sites] == [True]


def test_static_scan_flags_key_set_only_in_a_branch_or_another_dict(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_branch.py", _HEAD + (
        "def go(flag):\n"
        "    env = dict(os.environ)\n"
        "    if flag:\n"
        "        env['XDG_CACHE_HOME'] = '/tmp/x'\n"
        "    subprocess.run([PWSH, '-c', '1'], env=env)\n"
        "    subprocess.run([PWSH, '-c', '1'],\n"
        "                   env={'PATH': '/bin', 'X': {'XDG_CACHE_HOME': '/tmp/x'}})\n"))

    assert [s[3] is not None for s in sites] == [True, True]


def test_static_scan_flags_name_rebuilt_after_the_key_was_set(tmp_path):
    sites = _scan_fixture(tmp_path, "plugin/other/_test/test_reset.py", _HEAD + (
        "def go():\n"
        "    env = dict(os.environ, XDG_CACHE_HOME='/tmp/x')\n"
        "    env = {'PATH': '/bin'}\n"
        "    subprocess.run([PWSH, '-c', '1'], env=env)\n"))

    assert [s[3] is not None for s in sites] == [True]


def test_static_scan_flags_crew_helper_returning_a_from_scratch_name(tmp_path):
    sites = _scan_fixture(tmp_path, CREW_TESTS + "test_scratch.py", _HEAD + (
        "def _env():\n"
        "    env = {'PATH': '/bin'}\n"
        "    return env\n\n"
        "def test_f():\n"
        "    subprocess.run([PWSH, '-c', '1'], env=_env())\n"))

    assert [s[3] is not None for s in sites] == [True]


@pytest.mark.parametrize("suffix", (".py", ".sh"))
def test_tree_scans_report_an_unreadable_suite_instead_of_skipping_it(tmp_path, suffix):
    rel = "plugin/other/_test/test_bin" + suffix
    path = tmp_path / rel
    path.parent.mkdir(parents=True)
    path.write_bytes(b"subprocess.run(['pwsh', '-NoProfile'])\n\xff\xfe not utf-8\n")
    scan = _tree_python_problems if suffix == ".py" else _tree_shell_problems

    problems = scan(tmp_path, [rel])

    assert [p.split(" ", 1)[0] for p in problems] == [rel + ":0:"]


@pytest.mark.parametrize("line, covers", (
    ('    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))\n', True),
    ('    xdg = tmp_path_factory.mktemp("xdg-cache")\n'
     '    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg))\n', True),
    ('    monkeypatch.setenv("XDG_CACHE_HOME", "/tmp/shared")\n', False),
    ('    monkeypatch.setenv("XDG_CACHE_HOME", "")\n', False),
    ('    monkeypatch.setenv("XDG_CACHE_HOME", os.path.expanduser("~/.cache"))\n', False),
    ('    if False:\n        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))\n', False),
))
def test_conftest_premise_needs_a_per_test_value(line, covers):
    text = ("import os\nimport pytest\n\n@pytest.fixture(autouse=True)\n"
            "def _iso(tmp_path, monkeypatch):\n" + line)

    assert conftest_sets_per_test_cache(text) is covers


# Named spawn sites the tree scan must find, matched by file and enclosing
# function (never by line or count: the count depends on the scanner, and
# other lanes edit files that hold pwsh spawns). A refactor that hides one
# from the scan fails here and names it, rather than leaving the rule vacuous.
SENTINELS = (
    ("plugin/crew/tests/scope_fixtures.py", "run_hook", None),
    ("plugin/crew/tests/test_role_write_guard.py", None, "_no_python_env"),
    ("plugin/crew/tests/test_cloud_guard.py", None, "_clean_env"),
    ("plugin/crew/hooks/scripts/_test/test_flavour_guard.py", "pwsh", None),
    ("plugin/obsidian-vault/hooks/scripts/_test/test_flavour_guard.py", "pwsh", None),
    ("plugin/obsidian-vault/hooks/scripts/_test/test_memory_ops.py", None, None),
    ("plugin/obsidian-vault/hooks/scripts/_test/test_python_probe_proof.py", "ps1_resolve", None),
)


def _is_autouse(func):
    for deco in func.decorator_list:
        if isinstance(deco, ast.Call) and any(
                kw.arg == "autouse" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in deco.keywords):
            return True
    return False


_PYTEST_TMP = frozenset(("tmp_path", "tmp_path_factory"))


def _derives_from_pytest_tmp(value, func, module, depth=0):
    """True when `value` is built from `tmp_path` or `tmp_path_factory`,
    following each name in it to the values bound to it (every binding must
    derive from one)."""
    for node in ast.walk(value):
        if not isinstance(node, ast.Name):
            continue
        if node.id in _PYTEST_TMP:
            return True
        bound = _assigned_values(node.id, func, module) if depth < 3 else []
        if bound and all(_derives_from_pytest_tmp(v, func, module, depth + 1) for v in bound):
            return True
    return False


def conftest_sets_per_test_cache(text):
    """True when an autouse fixture in `text` unconditionally runs
    `monkeypatch.setenv("XDG_CACHE_HOME", <a per-test pytest temp dir>)` -- the
    premise every inherited-environment pass under plugin/crew/tests rests on.
    An empty value, the user default, or a set inside a branch is not it."""
    tree = ast.parse(text)
    for func in ast.walk(tree):
        if not isinstance(func, ast.FunctionDef) or not _is_autouse(func):
            continue
        for stmt in func.body:
            call = stmt.value if isinstance(stmt, ast.Expr) else None
            if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Attribute)
                    and call.func.attr == "setenv" and len(call.args) == 2
                    and _is_key(call.args[0])):
                continue
            value = call.args[1]
            ctx = {"src": text, "module": tree, "in_crew": True}
            if (_derives_from_pytest_tmp(value, func, tree)
                    and _value_problem(value, func, ctx) is None):
                return True
    return False


def crew_conftest_covers():
    path = REPO / CREW_TESTS / "conftest.py"
    return conftest_sets_per_test_cache(path.read_text(encoding="utf-8"))


def _read_suite(root, rel):
    """(text, None), or (None, a `file:0:` problem). A suite the scan cannot
    read is reported, never skipped: "could not inspect" is not "clean"."""
    try:
        return (root / rel).read_text(encoding="utf-8"), None
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"{rel}:0: could not be read, so it was not checked: {exc}"


def _tree_python_sites(root=REPO, files=None, covered=None):
    """(sites, sources, problems) over the tracked Python suites."""
    sites, sources, problems = [], {}, []
    covered = crew_conftest_covers() if covered is None else covered
    for rel in _suite_files(".py") if files is None else files:
        src, problem = _read_suite(root, rel)
        if problem:
            problems.append(problem)
            continue
        try:
            found = scan_python(rel, src, covered)
        except SyntaxError as exc:
            problems.append(f"{rel}:{exc.lineno or 0}: unparseable: {exc.msg}")
            continue
        sources[rel] = src
        sites.extend(found)
    return sites, sources, problems


def _tree_python_problems(root, files):
    sites, _sources, problems = _tree_python_sites(root, files, covered=True)
    return problems + [f"{rel}:{line}: ({func}) {reason}"
                       for rel, line, func, reason in sites if reason]


def _sentinel_missing(sites, sources):
    missing = []
    for rel, func, env_text in SENTINELS:
        hits = [s for s in sites if s[0] == rel and (func is None or s[2] == func)]
        if env_text is not None:
            lines = sources.get(rel, "").splitlines()
            hits = [s for s in hits
                    if any(env_text in lines[i] for i in range(s[1] - 1, min(s[1] + 6, len(lines))))]
        if not hits:
            missing.append(f"{rel}::{func or env_text or '*'}")
    return missing


def test_every_python_pwsh_spawn_carries_xdg_cache_home():
    sites, sources, problems = _tree_python_sites()

    bad = problems + [f"{rel}:{line} ({func}): {reason}"
                      for rel, line, func, reason in sites if reason]
    missing = _sentinel_missing(sites, sources)

    assert (bad, missing) == ([], []), (
        "pwsh spawns that would share the user's startup profile (L-0557), "
        "and sentinel spawn sites the scan no longer finds:\n"
        + "\n".join(bad + ["MISSING SENTINEL " + m for m in missing]))


# --- the shell rule --------------------------------------------------------------

PWSH_INVOKE_RE = re.compile(
    r'(?:"\$PWSH"|"\$\{PWSH\}"|"\$REAL_PWSH"|"\$\{REAL_PWSH\}"|(?<![\w$/.-])pwsh)\s+-No')
MKTEMP_RE = re.compile(r'^\s*(?:local\s+)?([A-Za-z_]\w*)="?\$\(mktemp -d\)')
EXPORT_RE = re.compile(r'^\s*export\s+XDG_CACHE_HOME="\$\{?([A-Za-z_]\w*)\}?/xdg-cache"')


def _invocations(text):
    lines = []
    for number, line in enumerate(text.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#") or stripped.startswith("stub "):
            continue
        if PWSH_INVOKE_RE.search(line):
            lines.append(number)
    return lines


def scan_shell(rel, text):
    """None when the suite runs no real pwsh or exports the key into its own
    mktemp dir before its first invocation; else a reason naming the line."""
    invoked = _invocations(text)
    if not invoked:
        return None
    first = invoked[0]
    temps = set()
    for number, line in enumerate(text.splitlines(), 1):
        if number >= first:
            break
        match = MKTEMP_RE.match(line)
        if match:
            temps.add(match.group(1))
        match = EXPORT_RE.match(line)
        if match and match.group(1) in temps:
            return None
    return (f"{rel}:{first}: runs pwsh with no earlier "
            f'`export {KEY}="$<its mktemp dir>/xdg-cache"`')


def test_shell_scan_flags_missing_export():
    text = 'TMP="$(mktemp -d)"\n"$PWSH" -NoProfile -File x.ps1\n'

    assert scan_shell("s.sh", text) == (
        's.sh:2: runs pwsh with no earlier `export XDG_CACHE_HOME="$<its mktemp dir>/xdg-cache"`')


def test_shell_scan_flags_export_after_first_pwsh():
    text = ('TMP="$(mktemp -d)"\n"$PWSH" -NoProfile -File x.ps1\n'
            'export XDG_CACHE_HOME="$TMP/xdg-cache"\n')

    assert scan_shell("s.sh", text) is not None


def test_shell_scan_flags_export_outside_own_tmp():
    text = ('TMP="$(mktemp -d)"\nexport XDG_CACHE_HOME="$HOME/xdg-cache"\n'
            'out="$("$REAL_PWSH" -NoProfile -File x.ps1)"\n')

    assert scan_shell("s.sh", text) is not None


def test_shell_scan_accepts_export_first():
    text = ('work="$(mktemp -d)"\ntrap \'rm -rf "$work"\' EXIT\n'
            'export XDG_CACHE_HOME="$work/xdg-cache"\n'
            '    "$PWSH" -NoProfile -Command "$cmd"\n')

    assert scan_shell("s.sh", text) is None


def test_shell_scan_ignores_stub_only_suite():
    text = ("TMP=\"$(mktemp -d)\"\n"
            "stub pwsh 'case \"$*\" in *Get-Module*) echo X ;; esac; exit 0'\n"
            "run_it pwsh\n")

    assert scan_shell("s.sh", text) is None


def test_shell_scan_ignores_comment_mention():
    text = 'TMP="$(mktemp -d)"\n# pwsh -NoProfile is what CI runs\n'

    assert scan_shell("s.sh", text) is None


# The nine shell suites that run a real pwsh at L-0557's anchor. The tree scan
# must still find an invocation in each, so a rename of $PWSH cannot quietly
# take a suite out of the rule.
SHELL_SENTINELS = (
    "plugin/obsidian-vault/hooks/scripts/_test/test_vault_guard_sh.sh",
    "plugin/obsidian-vault/hooks/scripts/_test/test_bridge_capture_sh.sh",
    "plugin/obsidian-vault/hooks/scripts/_test/test_ps1_legacy_args.sh",
    "scripts/_test/check-powershell.sh",
    "scripts/_test/ps-install-keys.sh",
    "scripts/_test/uv-install.sh",
    "scripts/_test/mcp-preflight-catalog.sh",
    "scripts/_test/lsp-stack-tools.sh",
    "scripts/_test/web-testing.sh",
)


def _tree_shell(root=REPO, files=None):
    """(problems, the suites that invoke a real pwsh)."""
    bad, invoking = [], set()
    for rel in _suite_files(".sh") if files is None else files:
        text, problem = _read_suite(root, rel)
        if problem:
            bad.append(problem)
            continue
        if _invocations(text):
            invoking.add(rel)
        reason = scan_shell(rel, text)
        if reason:
            bad.append(reason)
    return bad, invoking


def _tree_shell_problems(root, files):
    return _tree_shell(root, files)[0]


def test_every_shell_suite_exports_xdg_cache_home_before_its_first_pwsh():
    bad, invoking = _tree_shell()

    missing = [rel for rel in SHELL_SENTINELS if rel not in invoking]

    assert (bad, missing) == ([], []), "\n".join(
        bad + ["MISSING SENTINEL (no pwsh invocation found) " + m for m in missing])


# --- the runtime check ------------------------------------------------------------

PWSH_ARGV0 = ("pwsh", "/snap/bin/pwsh", r"C:\Program Files\PowerShell\7\pwsh.exe",
              "powershell.exe")


def _argv(argv0, as_str):
    if as_str:
        return f'"{argv0}" -NoProfile -Command 1' if " " in argv0 else f"{argv0} -NoProfile"
    return [argv0, "-NoProfile", "-Command", "1"]


@pytest.mark.parametrize("as_str", (False, True), ids=("list", "str"))
@pytest.mark.parametrize("argv0", PWSH_ARGV0)
def test_runtime_check_rejects_missing_key(argv0, as_str, tmp_path):
    reason = crew_fixtures.pwsh_cache_violation(None, _argv(argv0, as_str),
                                                {"PATH": "/bin"}, str(tmp_path))

    assert reason is not None and "unset" in reason


@pytest.mark.parametrize("as_str", (False, True), ids=("list", "str"))
@pytest.mark.parametrize("argv0", PWSH_ARGV0)
def test_runtime_check_rejects_empty_key(argv0, as_str, tmp_path):
    reason = crew_fixtures.pwsh_cache_violation(None, _argv(argv0, as_str),
                                                {KEY: ""}, str(tmp_path))

    assert reason is not None and "empty" in reason


@pytest.mark.parametrize("argv0", PWSH_ARGV0)
def test_runtime_check_rejects_user_default(argv0, tmp_path):
    default = os.path.join(os.path.expanduser("~"), ".cache")

    reason = crew_fixtures.pwsh_cache_violation(argv0, [argv0], {KEY: default},
                                                str(tmp_path))

    assert reason is not None and "user default" in reason


@pytest.mark.parametrize("argv0", PWSH_ARGV0)
def test_runtime_check_rejects_path_outside_allowed_root(argv0, tmp_path):
    reason = crew_fixtures.pwsh_cache_violation(
        None, [argv0], {KEY: str(tmp_path / "elsewhere" / "xdg-cache")},
        str(tmp_path / "test-dir"))

    assert reason is not None and "outside" in reason


@pytest.mark.parametrize("as_str", (False, True), ids=("list", "str"))
@pytest.mark.parametrize("argv0", PWSH_ARGV0)
def test_runtime_check_accepts_under_allowed_root(argv0, as_str, tmp_path):
    reason = crew_fixtures.pwsh_cache_violation(
        None, _argv(argv0, as_str), {KEY: str(tmp_path / "xdg-cache")}, str(tmp_path))

    assert reason is None


@pytest.mark.parametrize("argv0", ("bash", "/usr/bin/python3", "git", "pwsh-wrapper.sh"))
def test_runtime_check_ignores_non_pwsh(argv0, tmp_path):
    reason = crew_fixtures.pwsh_cache_violation(None, [argv0, "-c", "x"], {},
                                                str(tmp_path))

    assert reason is None


_SEEN_CACHE_DIRS = set()


@pytest.mark.parametrize("_run", (1, 2))
def test_autouse_fixture_never_hands_two_tests_the_same_cache_dir(_run):
    value = os.environ[KEY]
    seen_before = value in _SEEN_CACHE_DIRS
    _SEEN_CACHE_DIRS.add(value)

    assert not seen_before, f"{value} was already another test's cache dir"


def test_autouse_fixture_gives_each_test_its_own_cache_dir(tmp_path_factory):
    value = pathlib.Path(os.environ[KEY])

    assert (value.parent == tmp_path_factory.getbasetemp(),
            value.name.startswith("xdg-cache"), value.is_dir(),
            str(value) != crew_fixtures.pwsh_cache_session_dir(),
            str(value) == crew_fixtures._PWSH_CACHE_ROOT) == (  # pylint: disable=protected-access
                True, True, True, True, True)
