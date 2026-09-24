#!/usr/bin/env python3
"""The interpreter probe in all six wrappers proves Python 3, is bounded, and
kills the whole process tree when it times out.

    python3 hooks/scripts/_test/test_python_probe_proof.py

crew 1.0 Windows burn-in, Codex round 1 (FAIL 3):

* vault-guard.ps1:118 -- the resolver returned whatever path followed the
  token, without checking Python >= 3 or that sys.executable exists. A Python
  2 on PATH, or a fake that prints `vault-guard-python:C:\\missing.exe` and
  exits 0, was accepted. bridge-status and vault-capture, and the three .sh
  twins, shared it.
* vault-guard.sh:88 -- the bash every-match probes were unbounded, so a
  hanging PATH candidate stalled the hook forever.
* crew role-write-guard.ps1:66, which these copy -- the 3s timeout killed only
  the candidate, so a launcher's child holding the redirected handles lived on.

Each wrapper's resolver is lifted out of the tracked file (never edited in
place) and run against a PATH built for the case. Each case states what BOTH
flavours conclude. Needs bash; the .ps1 half needs pwsh and says so when it
cannot run. Exit 0 all passed, 1 a failure.
"""
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time

HERE = pathlib.Path(__file__).resolve().parent
SCRIPTS = HERE.parent
REAL = os.path.realpath(sys.executable)
BASH = shutil.which("bash")
PWSH = shutil.which("pwsh") or next((p for p in ("/snap/bin/pwsh", "/usr/bin/pwsh",
                                                  "/opt/microsoft/powershell/7/pwsh")
                                     if os.path.exists(p)), None)
HOOKS = ("vault-guard", "bridge-status", "vault-capture")
FAILURES = []
SKIPS = []


def check(desc, got, want):
    if got != want:
        FAILURES.append(f"{desc}: got {got!r}, want {want!r}")


def _body(src, header):
    start = src.index(header)
    return src[start:src.index("\n}\n", start) + 3]


def _camel(stem):
    return "".join(part.capitalize() for part in stem.split("-"))


def bash_resolve(stem, path):
    """(resolved, rejected) from `<stem>.sh`'s own resolver on `path`."""
    u = stem.replace("-", "_")
    src = (SCRIPTS / f"{stem}.sh").read_text(encoding="utf-8")
    driver = (_body(src, f"_{u}_reject() {{") + _body(src, f"_{u}_resolve_python() {{")
              + f'_{u}_resolve_python\nprintf "PY=%s\\nREJ=%s\\n" "${u.upper()}_PY" '
                f'"${u.upper()}_REJECTED"\n')
    done = subprocess.run([BASH, "-c", driver], env=dict(os.environ, PATH=path),
                          stdin=subprocess.DEVNULL, capture_output=True, text=True,
                          check=False, timeout=60)
    return _parse(done.stdout)


def ps1_resolve(stem, path):
    camel = _camel(stem)
    src = (SCRIPTS / f"{stem}.ps1").read_text(encoding="utf-8")
    driver = (f"$script:{camel}Rejected = @()\n" + _body(src, f"function Resolve-{camel}Python {{")
              + f"$r = Resolve-{camel}Python\nWrite-Output \"PY=$r\"\n"
              + f"Write-Output (\"REJ=\" + ($script:{camel}Rejected -join '; '))\n")
    with tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8") as handle:
        handle.write(driver)
    try:
        done = subprocess.run([PWSH, "-NoProfile", "-NonInteractive", "-File", handle.name],
                              env=dict(os.environ, PATH=path, OS="Windows_NT"),
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              check=False, timeout=120)
    finally:
        os.unlink(handle.name)
    return _parse(done.stdout)


def _parse(out):
    fields = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)
    return fields.get("PY", ""), fields.get("REJ", "")


def stub(directory, name, body):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="ascii", newline="\n")
    path.chmod(0o755)
    return directory


def tools(base):
    """/usr/bin and /bin minus python*/py*, so nothing rescues a case."""
    out = base / "tools"
    out.mkdir()
    for source in ("/usr/bin", "/bin"):
        if not os.path.isdir(source):
            continue
        for name in os.listdir(source):
            if name.startswith(("python", "py")) or (out / name).exists():
                continue
            os.symlink(os.path.join(source, name), out / name)
    return out


def answer(stem, major, minor, impl, exe):
    return f"printf '%s' '{stem}-python:{major}:{minor}:{impl}:{exe}'"


def survivors(token):
    found = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            argv = pathlib.Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if token.encode() in argv:
            found.append(int(pid))
    for pid in found:
        try:
            os.kill(pid, 9)
        except OSError:
            pass
    return found


def flavours():
    yield "sh", bash_resolve
    if PWSH:
        yield "ps1", ps1_resolve


def run():
    if not BASH:
        print("SKIP: no bash - nothing here was run")
        return
    if not PWSH:
        SKIPS.append("no pwsh - the .ps1 half was NOT run")
    base = pathlib.Path(tempfile.mkdtemp())
    try:
        tool_dir = tools(base)
        real = stub(base / "real", "python3", f'exec "{REAL}" "$@"')
        for stem in HOOKS:
            rejects = {
                "a liar that prints its own path": 'echo "$0"',
                "Python 2 answering the token": answer(stem, 2, 7, "cpython", REAL),
                "Python 3.7": answer(stem, 3, 7, "cpython", REAL),
                "an unknown implementation": answer(stem, 3, 12, "jython", REAL),
                "a sys.executable that does not exist": answer(stem, 3, 12, "cpython",
                                                               base / "missing.exe"),
                "the token with no version fields": f"printf '%s' '{stem}-python:{REAL}'",
            }
            for flavour, resolve in flavours():
                got, _ = resolve(stem, os.pathsep.join([str(real), str(tool_dir)]))
                check(f"{stem}.{flavour}: a real Python 3 is accepted", got, REAL)
                for index, (desc, body) in enumerate(rejects.items()):
                    fake = stub(base / f"{stem}-{flavour}-{index}", "python3", body)
                    got, rejected = resolve(stem, os.pathsep.join([str(fake), str(tool_dir)]))
                    check(f"{stem}.{flavour}: {desc} is rejected", (got, bool(rejected)), ("", True))

                hang = stub(base / f"{stem}-{flavour}-hang", "python3", "exec sleep 120")
                began = time.monotonic()
                got, _ = resolve(stem, os.pathsep.join([str(hang), str(real), str(tool_dir)]))
                check(f"{stem}.{flavour}: a hung candidate is bounded and the next one wins",
                      (got, time.monotonic() - began < 30), (REAL, True))

                if os.path.isdir("/proc"):
                    token = f"obsidian-probe-child-{stem}-{flavour}-{os.getpid()}"
                    launcher = stub(base / f"{stem}-{flavour}-launcher", "python3",
                                    f'"{REAL}" -c "import time; time.sleep(120)" {token} &\nwait')
                    got, _ = resolve(stem, os.pathsep.join([str(launcher), str(real),
                                                            str(tool_dir)]))
                    time.sleep(0.5)
                    check(f"{stem}.{flavour}: the timeout kills the launcher's child too",
                          (got, survivors(token)), (REAL, []))

                # FIX (Codex review of crew-1.0, item 2): the overall 8s
                # deadline used to be checked only BEFORE launching a
                # candidate, then waited a flat 3s regardless of budget
                # left. Four candidates that each fail after 1.8s (7.2s
                # total, comfortably under the deadline) followed by one
                # that hangs must still finish under the 10s hook timeout
                # that calls this -- the final wait has to be capped to
                # whatever remains, not a flat 3s. (Measured against the
                # unfixed shape: this exact fixture took 10.2s+ there and
                # 7.2s here -- tighter margins, like three candidates at
                # 2.5s, land close enough to the 8s boundary that bash's
                # own per-candidate overhead can tip the deadline check
                # before the final candidate is even launched, silently
                # passing either way.)
                slow_dirs = []
                for i in range(4):
                    slow_dirs.append(stub(base / f"{stem}-{flavour}-slow{i}",
                                          "python3", "sleep 1.8\nexit 1"))
                near_hang = stub(base / f"{stem}-{flavour}-near-deadline-hang",
                                 "python3", "exec sleep 60")
                began = time.monotonic()
                got, _ = resolve(stem, os.pathsep.join(
                    [str(d) for d in slow_dirs] + [str(near_hang), str(tool_dir)]))
                check(f"{stem}.{flavour}: near-deadline candidates then a hang "
                      "stay within the hook timeout",
                      (got, time.monotonic() - began < 10), ("", True))
    finally:
        shutil.rmtree(base, ignore_errors=True)


# --- FIX (Codex review of crew-1.0, item 1): the "memoized within this
#     process" caching an earlier version carried in each `.sh` resolver
#     never had a second call to save -- each of these three hooks calls
#     its resolver exactly once per process (`if ! _..._resolve_python`),
#     unlike crew's copies, which are additionally broken by their `$(...)`
#     call sites. Kept as inert weight either way; removed rather than left
#     in as a claimed optimisation that never fires.

def check_no_dead_memo():
    for stem in HOOKS:
        u = stem.replace("-", "_")
        src = (SCRIPTS / f"{stem}.sh").read_text(encoding="utf-8")
        body = _body(src, f"_{u}_resolve_python() {{")
        if "MEMO" in body:
            FAILURES.append(
                f"{stem}.sh still carries a memoization for its resolver "
                "that never has a second call to save")


# --- FIX (Codex review of crew-1.0, item 3): a python exposed only via a
#     .cmd/.bat shim (a pyenv-win install is exactly this shape) cannot be
#     launched with UseShellExecute=false -- CreateProcess only starts a
#     real PE executable, not a shell shim. crew's role-write-guard.ps1 (and
#     its ten sibling carriers) were already fixed to route a .cmd/.bat
#     candidate through `cmd.exe /d /c` in commit a39ac347; these three
#     obsidian-vault resolvers were not. Ported the same routing here.
#     STATIC, not behavioural: launching a real .cmd shim through
#     ProcessStartInfo is Windows-only, so there is nothing this sandbox can
#     execute end to end -- the fix is provably present or absent in the
#     source either way, which is what this checks.

def check_cmd_bat_routing_present():
    for stem in HOOKS:
        camel = _camel(stem)
        src = (SCRIPTS / f"{stem}.ps1").read_text(encoding="utf-8")
        body = _body(src, f"function Resolve-{camel}Python {{")
        if r"-match '\.(cmd|bat)$'" not in body or "System32\\cmd.exe" not in body:
            FAILURES.append(
                f"{stem}.ps1's Resolve-{camel}Python does not route a "
                ".cmd/.bat candidate through cmd.exe -- a python exposed "
                "only via a shim (pyenv-win) cannot be launched with "
                "UseShellExecute=false")


run()
check_no_dead_memo()
check_cmd_bat_routing_present()
for skip in SKIPS:
    print("SKIP:", skip)
print(f"RESULT: {len(FAILURES)} failed")
for failure in FAILURES:
    print("FAIL:", failure)
sys.exit(1 if FAILURES else 0)
