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


def _sets_key(node):
    """True when code under `node` names XDG_CACHE_HOME: a string constant or
    a keyword argument. Read from the AST, so a comment that mentions the
    variable is not mistaken for code that sets it."""
    if node is None:
        return False
    return any((isinstance(n, ast.Constant) and n.value == KEY)
               or (isinstance(n, ast.keyword) and n.arg == KEY)
               for n in ast.walk(node))


def _reads_environ(node):
    """True when code under `node` reads `os.environ` (or a bare `environ`)."""
    return any((isinstance(n, ast.Attribute) and n.attr == "environ")
               or (isinstance(n, ast.Name) and n.id == "environ")
               for n in ast.walk(node))


def _judge_env(src, expr, helpers, in_crew, scope):
    """None when the spawn's environment provably carries the key, else a
    one-line reason. Anything the rule cannot classify is a reason, never a
    pass (outside crew's conftest, where nothing else would set it)."""
    if expr is None or (isinstance(expr, ast.Constant) and expr.value is None):
        return None if in_crew else "inherits the environment, and no conftest sets " + KEY
    text = ast.get_source_segment(src, expr) or ""
    if _sets_key(expr):
        return None
    if isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name) and expr.func.id in helpers:
        body = helpers[expr.func.id]
        if _sets_key(body):
            return None
        if _reads_environ(body):
            return None if in_crew else (
                f"helper {expr.func.id}() copies the environment but sets no {KEY}")
        return f"helper {expr.func.id}() builds the environment from scratch without {KEY}"
    if _reads_environ(expr):
        return None if in_crew else f"copies the environment but sets no {KEY}"
    if isinstance(expr, ast.Dict) or (
            isinstance(expr, ast.Call) and isinstance(expr.func, ast.Name)
            and expr.func.id == "dict"):
        return f"builds the environment from scratch without {KEY}"
    if in_crew or _sets_key(scope):
        return None
    return f"env={text} - its enclosing function never sets {KEY}"


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
    in_crew = crew_covered and rel.startswith(CREW_TESTS)
    helpers = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    sites = []
    for call, scope in _scopes(tree).items():
        if _func_name(call) not in SPAWN_NAMES:
            continue
        first = _first_arg(call)
        if first is None or not any(PWSH_RE.search(t) for t in _argv0_texts(src, first, scope)):
            continue
        _present, env = _env_value(call)
        reason = _judge_env(src, env, helpers, in_crew, scope)
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
        "    env.setdefault('XDG_CACHE_HOME', XDG)\n"
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


CONFTEST_SETS_RE = re.compile(r'monkeypatch\.setenv\(\s*"XDG_CACHE_HOME"')


def crew_conftest_covers():
    """True when crew's conftest sets XDG_CACHE_HOME per test - the premise
    every inherited-environment pass under plugin/crew/tests rests on."""
    path = REPO / CREW_TESTS / "conftest.py"
    return bool(CONFTEST_SETS_RE.search(path.read_text(encoding="utf-8")))


def _tree_python_sites():
    sites, sources = [], {}
    covered = crew_conftest_covers()
    for rel in _suite_files(".py"):
        try:
            src = (REPO / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            found = scan_python(rel, src, covered)
        except SyntaxError as exc:
            sites.append((rel, exc.lineno or 0, "<module>", f"unparseable: {exc.msg}"))
            continue
        sources[rel] = src
        sites.extend(found)
    return sites, sources


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
    sites, sources = _tree_python_sites()

    bad = [f"{rel}:{line} ({func}): {reason}" for rel, line, func, reason in sites if reason]
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


def test_every_shell_suite_exports_xdg_cache_home_before_its_first_pwsh():
    bad, invoking = [], set()
    for rel in _suite_files(".sh"):
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if _invocations(text):
            invoking.add(rel)
        reason = scan_shell(rel, text)
        if reason:
            bad.append(reason)

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


def test_autouse_fixture_gives_each_test_its_own_cache_dir(tmp_path):
    value = os.environ.get(KEY)

    assert (value, value != crew_fixtures.pwsh_cache_session_dir()) == (
        str(tmp_path / "xdg-cache"), True)
