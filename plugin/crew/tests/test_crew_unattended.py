"""T-0044: `crew_unattended.py` -- unattended runs are STARTED holding
short-lived read-only cloud credentials, with the machine's credential stores
sealed, or they do not start at all.

This is the boundary T-0005's command-line guard cannot be, so it is tested as
a guard: must-refuse cases first, then must-launch, then a sentinel search
that proves no credential ever leaves memory. Every unit row below is built so
that the bug it names would collapse the verdict to `ready` -- a row whose
collapsed value would also refuse proves nothing (the lesson recorded in
`sabotage_cloud.py`).

Nothing here reaches AWS or a model. `aws` and `claude` are shims in a
`tmp_path/bin` put first on PATH; `HOME` is a `tmp_path` home with fake
stores; the machine config is a file in that home.
"""
import datetime
import json
import os
import shlex
import stat
import subprocess
import sys

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import crew_state
import crew_unattended as cu

IDENT = "arn:aws:sts::111111111111:assumed-role/ReadOnlyAccess/"
DEV_IDENT = "arn:aws:sts::222222222222:assumed-role/DevWriter/"
ARN = IDENT + "crew-unattended"
DEV_ARN = DEV_IDENT + "crew-unattended"

# Sentinels: if any of these appear anywhere outside the launched process's
# environment, a credential left memory.
KEY = "ASIASENTINELKEY0000001"
SECRET = "sentinel-secret-6c1f0e9d"
TOKEN = "sentinel-session-token-a77b"

NOW = datetime.datetime(2026, 10, 4, 12, 0, tzinfo=datetime.timezone.utc)
SECCOMP = ("apply-seccomp: write /proc/self/setgroups (nested userns is "
           "capability-restricted; caller must provide CAP_SYS_ADMIN): "
           "Permission denied")


def _iso(delta_minutes, base=None):
    base = base or datetime.datetime.now(datetime.timezone.utc)
    return (base + datetime.timedelta(minutes=delta_minutes)).isoformat()


def _export(**over):
    obj = {"Version": 1, "AccessKeyId": KEY, "SecretAccessKey": SECRET,
           "SessionToken": TOKEN, "Expiration": _iso(60)}
    for key, value in over.items():
        if value is None:
            obj.pop(key, None)
        else:
            obj[key] = value
    return obj


# --- the shims ---------------------------------------------------------------

_AWS_SHIM = r'''#!/usr/bin/env python3
import json, os, sys, time
args = sys.argv[1:]
if os.environ.get("FAKE_AWS_SLEEP"):
    time.sleep(float(os.environ["FAKE_AWS_SLEEP"]))
if args[:2] == ["configure", "export-credentials"]:
    rec = os.environ.get("FAKE_AWS_EXPORT_SEEN")
    if rec:
        with open(rec, "w") as fh:
            json.dump({"argv": args, "env": dict(os.environ)}, fh)
    sys.stdout.write(os.environ.get("FAKE_AWS_EXPORT", ""))
    sys.exit(int(os.environ.get("FAKE_AWS_EXPORT_RC", "0")))
if args[:2] == ["sts", "get-caller-identity"]:
    if os.environ.get("FAKE_STS_SLEEP"):
        time.sleep(float(os.environ["FAKE_STS_SLEEP"]))
    rec = os.environ.get("FAKE_AWS_STS_SEEN")
    if rec:
        with open(rec, "w") as fh:
            json.dump({"argv": args, "env": dict(os.environ)}, fh)
    rc = int(os.environ.get("FAKE_STS_RC", "0"))
    if rc:
        sys.stderr.write("An error occurred (ExpiredToken)\n")
        sys.exit(rc)
    sys.stdout.write(os.environ.get("FAKE_STS", ""))
    sys.exit(0)
sys.stderr.write("fake aws: unexpected argv %r\n" % (args,))
sys.exit(2)
'''

_CLAUDE_SHIM = r'''#!/usr/bin/env python3
import json, os, re, shlex, sys, time
args = sys.argv[1:]
if "-p" in args:
    rec = os.environ.get("FAKE_PROBE_SEEN")
    if rec:
        with open(rec, "w") as fh:
            json.dump({"argv": args, "env": dict(os.environ),
                       "cwd": os.getcwd()}, fh)
    if os.environ.get("FAKE_PROBE_SLEEP"):
        time.sleep(float(os.environ["FAKE_PROBE_SLEEP"]))
    prompt = args[args.index("-p") + 1]
    targets = [shlex.split(line)[1] for line in prompt.splitlines()
               if line.startswith("probe ")]
    nonce = re.search(r"echo NONCE (\S+)", prompt).group(1)
    mode = os.environ.get("FAKE_PROBE", "sealed")
    out = []
    def emit(obj):
        out.append(json.dumps(obj))
    def result(text, is_error=False):
        emit({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "id": "t1", "name": "Bash",
             "input": {"command": "probe"}}]}})
        emit({"type": "user", "message": {"content": [
            {"type": "tool_result", "tool_use_id": "t1", "is_error": is_error,
             "content": [{"type": "text", "text": text}]}]}})
    lines = ["SHUT " + t for t in targets]
    if mode == "seccomp":
        result(os.environ["FAKE_SECCOMP"] + "\nmore detail", True)
    elif mode == "notool":
        emit({"type": "assistant", "message": {"content": [
            {"type": "text", "text": "\n".join(lines + ["NONCE " + nonce])}]}})
    elif mode == "open":
        lines[0] = "OPEN " + targets[0]
        result("\n".join(lines + ["NONCE " + nonce]))
    elif mode == "skip":
        result("\n".join(lines[1:] + ["NONCE " + nonce]))
    elif mode == "err":
        lines[0] = "ERR " + targets[0]
        result("\n".join(lines + ["NONCE " + nonce]))
    elif mode == "wrongnonce":
        result("\n".join(lines + ["NONCE deadbeef"]))
    else:
        result("\n".join(lines + ["NONCE " + nonce]))
    emit({"type": "result", "subtype": "success", "result": "done"})
    sys.stdout.write("\n".join(out) + "\n")
    sys.exit(int(os.environ.get("FAKE_PROBE_RC", "0")))
dump = os.environ.get("FAKE_CLAUDE_DUMP")
if dump:
    with open(dump, "w") as fh:
        json.dump({"argv": sys.argv, "env": dict(os.environ)}, fh)
sys.exit(0)
'''


def _write_exe(path, text):
    path.write_text(text, encoding="utf-8", newline="\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


class World:
    """One fake machine: a home with stores, a machine config, a repo, shims."""

    def __init__(self, tmp_path, monkeypatch):
        self.tmp = tmp_path
        self.mp = monkeypatch
        self.home = tmp_path / "home"
        self.bin = tmp_path / "bin"
        self.repo = tmp_path / "repo"
        for path in (self.home, self.bin, self.repo / ".crew"):
            path.mkdir(parents=True)
        aws = self.home / ".aws"
        (aws / "sso" / "cache").mkdir(parents=True)
        (aws / "credentials").write_text(
            "[default]\naws_access_key_id = AKIASTATICSTORE\n", encoding="utf-8")
        (aws / "config").write_text("[profile ro]\n", encoding="utf-8")
        (aws / "sso" / "cache" / "tok.json").write_text("{}", encoding="utf-8")
        self.machine = self.home / ".claude" / "crew" / "config.json"
        self.machine.parent.mkdir(parents=True)
        _write_exe(self.bin / "aws", _AWS_SHIM)
        _write_exe(self.bin / "claude", _CLAUDE_SHIM)
        monkeypatch.setenv("HOME", str(self.home))
        monkeypatch.setenv("PATH", f"{self.bin}{os.pathsep}{os.environ['PATH']}")
        monkeypatch.setattr(crew_state, "GLOBAL_CONFIG_PATH", str(self.machine))
        # The pwd home is the REAL one; keep the store list to the fake home
        # for in-process runs so a real ~/.aws is never touched or listed.
        monkeypatch.setattr(cu, "_homes", lambda: [str(self.home)])
        monkeypatch.setenv("FAKE_SECCOMP", SECCOMP)
        monkeypatch.setenv("AWS_PROFILE", "admin")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "AKIAINHERITED")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "inherited-secret")
        monkeypatch.setenv("AWS_CONFIG_FILE", str(aws / "config"))
        self.set_machine({"unattendedCloud": {"aws": {
            "readOnly": {"profile": "ro", "identity": IDENT,
                         "region": "eu-west-1"},
            "nonProd": {"dev": {"profile": "devw", "identity": DEV_IDENT}}}}})
        self.set_repo({"environments": {"nonProd": ["dev", "qa-*"]}})
        self.set_export(_export())
        self.set_sts({"Arn": ARN, "Account": "111111111111", "UserId": "X"})
        self.execs = []
        monkeypatch.setattr(cu.os, "execvpe",
                            lambda f, a, e: self.execs.append((f, a, e)))

    def set_machine(self, cfg):
        self.machine.write_text(json.dumps(cfg), encoding="utf-8")

    def set_repo(self, cfg):
        (self.repo / ".crew" / "config.json").write_text(
            json.dumps(cfg), encoding="utf-8")

    def set_export(self, obj):
        self.mp.setenv("FAKE_AWS_EXPORT",
                       obj if isinstance(obj, str) else json.dumps(obj))

    def set_sts(self, obj):
        self.mp.setenv("FAKE_STS", obj if isinstance(obj, str) else json.dumps(obj))

    def run(self, *extra, command=("claude", "--resume")):
        argv = ["launch", "--root", str(self.repo), *extra, "--", *command]
        return cu.main(argv)


@pytest.fixture(name="world")
def _world(tmp_path, monkeypatch):
    return World(tmp_path, monkeypatch)


# --- unit tables: the pure core (`-k core`) ----------------------------------

CORE_EXPORT = [
    # (name, obj, now-relative, expected state, text, collapse a bug gives)
    ("static-keys", _export(SessionToken=None), "refuse", "static",
     "dropping the SessionToken check reads static keys as ready"),
    ("static-no-expiration", _export(Expiration=None), "refuse", "static",
     "dropping the Expiration check reads static keys as ready"),
    ("blank-token", _export(SessionToken=""), "refuse", "static",
     "a truthiness slip reads an empty token as present"),
    ("expiring-soon", _export(Expiration=_iso(14, NOW)), "refuse", "15 minutes",
     "dropping the floor launches a run that loses AWS mid-flight"),
    ("expired", _export(Expiration=_iso(-5, NOW)), "refuse", "15 minutes",
     "a sign slip reads an expired credential as fresh"),
    ("bad-expiration", _export(Expiration="soon"), "unknown", "parse",
     "a swallowed parse error collapses to ready"),
    ("naive-expiration", _export(Expiration="2026-10-04T13:00:00"), "unknown",
     "time zone", "a naive time compared as UTC"),
    ("no-version", _export(Version=None), "unknown", "Version",
     "an unrecognised payload read as a credential"),
    ("not-a-dict", [1, 2], "unknown", "object", "a list read as a credential"),
    ("no-secret", _export(SecretAccessKey=None), "unknown", "SecretAccessKey",
     "a half credential read as whole"),
]


@pytest.mark.parametrize("name,obj,state,text,_bug", CORE_EXPORT,
                         ids=[r[0] for r in CORE_EXPORT])
def test_core_export(name, obj, state, text, _bug):
    got, why = cu.judge_export(obj, NOW)
    assert got == state, (name, why)
    assert text in why, why
    assert SECRET not in why and TOKEN not in why and KEY not in why


def test_core_export_ready_and_floor_boundary():
    assert cu.judge_export(_export(Expiration=_iso(60, NOW)), NOW)[0] == "ready"
    assert cu.judge_export(_export(Expiration=_iso(15, NOW)), NOW)[0] == "ready"
    assert cu.judge_export(
        _export(Expiration=_iso(60, NOW).replace("+00:00", "Z")), NOW)[0] == "ready"


CORE_IDENTITY = [
    ("identity-match", {"Arn": ARN}, IDENT, "ready", ARN),
    ("identity-other-role",
     {"Arn": "arn:aws:sts::111111111111:assumed-role/AdministratorAccess/x"},
     IDENT, "refuse", "AdministratorAccess"),
    # A substring match would pass this one: the configured prefix appears,
    # but not at the start.
    ("identity-embedded",
     {"Arn": "arn:aws:sts::999999999999:assumed-role/X/" + IDENT}, IDENT,
     "refuse", "999999999999"),
    ("identity-user-arn", {"Arn": "arn:aws:iam::111111111111:user/ops"},
     "arn:aws:iam::111111111111:user/", "refuse", ":user/"),
    ("identity-no-arn", {"Account": "1"}, IDENT, "unknown", "Arn"),
    ("identity-not-dict", "nope", IDENT, "unknown", "object"),
    ("identity-unnamed", {"Arn": ARN}, None, "refuse", "no identity"),
    ("identity-no-slash", {"Arn": ARN}, IDENT.rstrip("/"), "refuse", "/"),
]


@pytest.mark.parametrize("name,obj,ident,state,text", CORE_IDENTITY,
                         ids=[r[0] for r in CORE_IDENTITY])
def test_core_identity(name, obj, ident, state, text):
    got, why = cu.judge_identity(obj, ident)
    assert got == state, (name, why)
    assert text in why, why


def _stream(*texts, tool=True, is_error=False):
    out = []
    for text in texts:
        if tool:
            out.append(json.dumps({"type": "user", "message": {"content": [
                {"type": "tool_result", "is_error": is_error,
                 "content": [{"type": "text", "text": text}]}]}}))
        else:
            out.append(json.dumps({"type": "assistant", "message": {
                "content": [{"type": "text", "text": text}]}}))
    return out


TARGETS = ["/h/.aws", "/h/.aws/credentials"]
SEALED = "SHUT /h/.aws\nSHUT /h/.aws/credentials\nNONCE n0nce"

CORE_PROBE_PARSE = [
    ("probe-sealed", _stream(SEALED), "ready", "sealed"),
    ("probe-seccomp", _stream(SECCOMP + "\nx", is_error=True), "unknown",
     SECCOMP),
    ("probe-no-tool-call", _stream(SEALED, tool=False), "unknown", "no tool call"),
    ("probe-open-store", _stream(SEALED.replace("SHUT /h/.aws/c", "OPEN /h/.aws/c")),
     "refuse", "OPEN /h/.aws/credentials"),
    ("probe-unreported-store",
     _stream("SHUT /h/.aws\nNONCE n0nce"), "unknown", "/h/.aws/credentials"),
    ("probe-err-store", _stream(SEALED.replace("SHUT /h/.aws\n", "ERR /h/.aws\n")),
     "unknown", "could not tell"),
    ("probe-wrong-nonce", _stream(SEALED.replace("n0nce", "other")), "unknown",
     "sandbox: unavailable"),
    # The nonce in a SECOND tool result does not vouch for the first's OPEN.
    ("probe-open-then-sealed",
     _stream("OPEN /h/.aws/credentials", SEALED), "refuse", "OPEN"),
    ("probe-garbage", ["not json", "{]"], "unknown", "no tool call"),
    # Both a SHUT and an OPEN for one store is OPEN.
    ("probe-shut-and-open", _stream(SEALED + "\nOPEN /h/.aws"), "refuse", "OPEN"),
]


@pytest.mark.parametrize("name,lines,state,text", CORE_PROBE_PARSE,
                         ids=[r[0] for r in CORE_PROBE_PARSE])
def test_core_probe_parse(name, lines, state, text):
    got, why = cu.judge_probe(lines, "n0nce", TARGETS)
    assert got == state, (name, why)
    assert text in why, why


def _cfg(read_only=None, non_prod=None, extra=None):
    aws = {"readOnly": read_only if read_only is not None else
           {"profile": "ro", "identity": IDENT, "region": "eu-west-1"},
           "nonProd": non_prod if non_prod is not None else
           {"dev": {"profile": "devw", "identity": DEV_IDENT}}}
    block = {"aws": aws}
    block.update(extra or {})
    return {"unattendedCloud": block}


_ENVS = {"nonProd": ["dev", "qa-*"], "problem": ""}

CORE_CONFIG = [
    ("config-readonly", _cfg(), _ENVS, None, "ready", "ro"),
    ("config-nonprod", _cfg(), _ENVS, "dev", "ready", "devw"),
    ("config-absent-file", None, _ENVS, None, "refuse", "no `unattendedCloud`"),
    ("config-no-block", {}, _ENVS, None, "refuse", "no `unattendedCloud`"),
    ("config-unnamed", _cfg(read_only={"profile": "ro", "identity": None}),
     _ENVS, None, "refuse", "no read-only identity named"),
    ("config-no-profile", _cfg(read_only={"profile": None, "identity": IDENT}),
     _ENVS, None, "refuse", "no read-only profile named"),
    ("config-azure", _cfg(extra={"azure": {}}), _ENVS, None, "refuse",
     "provider not implemented"),
    ("config-malformed", {"unattendedCloud": {"aws": {"nonProd": []}}}, _ENVS,
     None, "unknown", "nonProd"),
    ("config-unreadable", "corrupt", _ENVS, None, "unknown", "cannot be read"),
    ("nonprod-not-in-repo", _cfg(non_prod={"prod": {
        "profile": "p", "identity": DEV_IDENT}}), _ENVS, "prod", "refuse",
     "not nonProd"),
    ("nonprod-no-machine-entry", _cfg(), _ENVS, "qa-1", "refuse",
     "no machine entry"),
    ("nonprod-repo-problem", _cfg(), {"nonProd": [], "problem": "bad"}, "dev",
     "unknown", "bad"),
    ("nonprod-glob-case", _cfg(non_prod={"QA-1": {
        "profile": "q", "identity": DEV_IDENT}}), _ENVS, "QA-1", "ready", "q"),
]


@pytest.mark.parametrize("name,machine,envs,env,state,text", CORE_CONFIG,
                         ids=[r[0] for r in CORE_CONFIG])
def test_core_config(name, machine, envs, env, state, text):
    got, why, target = cu.resolve_target(machine, envs, env)
    assert got == state, (name, why)
    if state == "ready":
        assert target["profile"] == text
    else:
        assert text in why, why
        assert target is None


def test_core_env_strips_and_adds(tmp_path):
    base = {"PATH": "/bin", "AWS_PROFILE": "admin", "AWS_ROLE_ARN": "x",
            "AWS_WEB_IDENTITY_TOKEN_FILE": "/t", "HOME": "/h"}
    creds = _export()
    env = cu.sealed_env(base, creds, "eu-west-1", str(tmp_path))
    assert env["PATH"] == "/bin" and env["HOME"] == "/h"
    assert {k for k in env if k.startswith("AWS_")} == {
        "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_SESSION_TOKEN",
        "AWS_CREDENTIAL_EXPIRATION", "AWS_REGION", "AWS_DEFAULT_REGION",
        "AWS_EC2_METADATA_DISABLED", "AWS_CONFIG_FILE",
        "AWS_SHARED_CREDENTIALS_FILE"}
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"
    assert env["CREW_UNATTENDED"] == "1"
    assert env["AWS_SESSION_TOKEN"] == TOKEN
    assert env["AWS_CONFIG_FILE"] == os.path.join(str(tmp_path), "aws-config")
    assert not os.path.exists(env["AWS_SHARED_CREDENTIALS_FILE"])
    assert base["AWS_PROFILE"] == "admin"  # pure: the input is untouched


def test_core_settings_seal_every_store():
    stores = ["/h/.aws", "/h/.claude/crew/config.json"]
    settings = cu.sealed_settings(stores)
    box = settings["sandbox"]
    assert box["enabled"] is True and box["failIfUnavailable"] is True
    assert box["allowUnsandboxedCommands"] is False
    for store in stores:
        assert store in box["filesystem"]["denyRead"]
        assert f"Read(/{store})" in settings["permissions"]["deny"]
        assert f"Read(/{store}/**)" in settings["permissions"]["deny"]


def test_core_stores_cover_the_named_paths():
    got = cu.stores(["/h"], "/h/.claude/crew/config.json")
    for want in ("/h/.aws", "/h/.azure", "/h/.terraform.d/credentials.tfrc.json",
                 "/h/.claude/crew/config.json"):
        assert want in got


def test_core_probe_targets_walk_existing_stores(tmp_path):
    (tmp_path / ".aws" / "sso").mkdir(parents=True)
    (tmp_path / ".aws" / "credentials").write_text("x", encoding="utf-8")
    (tmp_path / ".aws" / "sso" / "t.json").write_text("x", encoding="utf-8")
    got = cu.probe_targets([str(tmp_path / ".aws"), str(tmp_path / "absent")])
    assert str(tmp_path / ".aws") in got
    assert str(tmp_path / ".aws" / "credentials") in got
    assert str(tmp_path / ".aws" / "sso" / "t.json") in got
    assert str(tmp_path / "absent") not in got


def test_core_probe_script_is_one_quoted_command():
    script = cu.probe_script(["/h/it's here", "/h/.aws"], "abc123")
    lines = script.splitlines()
    assert "probe " + shlex.quote("/h/it's here") in lines
    assert lines[-1] == "echo NONCE abc123"


# --- MUST_REFUSE: every case exits non-zero, execs nothing, names its reason --

def _repo_only(world):
    world.set_machine({})
    world.set_repo({"environments": {"nonProd": ["dev"]},
                    "unattendedCloud": {"aws": {"readOnly": {
                        "profile": "admin", "identity": IDENT}}}})


MUST_REFUSE = {
    "no-machine-block": (lambda w: w.set_machine({}), (),
                         ["no `unattendedCloud`"]),
    "repo-only-identity": (_repo_only, (),
                           ["no `unattendedCloud`", "ignored"]),
    "provider-not-aws": (lambda w: w.set_machine(_cfg(extra={"azure": {}})), (),
                         ["provider not implemented"]),
    "static-keys": (lambda w: w.set_export(_export(SessionToken=None)), (),
                    ["static"]),
    "static-no-expiration": (lambda w: w.set_export(_export(Expiration=None)),
                             (), ["static"]),
    "expiring-soon": (lambda w: w.set_export(_export(Expiration=_iso(5))), (),
                      ["15 minutes"]),
    "export-fails": (lambda w: w.mp.setenv("FAKE_AWS_EXPORT_RC", "255"), (),
                     ["exited 255"]),
    "export-times-out": (lambda w: (w.mp.setenv("FAKE_AWS_SLEEP", "5"),
                                    w.mp.setattr(cu, "EXPORT_TIMEOUT", 0.5)), (),
                         ["timed out"]),
    "export-not-json": (lambda w: w.set_export("not json " + SECRET), (),
                        ["not JSON"]),
    "identity-other-role": (lambda w: w.set_sts(
        {"Arn": "arn:aws:sts::111111111111:assumed-role/AdministratorAccess/s"}),
        (), ["AdministratorAccess"]),
    "identity-user-arn": (lambda w: w.set_sts(
        {"Arn": "arn:aws:iam::111111111111:user/ops"}), (), [":user/"]),
    "identity-malformed": (lambda w: w.set_sts("{nope"), (), ["not JSON"]),
    "identity-fails": (lambda w: w.mp.setenv("FAKE_STS_RC", "254"), (),
                       ["exited 254", "ExpiredToken"]),
    "identity-times-out": (lambda w: (w.mp.setenv("FAKE_STS_SLEEP", "5"),
                                      w.mp.setattr(cu, "STS_TIMEOUT", 0.5)), (),
                           ["timed out"]),
    "probe-seccomp": (lambda w: w.mp.setenv("FAKE_PROBE", "seccomp"), (),
                      ["sandbox: unavailable", SECCOMP]),
    "probe-open-store": (lambda w: w.mp.setenv("FAKE_PROBE", "open"), (),
                         ["OPEN"]),
    "probe-unreported-store": (lambda w: w.mp.setenv("FAKE_PROBE", "skip"), (),
                               ["not reported"]),
    "probe-no-tool-call": (lambda w: w.mp.setenv("FAKE_PROBE", "notool"), (),
                           ["no tool call"]),
    "probe-err-store": (lambda w: w.mp.setenv("FAKE_PROBE", "err"), (),
                        ["could not tell"]),
    "probe-times-out": (lambda w: (w.mp.setenv("FAKE_PROBE_SLEEP", "5"),
                                   w.mp.setattr(cu, "PROBE_TIMEOUT", 0.5)), (),
                        ["timed out"]),
    "env-prod": (lambda w: None, ("--environment", "prod"), ["not nonProd"]),
    "nonprod-no-machine-entry": (lambda w: None, ("--environment", "qa-7"),
                                 ["no machine entry"]),
    "nonprod-not-in-repo": (lambda w: w.set_machine(_cfg(non_prod={
        "staging": {"profile": "s", "identity": DEV_IDENT}})),
        ("--environment", "staging"), ["not nonProd"]),
    "windows": (lambda w: w.mp.setattr(cu, "_os_name", lambda: "nt"), (),
                ["native Windows"]),
}


@pytest.mark.parametrize("case", sorted(MUST_REFUSE))
def test_must_refuse(world, capsys, case):
    setup, extra, needles = MUST_REFUSE[case]
    setup(world)
    code = world.run(*extra)
    out = capsys.readouterr()
    text = out.out + out.err
    assert code != 0, text
    assert not world.execs, text
    for needle in needles:
        assert needle in text, (needle, text)
    assert SECRET not in text and TOKEN not in text and KEY not in text


@pytest.mark.parametrize("command", [("bash", "-c", "claude"),
                                     ("/usr/bin/env", "claude"),
                                     ("claude-evil",), ()])
def test_refuses_non_claude(world, capsys, command):
    code = world.run(command=command)
    text = capsys.readouterr().err
    assert code != 0 and not world.execs
    assert "claude" in text


@pytest.mark.parametrize("flag", ["--settings", "--settings=/x.json",
                                  "--setting-sources", "--setting-sources=user"])
def test_refuses_a_command_that_replaces_the_sealed_settings(world, capsys, flag):
    code = world.run(command=("claude", flag, "x"))
    assert code != 0 and not world.execs
    assert "settings" in capsys.readouterr().err


def test_refusal_removes_the_sealed_directory(world, capsys):
    world.mp.setenv("FAKE_PROBE", "open")
    seen = world.tmp / "probe-seen.json"
    world.mp.setenv("FAKE_PROBE_SEEN", str(seen))
    assert world.run() != 0
    capsys.readouterr()
    record = json.loads(seen.read_text(encoding="utf-8"))
    sealed = os.path.dirname(record["env"]["AWS_CONFIG_FILE"])
    assert not os.path.exists(sealed)


# --- MUST_LAUNCH --------------------------------------------------------------

def _assert_sealed_child(world, argv, env, profile, region):
    assert argv[0] == "claude" and argv[1] == "--settings"
    with open(argv[2], encoding="utf-8") as fh:
        settings = json.load(fh)
    assert argv[3:] == ["--resume"]
    # launch-strips-aws-env
    assert env.get("AWS_PROFILE") is None
    assert env["AWS_ACCESS_KEY_ID"] == KEY
    assert "AKIAINHERITED" not in json.dumps(env)
    assert env["AWS_CONFIG_FILE"] != str(world.home / ".aws" / "config")
    # launch-disables-imds
    assert env["AWS_EC2_METADATA_DISABLED"] == "true"
    assert env["CREW_UNATTENDED"] == "1"
    with open(env["AWS_CONFIG_FILE"], encoding="utf-8") as fh:
        config = fh.read()
    assert config == f"[default]\nregion = {region}\n"
    assert not os.path.exists(env["AWS_SHARED_CREDENTIALS_FILE"])
    sealed = os.path.dirname(env["AWS_CONFIG_FILE"])
    assert stat.S_IMODE(os.stat(sealed).st_mode) == 0o700
    assert sorted(os.listdir(sealed)) == ["aws-config", "settings.json"]
    box = settings["sandbox"]
    assert box["enabled"] is True and box["failIfUnavailable"] is True
    assert box["allowUnsandboxedCommands"] is False
    for store in (world.home / ".aws", world.machine):
        assert str(store) in box["filesystem"]["denyRead"]
        assert f"Read(/{store}/**)" in settings["permissions"]["deny"]
    del profile


MUST_LAUNCH = {
    "readonly": ((), "ro", "eu-west-1", ARN),
    "nonprod": (("--environment", "dev"), "devw", "us-east-1", DEV_ARN),
}


@pytest.mark.parametrize("case", sorted(MUST_LAUNCH))
def test_must_launch(world, capsys, case):
    extra, profile, region, arn = MUST_LAUNCH[case]
    world.set_sts({"Arn": arn})
    export_seen = world.tmp / "export-seen.json"
    sts_seen = world.tmp / "sts-seen.json"
    probe_seen = world.tmp / "probe-seen.json"
    world.mp.setenv("FAKE_AWS_EXPORT_SEEN", str(export_seen))
    world.mp.setenv("FAKE_AWS_STS_SEEN", str(sts_seen))
    world.mp.setenv("FAKE_PROBE_SEEN", str(probe_seen))
    code = world.run(*extra)
    out = capsys.readouterr()
    assert code == 0, out.out + out.err
    assert len(world.execs) == 1
    file_, argv, env = world.execs[0]
    assert file_ == "claude"
    _assert_sealed_child(world, argv, env, profile, region)
    assert arn in out.out
    # export ran with the profile and a stripped environment
    export = json.loads(export_seen.read_text(encoding="utf-8"))
    assert export["argv"][export["argv"].index("--profile") + 1] == profile
    assert not [k for k in export["env"] if k.startswith("AWS_")]
    # STS and the probe ran in the sealed environment, the probe from the repo
    for seen in (sts_seen, probe_seen):
        rec = json.loads(seen.read_text(encoding="utf-8"))
        assert rec["env"]["AWS_SESSION_TOKEN"] == TOKEN
        assert rec["env"]["AWS_CONFIG_FILE"] == env["AWS_CONFIG_FILE"]
        assert rec["env"].get("AWS_PROFILE") is None
    probe = json.loads(probe_seen.read_text(encoding="utf-8"))
    assert os.path.realpath(probe["cwd"]) == os.path.realpath(str(world.repo))
    assert probe["argv"][probe["argv"].index("--settings") + 1] == argv[2]


def test_check_runs_every_check_and_execs_nothing(world, capsys):
    code = cu.main(["check", "--root", str(world.repo), "--json"])
    out = capsys.readouterr().out
    rows = json.loads(out)
    assert code == 0 and not world.execs
    assert [r["check"] for r in rows] == ["platform", "config", "export",
                                          "identity", "sandbox"]
    assert all(r["state"] == "ready" for r in rows)


def test_check_keeps_unknown_distinct_from_refuse(world, capsys):
    world.mp.setenv("FAKE_PROBE", "seccomp")
    code = cu.main(["check", "--root", str(world.repo), "--json"])
    rows = {r["check"]: r for r in json.loads(capsys.readouterr().out)}
    assert code != 0
    assert rows["sandbox"]["state"] == "unknown"


def test_launch_execs_the_real_fake_claude(tmp_path):
    """No monkeypatching of `execvpe`: a subprocess runs the real launcher, the
    exec lands in the fake `claude`, and that process dumps what it got."""
    home = tmp_path / "home"
    (home / ".aws").mkdir(parents=True)
    (home / ".aws" / "credentials").write_text("[x]\n", encoding="utf-8")
    machine = home / ".claude" / "crew" / "config.json"
    machine.parent.mkdir(parents=True)
    machine.write_text(json.dumps(_cfg()), encoding="utf-8")
    repo = tmp_path / "repo"
    (repo / ".crew").mkdir(parents=True)
    (tmp_path / "bin").mkdir()
    _write_exe(tmp_path / "bin" / "aws", _AWS_SHIM)
    _write_exe(tmp_path / "bin" / "claude", _CLAUDE_SHIM)
    dump = tmp_path / "dump.json"
    env = {k: v for k, v in os.environ.items() if not k.startswith("AWS_")}
    env.update({"HOME": str(home), "PATH": f"{tmp_path / 'bin'}:{env['PATH']}",
                "FAKE_AWS_EXPORT": json.dumps(_export()),
                "FAKE_STS": json.dumps({"Arn": ARN}),
                "FAKE_CLAUDE_DUMP": str(dump), "AWS_PROFILE": "admin"})
    # The pwd home is the real one; the wrapper keeps the store list to the
    # fake home so the real ~/.aws is never even listed.
    wrapper = tmp_path / "run.py"
    wrapper.write_text(
        "import sys\n"
        f"sys.path.insert(0, {os.path.dirname(cu.__file__)!r})\n"
        "import crew_unattended as cu\n"
        f"cu._homes = lambda: [{str(home)!r}]\n"
        "sys.exit(cu.main(sys.argv[1:]))\n", encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(wrapper), "launch", "--root", str(repo), "--",
         "claude", "--resume"], env=env, capture_output=True, text=True,
        timeout=120, check=False)
    assert proc.returncode == 0, proc.stdout + proc.stderr
    got = json.loads(dump.read_text(encoding="utf-8"))
    assert got["argv"][1] == "--settings" and got["argv"][3:] == ["--resume"]
    assert got["env"]["AWS_SESSION_TOKEN"] == TOKEN
    assert "AWS_PROFILE" not in got["env"]
    assert got["env"]["AWS_EC2_METADATA_DISABLED"] == "true"
    assert got["env"]["CREW_UNATTENDED"] == "1"
    for sentinel in (KEY, SECRET, TOKEN):
        assert sentinel not in proc.stdout + proc.stderr


# --- no credential leaves memory ----------------------------------------------

def _files_under(*roots):
    for root in roots:
        for here, _dirs, files in os.walk(root):
            for name in files:
                yield os.path.join(here, name)


@pytest.mark.parametrize("outcome", ["refusal", "launch"])
def test_no_credential_leaves_memory(world, capsys, outcome):
    if outcome == "refusal":
        world.set_sts({"Arn": "arn:aws:sts::111111111111:assumed-role/Other/x"})
    seen = world.tmp / "probe-seen.json"
    world.mp.setenv("FAKE_PROBE_SEEN", str(seen))
    code = world.run()
    out = capsys.readouterr()
    assert (code == 0) is (outcome == "launch")
    roots = [world.repo / ".crew", world.machine.parent]
    if outcome == "launch":
        roots.append(os.path.dirname(world.execs[0][2]["AWS_CONFIG_FILE"]))
    blobs = [out.out, out.err]
    for path in _files_under(*roots):
        with open(path, encoding="utf-8", errors="replace") as fh:
            blobs.append(fh.read())
    for sentinel in (KEY, SECRET, TOKEN):
        assert not [b for b in blobs if sentinel in b], sentinel
