"""The environment-dump guard (L-0772): must-block, must-allow, could-not-tell.

CLAUDE.md requires a hook that can block to carry a committed regression suite
with must-block and must-allow cases, sabotage-tested. This is that suite for
`hooks/scripts/env_guard.py` and its two wrappers.

Three drivers:

    python   `env_guard.main()` in-process for every case (fast), and
             `python3 env_guard.py` as a subprocess for a parity sample
    bash     `bash env-guard.sh`, a parity sample
    pwsh     `pwsh -File env-guard.ps1` with `OS=Windows_NT` so its flavour
             guard lets it run; a parity sample. Skipped, with the reason,
             where no pwsh exists.

SAFETY. Nothing here runs a command the guard judges: every case is a
synthetic hook-input JSON handed to the guard on stdin. Every subprocess gets
a SCRUBBED environment built from an allowlist (`_scrubbed_env`), never a
copy of the real one, plus one fake marker variable (`FAKE_TOKEN`), and
`test_no_value_reaches_output_or_log` asserts the marker's value appears in
no stdout, stderr or `guard.log`. Variable names in the cases are synthetic
or well-known non-secret ones.
"""
import io
import json
import os
import shlex
import subprocess
import sys
import time

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_config
import crew_fixtures
import crew_state

import env_guard  # noqa: E402  pylint: disable=wrong-import-position

_ROOT = context._ROOT  # pylint: disable=protected-access
_SCRIPTS = os.path.join(_ROOT, "hooks", "scripts")
_PY = os.path.join(_SCRIPTS, "env_guard.py")
_SH = os.path.join(_SCRIPTS, "env-guard.sh")
_PS1 = os.path.join(_SCRIPTS, "env-guard.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = crew_fixtures.resolve_pwsh()
needs_bash = pytest.mark.skipif(_BASH is None, reason="no MSYS/POSIX bash")
needs_pwsh = pytest.mark.skipif(
    _PWSH is None,
    reason="pwsh is not installed here, so env-guard.ps1 cannot be run; its "
           "cases are written and skipped, not passed")

MARKER = "xxxx-marker"
ARMED = {"guards": {"envGuard": "block"}}
REPORT = {"guards": {"envGuard": "report"}}


# --- the cases ------------------------------------------------------------------

# Bash forms that print the whole environment, or a credential-named variable.
BLOCK_BASH = [
    "env", "env -0", "env --null", "env -u FAKE_X", "env FAKE_A=1",
    "printenv", "printenv -0", "set", "export", "export -p",
    "declare", "declare -p", "declare -x", "typeset -p", "typeset -x",
    "readonly", "readonly -p",
    "systemctl show-environment", "tmux show-environment", "ps e", "ps eww",
    "ps auxe",
    "cat /proc/1/environ", "cat /proc/self/environ", "xxd /proc/$$/environ",
    "tr '\\0' '\\n' < /proc/self/environ", "cat /proc/*/env*",
    "strings /proc/self/e?viron", "cat /proc/1/task/1/environ",
    "echo $(< /proc/self/environ)",
    "python3 -c 'import os; print(os.environ)'",
    "python -c 'print(dict(os.environ))'",
    "node -e 'console.log(process.env)'",
    "deno eval 'console.log(Deno.env.toObject())'",
    "perl -e 'print %ENV'", "perl -le 'print for keys %ENV'",
    "ruby -e 'p ENV'", "php -r 'print_r(getenv());'", "php -r 'print_r($_ENV);'",
    "awk 'BEGIN{for (k in ENVIRON) print k}'", "jq -n env", "jq -n '$ENV'",
    "\"$PY\" -c 'import os; print(os.environ)'",
    "printenv FAKE_GITHUB_TOKEN", "echo \"$FAKE_SECRET_ACCESS_KEY\"",
    "printf %s \"${FAKE_API_KEY:0:4}\"", "declare -p FAKE_TOKEN",
    "python3 -c 'import os; print(os.environ[\"FAKE_TOKEN\"])'",
    "echo \"$FAKE_GITHUB_TOKEN\" | gh auth login --with-token",
    "cmd /c set", "cmd.exe /c set P", "cmd /c echo %FAKE_API_KEY%",
    "alias x='env'", "f() { env; }", "`env`", "cat <(env)",
    "bash <<'EOF'\nenv\nEOF",
    "python3 - <<'EOF'\nimport os\nprint(os.environ)\nEOF",
    "ssh host env", "docker exec box env", "podman exec box printenv",
    "kubectl exec pod -- env", "wsl env", "find . -exec printenv \\;",
    "xargs printenv", "watch env", "timeout 5 env", "nice -n 5 env",
    "nohup env", "stdbuf -oL env", "setsid env", "command env", "exec env",
    "builtin set", "doas env", "time env", "pwsh -c 'Get-ChildItem env:'",
]

# The wrappers check 1 asks for, applied to every Bash form above.
WRAPS = {
    "bash-c": lambda c: "bash -c " + shlex.quote(c),
    "eval": lambda c: "eval " + shlex.quote(c),
    "pipe": lambda c: c + " | grep X" if "\n" not in c else c,
    "for": lambda c: "for i in 1; do " + c + "; done" if "\n" not in c else c,
    "subst": lambda c: "x=$(" + c + ")" if "\n" not in c else c,
    "sudo": lambda c: "sudo " + c,
}

BLOCK_PS = [
    "Get-ChildItem env:", "gci env:", "dir env:", "ls env:", "Get-Item env:*",
    "gci -Path Env:\\", "Get-ChildItem -LiteralPath 'env:'", "Set-Location env:",
    "Get-ChildItem Environment::", "gci -Path:env:",
    "[Environment]::GetEnvironmentVariables()",
    "[System.Environment]::GetEnvironmentVariables('Machine')",
    "(Get-Process)[0].StartInfo.EnvironmentVariables",
    "Get-Variable", "gv", "Get-ChildItem variable:",
    "cmd /c set", "cmd /c echo %FAKE_GITHUB_TOKEN%",
    "$env:FAKE_GITHUB_TOKEN", "${env:FAKE_GITHUB_TOKEN}",
    "Write-Output $env:FAKE_API_KEY", "Write-Host \"t=$env:FAKE_API_KEY\"",
    "$env:FAKE_GITHUB_TOKEN | docker login --password-stdin",
    "Get-Item env:FAKE_GITHUB_TOKEN", "Get-Content env:FAKE_API_KEY",
    "[Environment]::GetEnvironmentVariable('FAKE_API_KEY')",
    "Invoke-Expression 'gci env:'", "& { gci env: }", "pwsh -c 'gci env:'",
    "bash -c env", "cat /proc/self/environ", "env",
]

ALLOW_BASH = [
    "echo $HOME", "printenv PATH", "printenv HOME USER", "env FOO=bar cmd",
    "env -u NAME cmd", "env -i", "env -i FOO=bar", "env -i PATH=/bin cmd",
    "set -euo pipefail", "set -x", "set +e", "set -o", "set -- a b",
    "export FOO=bar", "export FOO", "declare -a arr=()", "declare -A m",
    "declare -f", "ps aux", "ps -ef", "ps -o user,pid", "cat /proc/cpuinfo",
    "cat /proc/self/status", "git commit -m \"fix env handling\"",
    "grep -r printenv docs/",
    "python -c 'import os; print(os.environ[\"HOME\"])'",
    "curl -H \"Authorization: Bearer $FAKE_GITHUB_TOKEN\" https://x",
    "\"$PY\" -c 'print(1)'", "git commit -m \"read /proc/self/environ\"",
    "grep -rn /proc/self/environ docs/", "echo $GIT_AUTHOR_NAME",
    "gh auth login --with-token < file",
    "docker login --password-stdin <<< \"$FAKE_PW\"",
    "compgen -v", "compgen -e", "awk -F: '{print $1}' /etc/passwd",
    "jq '.env' f.json", "command -v env", "ls -la | head -n 2 2>&1",
    "cd /x && make test", "git log --oneline -5", "echo \"$(date)\"",
    "python3 x.py", "[[ -n $X ]] && echo ok",
    "cat > f <<EOF\nhello $HOME\nEOF", "case $x in a) echo a;; esac",
    "node -e 'console.log(process.env.HOME)'",
    "ruby -e 'puts ENV[\"HOME\"]'", "$EDITOR f", "\"$PY\" script.py",
    "PY=python3; \"$PY\" -c 'print(1)'", "echo $SSH_AUTH_SOCK",
    "echo $XDG_SESSION_TYPE",
]

ALLOW_PS = [
    "$env:PATH", "Remove-Item env:FOO", "$env:FOO = 'x'", "Get-ChildItem C:\\",
    "$t = $env:FAKE_GITHUB_TOKEN", "Write-Output $env:PATH", "Get-Item env:PATH",
    "git commit -m 'fix env: handling'", "Get-Process | Select-Object -First 3",
    "$x = 1; $x", "Set-Item env:FOO 'bar'", "gh pr list",
    "curl -H \"Authorization: Bearer $env:FAKE_GITHUB_TOKEN\" https://x",
    "Get-Variable -Name PSVersionTable",
]

CNT_BASH = [
    "env '", "eval \"$(ssh-agent -s)\"", "eval \"$X\"", "bash -c \"$CMD\"",
    "X=$(echo env); $X", "echo \"${!n}\"", "echo $(env", "cat <<EOF\nno end",
]
CNT_PS = ["iex $s", "& $cmd", "Invoke-Expression $code", "Write-Output 'x",
          "gci env: | Out-String )"]


def _ids(cases):
    return [c.replace("\n", "\\n")[:60] for c in cases]


def _nested(depth):
    command = "env"
    for _ in range(depth):
        command = "bash -c " + shlex.quote(command)
    return command


# --- harness ---------------------------------------------------------------------


def _scrubbed_env(tmp_path, driver=None, extra=None):
    """An ALLOWLIST environment, never a copy of the real one: what the
    interpreters need to start, the fixture's HOME and project dir, and the
    fake marker."""
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"),
           "HOME": str(home), "USERPROFILE": str(home),
           "CLAUDE_PROJECT_DIR": str(tmp_path / "repo"),
           "PYTHONDONTWRITEBYTECODE": "1", "LANG": "C.UTF-8",
           "FAKE_TOKEN": MARKER}
    for key in ("SYSTEMROOT", "SystemRoot", "WINDIR", "TMPDIR", "TEMP", "TMP",
                "XDG_CACHE_HOME", "PATHEXT", "COMSPEC", "MSYSTEM"):
        if key in os.environ:
            env[key] = os.environ[key]
    if driver == "pwsh":
        env["OS"] = "Windows_NT"
    env.update(extra or {})
    return env


def _fixture(tmp_path, repo_cfg=None, global_cfg=None, raw_repo=None):
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True, exist_ok=True)
    if raw_repo is not None:
        (repo / ".crew" / "config.json").write_text(raw_repo, encoding="utf-8")
    elif repo_cfg is not None:
        (repo / ".crew" / "config.json").write_text(json.dumps(repo_cfg),
                                                    encoding="utf-8")
    if global_cfg is not None:
        glob = tmp_path / "home" / ".claude" / "crew"
        glob.mkdir(parents=True, exist_ok=True)
        (glob / "config.json").write_text(json.dumps(global_cfg),
                                          encoding="utf-8")
    return repo


def _log_text(tmp_path):
    path = tmp_path / "repo" / ".crew" / "guard.log"
    return path.read_text(encoding="utf-8") if path.exists() else ""


def _parse(out):
    out = out.strip()
    if not out:
        return "allow", ""
    lines = [ln for ln in out.splitlines() if ln.startswith("{")]
    assert len(lines) == 1, f"want ONE JSON object: {out!r}"
    spec = json.loads(lines[0])["hookSpecificOutput"]
    assert spec["hookEventName"] == "PreToolUse"
    assert spec["permissionDecision"] == "deny", spec
    return "deny", spec["permissionDecisionReason"]


def run_main(monkeypatch, capsys, tmp_path, tool, command, raw=None,
             flavour=None):
    """`env_guard.main()` in-process: (decision, reason)."""
    body = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command},
         "cwd": str(tmp_path / "repo")}).encode("utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path / "repo"))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    if flavour is None:
        monkeypatch.delenv(env_guard.FLAVOUR_VAR, raising=False)
    else:
        monkeypatch.setenv(env_guard.FLAVOUR_VAR, flavour)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(body)))
    capsys.readouterr()
    assert env_guard.main() == 0
    return _parse(capsys.readouterr().out)


def _argv(driver):
    if driver == "python":
        return [sys.executable, _PY]
    if driver == "bash":
        return [_BASH, _SH]
    return [_PWSH, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", _PS1]


def run_hook(driver, tmp_path, tool, command, extra=None, raw=None):
    """One subprocess hook call: (decision, reason, exit code, stdout+stderr)."""
    body = raw if raw is not None else json.dumps(
        {"tool_name": tool, "tool_input": {"command": command},
         "cwd": str(tmp_path / "repo")}).encode("utf-8")
    proc = subprocess.run(_argv(driver), input=body, capture_output=True,
                          env=_scrubbed_env(tmp_path, driver, extra),
                          cwd=str(tmp_path), timeout=180, check=False)
    out = proc.stdout.decode("utf-8", "replace")
    err = proc.stderr.decode("utf-8", "replace")
    decision, reason = _parse(out)
    return decision, reason, proc.returncode, out + err


@pytest.fixture
def global_layer(tmp_path, monkeypatch):
    """Write the in-process machine-global layer (conftest points both
    readers at a per-test path that does not exist)."""
    path = tmp_path / "global-config.json"
    monkeypatch.setattr(crew_config, "GLOBAL_CONFIG_PATH", str(path))
    monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(path))

    def write(cfg):
        path.write_text(json.dumps(cfg), encoding="utf-8")
    return write


def _kind(labels):
    return {label.split(":", 1)[0] for label in labels}


# --- 1-3: the reader, every case ----------------------------------------------------


@pytest.mark.parametrize("command", BLOCK_BASH, ids=_ids(BLOCK_BASH))
def test_must_block_bash_findings(command):
    labels = env_guard.findings(command, "bash")
    assert labels and _kind(labels) & {"env-dump", "secret-read"}, labels


@pytest.mark.parametrize("wrap", sorted(WRAPS))
@pytest.mark.parametrize("command", BLOCK_BASH, ids=_ids(BLOCK_BASH))
def test_must_block_bash_wrapped(command, wrap):
    wrapped = WRAPS[wrap](command)
    labels = env_guard.findings(wrapped, "bash")
    assert labels and _kind(labels) & {"env-dump", "secret-read"}, (wrapped, labels)


@pytest.mark.parametrize("command", BLOCK_PS, ids=_ids(BLOCK_PS))
def test_must_block_powershell_findings(command):
    labels = env_guard.findings(command, "powershell")
    assert labels and _kind(labels) & {"env-dump", "secret-read"}, labels


@pytest.mark.parametrize("command", ALLOW_BASH, ids=_ids(ALLOW_BASH))
def test_must_allow_bash_findings(command):
    assert env_guard.findings(command, "bash") == []


@pytest.mark.parametrize("command", ALLOW_PS, ids=_ids(ALLOW_PS))
def test_must_allow_powershell_findings(command):
    assert env_guard.findings(command, "powershell") == []


@pytest.mark.parametrize("command", CNT_BASH + [_nested(9)],
                         ids=_ids(CNT_BASH) + ["bash-c-nested-9"])
def test_could_not_tell_bash(command):
    assert "could-not-tell" in _kind(env_guard.findings(command, "bash"))


@pytest.mark.parametrize("command", CNT_PS, ids=_ids(CNT_PS))
def test_could_not_tell_powershell(command):
    assert "could-not-tell" in _kind(env_guard.findings(command, "powershell"))


def test_eight_deep_nesting_is_still_judged_not_could_not_tell():
    assert env_guard.findings(_nested(8), "bash") == ["env-dump:env"]


def test_labels_are_fixed_strings_never_names_or_values():
    labels = env_guard.findings("printenv FAKE_GITHUB_TOKEN; echo $FAKE_API_KEY",
                                "bash")
    assert labels == ["secret-read:printenv", "secret-read:echo"]


def test_secret_name_pattern_and_exemptions():
    for name in ("GITHUB_TOKEN", "AWS_SECRET_ACCESS_KEY", "DB_PASSWORD",
                 "FAKE_API_KEY", "FOO_PAT", "OAUTH_X", "SENTRY_DSN",
                 "DATABASE_URL", "SLACK_WEBHOOK", "env:FAKE_TOKEN"):
        assert env_guard.is_secret_name(name), name
    for name in ("HOME", "PATH", "USER", "SSH_AUTH_SOCK", "XAUTHORITY",
                 "GPG_AGENT_INFO", "GIT_AUTHOR_NAME", "GIT_COMMITTER_EMAIL",
                 "XDG_SESSION_TYPE", "DBUS_SESSION_BUS_ADDRESS", ""):
        assert not env_guard.is_secret_name(name), name


def test_module_imports_nothing_from_crew_at_top_level():
    """crew_guards imports env_guard lazily; a crew import at the top here
    would make that a cycle."""
    import ast  # pylint: disable=import-outside-toplevel
    with open(_PY, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names.append(node.module or "")
    assert not [n for n in names if n.startswith("crew")], names


@pytest.mark.wallclock
def test_latency_bound():
    """U2: a pure-python reader with no subprocess, well inside the 15 s hook
    timeout. Bound per call, over every case."""
    cases = [(c, "bash") for c in BLOCK_BASH + ALLOW_BASH + CNT_BASH] + \
        [(c, "powershell") for c in BLOCK_PS + ALLOW_PS + CNT_PS]
    start = time.perf_counter()
    for command, shell in cases:
        env_guard.findings(command, shell)
    per_call = (time.perf_counter() - start) / len(cases)
    assert per_call < 0.150, per_call


# --- the python driver: main(), every case -------------------------------------------


@pytest.mark.parametrize("tool,command",
                         [("Bash", c) for c in BLOCK_BASH]
                         + [("PowerShell", c) for c in BLOCK_PS],
                         ids=_ids(BLOCK_BASH) + _ids(BLOCK_PS))
def test_must_block_python(monkeypatch, capsys, tmp_path, tool, command):
    _fixture(tmp_path, ARMED)
    decision, reason = run_main(monkeypatch, capsys, tmp_path, tool, command)
    assert decision == "deny"
    assert reason.startswith("crew env guard: refused (")


@pytest.mark.parametrize("tool,command",
                         [("Bash", c) for c in ALLOW_BASH]
                         + [("PowerShell", c) for c in ALLOW_PS],
                         ids=_ids(ALLOW_BASH) + _ids(ALLOW_PS))
def test_must_allow_python(monkeypatch, capsys, tmp_path, tool, command):
    _fixture(tmp_path, ARMED)
    assert run_main(monkeypatch, capsys, tmp_path, tool, command) == ("allow", "")
    assert _log_text(tmp_path) == ""


@pytest.mark.parametrize("tool,command",
                         [("Bash", c) for c in CNT_BASH]
                         + [("PowerShell", c) for c in CNT_PS],
                         ids=_ids(CNT_BASH) + _ids(CNT_PS))
def test_could_not_tell_denies_in_block_and_logs_in_report(
        monkeypatch, capsys, tmp_path, tool, command):
    _fixture(tmp_path, ARMED)
    decision, reason = run_main(monkeypatch, capsys, tmp_path, tool, command)
    assert decision == "deny" and "could-not-tell:" in reason
    _fixture(tmp_path, REPORT)
    (tmp_path / "repo" / ".crew" / "guard.log").unlink(missing_ok=True)
    assert run_main(monkeypatch, capsys, tmp_path, tool, command) == ("allow", "")
    assert "\treport:deny\tcould-not-tell:" in _log_text(tmp_path)


@pytest.mark.parametrize("raw", [b"", b"not json", b"[1]",
                                 b'{"tool_name":"Bash","tool_input":{}}'],
                         ids=["empty", "not-json", "not-object", "no-command"])
def test_malformed_input_is_could_not_tell(monkeypatch, capsys, tmp_path, raw):
    _fixture(tmp_path, ARMED)
    decision, reason = run_main(monkeypatch, capsys, tmp_path, "Bash", "",
                                raw=raw)
    assert decision == "deny" and "could-not-tell:malformed-input" in reason


def test_malformed_input_unarmed_is_left_alone(monkeypatch, capsys, tmp_path):
    _fixture(tmp_path)
    assert run_main(monkeypatch, capsys, tmp_path, "Bash", "",
                    raw=b"not json") == ("allow", "")


def test_corrupt_config_layer_blocks(monkeypatch, capsys, tmp_path):
    _fixture(tmp_path, raw_repo="{ this is not json")
    decision, reason = run_main(monkeypatch, capsys, tmp_path, "Bash", "env")
    assert decision == "deny" and "failing closed" in reason


def test_other_tools_are_not_judged(monkeypatch, capsys, tmp_path):
    _fixture(tmp_path, ARMED)
    raw = json.dumps({"tool_name": "Write", "tool_input": {
        "file_path": "x", "content": "env"}}).encode("utf-8")
    assert run_main(monkeypatch, capsys, tmp_path, "Write", "", raw=raw) == \
        ("allow", "")


# --- 4: the switch ------------------------------------------------------------------

_SWITCH_SAMPLE = [("Bash", "env"), ("Bash", "printenv"), ("Bash", "set"),
                  ("Bash", "cat /proc/self/environ"),
                  ("Bash", "echo $FAKE_GITHUB_TOKEN"),
                  ("PowerShell", "gci env:"),
                  ("PowerShell", "[Environment]::GetEnvironmentVariables()"),
                  ("Bash", "eval \"$X\"")]


@pytest.mark.parametrize("cfg", [None, {"guards": {}}, {"guards": {"envGuard": "off"}},
                                 {"guards": {"envGuard": None}}],
                         ids=["no-config", "absent-key", "off", "null"])
@pytest.mark.parametrize("tool,command", _SWITCH_SAMPLE)
def test_off_and_absent_allow_everything_silently(monkeypatch, capsys, tmp_path,
                                                  cfg, tool, command):
    _fixture(tmp_path, cfg)
    assert run_main(monkeypatch, capsys, tmp_path, tool, command) == ("allow", "")
    assert _log_text(tmp_path) == ""


@pytest.mark.parametrize("tool,command", _SWITCH_SAMPLE)
def test_report_allows_and_logs(monkeypatch, capsys, tmp_path, tool, command):
    _fixture(tmp_path, REPORT)
    assert run_main(monkeypatch, capsys, tmp_path, tool, command) == ("allow", "")
    rows = _log_text(tmp_path).splitlines()
    assert rows and all(r.split("\t")[1:4] == ["envGuard", "report", "report:deny"]
                        for r in rows), rows


@pytest.mark.parametrize("value", ["blok", 1, True, ["block"]])
def test_malformed_value_blocks(monkeypatch, capsys, tmp_path, value):
    _fixture(tmp_path, {"guards": {"envGuard": value}})
    assert run_main(monkeypatch, capsys, tmp_path, "Bash", "env")[0] == "deny"


@pytest.mark.parametrize("repo,glob,want", [
    ("off", "block", "deny"), ("block", "off", "deny"),
    ("off", "report", "report"), ("report", "off", "report"),
    ("report", "block", "deny"), ("off", "off", "allow")])
def test_ratchet_takes_the_narrower_layer(monkeypatch, capsys, tmp_path,
                                          global_layer, repo, glob, want):
    _fixture(tmp_path, {"guards": {"envGuard": repo}})
    global_layer({"guards": {"envGuard": glob}})
    decision, _ = run_main(monkeypatch, capsys, tmp_path, "Bash", "env")
    logged = "report:deny" in _log_text(tmp_path)
    got = "deny" if decision == "deny" else ("report" if logged else "allow")
    assert got == want


def test_default_config_and_templates_read_off():
    assert crew_config.default_config()["guards"]["envGuard"] == "off"
    assert crew_config.default_global_config()["guards"]["envGuard"] == "off"
    for name in ("config.template.json", "global.template.json"):
        with open(os.path.join(_ROOT, "templates", name), encoding="utf-8") as fh:
            assert json.load(fh)["guards"]["envGuard"] == "off"


# --- 5: flavour by tool, not OS -----------------------------------------------------


def test_stands_down_by_tool():
    sd = env_guard.stands_down
    assert sd("Bash", {env_guard.FLAVOUR_VAR: "powershell"})
    assert not sd("PowerShell", {env_guard.FLAVOUR_VAR: "powershell"})
    assert not sd("Bash", {env_guard.FLAVOUR_VAR: "bash", "OS": "Windows_NT"})
    assert sd("PowerShell", {env_guard.FLAVOUR_VAR: "bash", "OS": "Windows_NT"})
    assert not sd("PowerShell", {env_guard.FLAVOUR_VAR: "bash"})
    assert not sd("PowerShell", {})


def test_bash_flavour_judges_a_powershell_call_off_windows(monkeypatch, capsys,
                                                           tmp_path):
    _fixture(tmp_path, ARMED)
    monkeypatch.delenv("OS", raising=False)
    assert run_main(monkeypatch, capsys, tmp_path, "PowerShell", "gci env:",
                    flavour="bash")[0] == "deny"


def test_bash_flavour_stands_down_for_powershell_on_windows(monkeypatch, capsys,
                                                            tmp_path):
    _fixture(tmp_path, ARMED)
    monkeypatch.setenv("OS", "Windows_NT")
    assert run_main(monkeypatch, capsys, tmp_path, "PowerShell", "gci env:",
                    flavour="bash") == ("allow", "")
    assert run_main(monkeypatch, capsys, tmp_path, "Bash", "env",
                    flavour="bash")[0] == "deny"


# --- 6: no value reaches any output --------------------------------------------------

_NO_VALUE = [("Bash", "printenv FAKE_TOKEN"), ("Bash", "env"),
             ("Bash", "echo \"$FAKE_TOKEN\""), ("Bash", "eval \"$FAKE_TOKEN\""),
             ("PowerShell", "$env:FAKE_TOKEN"), ("PowerShell", "gci env:")]


@pytest.mark.parametrize("tool,command", _NO_VALUE)
def test_no_value_reaches_output_or_log(tmp_path, tool, command):
    """The marker is in the subprocess's (scrubbed) environment. Whatever the
    guard says, neither the value nor the command text reaches stdout,
    stderr or guard.log."""
    _fixture(tmp_path, ARMED)
    decision, reason, code, output = run_hook("python", tmp_path, tool, command)
    assert decision == "deny" and code == 0
    log = _log_text(tmp_path)
    assert MARKER not in output and MARKER not in log
    assert "FAKE_TOKEN" not in log
    rows = [row.split("\t") for row in log.splitlines()]
    assert rows and all(len(r) == 6 and r[5] == "-" for r in rows), rows
    assert "FAKE_TOKEN" not in reason


# --- the subprocess drivers: a parity sample -----------------------------------------

_PARITY = [("Bash", "env", "deny"), ("Bash", "printenv HOME", "allow"),
           ("Bash", "bash -c 'cat /proc/self/environ'", "deny"),
           ("Bash", "set -euo pipefail", "allow"),
           ("Bash", "eval \"$X\"", "deny"),
           ("PowerShell", "gci env:", "deny"),
           ("PowerShell", "$env:PATH", "allow")]


@pytest.mark.parametrize("tool,command,want", _PARITY)
def test_python_subprocess_parity(tmp_path, tool, command, want):
    _fixture(tmp_path, ARMED)
    decision, _, code, _ = run_hook("python", tmp_path, tool, command)
    assert (decision, code) == (want, 0)


@needs_bash
@pytest.mark.parametrize("tool,command,want", _PARITY)
def test_bash_driver_parity(tmp_path, tool, command, want):
    _fixture(tmp_path, ARMED)
    decision, _, code, out = run_hook("bash", tmp_path, tool, command)
    assert (decision, code) == (want, 0), out


@needs_pwsh
@pytest.mark.parametrize("tool,command,want",
                         [p for p in _PARITY if p[0] == "PowerShell"]
                         + [("PowerShell", "Write-Output $env:FAKE_API_KEY", "deny"),
                            ("PowerShell", "[Environment]::GetEnvironmentVariables()",
                             "deny")])
def test_pwsh_driver_parity(tmp_path, tool, command, want):
    _fixture(tmp_path, ARMED)
    decision, _, code, out = run_hook("pwsh", tmp_path, tool, command)
    assert (decision, code) == (want, 0), out


@needs_pwsh
def test_pwsh_driver_stands_down_for_bash(tmp_path):
    _fixture(tmp_path, ARMED)
    decision, _, code, out = run_hook("pwsh", tmp_path, "Bash", "env")
    assert (decision, code) == ("allow", 0), out


@needs_bash
def test_bash_driver_stands_down_for_powershell_on_windows(tmp_path):
    _fixture(tmp_path, ARMED)
    decision, _, code, out = run_hook("bash", tmp_path, "PowerShell", "gci env:",
                                      extra={"OS": "Windows_NT"})
    assert (decision, code) == ("allow", 0), out
    decision, _, code, out = run_hook("bash", tmp_path, "Bash", "env",
                                      extra={"OS": "Windows_NT"})
    assert (decision, code) == ("deny", 0), out


@needs_bash
def test_bash_driver_off_is_silent(tmp_path):
    _fixture(tmp_path, {"guards": {"envGuard": "off"}})
    assert run_hook("bash", tmp_path, "Bash", "env")[:3] == ("allow", "", 0)


_NO_PYTHON = {"PYTHONHOME": "/nonexistent-python-home"}


@needs_bash
@pytest.mark.parametrize("armed", [True, False], ids=["armed", "not-armed"])
def test_bash_wrapper_without_python(tmp_path, armed):
    """No usable python: armed fails closed (exit 2), unarmed stays out of the
    way."""
    _fixture(tmp_path, ARMED if armed else {"guards": {"envGuard": "off"}})
    _, _, code, out = run_hook("bash", tmp_path, "Bash", "env", extra=_NO_PYTHON)
    assert code == (2 if armed else 0), out
    assert MARKER not in out


@needs_pwsh
@pytest.mark.parametrize("armed", [True, False], ids=["armed", "not-armed"])
def test_pwsh_wrapper_without_python(tmp_path, armed):
    _fixture(tmp_path, ARMED if armed else {"guards": {"envGuard": "off"}})
    _, _, code, out = run_hook("pwsh", tmp_path, "PowerShell", "gci env:",
                               extra=_NO_PYTHON)
    assert code == (2 if armed else 0), out
    assert MARKER not in out


# --- 9: registration -----------------------------------------------------------------


def test_registered_once_per_flavour_on_bash_and_powershell():
    with open(os.path.join(_ROOT, "hooks", "hooks.json"), encoding="utf-8") as fh:
        pre = json.load(fh)["hooks"]["PreToolUse"]
    entries = [(e["matcher"], h) for e in pre for h in e["hooks"]
               if "env-guard" in h["command"]]
    assert len(entries) == 2
    by_script = {("ps1" if "env-guard.ps1" in h["command"] else "sh"): (m, h)
                 for m, h in entries}
    assert by_script["sh"][0] == by_script["ps1"][0] == "Bash|PowerShell"
    assert by_script["ps1"][1].get("shell") == "powershell"
    assert "shell" not in by_script["sh"][1]
    assert by_script["sh"][1]["timeout"] == by_script["ps1"][1]["timeout"] == 15
