#!/usr/bin/env python3
"""Suite for scripts/run-plugin-evals.{sh,ps1} (L-0713).

The runners discover their cases from `<plugin>/evals/*/case.yaml`. Every case
here builds a throwaway plugin directory in a temp dir and puts a stub `claude`
first on PATH, so no real model call is ever made and nothing in this
repository is read as a case. The stub records its argv and writes the result
JSON the case asks it to.

Must-allow: an empty evals/ prints "no eval cases", exits 0 and never calls
`claude`; one case with a scored result exits 0, called once with
`--case <name>` (and `--scaffold` when case.yaml names a scaffold_script).
Must-block: a non-zero exit, and an exit-0 run with no scored result, each
exit 1.

The .ps1 runs only where pwsh resolves; when it does not, the suite says so
rather than counting it as passed.

Run: python3 scripts/_test/plugin-evals-runner.py
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.dirname(HERE)
SH = os.path.join(SCRIPTS, "run-plugin-evals.sh")
PS1 = os.path.join(SCRIPTS, "run-plugin-evals.ps1")

SCORED = {"cases": [{"name": "x", "aggregates": {"score": 1.0, "delta": 0.5},
                     "arms": {"with": [{"costUsd": 0.01}], "without": []}}]}

STUB = '''#!/usr/bin/env python3
import json, os, sys
argv = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")
mode = os.environ.get("STUB_MODE", "scored")
if "--json" in argv and mode != "nothing":
    with open(argv[argv.index("--json") + 1], "w", encoding="utf-8") as fh:
        json.dump(json.loads(os.environ["STUB_RESULT"]) if mode == "scored" else {"cases": []}, fh)
sys.exit(int(os.environ.get("STUB_EXIT", "0")))
'''


def pwsh_path() -> str | None:
    for candidate in (shutil.which("pwsh"), "/snap/bin/pwsh", "/usr/bin/pwsh",
                      "/opt/microsoft/powershell/7/pwsh",
                      r"C:\Program Files\PowerShell\7\pwsh.exe"):
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def make_plugin(tmp: str, cases: dict[str, str]) -> str:
    plugin = os.path.join(tmp, "plugin")
    os.makedirs(os.path.join(plugin, "evals"))
    for name, case_yaml in cases.items():
        os.makedirs(os.path.join(plugin, "evals", name))
        with open(os.path.join(plugin, "evals", name, "case.yaml"), "w",
                  encoding="utf-8", newline="\n") as fh:
            fh.write(case_yaml)
    return plugin


def run(runner: str, tmp: str, plugin: str, **stub) -> tuple[int, str, list[list[str]]]:
    bindir = os.path.join(tmp, "bin")
    os.makedirs(bindir, exist_ok=True)
    claude = os.path.join(bindir, "claude")
    with open(claude, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(STUB.replace("python3", sys.executable, 1) if os.name != "nt" else STUB)
    os.chmod(claude, os.stat(claude).st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    log = os.path.join(tmp, "calls.jsonl")
    env = dict(os.environ, PATH=bindir + os.pathsep + os.environ.get("PATH", ""),
               EVAL_PLUGIN_DIR=plugin, EVAL_OUTPUT_DIR=os.path.join(tmp, "out"),
               STUB_LOG=log, STUB_RESULT=json.dumps(SCORED),
               **{k: str(v) for k, v in stub.items()})
    argv = (["bash", SH] if runner == "sh"
            else [pwsh_path(), "-NoProfile", "-NonInteractive", "-File", PS1])
    done = subprocess.run(argv, capture_output=True, text=True, env=env, check=False)
    calls = []
    if os.path.exists(log):
        with open(log, encoding="utf-8") as fh:
            calls = [json.loads(line) for line in fh if line.strip()]
    return done.returncode, done.stdout + done.stderr, calls


def case_empty(runner, tmp):
    code, out, calls = run(runner, tmp, make_plugin(tmp, {}))
    return code == 0 and "no eval cases" in out and not calls, (code, out, calls)


def case_scored_scaffold(runner, tmp):
    plugin = make_plugin(tmp, {"b-plain": "name: b-plain\n",
                               "a-scaffold": "name: a\ncontext:\n  scaffold_script: fixture.sh\n"})
    code, out, calls = run(runner, tmp, plugin)
    ok = (code == 0 and len(calls) == 2
          and calls[0][:4] == ["plugin", "eval", plugin, "--case"] and calls[0][4] == "a-scaffold"
          and "--scaffold" in calls[0] and calls[1][4] == "b-plain" and "--scaffold" not in calls[1]
          and all(c[-3:] == ["--allow-tools", "Write", "Edit"] for c in calls))
    return ok, (code, out, calls)


def case_nonzero_exit(runner, tmp):
    code, out, calls = run(runner, tmp, make_plugin(tmp, {"a": "name: a\n"}), STUB_EXIT=1)
    return code == 1 and len(calls) == 1, (code, out, calls)


def case_no_scored_result(runner, tmp):
    code, out, calls = run(runner, tmp, make_plugin(tmp, {"a": "name: a\n"}), STUB_MODE="empty")
    return code == 1 and "no scored result" in out, (code, out, calls)


CASES = (
    ("must-allow: empty evals/ says no eval cases, exit 0, claude never called", case_empty),
    ("must-allow: each discovered case runs once, scaffold only where named", case_scored_scaffold),
    ("must-block: a non-zero claude exit fails the run", case_nonzero_exit),
    ("must-block: exit 0 with no scored result fails the run", case_no_scored_result),
)


def main() -> int:
    passed = failed = 0
    runners = ["sh"]
    if pwsh_path():
        runners.append("ps1")
    else:
        print("  NOT RUN  run-plugin-evals.ps1 - pwsh does not resolve here; not a pass")
    for runner in runners:
        for name, case in CASES:
            with tempfile.TemporaryDirectory() as tmp:
                ok, detail = case(runner, tmp)
            if ok:
                passed += 1
                print(f"  ok   [{runner}] {name}")
            else:
                failed += 1
                print(f"  FAIL [{runner}] {name}\n       got {detail}")
    print(f"\nplugin-evals-runner: {passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
