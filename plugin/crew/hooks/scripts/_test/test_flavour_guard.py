#!/usr/bin/env python3
"""The flavour guard: every .ps1 this plugin registers stands down off Windows.

## What this covers and why it exists

`hooks.json` registers EVERY event twice - a bash `command` and a
`shell: "powershell"` command running the `.ps1` twin. That is correct: a
single-shell machine then always gets exactly one flavour. On a host with BOTH
interpreters it is not, and until PowerShell was installed on this repository's
Linux host the second registration merely printed a red `hook error` per event.
Installing pwsh converts that loud noise into SILENT DOUBLE EXECUTION - two
Stop gates on one turn, two PostToolUse guards on one write, two captures per
session end.

The fix is one line at the top of each `.ps1`:

    if ($env:OS -ne 'Windows_NT') { exit 0 }

`$env:OS` is 'Windows_NT' on BOTH Windows PowerShell 5.1 and PowerShell 7, and
unset on Linux/macOS. The obvious alternative, `if (-not $IsWindows)`, is
WRONG: `$IsWindows` does not exist in 5.1, so it is `$null` there, `-not $null`
is `$true`, and the hook stands down on the one platform it exists for. crew
has shipped that shape of bug before - a guard that stood down on Windows and
blocked nothing there - which is why case (3) below is not optional.

## The four cases

1. STATIC, and derived: every `.ps1` named by `hooks.json` carries the guard,
   AS ITS FIRST EXECUTABLE STATEMENT (checked through PowerShell's own parser,
   not by grep, so a guard sitting after a `Set-Location` or a `Remove-Item`
   fails). The list comes from parsing `hooks.json`, so registering a new hook
   with no guard turns this red without anyone remembering to update a number.
2. PROCEEDS with `OS=Windows_NT`: the script executes statements past the
   guard line.
3. THE 5.1 CASE: `$IsWindows` absent from the session AND `OS=Windows_NT` -
   the script must still proceed. This is the case the bare `$IsWindows` form
   fails, so it is the one that must be RED before the fix. Sabotage-test with
   it: put `if (-not $IsWindows) { exit 0 }` back into any one file and this
   case goes red for that file alone.
4. STANDS DOWN with `OS` unset: exit 0, no stdout, no stderr, AND THE FIXTURE
   TREE IS BYTE-IDENTICAL AFTERWARDS. Exit code alone proves nothing here - a
   script that ran to completion and happened to succeed also exits 0. The
   tree snapshot is what catches a guard placed too low: several of these
   hooks `Remove-Item` a `.crew/` marker or `New-Item` a directory within two
   lines of the top.

## How "proceeded" is observed

`Set-PSDebug -Trace 1` prints one `DEBUG: <line>+ ...` row per executed
statement. Proceeded == some row's line number exceeds the guard's. That is
uniform across all of these scripts, which otherwise have nothing in common -
some read stdin, some take parameters, some delegate to python, one blocks.
Concrete side effects are asserted ON TOP of it where a script has a cheap
deterministic one (a deleted marker, a created directory, an exit 2, a
delegated python call), never instead of it.

## Isolation

Everything runs in a throwaway fixture with its own HOME, its own
CLAUDE_PROJECT_DIR and a PATH whose first entry holds fake `python3`,
`python`, `py`, `git` and `curl` that record a call and exit 0. Nothing here
reads or writes real config, runs a real interpreter over a real repo, or
makes a network call.

## Matched pair

This file is IDENTICAL in every plugin that registers PowerShell hooks - it
derives the plugin root from its own location and reads that plugin's
`hooks.json`, so it has no plugin-specific content. Change one copy, change
the others. It is a matched pair for the same reason
`scripts/install-prerequisites.{sh,ps1}` are.

Run:  python3 hooks/scripts/_test/test_flavour_guard.py
Exit 0 = all pass, 1 = something regressed, 77 = pwsh unavailable (skipped).
"""
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
PLUGIN = SCRIPTS.parent.parent
HOOKS_JSON = PLUGIN / "hooks" / "hooks.json"

GUARD_TEXT = "if ($env:OS -ne 'Windows_NT') { exit 0 }"
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
DEBUG_ROW = re.compile(r"^DEBUG:\s+(\d+)\+")

PASS = 0
FAIL = 0


def check(ok, desc, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
        print(f"  FAIL  {desc}")
        if detail:
            for line in str(detail).rstrip().splitlines():
                print(f"          {line}")


# --------------------------------------------------------------------------
# What hooks.json actually registers. The .ps1 list is DERIVED, never typed.
# --------------------------------------------------------------------------
def registered_powershell_hooks():
    """[(script_path, [args]), ...] for every powershell hook in hooks.json.

    The args come out of the registered command too, so a hook whose guard
    only works when it is called without its parameters cannot pass here.
    """
    data = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))
    found = {}
    for entries in data.get("hooks", {}).values():
        for entry in entries:
            for hook in entry.get("hooks", []):
                if hook.get("shell") != "powershell":
                    continue
                cmd = hook.get("command", "")
                m = re.search(r'"\$\{CLAUDE_PLUGIN_ROOT\}/(.+?\.ps1)"(.*)', cmd)
                if not m:
                    raise SystemExit(
                        f"cannot parse a powershell hook command in {HOOKS_JSON}: {cmd!r}"
                    )
                path = PLUGIN / m.group(1)
                tail = m.group(2).split(";")[0].strip()
                args = _split_args(tail)
                found.setdefault(path, args)
    return sorted(found.items())


def _split_args(tail):
    out, buf, quote = [], "", None
    for ch in tail:
        if quote:
            if ch == quote:
                out.append(buf)
                buf, quote = "", None
            else:
                buf += ch
        elif ch in "'\"":
            quote = ch
        elif ch.isspace():
            if buf:
                out.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        out.append(buf)
    return out


# --------------------------------------------------------------------------
# pwsh plumbing
# --------------------------------------------------------------------------
PWSH = shutil.which("pwsh") or shutil.which("powershell")


def pwsh(command, env=None, cwd=None, stdin=""):
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command", command],
        input=stdin, capture_output=True, text=True, env=env, cwd=cwd, timeout=120,
    )
    return proc


def first_statements():
    """{path: {"line": n, "text": "...", "parse_errors": [...]}} via PowerShell's parser.

    Uses the AST rather than a grep so "the guard is the FIRST executable
    statement" is a real assertion: a guard placed after a Set-Location reads
    identically to grep and is useless.
    """
    paths = [str(p) for p, _ in registered_powershell_hooks()]
    # The paths are embedded as a PowerShell array literal rather than passed
    # as arguments: `pwsh -Command <script> -- a b c` does not bind $args, it
    # parses `--` as a unary operator and dies.
    literal = "@(" + ",".join("'" + s.replace("'", "''") + "'" for s in paths) + ")"
    script = r"""
$out = @{}
foreach ($p in __PATHS__) {
  $errs = $null
  $ast = [System.Management.Automation.Language.Parser]::ParseFile($p, [ref]$null, [ref]$errs)
  $row = @{ parse_errors = @($errs | ForEach-Object { $_.ToString() }) }
  $st = $ast.EndBlock.Statements
  if ($st.Count -gt 0) {
    $row['line'] = $st[0].Extent.StartLineNumber
    $row['text'] = ($st[0].Extent.Text -split "`n")[0].Trim()
  } else {
    $row['line'] = 0
    $row['text'] = ''
  }
  $out[$p] = $row
}
$out | ConvertTo-Json -Depth 6 -Compress
"""
    proc = subprocess.run(
        [PWSH, "-NoProfile", "-NonInteractive", "-Command",
         script.replace("__PATHS__", literal)],
        capture_output=True, text=True, timeout=180,
    )
    if proc.returncode != 0:
        raise SystemExit(f"AST probe failed:\n{proc.stdout}\n{proc.stderr}")
    return json.loads(proc.stdout)


def traced_lines(stream):
    """Every source line number Set-PSDebug -Trace 1 reported as executed."""
    lines = []
    for raw in ANSI.sub("", stream).splitlines():
        m = DEBUG_ROW.match(raw.strip())
        if m:
            lines.append(int(m.group(1)))
    return lines


def non_debug(stream):
    """Whatever the script itself wrote, with the trace rows removed."""
    kept = []
    for raw in ANSI.sub("", stream).splitlines():
        if DEBUG_ROW.match(raw.strip()):
            continue
        if raw.strip():
            kept.append(raw)
    return "\n".join(kept)


# --------------------------------------------------------------------------
# The throwaway fixture
# --------------------------------------------------------------------------
SHIM_NAMES = ("python3", "python", "py", "git", "curl")

STDIN_PAYLOAD = json.dumps({
    "session_id": "flavour-guard-test",
    "source": "clear",
    "trigger": "manual",
    "stop_hook_active": False,
    "tool_name": "Bash",
    "agent_type": "crew:developer",
    "tool_input": {"command": "deploy-to-prod", "file_path": "note.md"},
})


def build_fixture(root):
    root = pathlib.Path(root)
    crew = root / "repo" / ".crew"
    crew.mkdir(parents=True)
    (crew / "config.json").write_text(json.dumps({
        "context": {"enabled": True, "warnAt": 0.5, "keepTranscripts": 5},
        "notify": {"provider": "none", "events": "waiting"},
        "guards": {"roleWrites": "off"},
    }), encoding="utf-8")
    (crew / "verify.json").write_text(json.dumps({
        "environments": {"prod": {"deploy": "deploy-to-prod"}},
    }), encoding="utf-8")
    # The two markers handoff-read.ps1 deletes on its second and third lines.
    # They are the sharpest evidence available that a stood-down hook did
    # nothing: a guard one line too low removes them and still exits 0.
    (crew / ".handoff-requested").write_text("marker\n", encoding="utf-8")
    (crew / ".autoclear-sent").write_text("marker\n", encoding="utf-8")

    home = root / "home"
    (home / ".claude" / "obsidian").mkdir(parents=True)
    (home / ".claude" / "crew").mkdir(parents=True)

    shims = root / "bin"
    shims.mkdir()
    calls = root / "calls"
    calls.mkdir()
    for name in SHIM_NAMES:
        p = shims / name
        p.write_text(
            "#!/usr/bin/env bash\n"
            f'printf "%s\\n" "$*" >> "{calls}/{name}.called"\n'
            "exit 0\n",
            encoding="utf-8", newline="\n",
        )
        p.chmod(0o755)
    return root / "repo", home, shims, calls


def snapshot(path):
    out = {}
    for dirpath, dirnames, filenames in os.walk(path):
        for name in dirnames:
            full = pathlib.Path(dirpath) / name
            out[str(full.relative_to(path))] = "dir"
        for name in filenames:
            full = pathlib.Path(dirpath) / name
            st = full.stat()
            out[str(full.relative_to(path))] = (st.st_size, st.st_mtime_ns)
    return out


def run_hook(script, args, os_value, drop_iswindows, fixture):
    repo, home, shims, calls = fixture
    env = dict(os.environ)
    env["PATH"] = f"{shims}{os.pathsep}{env.get('PATH', '')}"
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["CLAUDE_PROJECT_DIR"] = str(repo)
    env.pop("OS", None)
    if os_value is not None:
        env["OS"] = os_value

    prelude = ""
    if drop_iswindows:
        # The only way to reach PowerShell 5.1's condition from pwsh 7: 5.1
        # has no $IsWindows at all, and a session it has been removed from is
        # indistinguishable to the guard expression. The bare `-not
        # $IsWindows` form stands down here; the $env:OS form must not.
        prelude = "Remove-Variable IsWindows -Force -Scope Global -ErrorAction SilentlyContinue; "

    quoted = " ".join(f"'{a}'" for a in args)
    cmd = (f"{prelude}Set-PSDebug -Trace 1; & '{script}' {quoted}; "
           "Set-PSDebug -Off; exit $LASTEXITCODE")
    return pwsh(cmd, env=env, cwd=str(repo), stdin=STDIN_PAYLOAD)


# --------------------------------------------------------------------------
def main():
    if PWSH is None:
        print("SKIP: no pwsh/powershell on PATH - the guard can only be "
              "checked statically, and this suite refuses to report a static "
              "pass as a behavioural one.")
        return 77
    if not HOOKS_JSON.exists():
        print(f"FATAL: {HOOKS_JSON} not found", file=sys.stderr)
        return 1

    hooks = registered_powershell_hooks()
    print(f"== {len(hooks)} powershell hook(s) registered by {HOOKS_JSON.relative_to(PLUGIN)} ==")
    if not hooks:
        print("FATAL: hooks.json registers no powershell hooks; this suite "
              "would pass vacuously.", file=sys.stderr)
        return 1

    # --- case 1: static, via the parser ------------------------------------
    print("\n-- case 1: the guard is the first executable statement --")
    asts = first_statements()
    guard_line = {}
    for path, _ in hooks:
        row = asts.get(str(path), {})
        check(not row.get("parse_errors"), f"{path.name} parses",
              "\n".join(row.get("parse_errors", [])))
        text = row.get("text", "")
        ok = text == GUARD_TEXT
        check(ok, f"{path.name}: first executable statement is the flavour guard",
              f"got line {row.get('line')}: {text!r}\nwant: {GUARD_TEXT!r}")
        # The LINE comes from the AST whatever the guard says, so the
        # behavioural cases below still run against a WRONG guard. That is
        # the point of the sabotage test: revert one file to the bare
        # `$IsWindows` form and case 3 must go red because the hook stood
        # down, not because case 1 already refused to exercise it.
        guard_line[path] = row.get("line") or None
        body = path.read_text(encoding="utf-8")
        check(body.count(GUARD_TEXT) == 1,
              f"{path.name}: exactly one guard", f"count={body.count(GUARD_TEXT)}")
        # Code lines only. The guard's own comment block QUOTES the bare
        # form as the thing not to write, and a check that cannot tell an
        # example from the real thing reports every correct file as broken.
        bare = [n for n, line in enumerate(body.splitlines(), 1)
                if not line.lstrip().startswith("#") and "-not $IsWindows" in line]
        check(not bare, f"{path.name}: no bare $IsWindows test in code",
              f"the bare form is the bug this guard replaces; found at line(s) {bare}")

    # --- cases 2-4: behaviour ----------------------------------------------
    for label, os_value, drop in (
        ("case 2: OS=Windows_NT proceeds past the guard", "Windows_NT", False),
        ("case 3: PowerShell 5.1 ($IsWindows ABSENT, OS=Windows_NT) proceeds",
         "Windows_NT", True),
        ("case 4: OS unset stands down and touches nothing", None, False),
    ):
        print(f"\n-- {label} --")
        for path, args in hooks:
            gline = guard_line.get(path)
            if gline is None:
                check(False, f"{path.name}: has no first statement to exercise")
                continue
            with tempfile.TemporaryDirectory(prefix="flavour-guard-") as tmp:
                fixture = build_fixture(tmp)
                repo, _home, _shims, calls = fixture
                before = snapshot(repo)
                proc = run_hook(path, args, os_value, drop, fixture)
                after = snapshot(repo)
                past = [n for n in traced_lines(proc.stderr + proc.stdout) if n > gline]
                called = sorted(p.name for p in calls.iterdir())

                if os_value is None:
                    check(proc.returncode == 0,
                          f"{path.name}: stands down with exit 0",
                          f"rc={proc.returncode}\n{non_debug(proc.stderr)}")
                    check(not past,
                          f"{path.name}: executed NOTHING past line {gline}",
                          f"traced lines past the guard: {past}")
                    check(before == after,
                          f"{path.name}: the .crew/ tree is byte-identical afterwards",
                          _diff(before, after))
                    check(non_debug(proc.stdout) == "",
                          f"{path.name}: wrote no stdout",
                          non_debug(proc.stdout))
                    check(non_debug(proc.stderr) == "",
                          f"{path.name}: wrote no stderr",
                          non_debug(proc.stderr))
                    check(called == [],
                          f"{path.name}: invoked no interpreter or tool",
                          f"called: {called}")
                else:
                    check(bool(past),
                          f"{path.name}: reached a statement past line {gline}",
                          "nothing past the guard executed. Trace:\n"
                          + "\n".join(ANSI.sub("", proc.stderr + proc.stdout)
                                      .splitlines()[:20]))

    # --- the blocking hooks still block ------------------------------------
    # CLAUDE.md: a hook that can BLOCK needs must-block and must-allow cases.
    # For THIS change those are: under Windows the block is still reached, and
    # off Windows the hook stands down rather than blocking. The second half is
    # case 4 above (exit 0 for every script). This is the first half, for the
    # one blocker whose block is reachable without a real interpreter:
    # promote-gate refuses a deploy it cannot attribute to a commit.
    blockers = [(p, a) for p, a in hooks if p.name == "promote-gate.ps1"]
    if blockers:
        print("\n-- must-block: a blocker still blocks under OS=Windows_NT --")
        for path, args in blockers:
            with tempfile.TemporaryDirectory(prefix="flavour-guard-") as tmp:
                fixture = build_fixture(tmp)
                proc = run_hook(path, args, "Windows_NT", False, fixture)
                check(proc.returncode == 2,
                      f"{path.name}: blocks a gated deploy (exit 2)",
                      f"rc={proc.returncode}\n{non_debug(proc.stderr)}")
                check("PROMOTION BLOCKED" in non_debug(proc.stderr),
                      f"{path.name}: says why it blocked",
                      non_debug(proc.stderr))
            with tempfile.TemporaryDirectory(prefix="flavour-guard-") as tmp:
                fixture = build_fixture(tmp)
                proc = run_hook(path, args, None, False, fixture)
                check(proc.returncode == 0,
                      f"{path.name}: the SAME deploy is not blocked off Windows "
                      "(the bash flavour owns it there)",
                      f"rc={proc.returncode}\n{non_debug(proc.stderr)}")

    print(f"\nRESULT: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


def _diff(before, after):
    out = []
    for k in sorted(set(before) | set(after)):
        if before.get(k) != after.get(k):
            out.append(f"{k}: {before.get(k)!r} -> {after.get(k)!r}")
    return "\n".join(out)


if __name__ == "__main__":
    sys.exit(main())
