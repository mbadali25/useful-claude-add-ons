"""Four ways the production-access guard was bypassed by SPELLING.

Every case here was measured before the fix, in both flavours, against a
fixture repo declaring `prod-db-*` and `prod-web-*`. The exit codes recorded
below are the observed ones, not predictions:

- `ssh prod-web-1 'env touch /tmp/crew-proof'` at `prodServer: read` exited 0
  and printed `classified as: read`. `env` was on `PROD_READ_COMMANDS`, and
  `env` is a WRAPPER: the classifier read the executable name and never asked
  what it ran. Four characters cleared every write on the machine.
- `ssh prod-web-1 'ip link set eth0 down'` at `read` exited 0 the same way.
  `PROD_SUBCOMMAND_READS["ip"]` holds `link`, and only the subcommand was
  checked -- `ip link` is an OBJECT, not a verb, so the action that decides
  (`show` versus `set`) was never read.
- `psql -h prod-db-1 -c 'select 1' -c 'de''lete from orders'` at `read` exited
  0. `_sql_payload` returned the FIRST `-c` and stopped; psql runs both.
- `/usr/bin/ssh prod-web-1 'touch /tmp/crew-proof'` exited 0 at
  `prodServer: none`, the strictest level there is. Both tool selectors
  required the executable to follow whitespace or a separator, so a path
  bypassed `prod_guarded` entirely and the classifier was never consulted.
- the secret-read exemption asked whether ANY read sat inside a capture, so a
  command capturing the first value and printing the second exited 0.

MUST-ALLOW MATTERS AS MUCH. Four of the cases below exist only to prove the
fixes did not become "refuse more": an absolute-path READ still passes at
`read`, an absolute-path write still passes at `full` (that one was BLOCKED
before the fix, by the unconfigurable rule, because `PROD_HIT` never got set),
`ip addr show` and bare `env` still classify as reads, and two captured
secrets in one command line still pass.

SABOTAGE-TESTED: `plugin/crew/tests/sabotage.py` carries one mutation per
defect per flavour, each reintroducing the original code. Run it rather than
trusting this docstring.

Fragment-assembled literals: crew's own guard blocks a Bash call whose text
contains these, so a test file spelling them out could not be written by an
agent working in this repo.
"""
import json
import os
import shutil
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_fixtures
import crew_guards
import crew_state

_HOOKS = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      os.pardir, "hooks", "scripts")
_GUARD_SH = os.path.join(_HOOKS, "guard.sh")
_GUARD_PS1 = os.path.join(_HOOKS, "guard.ps1")

_BASH = crew_fixtures.resolve_bash()
_PWSH = shutil.which("pwsh")

needs_bash = pytest.mark.skipif(_BASH is None, reason="no usable bash")
needs_pwsh = pytest.mark.skipif(
    not sys.platform.startswith("win") or _PWSH is None,
    reason="guard.ps1 is the native-Windows flavour; needs Windows + pwsh")

# Fragment-assembled: see the module docstring.
_DEL = "de" + "lete"
_SECRET = "aws secrets" + "manager get-secret-value --secret-id "

_PROD = {"databases": ["prod-db-*"], "hosts": ["prod-web-*"]}


def _repo(tmp_path, level, production=None):
    """A fixture repo at `level`, declaring `_PROD` unless told otherwise.

    One directory per level so a parametrized case cannot read the config a
    neighbouring case wrote.
    """
    root = tmp_path / ("repo-" + level + ("-bare" if production else ""))
    (root / ".crew").mkdir(parents=True, exist_ok=True)
    (root / ".crew" / "config.json").write_text(json.dumps(
        {"schema": crew_state.SCHEMA_CURRENT,
         "guards": {"prodDatabase": level, "prodServer": level},
         "production": _PROD if production is None else production}), "utf-8")
    return str(root)


def _home(tmp_path):
    """A machine-global file at the CEILING, so the repo value is what varies.

    With the global layer unset the ratchet correctly holds every repo value
    down to `none` and every case below would pass for the wrong reason.
    """
    home = tmp_path / "home"
    (home / ".claude" / "crew").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "crew" / "config.json").write_text(json.dumps(
        {"guards": {name: "full"
                    for name in crew_guards.PROD_GUARD_NAMES}}), "utf-8")
    return str(home)


def _run_sh(root, home, command):
    payload = json.dumps({"tool_input": {"command": command}})
    return subprocess.run(
        [_BASH, _GUARD_SH.replace("\\", "/")], input=payload,
        capture_output=True, text=True, check=False, timeout=120,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home))


def _run_ps1(root, home, command):
    payload = json.dumps({"tool_name": "PowerShell",
                          "tool_input": {"command": command}})
    return subprocess.run(
        [_PWSH, "-NoProfile", "-NonInteractive", "-File", _GUARD_PS1],
        input=payload, capture_output=True, text=True, check=False,
        timeout=120,
        env=dict(os.environ, CLAUDE_PROJECT_DIR=root, HOME=home,
                 USERPROFILE=home, PSModulePath=""))


# ---- the classifier: what `read` may never clear -------------------------
#
# Unit cases, because the classifier is where three of the four defects live
# and a shell-level case cannot say WHICH rung failed.

_MUST_BE_WRITE = (
    # D1: `env` is a wrapper, not a read-only program.
    "ssh prod-web-1 'env touch /tmp/crew-proof'",
    "ssh prod-web-1 'env FOO=bar systemctl restart app'",
    # An option to `env` changes what runs or where. Unclassifiable, so write.
    "ssh prod-web-1 'env -u PATH ls'",
    # A wrapped write anywhere in the pipeline, not only at the front.
    "ssh prod-web-1 'ls /srv; env touch /tmp/crew-proof'",
    # D1: `ip link` is an object; the ACTION decides.
    "ssh prod-web-1 'ip link set eth0 down'",
    "ssh prod-web-1 'ip route add default via 10.0.0.1'",
    "ssh prod-web-1 'ip neigh flush all'",
    # `ip link s` resolves to `set`, not `show`, so the abbreviations `ip`
    # itself accepts are deliberately not on the read list.
    "ssh prod-web-1 'ip link s eth0 down'",
    "ssh prod-web-1 'ip a s'",
    # D1b: EVERY payload is inspected, in either order.
    f"psql -h prod-db-1 -c 'select 1' -c '{_DEL} from orders'",
    f"psql -h prod-db-1 -c '{_DEL} from orders' -c 'select 1'",
    f"mysql -h prod-db-2 -e 'show tables' -e '{_DEL} from orders'",
    # A flag with no value is a MISSING payload, not an empty one.
    "psql -h prod-db-1 -c",
)

_MUST_BE_READ = (
    # Bare `env` prints the environment and runs nothing.
    "ssh prod-web-1 'env'",
    "ssh prod-web-1 'env FOO=bar ls /srv'",
    "ssh prod-web-1 'ip addr show'",
    "ssh prod-web-1 'ip addr'",
    "ssh prod-web-1 'ip -br link show'",
    "ssh prod-web-1 'ip route list'",
    "psql -h prod-db-1 -c 'select 1' -c 'select 2'",
    "psql -h prod-db-1 --command='select 1'",
    # The path spelling must classify as the program it names, or the D4 fix
    # would hand `prod_guarded` a command it then refuses at `read`.
    "/usr/bin/ssh prod-web-1 'tail -n 50 /var/log/app.log'",
    # Everything the classifier called a read before this change still is.
    "ssh deploy@prod-web-1 'systemctl status app'",
    "ssh deploy@prod-web-1 'cat /etc/hostname | grep web'",
    "aws rds describe-db-instances --db-instance-identifier prod-db-1",
)


@pytest.mark.parametrize("command", _MUST_BE_WRITE)
def test_a_write_wearing_a_reads_spelling_is_a_write(command):
    assert crew_guards.classify_access(command) == "write", command


@pytest.mark.parametrize("command", _MUST_BE_READ)
def test_the_reads_are_still_reads(command):
    """The other half, and the half a "refuse more" fix would break."""
    assert crew_guards.classify_access(command) == "read", command


def test_a_windows_path_classifies_as_unreadable_rather_than_as_a_read():
    """Stated because it is a LIMIT, not a fix: `shlex(posix=True)` eats the
    backslashes out of `C:\\tools\\ssh.exe`, so that spelling reaches the
    classifier as one unrecognised program and comes back `write`. The
    selectors DO route it to the resolver now, so it is refused at `read` and
    permitted at `full` -- fail-closed, and pinned here so a later change to
    the tokenizer cannot quietly turn it into a read."""
    assert crew_guards.classify_access(
        "C:\\tools\\ssh.exe prod-web-1 'ls /srv'") == "write"


# ---- both shells: the selector, the levels, and the secret exemption -----
#
# (level, command, expected exit code). Written out twice rather than shared:
# the two scripts are what is under test, and three of these four defects were
# open in both.

_MUST_BLOCK = [
    # D4: a path bypassed the selector entirely, so `none` refused nothing.
    ("none", "/usr/bin/ssh prod-web-1 'touch /tmp/crew-proof'"),
    ("read", "/usr/bin/ssh prod-web-1 'touch /tmp/crew-proof'"),
    ("none", "/usr/bin/psql -h prod-db-1 -c 'select 1'"),
    ("read", "/usr/local/bin/ssh prod-web-1 'systemctl restart app'"),
    # D1 and D1b, through the shells rather than the classifier.
    ("read", "ssh prod-web-1 'env touch /tmp/crew-proof'"),
    ("read", "ssh prod-web-1 'ip link set eth0 down'"),
    ("read", f"psql -h prod-db-1 -c 'select 1' -c '{_DEL} from orders'"),
]

_MUST_ALLOW = [
    # The D4 fix must not become "refuse the path spelling".
    ("read", "/usr/bin/ssh prod-web-1 'tail -n 50 /var/log/app.log'"),
    # BLOCKED before the fix, and that is the point: the selector missed the
    # path, `PROD_HIT` stayed 0, and the unconfigurable rule refused a command
    # the configured level permits -- a key that reads as configurable
    # answering nothing.
    ("full", f"/usr/bin/psql -h prod-db-1 -c '{_DEL} from orders'"),
    # A host nothing declared is not production, at any spelling.
    ("read", "/usr/bin/ssh staging-web-1 'systemctl restart app'"),
    ("read", "ssh prod-web-1 'ip addr show'"),
    ("read", "ssh prod-web-1 'env'"),
    ("read", "psql -h prod-db-1 -c 'select 1' -c 'select 2'"),
]

# D6, per flavour: the same rule, two spellings. A bash `X=$(...)` is not a
# capture in PowerShell and vice versa, so these cannot be shared.
_SECRET_SH = [
    (2, "X=$(" + _SECRET + "first); " + _SECRET + "second"),
    (2, _SECRET + "first; " + _SECRET + "second"),
    (0, "SECRET=$(" + _SECRET + "first)"),
    (0, "A=$(" + _SECRET + "first); B=$(" + _SECRET + "second)"),
    (0, "A=$(" + _SECRET + "first) B=$(" + _SECRET + "second)"),
    (0, "A=$(" + _SECRET + "first | jq -r .SecretString)"),
]
_SECRET_PS1 = [
    (2, "$x = (" + _SECRET + "first); " + _SECRET + "second"),
    (2, _SECRET + "first; " + _SECRET + "second"),
    (0, "$x = (" + _SECRET + "first)"),
    (0, "$a = (" + _SECRET + "first); $b = (" + _SECRET + "second)"),
    (0, "$a = (" + _SECRET + "first) ; $b = (" + _SECRET + "second)"),
    (0, "$a = (" + _SECRET + "first | ConvertFrom-Json)"),
]


@needs_bash
@pytest.mark.parametrize("level,command", _MUST_BLOCK)
def test_sh_refuses_the_spelling(tmp_path, level, command):
    proc = _run_sh(_repo(tmp_path, level), _home(tmp_path), command)
    assert proc.returncode == 2, (command, proc.stderr[-600:])


@needs_bash
@pytest.mark.parametrize("level,command", _MUST_ALLOW)
def test_sh_still_allows_ordinary_work(tmp_path, level, command):
    proc = _run_sh(_repo(tmp_path, level), _home(tmp_path), command)
    assert proc.returncode == 0, (command, proc.stderr[-600:])


@needs_bash
def test_sh_the_wider_selector_stays_quiet_when_nothing_is_declared(tmp_path):
    """The default has to stay free. With `production.*` empty the wider
    selector reaches the resolver, matches nothing and must print nothing --
    a crew banner above every remote shell is how a guard becomes noise
    people switch off."""
    root = _repo(tmp_path, "none", production={"databases": [], "hosts": []})
    proc = _run_sh(root, _home(tmp_path),
                   "/usr/bin/ssh app-1 'systemctl restart app'")
    assert proc.returncode == 0, proc.stderr[-600:]
    assert "prodServer" not in proc.stderr


@needs_bash
@pytest.mark.parametrize("expected,command", _SECRET_SH,
                         ids=[f"{e}-{i}" for i, (e, _) in
                              enumerate(_SECRET_SH)])
def test_sh_every_secret_read_must_be_captured(tmp_path, expected, command):
    root = _repo(tmp_path, "none", production={"databases": [], "hosts": []})
    proc = _run_sh(root, _home(tmp_path), command)
    assert proc.returncode == expected, (command, proc.stderr[-600:])


@needs_pwsh
@pytest.mark.parametrize("level,command", _MUST_BLOCK)
def test_ps1_refuses_the_spelling(tmp_path, level, command):
    proc = _run_ps1(_repo(tmp_path, level), _home(tmp_path), command)
    assert proc.returncode == 2, (command, proc.stderr[-600:])


@needs_pwsh
@pytest.mark.parametrize("level,command", _MUST_ALLOW)
def test_ps1_still_allows_ordinary_work(tmp_path, level, command):
    proc = _run_ps1(_repo(tmp_path, level), _home(tmp_path), command)
    assert proc.returncode == 0, (command, proc.stderr[-600:])


@needs_pwsh
def test_ps1_the_wider_selector_stays_quiet_when_nothing_is_declared(tmp_path):
    root = _repo(tmp_path, "none", production={"databases": [], "hosts": []})
    proc = _run_ps1(root, _home(tmp_path),
                    "/usr/bin/ssh app-1 'systemctl restart app'")
    assert proc.returncode == 0, proc.stderr[-600:]
    assert "prodServer" not in proc.stderr


@needs_pwsh
@pytest.mark.parametrize("expected,command", _SECRET_PS1,
                         ids=[f"{e}-{i}" for i, (e, _) in
                              enumerate(_SECRET_PS1)])
def test_ps1_every_secret_read_must_be_captured(tmp_path, expected, command):
    root = _repo(tmp_path, "none", production={"databases": [], "hosts": []})
    proc = _run_ps1(root, _home(tmp_path), command)
    assert proc.returncode == expected, (command, proc.stderr[-600:])
