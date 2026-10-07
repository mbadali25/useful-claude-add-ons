"""L-1508: a tool is run the way it was found -- no bare-name subprocess.

On native Windows a bare `["git", ...]` reaches CreateProcess, which ignores
PATHEXT and tries only `git.exe`, while bash, pwsh and `shutil.which` find a
`git.cmd` first. crew then judges a different tool from the one the user's
shell runs; at a guard that is a fail-open (T-0017's wrap-up veto), and in
the suite it is a false green (the `.cmd` stub is skipped for the real tool).

Three parts:
  * `crew_common.resolve_tool` / `require_tool` unit tests, including a PATH
    swap inside one process (no cache may hide it);
  * an AST lint over every plugin and skill script: any
    `subprocess.run/Popen/check_output/check_call/call` whose argv starts
    with a string literal fails unless `ALLOWLIST` names the file, the
    function, the tool and why -- with must-block, must-allow and sabotage
    cases for the lint itself;
  * per-site tests: each fixed site runs the path `shutil.which` answers,
    and an unresolved tool takes the site's existing failure path.

The guard tests (a failing tool reachable only through `shutil.which`, the
guard refuses on every OS) live beside each guard's own suite:
test_wrapup.py (#356), test_ci_receipt.py, test_status.py, test_crew_tracker.py.
"""
import ast
import functools
import os
import pathlib
import shutil
import subprocess

import pytest

import context
import ci_receipt
import crew_autocycle
import crew_common
import crew_fixtures
import crew_instructions
import crew_refresh_check
import crew_shell
import crew_state
import crew_status
import crew_tracker
import crew_trailers
import crew_upgrade
import event_claim
import qa_audit
import qa_audit_env
import qa_doc

REPO = pathlib.Path(context._ROOT).parent.parent  # pylint: disable=protected-access
SCAN_ROOTS = ("plugin", "skills")
SKIP_PARTS = {"tests", "_test", "node_modules", "__pycache__"}
SUBPROCESS_FNS = {"run", "Popen", "check_output", "check_call", "call"}

# (file, enclosing function, tool) -> why a bare name is right, or not fixed
# here. A gated entry also cites the gate's `path:line` and the text on that
# line, and test_every_gate_citation_still_points_at_its_gate checks it.
ALLOWLIST = (
    {"file": "plugin/crew/hooks/scripts/crew_autocycle.py", "function": "_proc",
     "tool": "ps", "reason": "POSIX only: _proc returns before ps on native Windows",
     "gate": "plugin/crew/hooks/scripts/crew_autocycle.py:651",
     "gate_text": 'if found is not None or os.name == "nt":'},
    {"file": "plugin/crew/hooks/scripts/crew_platform.py", "function": "_wsl_facts",
     "tool": "ip", "reason": "WSL2 only: _wsl_facts is called only when platform.system() is Linux",
     "gate": "plugin/crew/hooks/scripts/crew_platform.py:145",
     "gate_text": 'if system == "Linux":'},
    {"file": "plugin/obsidian-vault/hooks/scripts/obsidian_common.py",
     "function": "_macos_obsidian_running", "tool": "ps",
     "reason": "macOS only: Windows returns earlier and Linux reads /proc",
     "gate": "plugin/obsidian-vault/hooks/scripts/obsidian_common.py:912",
     "gate_text": ('running = _linux_obsidian_running() if system == "Linux" '
                   'else _macos_obsidian_running()')},
    {"file": "skills/notify/scripts/notifyd.py", "function": "_pid_alive", "tool": "tasklist",
     "reason": "Windows only, and tasklist ships as tasklist.exe, the one form CreateProcess tries",
     "gate": "skills/notify/scripts/notifyd.py:301", "gate_text": 'if os.name == "nt":'},
    {"file": "plugin/crew/hooks/scripts/crew_shell.py", "function": "run", "tool": "bash",
     "reason": "POSIX only: run() takes `bash -c` only off native Windows",
     "gate": "plugin/crew/hooks/scripts/crew_shell.py:776", "gate_text": "if not on_windows():"},
    {"file": "plugin/crew/hooks/scripts/webtest_guard.py", "function": "check_visual", "tool": "npx",
     "reason": "Linux only: check_visual returns before npx off Linux (then off the pinned Playwright container)",
     "gate": "plugin/crew/hooks/scripts/webtest_guard.py:673",
     "gate_text": 'if not sys.platform.startswith("linux"):'},
    {"file": "plugin/obsidian-vault/hooks/scripts/vault_garden.py", "function": "commit_owned",
     "tool": "git", "reason": "L-1509"},
    {"file": "plugin/rule-of-two/scripts/rule_of_two.py", "function": "run_codex",
     "tool": "codex", "reason": "L-1509"},
    {"file": "skills/repo-docs/scripts/git_changelog.py", "function": "git",
     "tool": "git", "reason": "L-1509"},
    {"file": "skills/repo-docs/scripts/repo_survey.py", "function": "run_git",
     "tool": "git", "reason": "L-1509"},
)


# --- the resolver -----------------------------------------------------------------

def _stub_dir(tmp_path, name, tool="crewtool"):
    crew_fixtures.write_shim(tmp_path / name, tool)
    return str(tmp_path / name)


def _found(directory, tool="crewtool"):
    return os.path.join(directory, tool + (".cmd" if os.name == "nt" else ""))


def test_resolve_tool_answers_what_shutil_which_finds(tmp_path, monkeypatch):
    bindir = _stub_dir(tmp_path, "bin")
    monkeypatch.setenv("PATH", bindir)

    assert os.path.normcase(crew_common.resolve_tool("crewtool")) == os.path.normcase(_found(bindir))


def test_resolve_tool_answers_none_for_a_tool_not_on_path(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    assert crew_common.resolve_tool("crewtool") is None


def test_resolve_tool_sees_a_path_change_within_one_process(tmp_path, monkeypatch):
    # No cache may hide a PATH swap: the suite swaps PATH to put a stub first.
    first, second = _stub_dir(tmp_path, "a"), _stub_dir(tmp_path, "b")
    seen = []
    for path in (first, second, str(tmp_path), first):
        monkeypatch.setenv("PATH", path)
        found = crew_common.resolve_tool("crewtool")
        seen.append(found and os.path.normcase(found))

    assert seen == [os.path.normcase(_found(first)), os.path.normcase(_found(second)), None,
                    os.path.normcase(_found(first))]


def test_require_tool_names_the_missing_tool_as_a_file_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("PATH", str(tmp_path))

    with pytest.raises(FileNotFoundError) as caught:
        crew_common.require_tool("crewtool")

    assert isinstance(caught.value, crew_common.ToolNotFound)
    assert "crewtool is not on PATH" in str(caught.value)


# --- the lint ---------------------------------------------------------------------

# Calls whose first argument is an argv list (or a command string), by module.
ARGV_FNS = {"subprocess": SUBPROCESS_FNS | {"getoutput", "getstatusoutput"},
            "os": {"system", "popen"}}
# Calls whose first argument is the program name itself.
PROGRAM_FNS = {"os": {"execlp", "execlpe", "execvp", "execvpe", "spawnlp", "spawnlpe",
                      "spawnvp", "spawnvpe"},
               "asyncio": {"create_subprocess_exec"}}
# Known argv wrappers: a function in a scanned script that hands its first
# argument to subprocess unchanged, matched by name when called bare (never as
# an attribute: `conn.execute("SELECT ...")` is sqlite). crew_shell's
# injectable `runner`/`execute` and their defaults, obsidian's `_run_bounded`.
WRAPPERS = {"capture", "runner", "execute", "execute_job", "_run_bounded"}


def _first_word(text):
    words = text.split()
    return words[0] if words else None


def _literal_head(node, assigns=None):
    """The program an argv expression names literally, or None: the first
    element of a list/tuple (or of the left side of a `+`), the first word of
    a command string, or -- for a bare name -- the same of the one value the
    enclosing function assigns to it."""
    assigns = assigns or {}
    if isinstance(node, (ast.List, ast.Tuple)):
        if not node.elts:
            return None
        first = node.elts[0]
        return first.value if isinstance(first, ast.Constant) and isinstance(first.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _literal_head(node.left, assigns)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return _first_word(node.value)
    if isinstance(node, ast.JoinedStr) and node.values:
        first = node.values[0]
        if isinstance(first, ast.Constant) and isinstance(first.value, str) and first.value[:1].strip():
            return _first_word(first.value)
        return None
    if isinstance(node, ast.Name) and node.id in assigns:
        return _literal_head(assigns[node.id])
    return None


def _program(node):
    """A program-name argument (`os.execvp("git", ...)`): the literal itself."""
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def _aliases(tree):
    """{local name: (module, function or None)} for the modules this file uses."""
    names = {m: (m, None) for m in set(ARGV_FNS) | set(PROGRAM_FNS)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name in names:
                    names[a.asname or a.name] = (a.name, None)
        elif isinstance(node, ast.ImportFrom) and node.module in names:
            for a in node.names:
                names[a.asname or a.name] = (node.module, a.name)
    return names


def _classify(call, aliases):
    """("argv" | "program", node) for a call that starts a process, else None."""
    func = call.func
    module = fn = None
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        bound = aliases.get(func.value.id)
        if bound and bound[1] is None:
            module, fn = bound[0], func.attr
    elif isinstance(func, ast.Name):
        bound = aliases.get(func.id)
        if bound and bound[1]:
            module, fn = bound
        elif func.id in WRAPPERS:
            module, fn = "<wrapper>", func.id
    if module == "<wrapper>":
        kind = "argv"
    elif fn in ARGV_FNS.get(module, ()):
        kind = "argv"
    elif fn in PROGRAM_FNS.get(module, ()):
        kind = "program"
    else:
        return None
    at = 1 if fn.startswith("spawn") else 0  # os.spawn*p(mode, file, ...)
    if len(call.args) > at:
        return kind, call.args[at]
    key = "args" if kind == "argv" else "program"
    found = next((k.value for k in call.keywords if k.arg in (key, "cmd")), None)
    return (kind, found) if found is not None else None


def _single_assigns(func):
    """{name: value} for names assigned exactly once in `func` (nested defs excluded)."""
    seen = {}
    stack = list(ast.iter_child_nodes(func))
    while stack:
        node = stack.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
            continue
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    seen.setdefault(target.id, []).append(node.value)
        elif isinstance(node, (ast.AugAssign, ast.AnnAssign)) and isinstance(node.target, ast.Name):
            seen.setdefault(node.target.id, []).append(getattr(node, "value", None))
        stack.extend(ast.iter_child_nodes(node))
    return {k: v[0] for k, v in seen.items() if len(v) == 1 and v[0] is not None}


def bare_sites(source, rel):
    """[(rel, enclosing function, tool, line)] for every bare-name call in `source`."""
    tree = ast.parse(source)
    aliases = _aliases(tree)
    found = []

    def walk(node, where, assigns):
        for child in ast.iter_child_nodes(node):
            inner, inner_assigns = where, assigns
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner, inner_assigns = child.name, _single_assigns(child)
            if isinstance(child, ast.Call):
                got = _classify(child, aliases)
                if got:
                    kind, arg = got
                    tool = _literal_head(arg, assigns) if kind == "argv" else _program(arg)
                    if tool:
                        found.append((rel, where, tool, child.lineno))
            walk(child, inner, inner_assigns)
    walk(tree, "<module>", _single_assigns(tree))
    return found


def scan(root):
    """Every bare-name site in the plugin and skill scripts under `root`."""
    sites = []
    for top in SCAN_ROOTS:
        for path in sorted((root / top).rglob("*.py")):
            rel = path.relative_to(root)
            if SKIP_PARTS & set(rel.parts[:-1]):
                continue
            sites += bare_sites(path.read_text(encoding="utf-8"), rel.as_posix())
    return sites


def problems(sites, allowlist, root=REPO):
    """Why the lint fails, one line each; [] when it passes."""
    out = []
    for entry in allowlist:
        if not all(str(entry.get(k) or "").strip() for k in ("file", "function", "tool", "reason")):
            out.append(f"allowlist entry without a file, function, tool or reason: {entry}")
    keys = {(e.get("file"), e.get("function"), e.get("tool")) for e in allowlist
            if str(e.get("reason") or "").strip()}
    for rel, where, tool, line in sites:
        if (rel, where, tool) not in keys:
            out.append(f"{rel}:{line} runs a bare {tool!r} in {where}(): run "
                       f"crew_common.require_tool({tool!r}) / resolve_tool, or allowlist it with a reason")
    used = {(rel, where, tool) for rel, where, tool, _ in sites}
    for entry in allowlist:
        key = (entry.get("file"), entry.get("function"), entry.get("tool"))
        if key not in used:
            out.append(f"stale allowlist entry (no such bare call any more): {key}")
        if "gate" in entry:
            gate_file, _, gate_line = entry["gate"].rpartition(":")
            try:
                text = (root / gate_file).read_text(encoding="utf-8").splitlines()[int(gate_line) - 1]
            except (OSError, ValueError, IndexError):
                text = ""
            if text.strip() != entry.get("gate_text"):
                out.append(f"{key}: gate {entry['gate']} no longer reads {entry.get('gate_text')!r}")
    return out


@functools.lru_cache(maxsize=None)
def _repo_sites():
    """This checkout's sites, scanned once per run (a scan parses every script)."""
    return tuple(scan(REPO))


def test_no_bare_name_subprocess_outside_the_allowlist():
    assert problems(list(_repo_sites()), ALLOWLIST) == []


def test_the_scan_reaches_every_plugin_and_skill_script():
    # A scan that silently found nothing would pass the test above.
    files = {rel for rel, _, _, _ in _repo_sites()}
    assert {"plugin/crew/hooks/scripts/crew_autocycle.py",
            "plugin/obsidian-vault/hooks/scripts/obsidian_common.py",
            "skills/notify/scripts/notifyd.py"} <= files


BLOCK = {
    "list": 'import subprocess\ndef f():\n    subprocess.run(["git", "status"])\n',
    "tuple": 'import subprocess\ndef f(args):\n    subprocess.run(("git", "-c", "x=y") + args)\n',
    "list concatenation": 'import subprocess\ndef f(x, args):\n    subprocess.run(["git", "-C", x] + args)\n',
    "unpacked tail": 'import subprocess\ndef f(args):\n    subprocess.run(["git", *args])\n',
    "args keyword": 'import subprocess\ndef f():\n    subprocess.run(args=["git", "status"])\n',
    "Popen": 'import subprocess\ndef f():\n    subprocess.Popen(["ps", "-A"])\n',
    "check_output": 'import subprocess\ndef f():\n    subprocess.check_output(["ip", "route"])\n',
    "check_call": 'import subprocess\ndef f():\n    subprocess.check_call(["git", "fetch"])\n',
    "call": 'import subprocess\ndef f():\n    subprocess.call(["git", "fetch"])\n',
    "module alias": 'import subprocess as sp\ndef f():\n    sp.run(["git", "status"])\n',
    "imported function": 'from subprocess import run\ndef f():\n    run(["git", "status"])\n',
    "module level": 'import subprocess\nsubprocess.run(["git", "status"])\n',
    "name assigned once (a)": 'import subprocess\ndef f(x):\n    cmd = ["git", "-C", x]\n    subprocess.run(cmd)\n',
    "name assigned a concatenation (a)": ('import subprocess\ndef f(args):\n'
                                          '    argv = ("git", "log") + args\n    subprocess.run(argv)\n'),
    "command string (b)": 'import subprocess\ndef f():\n    subprocess.run("git status", shell=True)\n',
    "f-string command (b)": 'import subprocess\ndef f(x):\n    subprocess.check_output(f"git -C {x} status")\n',
    "getoutput (c)": 'import subprocess\ndef f():\n    subprocess.getoutput("git status")\n',
    "os.system (c)": 'import os\ndef f():\n    os.system("git status")\n',
    "os.popen (c)": 'import os\ndef f():\n    os.popen("ps -A")\n',
    "os.execvp (c)": 'import os\ndef f(argv):\n    os.execvp("git", argv)\n',
    "os.spawnlp (c)": 'import os\ndef f():\n    os.spawnlp(os.P_WAIT, "git", "git")\n',
    "asyncio exec (c)": 'import asyncio\nasync def f():\n    await asyncio.create_subprocess_exec("git", "status")\n',
    "wrapper runner (d)": 'def f(runner):\n    runner(["git", "--exec-path"], 10)\n',
    "wrapper _run_bounded (d)": 'def f(vault):\n    _run_bounded(["git", "-C", vault, "add"], 5)\n',
}


@pytest.mark.parametrize("case", sorted(BLOCK))
def test_lint_blocks_a_bare_name_call(case):
    sites = bare_sites(BLOCK[case], "plugin/x/hooks/scripts/synthetic.py")

    assert len(problems(sites, ())) == 1, sites


ALLOW = {
    "resolved path": ('import subprocess, crew_common\ndef f():\n'
                      '    subprocess.run([crew_common.require_tool("git"), "status"])\n'),
    "resolved variable": 'import subprocess\ndef f(git, args):\n    subprocess.run((git, *args))\n',
    "interpreter": 'import subprocess, sys\ndef f():\n    subprocess.run([sys.executable, "-c", "1"])\n',
    "argv built elsewhere": 'import subprocess\ndef f(cmd):\n    subprocess.run(cmd)\n',
    "not subprocess": 'import other\ndef f():\n    other.run(["git", "status"])\n',
    "name assigned twice": ('import subprocess\ndef f(git, x):\n    cmd = ["git"]\n'
                            '    cmd = [git, x]\n    subprocess.run(cmd)\n'),
    "sqlite execute": 'def f(conn):\n    conn.execute("SELECT 1")\n',
    "resolved wrapper": 'import crew_common\ndef f(runner):\n    runner([crew_common.require_tool("git"), "x"], 10)\n',
}


@pytest.mark.parametrize("case", sorted(ALLOW))
def test_lint_allows_a_resolved_call(case):
    assert bare_sites(ALLOW[case], "plugin/x/hooks/scripts/synthetic.py") == []


def test_lint_allows_an_allowlisted_site():
    sites = bare_sites(BLOCK["list"], "plugin/x/hooks/scripts/synthetic.py")
    entry = {"file": "plugin/x/hooks/scripts/synthetic.py", "function": "f", "tool": "git",
             "reason": "synthetic"}

    assert problems(sites, (entry,)) == []


def _copy_tree(tmp_path):
    """The scanned scripts (and the gate files they cite), nothing else."""
    for top in SCAN_ROOTS:
        for path in (REPO / top).rglob("*.py"):
            rel = path.relative_to(REPO)
            if not SKIP_PARTS & set(rel.parts[:-1]):
                (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, tmp_path / rel)
    return tmp_path


def test_sabotage_a_bare_call_added_to_a_real_hook_script_goes_red(tmp_path):
    root = _copy_tree(tmp_path)
    assert problems(scan(root), ALLOWLIST, root) == []
    script = root / "plugin" / "crew" / "hooks" / "scripts" / "crew_status.py"
    script.write_text(script.read_text(encoding="utf-8")
                      + '\n\ndef _sabotage():\n    subprocess.run(["git", "status"], check=False)\n',
                      encoding="utf-8", newline="\n")

    assert problems(scan(root), ALLOWLIST, root) == [
        f"plugin/crew/hooks/scripts/crew_status.py:{len(script.read_text(encoding='utf-8').splitlines())} "
        "runs a bare 'git' in _sabotage(): run crew_common.require_tool('git') / resolve_tool, "
        "or allowlist it with a reason"]


def test_sabotage_an_allowlist_entry_without_its_reason_goes_red():
    dropped = [dict(e) for e in ALLOWLIST]
    dropped[0]["reason"] = ""

    got = problems(list(_repo_sites()), dropped)

    assert any("without a file, function, tool or reason" in p for p in got)
    assert any(dropped[0]["file"] in p and f"runs a bare '{dropped[0]['tool']}'" in p for p in got)


def test_a_stale_allowlist_entry_goes_red():
    extra = ALLOWLIST + ({"file": "plugin/crew/hooks/scripts/crew_common.py", "function": "git_out",
                          "tool": "git", "reason": "fixed in PR A"},)

    assert problems(list(_repo_sites()), extra) == [
        "stale allowlist entry (no such bare call any more): "
        "('plugin/crew/hooks/scripts/crew_common.py', 'git_out', 'git')"]


def test_every_gate_citation_still_points_at_its_gate():
    moved = [dict(e, gate=e["gate"].rpartition(":")[0] + ":1") if "gate" in e else e
             for e in ALLOWLIST]

    got = [p for p in problems(list(_repo_sites()), moved) if "no longer reads" in p]

    assert len(got) == sum("gate" in e for e in ALLOWLIST) == 6


def test_a_gate_weakened_on_its_own_line_goes_red():
    # The whole stripped line must match: `if found is not None or os.name == "nt":`
    # weakened to `if True or os.name == "nt":` still contains the old substring.
    cited = [dict(e, gate_text='os.name == "nt"') if e["tool"] == "ps" and "gate" in e
             and e["function"] == "_proc" else e for e in ALLOWLIST]

    got = [p for p in problems(list(_repo_sites()), cited) if "no longer reads" in p]

    assert got == ["('plugin/crew/hooks/scripts/crew_autocycle.py', '_proc', 'ps'): gate "
                   "plugin/crew/hooks/scripts/crew_autocycle.py:651 no longer reads 'os.name == \"nt\"'"]


# --- per site: the resolved path runs, and an unresolved tool fails as before --------

SENTINEL = os.path.join(os.sep, "resolved", "bin", "tool")


def _record(monkeypatch, calls):
    def fake(cmd, *args, **kwargs):
        calls.append(list(cmd))
        texty = kwargs.get("text") or kwargs.get("encoding") or kwargs.get("universal_newlines")
        return subprocess.CompletedProcess(cmd, 0, "" if texty else b"x\0", "" if texty else b"")
    monkeypatch.setattr(subprocess, "run", fake)


def _which(monkeypatch, tool, answer):
    real = shutil.which
    monkeypatch.setattr(shutil, "which",
                        lambda name, *a, **k: answer if name == tool else real(name, *a, **k))


def _no_proc(monkeypatch):
    real = os.listdir
    monkeypatch.delenv(crew_autocycle.PROC_STUB_ENV, raising=False)

    def listdir(path="."):
        if str(path) == "/proc":
            raise FileNotFoundError(path)
        return real(path)
    monkeypatch.setattr(os, "listdir", listdir)


def _raises_unreadable(func, *args):
    try:
        func(*args)
    except ci_receipt.Unreadable as exc:
        return "could not run" in str(exc) and "git is not on PATH" in str(exc)
    return False


# (id, tool, call(root), the site's answer when the tool does not resolve)
SITES = [
    ("crew_common.git_out", "git", lambda r: crew_common.git_out(r, "rev-parse", "HEAD"), None),
    ("ci_receipt._git", "git", lambda r: _raises_unreadable(ci_receipt._git, r, "rev-parse"), True),
    ("ci_receipt._git_ok", "git", lambda r: _raises_unreadable(ci_receipt._git_ok, r, "cat-file"), True),
    ("crew_instructions._tracked", "git", crew_instructions._tracked, None),
    ("crew_refresh_check._git_rc", "git", lambda r: crew_refresh_check._git_rc(r, "status"), None),
    ("crew_refresh_check._git_out", "git", lambda r: crew_refresh_check._git_out(r, "status"), (None, b"")),
    ("crew_refresh_check._base_text", "git", lambda r: crew_refresh_check._base_text(r, "HEAD", "a"),
     (None, "error: git ls-tree could not run")),
    ("crew_state.in_git_repo", "git", crew_state.in_git_repo, None),
    ("crew_status._git", "git", lambda r: crew_status._git(r, "status"), None),
    ("crew_tracker._git_out", "git", lambda r: crew_tracker._git_out(r, "status"), (None, "")),
    ("crew_tracker._git_ignored", "git", lambda r: crew_tracker._git_ignored(r, "a"), None),
    ("crew_trailers._log_messages", "git", lambda r: crew_trailers._log_messages(r, "HEAD~1"), None),
    ("event_claim.claims_dir", "git", event_claim.claims_dir, "<root>/.crew/event-claims"),
    ("crew_autocycle._process_table", "ps", lambda r: crew_autocycle._process_table(), None),
    ("crew_autocycle._xdotool", "xdotool", lambda r: crew_autocycle._xdotool("search"), ""),
    ("qa_audit.stamp", "git", qa_audit.stamp, None),
    ("qa_audit_env._git", "git", lambda r: qa_audit_env._git(r, "status"), None),
    ("qa_doc._git", "git", lambda r: qa_doc._git(r, "status"), None),
    ("crew_upgrade._head", "git", crew_upgrade._head, None),
    ("crew_shell.resolve_gitbash", "git",
     lambda r: crew_shell.resolve_gitbash(exists=lambda _p: False, which=lambda _n: None)[0], None),
]


@pytest.fixture(name="root")
def _root(tmp_path):
    (tmp_path / ".crew").mkdir()
    return str(tmp_path)


@pytest.mark.parametrize("site", SITES, ids=[s[0] for s in SITES])
def test_each_site_runs_the_path_which_resolves(site, root, monkeypatch):
    _, tool, call, _ = site
    calls = []
    _no_proc(monkeypatch)
    _which(monkeypatch, tool, SENTINEL)
    _record(monkeypatch, calls)

    call(root)

    assert calls and all(c[0] == SENTINEL for c in calls), calls


@pytest.mark.parametrize("site", SITES, ids=[s[0] for s in SITES])
def test_each_site_takes_its_failure_path_when_the_tool_does_not_resolve(site, root, monkeypatch):
    _, tool, call, unresolved = site
    calls = []
    _no_proc(monkeypatch)
    _which(monkeypatch, tool, None)
    _record(monkeypatch, calls)
    if unresolved == "<root>/.crew/event-claims":
        unresolved = os.path.join(root, ".crew", "event-claims")

    assert (call(root), calls) == (unresolved, [])
