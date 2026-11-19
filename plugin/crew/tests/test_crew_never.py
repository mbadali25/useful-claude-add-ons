"""R-33: the Never lane's command-text tripwire (`crew_never.py`), report-only.

Must-block rows (verdict `hit`, operation named), the pinned known false
positive, could-not-tell rows, must-allow rows (verdict `clear`), the helper
pins on `crew_gitallow`, the redactor, the binding of every emitted name to a
Never row of the policy table, the coordination push held unaffected, the
inertness checks, and the in-file MUTATIONS: weakened copies of the module,
each of which must turn a named case red (R-01's pattern; the shared
`sabotage*.py` files are review harness and wait for the ticket that lets a
verdict block, spec D12).

Every case passes its own `env` (no secret is read from the real
environment) and nothing touches real config: the coordination argv is taken
with `crew_coord.run_git` replaced by a fake, so no git process starts.
"""
import ast
import json
import os
import subprocess
import sys
import types

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_coord
import crew_gitallow
import crew_never
import crew_policy

SCRIPTS = os.path.dirname(os.path.abspath(crew_never.__file__))
PLUGIN = os.path.dirname(os.path.dirname(SCRIPTS))
MODULE = os.path.join(SCRIPTS, "crew_never.py")
SKIP = crew_never.SKIP_HOOKS
SECRET = crew_never.WRITE_SECRET


def source():
    with open(MODULE, encoding="utf-8") as handle:
        return handle.read()


def run(mod, command, shell="bash", env=None):
    return mod.judge(command, shell, {} if env is None else env)


def rules(result):
    return [f["rule"] for f in result["findings"]]


def assert_hit(mod, command, rule, shell="bash", env=None, operation=SKIP):
    result = run(mod, command, shell, env)
    assert result["verdict"] == "hit", (command, result)
    assert rule in rules(result), (command, result)
    assert operation in result["operations"], (command, result)
    return result


def assert_clear(mod, command, shell="bash", env=None):
    result = run(mod, command, shell, env)
    assert result["verdict"] == "clear", (command, result)
    assert result["operations"] == [], (command, result)
    return result


def assert_cnt(mod, command, shell="bash", env=None):
    result = run(mod, command, shell, env)
    assert result["verdict"] == "could-not-tell", (command, result)
    return result


# --- the tables ------------------------------------------------------------------------------

HEREDOC_N = "git commit -n -F - <<'EOF'\nsubject\n\nbody\nEOF"
HEREDOC_STANDARD = ("git commit -m \"$(cat <<'EOF'\nSubject line\n\nBody text names git push.\n"
                    "Co-Authored-By: someone\nEOF\n)\"")
COORD_PUSH = "git push --no-verify -- crew-coord--push abc:refs/heads/crew-coord/x"

# (shell, command, rule)
MUST_BLOCK_HOOKS = (
    ("bash", "git commit --no-verify -m x", "no-verify"),
    ("bash", "git commit -n -m x", "commit-n"),
    ("bash", "git commit -anm x", "commit-n"),
    ("bash", "git commit --no-ver -m x", "no-verify"),
    ("bash", "git push --no-verify origin b", "no-verify"),
    ("bash", "git merge --no-verify f", "no-verify"),
    ("bash", "git rebase --no-verify main", "no-verify"),
    ("bash", "git pull --no-verify", "no-verify"),
    ("bash", "git am --no-verify x.patch", "no-verify"),
    ("bash", "git commit --no-gpg-sign -m x", "no-gpg-sign"),
    ("bash", "git commit-tree --no-gpg-sign T", "no-gpg-sign"),
    ("bash", "git cherry-pick --no-gpg-sign abc", "no-gpg-sign"),
    ("bash", "git tag --no-sign v1", "tag-no-sign"),
    ("bash", "git push --signed=no", "push-no-signed"),
    ("bash", "git push --no-signed origin b", "push-no-signed"),
    ("bash", "git -c core.hooksPath=/dev/null commit -m x", "config-hookspath"),
    ("bash", "git -c CORE.HOOKSPATH= commit", "config-hookspath"),
    ("bash", "git --config-env=core.hooksPath=HP commit -m x", "config-hookspath"),
    ("bash", "git -c commit.gpgsign=false commit -m x", "config-gpgsign-off"),
    ("bash", "git config core.hooksPath .nohooks", "config-write-hookspath"),
    ("bash", "git config --global commit.gpgSign false", "config-write-gpgsign-off"),
    ("bash", "HUSKY=0 git commit -m x", "env-husky"),
    ("bash", "SKIP=lint git commit -m x", "env-skip"),
    ("bash", "LEFTHOOK=0 git push", "env-lefthook"),
    ("bash", "HUSKY_SKIP_HOOKS=1 git commit -m x", "env-husky-skip-hooks"),
    ("bash", "GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.hooksPath GIT_CONFIG_VALUE_0=/x "
             "git commit -m x", "env-git-config-key"),
    ("bash", "env HUSKY=0 git commit -m x", "env-husky"),
    ("bash", "GIT_TRACE=1 git commit --no-verify -m x", "no-verify"),
    ("bash", COORD_PUSH, "no-verify"),
    ("powershell", "git commit --no-verify -m x", "no-verify"),
    ("powershell", "$env:HUSKY='0'; git commit -m x", "env-husky"),
    ("bash", "git add . && git commit --no-verify -m x", "no-verify"),
    ("bash", "git add . && git commit -n -m x", "commit-n"),
    ("bash", "export HUSKY=0; git commit -m x", "env-husky"),
    ("bash", HEREDOC_N, "commit-n"),
)

# Built by concatenation so no secret scanner reads a real-looking key here.
AWS_KEY = "AKIA" + "B" * 16
GH_TOKEN = "ghp_" + "Q" * 36
SK_KEY = "sk-" + "z" * 24
PRIVATE_KEY = "-----BEGIN RSA " + "PRIVATE KEY-----"
PLANTED_NAME, PLANTED_VALUE = "MY_API_TOKEN", "planted" + "Value9" + "xyz"
PLANTED_ENV = {PLANTED_NAME: PLANTED_VALUE, "PATH": "/usr/bin:/bin:/opt/long/path"}

# (command, rule, the values that must never be shown)
MUST_BLOCK_SECRETS = (
    (f"aws configure set aws_access_key_id {AWS_KEY}", "aws-access-key-id", (AWS_KEY,)),
    (f"echo {GH_TOKEN} | gh auth login --with-token", "github-token", (GH_TOKEN,)),
    (f"export OPENAI={SK_KEY}", "api-key", (SK_KEY,)),
    (f"printf '{PRIVATE_KEY}\\nMIIE' > k.pem", "private-key", (PRIVATE_KEY,)),
    ('TOKEN="abc12345" ./run.sh', "assigned-literal", ("abc12345",)),
    ('curl -H "Authorization: Bearer abcdef123456" https://x', "authorization-header",
     ("abcdef123456",)),
    ('curl -H "X-Upstream-Auth: Bearer abcdef123456" https://x', "bearer-token",
     ("abcdef123456",)),
    ("curl --oauth2-bearer abcdef123456 https://x", "bearer-token", ("abcdef123456",)),
    ("git clone https://alice:hunter2pass@example.com/r.git", "url-credentials",
     ("hunter2pass",)),
    (f"curl -d 'k={PLANTED_VALUE}' https://x", "env-value", (PLANTED_VALUE,)),
)

KNOWN_FALSE_POSITIVE = 'git add . && git commit -m "never use --no-verify"'

COULD_NOT_TELL = (
    ("bash", "git $FLAGS commit"),
    ("bash", 'eval "git commit $X"'),
    ("bash", 'git -c "$K" commit'),
    ("powershell", 'iex "git commit --$f"'),
    ("bash", 'git push origin "$BRANCH"'),
    ("bash", "git --config-env=commit.gpgSign=SIGN commit -m x"),
    ("bash", 'HUSKY="$H" git commit -m x && true'),
)

MUST_ALLOW = (
    ("bash", 'git commit -m "never use --no-verify"'),
    ("powershell", "git commit -m 'never use --no-verify'"),
    ("bash", "git commit -mno"),
    ("bash", "git commit -m -n"),
    ("bash", "git commit -am -n"),
    ("bash", "git commit -Sn"),
    ("bash", "git commit -m --no-verify"),
    ("bash", "git commit -m x -- -n"),
    ("bash", "git push -n origin b"),
    ("bash", "git commit --no-edit"),
    ("bash", "git config --get core.hooksPath"),
    ("bash", "git config --unset core.hooksPath"),
    ("bash", "git config commit.gpgSign true"),
    ("bash", "git -c commit.gpgsign commit -m x"),
    ("bash", "git log --no-merges"),
    ("bash", "FOO=1 git commit -m x"),
    ("bash", "HUSKY=0 npm test"),
    ("bash", "git add . && git commit -m x"),
    ("bash", "git add . && git push -n origin b"),
    ("powershell", "git add .; git commit -m x"),
    ("bash", HEREDOC_STANDARD),
    ("bash", "python3 plugin/crew/hooks/scripts/crew_coord.py claim R-33"),
    ("bash", "python3 plugin/crew/hooks/scripts/crew_coord.py heartbeat R-33"),
    ("bash", "python3 plugin/crew/hooks/scripts/crew_coord.py release R-33"),
    ("bash", "python3 plugin/crew/hooks/scripts/crew_coord.py done R-33"),
    ("bash", "python3 plugin/crew/hooks/scripts/crew_coord.py recover"),
    ("bash", "python3 plugin/crew/hooks/scripts/crew_coord.py status --root ."),
    ("bash", "echo $GITHUB_TOKEN | gh auth login --with-token"),
    ("bash", 'curl -H "Authorization: Bearer $TOKEN" https://x'),
    ("bash", 'curl -H "X-Upstream-Auth: Bearer $TOKEN" https://x'),
    ("bash", 'curl --oauth2-bearer "$TOKEN" https://x'),
    ("bash", 'curl -H "X-Auth: Bearer <token>" -H "Y: Bearer %TOKEN%" https://x'),
    ("bash", 'echo "send it as a Bearer credential"'),
    ("bash", 'echo "Bearer xxxxxxxxxxxx"'),
    ("powershell", "$env:API_KEY"),
    ("bash", "aws ssm get-parameter --name /app/prod/token --with-decryption"),
    ("bash", 'TOKEN="<token>"'),
    ("bash", "password: ${DB_PASSWORD}"),
    ("bash", f"echo ${PLANTED_NAME}"),
    ("bash", ""),
)


@pytest.mark.parametrize("shell,command,rule", MUST_BLOCK_HOOKS)
def test_must_block_hooks(shell, command, rule):
    assert_hit(crew_never, command, rule, shell)


@pytest.mark.parametrize("command,rule,values", MUST_BLOCK_SECRETS)
def test_must_block_secrets(command, rule, values):
    result = assert_hit(crew_never, command, rule, env=PLANTED_ENV, operation=SECRET)
    shown = json.dumps(result)
    for value in values:
        assert value not in shown


@pytest.mark.parametrize("command", [
    'curl -H "X-Upstream-Auth: Bearer abcdef123456" https://x',
    "curl --oauth2-bearer abcdef123456 https://x"])
def test_a_bearer_token_outside_authorization_is_only_the_own_shape(command):
    assert rules(run(crew_never, command)) == ["bearer-token"]


def test_known_false_positive_a_chained_message_naming_a_shape():
    # A KNOWN FALSE POSITIVE, pinned on purpose: the raw pass is quote-blind, so
    # `"never` is -m's value and `--no-verify"` strips to the flag. Changing this
    # verdict is a deliberate decision (R-33b measures the rate first).
    assert_hit(crew_never, KNOWN_FALSE_POSITIVE, "no-verify")


@pytest.mark.parametrize("shell,command", COULD_NOT_TELL)
def test_could_not_tell(shell, command):
    assert_cnt(crew_never, command, shell)


@pytest.mark.parametrize("shell,command", MUST_ALLOW)
def test_must_allow(shell, command):
    assert_clear(crew_never, command, shell, env=PLANTED_ENV)


def test_findings_name_rule_operation_and_place_only():
    result = run(crew_never, "git commit --no-verify -m secretmessage")
    for finding in result["findings"]:
        assert set(finding) <= {"verdict", "rule", "operation", "pass", "command", "word"}
    assert "secretmessage" not in json.dumps(result)
    assert result["report_only"] is True


@pytest.mark.parametrize("tool", ["Write", "Edit", "Read", None, "Bashx"])
def test_a_payload_that_is_not_a_command(tool):
    payload = {"tool_name": tool, "tool_input": {"command": "git commit --no-verify",
                                                 "content": "git commit --no-verify"}}
    assert crew_never.judge_payload(payload, env={})["verdict"] == "not-a-command"


def test_payloads_that_are_commands():
    bash = {"tool_name": "Bash", "tool_input": {"command": "git commit -n -m x"}}
    pwsh = {"tool_name": "PowerShell", "tool_input": {"command": "git add .; git commit -n"}}
    empty = {"tool_name": "Bash", "tool_input": {}}
    assert crew_never.judge_payload(bash, env={})["verdict"] == "hit"
    assert crew_never.judge_payload(pwsh, env={})["verdict"] == "hit"
    assert crew_never.judge_payload(empty, env={})["verdict"] == "could-not-tell"
    assert crew_never.judge_payload("not a dict")["verdict"] == "not-a-command"


def test_an_unknown_shell_is_could_not_tell():
    assert crew_never.judge("git commit -m x", "zsh", {})["verdict"] == "could-not-tell"


def test_every_shape_has_a_row():
    seen = {rule for _, _, rule in MUST_BLOCK_HOOKS} | {rule for _, rule, _ in MUST_BLOCK_SECRETS}
    assert crew_never.SHAPE_NAMES <= seen, crew_never.SHAPE_NAMES - seen


# --- helper pins: a change in crew_gitallow turns this suite red ------------------------------

@pytest.mark.parametrize("shell,command,expected", [
    ("bash", 'git commit -m "never use --no-verify"',
     [["git", "commit", "-m", "never use --no-verify"]]),
    ("powershell", "git commit -m 'never use --no-verify'",
     [["git", "commit", "-m", "never use --no-verify"]]),
    ("bash", "HUSKY=0 git commit -m x", [["HUSKY=0", "git", "commit", "-m", "x"]]),
    ("bash", "env HUSKY=0 git commit -m x", [["env", "HUSKY=0", "git", "commit", "-m", "x"]]),
    ("bash", "git add . && git commit -m x", None),
    ("bash", "git commit -m x; git push", None),
    ("bash", "git commit -m x | cat", None),
    ("bash", "git $FLAGS commit", None),
    ("bash", "git commit -F - <<'EOF'\nmsg\nEOF", None),
    ("powershell", "$env:HUSKY='0'; git commit -m x", None),
    ("powershell", "git add .; git commit -m x", None),
])
def test_plain_commands_pin(shell, command, expected):
    assert crew_gitallow.plain_commands(command, shell) == expected


def test_gitallow_private_helper_pins():
    # pylint: disable=protected-access
    assert crew_gitallow._option_hit("--no-ver", "--no-verify") is True
    assert crew_gitallow._option_hit("--no-edit", "--no-verify") is False
    assert crew_gitallow._option_hit("-mno", "-n") is True  # why -n has its own reader
    assert crew_gitallow._config_is_read(["--get", "core.hooksPath"]) is True
    assert crew_gitallow._config_is_read(["core.hooksPath", ".nohooks"]) is False
    assert crew_gitallow._config_is_read(["--global", "commit.gpgSign", "false"]) is False


# --- the redactor ------------------------------------------------------------------------------

def test_redact_replaces_each_shape_with_its_label():
    for command, rule, values in MUST_BLOCK_SECRETS:
        out, count = crew_never.redact(command, env=PLANTED_ENV)
        assert count >= 1, command
        label = f"[redacted:env:{PLANTED_NAME}]" if rule == "env-value" else f"[redacted:{rule}]"
        assert label in out, (command, out)
        for value in values:
            assert value not in out


def test_redact_counts_and_is_idempotent():
    text = f"a {GH_TOKEN} b {AWS_KEY} c {PLANTED_VALUE} d {PLANTED_VALUE}"
    once, count = crew_never.redact(text, env=PLANTED_ENV)
    assert count == 4
    assert once.count(f"[redacted:env:{PLANTED_NAME}]") == 2
    twice, again = crew_never.redact(once, env=PLANTED_ENV)
    assert twice == once and again == 0


def test_redact_leaves_names_and_plain_text_alone():
    text = f"echo ${PLANTED_NAME} and $GITHUB_TOKEN and Bearer $TOKEN"
    assert crew_never.redact(text, env=PLANTED_ENV) == (text, 0)


def test_redact_empty_and_none():
    assert crew_never.redact("") == ("", 0)
    assert crew_never.redact(None) == ("", 0)


def test_a_short_env_value_is_ignored():
    env = {"MY_API_TOKEN": "abc"}
    assert crew_never.redact("abc abc", env=env) == ("abc abc", 0)
    assert run(crew_never, "echo abc", env=env)["verdict"] == "clear"


# --- policy binding --------------------------------------------------------------------------

def _emitted():
    names = set(crew_never.OPERATIONS_EMITTED)
    for shell, command, _ in MUST_BLOCK_HOOKS:
        names.update(run(crew_never, command, shell)["operations"])
    for command, _, _ in MUST_BLOCK_SECRETS:
        names.update(run(crew_never, command, env=PLANTED_ENV)["operations"])
    return names


def test_every_emitted_name_is_a_never_row_denied_at_rule_one():
    names = _emitted()
    assert names == {SKIP, SECRET}
    assert all(op for _, op, _ in crew_never.SHAPES)
    for name in names:
        assert crew_policy.OPERATIONS[name].lane == "never"
        for presence in crew_policy.PRESENCE:
            for tier in crew_policy.TIERS:
                for provenance in crew_policy.PROVENANCE:
                    got = crew_policy.decide({"operation": name, "presence": presence,
                                              "tier": tier, "provenance": provenance})
                    assert (got["outcome"], got["rule"]) == ("deny", "1"), got


# --- the coordination push is unaffected -----------------------------------------------------

def _plugin_sources():
    for root, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in ("node_modules", "__pycache__", "tests", "_test")]
        for name in files:
            if name.endswith((".py", ".sh", ".ps1", ".json", ".md")):
                yield os.path.join(root, name)


def test_nothing_in_the_plugin_reaches_the_tripwire_yet():
    me = os.path.normcase(MODULE)
    hits = []
    for path in _plugin_sources():
        if os.path.normcase(path) == me:
            continue
        with open(path, encoding="utf-8", errors="replace") as handle:
            if "crew_never" in handle.read():
                hits.append(os.path.relpath(path, PLUGIN))
    assert hits == [], "report-only until R-33b wires it"


def _imports(path):
    with open(path, encoding="utf-8") as handle:
        tree = ast.parse(handle.read())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_the_coordination_script_imports_neither_module():
    names = _imports(os.path.join(SCRIPTS, "crew_coord.py"))
    assert "crew_never" not in names and "crew_policy" not in names


def test_the_real_coordination_argv_is_a_hit_but_never_a_payload(tmp_path, monkeypatch):
    calls = []

    def fake(root, args, **kwargs):  # pylint: disable=unused-argument
        calls.append(list(args))
        return crew_coord.GitRun(0, b"a" * 40 + b"\n", "")

    monkeypatch.setattr(crew_coord, "run_git", fake)
    chan = crew_coord.Channel(str(tmp_path), "origin", "r33")
    push = chan.push_argv("a" * 40)
    chan._commit({"f": b"x"}, None, "m")  # pylint: disable=protected-access
    assert calls and all(c[0] in ("hash-object", "mktree", "commit-tree") for c in calls)
    commit = [c for c in calls if c[0] == "commit-tree"]
    assert len(commit) == 1
    for argv, rule in ((push, "no-verify"), (commit[0], "no-gpg-sign")):
        assert_hit(crew_never, "git " + " ".join(argv), rule)


# --- inertness -------------------------------------------------------------------------------

def test_direct_imports_are_the_standard_library_and_three_modules():
    allowed = {"crew_gitallow", "crew_reference", "env_guard"}
    for name in _imports(MODULE):
        assert name in sys.stdlib_module_names or name in allowed, name


def test_the_module_declares_itself_report_only():
    assert crew_never.REPORT_ONLY is True
    assert "REPORT-ONLY" in source()
    assert "crew_policy" not in source()


def _tree(path):
    return sorted(os.path.relpath(os.path.join(r, f), path)
                  for r, _, files in os.walk(path) for f in files)


def test_importing_loads_no_policy_hook_or_coord_and_writes_nothing(tmp_path):
    cwd, home = tmp_path / "cwd", tmp_path / "home"
    cwd.mkdir()
    home.mkdir()
    env = dict(os.environ)
    for key in ("HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "XDG_CONFIG_HOME",
                "XDG_CACHE_HOME", "XDG_STATE_HOME"):
        env[key] = str(home)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    code = ("import json, sys; sys.path.insert(0, sys.argv[1]); before = set(sys.modules); "
            "import crew_never; print(json.dumps(sorted(set(sys.modules) - before)))")
    before = (_tree(cwd), _tree(home))
    done = subprocess.run([sys.executable, "-c", code, SCRIPTS], cwd=cwd, env=env,
                          capture_output=True, text=True, check=False, timeout=120)
    assert done.returncode == 0 and done.stderr == "", done.stderr
    loaded = set(json.loads(done.stdout))
    assert "crew_never" in loaded
    assert not loaded & {"crew_policy", "crew_hook", "crew_coord"}, loaded
    assert (_tree(cwd), _tree(home)) == before == ([], [])


def test_the_cli():
    def cli(*args, stdin=None):
        return subprocess.run([sys.executable, MODULE, *args], input=stdin, capture_output=True,
                              text=True, check=False, timeout=120)
    done = cli("judge", "--", "git commit --no-verify -m x")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "hit"
    done = cli("judge", "--shell", "powershell", "--", "git add .; git commit -m x")
    assert done.returncode == 0 and json.loads(done.stdout)["verdict"] == "clear"
    done = cli("redact", stdin=f"key {GH_TOKEN} end")
    assert done.returncode == 0 and done.stdout == "key [redacted:github-token] end"
    done = cli("shapes")
    assert done.returncode == 0
    for name in crew_never.SHAPE_NAMES:
        assert name in done.stdout
    assert cli("frobnicate").returncode == 2
    assert cli("judge", "--shell", "zsh", "--", "x").returncode == 2


# --- sabotage: each weakened copy must turn a named case red --------------------------------

def case_block_no_verify(mod):
    for command in ("git commit --no-verify -m x", "git push --no-verify origin b"):
        assert_hit(mod, command, "no-verify")


def case_block_abbrev(mod):
    assert_hit(mod, "git commit --no-ver -m x", "no-verify")


def case_allow_push_dry_run_plain(mod):
    assert_clear(mod, "git push -n origin b")


def case_allow_push_dry_run_raw(mod):
    assert_clear(mod, "git add . && git push -n origin b")


def case_allow_message_names_flag(mod):
    assert_clear(mod, 'git commit -m "never use --no-verify"')


def case_cnt_flags(mod):
    assert_cnt(mod, "git $FLAGS commit")


def case_block_husky(mod):
    assert_hit(mod, "HUSKY=0 git commit -m x", "env-husky")


def case_block_config_write(mod):
    assert_hit(mod, "git config core.hooksPath .nohooks", "config-write-hookspath")


def case_allow_config_read(mod):
    assert_clear(mod, "git config --get core.hooksPath")


def case_secret_value_not_shown(mod):
    for command, rule, values in MUST_BLOCK_SECRETS:
        shown = json.dumps(assert_hit(mod, command, rule, env=PLANTED_ENV, operation=SECRET))
        for value in values:
            assert value not in shown, rule


def case_block_env_value(mod):
    assert_hit(mod, f"curl -d 'k={PLANTED_VALUE}' https://x", "env-value", env=PLANTED_ENV,
               operation=SECRET)


def case_not_a_command(mod):
    payload = {"tool_name": "Write", "tool_input": {"content": "git commit --no-verify"}}
    assert mod.judge_payload(payload, env={})["verdict"] == "not-a-command"


def case_allow_bearer_prose(mod):
    assert_clear(mod, 'echo "send it as a Bearer credential"')


def case_block_upstream_bearer(mod):
    assert_hit(mod, 'curl -H "X-Upstream-Auth: Bearer abcdef123456" https://x', "bearer-token",
               operation=SECRET)


def case_allow_mno(mod):
    assert_clear(mod, "git commit -mno")


def case_allow_m_dash_n(mod):
    assert_clear(mod, "git commit -m -n")


def case_block_git_trace(mod):
    assert_hit(mod, "GIT_TRACE=1 git commit --no-verify -m x", "no-verify")


def case_block_raw_no_verify(mod):
    assert_hit(mod, "git add . && git commit --no-verify -m x", "no-verify")


MUTATIONS = (
    ("1 --no-verify dropped from the shape list",
     '    ("--no-verify", "no-verify", ("commit", "push", "merge", "pull", "am", "rebase")),\n',
     "", ("case_block_no_verify",)),
    ("2 abbreviation matching off",
     "    return crew_gitallow._option_hit(word, option)  # pylint: disable=protected-access",
     '    return word.split("=", 1)[0] == option', ("case_block_abbrev",)),
    ("3 -n counts on push", '            if sub == "commit" and carries_n:',
     '            if sub in ("commit", "push") and carries_n:',
     ("case_allow_push_dry_run_plain", "case_allow_push_dry_run_raw")),
    ("4 the plain pass is not authoritative",
     "    commands = crew_gitallow.plain_commands(command, shell)\n", "    commands = None\n",
     ("case_allow_message_names_flag",)),
    ("5 could-not-tell collapses to clear",
     "    if COULD_NOT_TELL in verdicts:\n        return COULD_NOT_TELL",
     "    if COULD_NOT_TELL in verdicts:\n        return CLEAR", ("case_cnt_flags",)),
    ("6 env-prefix check dropped",
     "    for name, value in pairs:\n        upper = name.upper()",
     "    for name, value in ():\n        upper = name.upper()", ("case_block_husky",)),
    ("7a config write check dropped",
     "        _config_write(rest, out, dict(where, word=sub_index))", "        pass",
     ("case_block_config_write",)),
    ("7b config reads treated as writes",
     "    if crew_gitallow._config_is_read(rest):  # pylint: disable=protected-access\n"
     "        return", "    if False:\n        return", ("case_allow_config_read",)),
    ("8 the matched value echoed in the finding",
     "            out.append(_finding(HIT, name, WRITE_SECRET))",
     "            out.append(dict(_finding(HIT, name, WRITE_SECRET), value=match.group(0)))",
     ("case_secret_value_not_shown",)),
    ("9 env-value secret check dropped",
     "    if any(value in text for _, value in _env_values(env)):", "    if False:",
     ("case_block_env_value",)),
    ("10 non-command payloads judged",
     '    shell = _SHELLS.get(payload.get("tool_name"))',
     '    shell = _SHELLS.get(payload.get("tool_name"), "bash")', ("case_not_a_command",)),
    ("11a bearer-token digit lookahead removed",
     r'BEARER_RE = re.compile(r"(?i)\bbearer\s+(?=[A-Za-z0-9._~+/=-]*\d)[A-Za-z0-9._~+/=-]{8,}")',
     r'BEARER_RE = re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{8,}")',
     ("case_allow_bearer_prose",)),
    ("11b bearer-token check dropped",
     '    return tuple(crew_reference.SECRET_PATTERNS) + (("bearer-token", BEARER_RE),)',
     "    return tuple(crew_reference.SECRET_PATTERNS)", ("case_block_upstream_bearer",)),
    ("12 -n read by _option_hit", '            if sub == "commit" and carries_n:',
     '            if sub == "commit" and crew_gitallow._option_hit(word, "-n"):',
     ("case_allow_mno",)),
    ("13 option values not skipped", "        index += 2 if skip else 1\n    return judged",
     "        index += 1\n    return judged", ("case_allow_m_dash_n",)),
    ("14 leading assignments not split off",
     "        if match:\n            pairs.append", "        if False:\n            pairs.append",
     ("case_block_git_trace",)),
    ("15 raw pass skipped", "    if commands is None:\n        return _raw_pass(command)",
     "    if commands is None:\n        return []", ("case_block_raw_no_verify",)),
)


def _variant(old, new):
    text = source()
    assert text.count(old) == 1, f"mutation target moved: {old!r}"
    name = "crew_never_mutant"
    module = types.ModuleType(name)
    module.__file__ = MODULE
    sys.modules[name] = module
    try:
        exec(compile(text.replace(old, new), name, "exec"),  # pylint: disable=exec-used
             module.__dict__)
    finally:
        sys.modules.pop(name, None)
    return module


@pytest.mark.parametrize("name", sorted(n for n in globals() if n.startswith("case_")))
def test_every_case_is_green_on_the_real_module(name):
    globals()[name](crew_never)


@pytest.mark.parametrize("label,old,new,cases", MUTATIONS, ids=[m[0] for m in MUTATIONS])
def test_a_weakened_tripwire_is_caught(label, old, new, cases):
    mutant = _variant(old, new)
    for name in cases:
        try:
            globals()[name](mutant)
        except AssertionError:
            continue  # red for the reason the case asserts, not a crash
        pytest.fail(f"{label}: {name} stayed green against the mutant")
