"""Start an unattended Claude session holding short-lived, owner-named cloud
credentials, with the machine's credential stores sealed -- or refuse (T-0044).

    python3 crew_unattended.py check  --root R [--environment NAME] [--json]
    python3 crew_unattended.py launch --root R [--environment NAME] -- claude [args...]

This is the boundary T-0005's guard cannot be. `cloud_guard.py` reads command
lines, so a renamed binary, `python -c` or a script file walks past it. What
holds whatever the command line says is what the process can authenticate as
and what it can read. So `launch` hands the session temporary credentials for
ONE identity the machine owner named, and denies the session's Bash and file
tools every credential store on the machine (`~/.aws` whole, `~/.azure`,
`~/.terraform.d/credentials.tfrc.json`, and crew's own machine config so the
session cannot rename its identity).

Checks, in order; the first that is not `ready` stops the chain:

  1. platform  native Windows has no sandbox probe here: unknown.
  2. config    `unattendedCloud` from the MACHINE file alone
               (`~/.claude/crew/config.json`). A repo copy is reported as
               ignored. `--environment NAME` needs a machine `nonProd` entry
               AND the repo's `environments.nonProd` classifying NAME as
               nonProd -- both layers agree, or it refuses.
  3. export    `aws configure export-credentials --format process`, read into
               memory only. No SessionToken or Expiration is static keys:
               refuse. Under 15 minutes left: refuse.
  4. identity  `aws sts get-caller-identity` in the sealed environment must
               print an ARN that STARTS WITH the named identity prefix.
  5. sandbox   one headless `claude -p` call in the sealed settings, from the
               repo root, runs a probe script that tries to open every store
               that exists. Its verdict is parsed from the stream-json TOOL
               RESULTS only, never from the model's prose.

Every check returns `(state, why)` with `state` one of `ready`, `refuse` or
`unknown`. `unknown` refuses exactly like `refuse` and keeps its own label:
"could not tell" is never printed as a verdict and never becomes `ready`.

Never: it never falls back to ambient credentials, never writes, copies or
logs a credential (the sealed directory holds a region-only AWS config and the
sealed settings file, nothing else), never writes to `~/.aws`, never runs
`aws sso login`.
"""

import argparse
import datetime
import json
import os
import pwd
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile

import cloud_guard
import crew_config
import crew_state

READY, REFUSE, UNKNOWN = "ready", "refuse", "unknown"
CHECKS = ("platform", "config", "export", "identity", "sandbox")

EXPORT_TIMEOUT = 60
STS_TIMEOUT = 30
PROBE_TIMEOUT = 300
MIN_LIFETIME = datetime.timedelta(minutes=15)
DEFAULT_REGION = "us-east-1"
# A store directory is walked to this many entries; past it, the probe could
# not cover the store and says so rather than vouching for a sample.
MAX_PROBE_TARGETS = 400

# Flags that would replace or drop the sealed settings for the launched session.
_SETTINGS_FLAGS = ("--settings", "--setting-sources")

_PROBE_PROMPT = (
    "Run exactly the following as ONE Bash tool call, unchanged, and nothing "
    "else. Do not read, explain or summarise its output; stop after it runs.\n"
    "\n{script}\n")


def _os_name():
    return os.name


def _homes():
    """Every home directory the stores are expanded from: `$HOME` and the
    account's real home from the password database. Two, because a session
    that re-points `HOME` must not unseal the real one."""
    out = []
    for home in (os.path.expanduser("~"), _pwd_home()):
        if home and home not in out:
            out.append(home)
    return out


def _pwd_home():
    try:
        return pwd.getpwuid(os.getuid()).pw_dir
    except (KeyError, OSError):
        return ""


# --- the pure core ------------------------------------------------------------

def stores(homes, machine_config):
    """The credential stores the session is denied, expanded per home."""
    out = []
    for home in homes:
        for rel in (".aws", ".azure", os.path.join(".terraform.d",
                                                   "credentials.tfrc.json"),
                    os.path.join(".claude", "crew", "config.json")):
            path = os.path.join(home, rel)
            if path not in out:
                out.append(path)
    if machine_config and machine_config not in out:
        out.append(machine_config)
    return out


def probe_targets(store_paths):
    """Every store that exists, and every entry inside a store directory.

    Returns the list, or `None` when a store could not be fully listed (too
    many entries, or a walk error): the probe cannot cover what it cannot
    name, and a sample is not a verdict."""
    out = []
    for store in store_paths:
        if not os.path.lexists(store):
            continue
        out.append(store)
        if os.path.isdir(store) and not os.path.islink(store):
            errors = []
            for here, dirs, files in os.walk(store, onerror=errors.append):
                for name in sorted(dirs) + sorted(files):
                    out.append(os.path.join(here, name))
            if errors:
                return None
        if len(out) > MAX_PROBE_TARGETS:
            return None
    return out


def probe_script(targets, nonce):
    """The one Bash command the probe session runs. It prints, per target,
    `OPEN` (some reader opened it), `SHUT` (every reader was refused) or
    `ERR` (could not tell), then `NONCE <nonce>`. It prints no contents."""
    lines = [
        "probe() { t=\"$1\"",
        "  if [ -d \"$t\" ]; then ls -- \"$t\" >/dev/null 2>&1 && "
        "{ echo \"OPEN $t\"; return; }",
        "  else head -c1 -- \"$t\" >/dev/null 2>&1 && "
        "{ echo \"OPEN $t\"; return; }; fi",
        "  v=$(python3 -c 'import os,sys\n"
        "p=sys.argv[1]\n"
        "try:\n"
        "    os.listdir(p) if os.path.isdir(p) else open(p,\"rb\").read(1)\n"
        "    print(\"OPEN\")\n"
        "except OSError:\n"
        "    print(\"SHUT\")' \"$t\" 2>/dev/null)",
        "  case \"$v\" in OPEN) echo \"OPEN $t\";; SHUT) echo \"SHUT $t\";; "
        "*) echo \"ERR $t\";; esac; }",
    ]
    for target in targets:
        lines.append("probe " + shlex.quote(target))
    lines.append("echo NONCE " + nonce)
    return "\n".join(lines)


def _tool_results(stream_lines):
    """The text of every `tool_result` block in stream-json output."""
    out = []
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "tool_result":
                continue
            body = block.get("content")
            if isinstance(body, str):
                out.append(body)
            elif isinstance(body, list):
                out.append("\n".join(
                    part.get("text", "") for part in body
                    if isinstance(part, dict) and isinstance(part.get("text"), str)))
            else:
                out.append("")
    return out


def judge_probe(stream_lines, nonce, targets):
    """`(state, why)` for the sandbox probe's stream-json output."""
    results = _tool_results(stream_lines)
    if not results:
        return UNKNOWN, "probe made no tool call, so nothing was measured"
    seen = {}
    for text in results:
        for line in text.splitlines():
            word, _, rest = line.strip().partition(" ")
            if word in ("OPEN", "SHUT", "ERR"):
                # Worst wins: OPEN over ERR over SHUT, whatever the order.
                rank = {"SHUT": 0, "ERR": 1, "OPEN": 2}
                if rank[word] >= rank.get(seen.get(rest), -1):
                    seen[rest] = word
    opened = [t for t, word in seen.items() if word == "OPEN"]
    if opened:
        return REFUSE, f"sandbox: the session can read a store: OPEN {opened[0]}"
    nonce_seen = any(line.strip() == f"NONCE {nonce}"
                     for text in results for line in text.splitlines())
    if not nonce_seen:
        first = next((line for text in results for line in text.splitlines()
                      if line.strip()), "")
        return UNKNOWN, f"sandbox: unavailable: {first or '(empty tool result)'}"
    for target in targets:
        if target not in seen:
            return UNKNOWN, f"sandbox: store not reported by the probe: {target}"
        if seen[target] == "ERR":
            return UNKNOWN, f"sandbox: could not tell whether {target} is sealed"
    return READY, f"sandbox: sealed ({len(targets)} store paths shut)"


def _parse_time(text):
    if not isinstance(text, str):
        return None
    try:
        when = datetime.datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return when


def judge_export(obj, now):
    """`(state, why)` for `aws configure export-credentials` output. Never
    names a credential value."""
    if not isinstance(obj, dict):
        return UNKNOWN, "export: output is not a JSON object"
    if "Version" not in obj:
        return UNKNOWN, "export: no `Version` field, not a credential_process payload"
    for key in ("AccessKeyId", "SecretAccessKey"):
        if not isinstance(obj.get(key), str) or not obj[key]:
            return UNKNOWN, f"export: no `{key}`"
    for key in ("SessionToken", "Expiration"):
        if not isinstance(obj.get(key), str) or not obj[key].strip():
            return REFUSE, (f"export: no `{key}`: these are static keys, not "
                            "temporary credentials")
    when = _parse_time(obj["Expiration"])
    if when is None:
        return UNKNOWN, "export: `Expiration` does not parse as a time"
    if when.tzinfo is None:
        return UNKNOWN, "export: `Expiration` carries no time zone"
    left = when - now
    if left < MIN_LIFETIME:
        return REFUSE, (f"export: credentials expire in under 15 minutes "
                        f"({int(left.total_seconds() // 60)} min left)")
    return READY, f"export: temporary credentials, {int(left.total_seconds() // 60)} min left"


def judge_identity(obj, identity):
    """`(state, why)`: STS's ARN must START WITH the named identity prefix."""
    if not isinstance(identity, str) or not identity:
        return REFUSE, "identity: no identity named"
    if not identity.endswith("/"):
        return REFUSE, "identity: the named identity must end in `/`"
    if not isinstance(obj, dict):
        return UNKNOWN, "identity: STS output is not a JSON object"
    arn = obj.get("Arn")
    if not isinstance(arn, str) or not arn:
        return UNKNOWN, "identity: STS output has no `Arn`"
    if ":user/" in arn:
        return REFUSE, (f"identity: STS says {arn}, a long-lived :user/ "
                        "identity, not an assumed role")
    if not arn.startswith(identity):
        return REFUSE, f"identity: STS says {arn}, expected {identity}..."
    return READY, f"identity: {arn}"


def _target_from(entry):
    return {"profile": entry.get("profile"), "identity": entry.get("identity"),
            "region": entry.get("region") or DEFAULT_REGION}


def resolve_target(machine_cfg, repo_envs, environment):
    """`(state, why, target)` from the machine config alone.

    `machine_cfg` is the parsed machine file, `None` when absent, or the
    string "corrupt" when it cannot be read. `repo_envs` is
    `cloud_guard.environments_config(root)`. `target` is `None` unless ready.
    """
    if machine_cfg == "corrupt" or (machine_cfg is not None
                                    and not isinstance(machine_cfg, dict)):
        return UNKNOWN, "config: the machine config cannot be read", None
    if not machine_cfg or "unattendedCloud" not in machine_cfg:
        return (REFUSE, "config: no `unattendedCloud` in the machine config, "
                "so no read-only identity named", None)
    block = machine_cfg["unattendedCloud"]
    problem = crew_config.unattended_cloud_block_problem(block)
    if problem:
        state = REFUSE if "provider not implemented" in problem else UNKNOWN
        return state, f"config: {problem}", None
    aws = block.get("aws", {})
    if environment is None:
        entry = aws.get("readOnly", {})
        if not entry.get("identity"):
            return REFUSE, "config: no read-only identity named", None
        if not entry.get("profile"):
            return REFUSE, "config: no read-only profile named", None
        return READY, "config: read-only identity", _target_from(entry)
    if repo_envs.get("problem"):
        return (UNKNOWN, f"config: the repo's environments block cannot be "
                f"read: {repo_envs['problem']}", None)
    if not _repo_says_nonprod(environment, repo_envs.get("nonProd", [])):
        return (REFUSE, f"config: environment `{environment}` is not nonProd "
                "in this repo's environments.nonProd", None)
    entry = aws.get("nonProd", {}).get(environment)
    if entry is None:
        return (REFUSE, f"config: no machine entry for nonProd environment "
                f"`{environment}`", None)
    return READY, f"config: nonProd `{environment}`", _target_from(entry)


def _repo_says_nonprod(name, globs):
    # pylint: disable=protected-access
    return cloud_guard._matches(name, globs)


def sealed_env(base, creds, region, sealed_dir):
    """The launched session's environment. Pure: `base` is not modified."""
    env = {k: v for k, v in base.items() if not k.startswith("AWS_")}
    env.update({
        "AWS_ACCESS_KEY_ID": creds["AccessKeyId"],
        "AWS_SECRET_ACCESS_KEY": creds["SecretAccessKey"],
        "AWS_SESSION_TOKEN": creds["SessionToken"],
        "AWS_CREDENTIAL_EXPIRATION": creds["Expiration"],
        "AWS_REGION": region,
        "AWS_DEFAULT_REGION": region,
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_CONFIG_FILE": os.path.join(sealed_dir, "aws-config"),
        "AWS_SHARED_CREDENTIALS_FILE": os.path.join(sealed_dir, "no-credentials"),
        "CREW_UNATTENDED": "1",
    })
    return env


def sealed_settings(store_paths):
    """The `--settings` file: sandbox on, no escape hatch, every store denied
    to sandboxed Bash and to the file tools. Absolute paths are written both
    as `/abs` and `//abs`, so either path convention denies them."""
    deny_read, deny = [], []
    for path in store_paths:
        for form in (path, "/" + path):
            deny_read.append(form)
            deny.extend((f"Read({form})", f"Read({form}/**)"))
    return {
        "sandbox": {"enabled": True, "failIfUnavailable": True,
                    "autoAllowBashIfSandboxed": True,
                    "allowUnsandboxedCommands": False,
                    "filesystem": {"denyRead": deny_read}},
        "permissions": {"deny": deny},
    }


# --- the probes ---------------------------------------------------------------

def _run(argv, env, timeout, cwd=None):
    """`(proc, why)`; `proc` is None and `why` names the failure when the
    process could not be run or timed out. argv list, never a shell."""
    try:
        proc = subprocess.run(argv, env=env, cwd=cwd, capture_output=True,
                              text=True, timeout=timeout, check=False,
                              stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    except OSError as exc:
        return None, f"could not run `{argv[0]}` ({type(exc).__name__})"
    return proc, ""


def _first_line(text):
    for line in (text or "").splitlines():
        if line.strip():
            return line.strip()[:300]
    return ""


def run_export(profile, base):
    """`(state, why, creds)`. Credentials stay in memory; `why` never holds one."""
    env = {k: v for k, v in base.items() if not k.startswith("AWS_")}
    proc, why = _run(["aws", "configure", "export-credentials", "--profile",
                      profile, "--format", "process"], env, EXPORT_TIMEOUT)
    if proc is None:
        return UNKNOWN, f"export: {why}", None
    if proc.returncode != 0:
        tail = _first_line(proc.stderr)
        return UNKNOWN, (f"export: `aws configure export-credentials` exited "
                         f"{proc.returncode}" + (f": {tail}" if tail else "")), None
    try:
        obj = json.loads(proc.stdout)
    except ValueError:
        return UNKNOWN, "export: output is not JSON", None
    state, why = judge_export(obj, datetime.datetime.now(datetime.timezone.utc))
    return state, why, (obj if state == READY else None)


def run_identity(identity, env):
    proc, why = _run(["aws", "sts", "get-caller-identity", "--output", "json"],
                     env, STS_TIMEOUT)
    if proc is None:
        return UNKNOWN, f"identity: {why}", ""
    if proc.returncode != 0:
        tail = _first_line(proc.stderr)
        return UNKNOWN, (f"identity: `aws sts get-caller-identity` exited "
                         f"{proc.returncode}" + (f": {tail}" if tail else "")), ""
    try:
        obj = json.loads(proc.stdout)
    except ValueError:
        return UNKNOWN, "identity: STS output is not JSON", ""
    state, why = judge_identity(obj, identity)
    return state, why, (obj.get("Arn", "") if state == READY else "")


def run_probe(root, settings_path, env, targets):
    nonce = secrets.token_hex(16)
    prompt = _PROBE_PROMPT.format(script=probe_script(targets, nonce))
    proc, why = _run(["claude", "-p", prompt, "--settings", settings_path,
                      "--output-format", "stream-json", "--verbose",
                      "--max-turns", "2", "--allowedTools", "Bash"],
                     env, PROBE_TIMEOUT, cwd=root)
    if proc is None:
        return UNKNOWN, f"sandbox: probe {why}"
    return judge_probe(proc.stdout.splitlines(), nonce, targets)


# --- the chain ----------------------------------------------------------------

def _read_machine():
    path = crew_state.GLOBAL_CONFIG_PATH
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None
    except OSError:
        return "corrupt"
    try:
        return json.loads(text)
    except ValueError:
        return "corrupt"


def _repo_copy_note(root):
    cfg = crew_state.load_config(root)
    if isinstance(cfg, dict) and "unattendedCloud" in cfg:
        return ("the repo's .crew/config.json `unattendedCloud` is ignored: "
                "only the machine config names credentials")
    return ""


def _make_sealed(region, store_paths):
    sealed = tempfile.mkdtemp(prefix="crew-sealed-")
    os.chmod(sealed, 0o700)
    config = os.path.join(sealed, "aws-config")
    settings = os.path.join(sealed, "settings.json")
    _write_new(config, f"[default]\nregion = {region}\n")
    _write_new(settings, json.dumps(sealed_settings(store_paths), indent=2) + "\n")
    return sealed, settings


def _write_new(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def run_checks(root, environment):
    """Run the chain. Returns `(rows, launch)`: `rows` is one
    `{"check", "state", "why"}` per check (`not run` after the first
    non-ready), `launch` is `(env, settings_path, sealed_dir, arn)` when every
    check is ready, else None -- and then no sealed directory is left behind."""
    rows = []
    notes = []

    def done(name, state, why):
        rows.append({"check": name, "state": state, "why": why})
        return state == READY

    def finish():
        for name in CHECKS[len(rows):]:
            rows.append({"check": name, "state": "not run", "why": ""})
        for note in notes:
            rows.append({"check": "note", "state": "note", "why": note})
        return rows

    if _os_name() == "nt":
        done("platform", UNKNOWN,
             "platform: sandbox probe not implemented for native Windows")
        return finish(), None
    done("platform", READY, "platform: posix")

    note = _repo_copy_note(root)
    if note:
        notes.append(note)
    state, why, target = resolve_target(
        _read_machine(), cloud_guard.environments_config(root), environment)
    if not done("config", state, why):
        return finish(), None

    state, why, creds = run_export(target["profile"], dict(os.environ))
    if not done("export", state, why):
        return finish(), None

    store_paths = stores(_homes(), crew_state.GLOBAL_CONFIG_PATH)
    targets = probe_targets(store_paths)
    sealed, settings = _make_sealed(target["region"], store_paths)
    env = sealed_env(dict(os.environ), creds, target["region"], sealed)
    sealed_ok = False
    try:
        state, why, arn = run_identity(target["identity"], env)
        if not done("identity", state, why):
            return finish(), None
        if targets is None:
            done("sandbox", UNKNOWN, "sandbox: a store could not be fully "
                 "listed, so the probe cannot cover it")
            return finish(), None
        if any("\n" in t or "\r" in t for t in targets):
            done("sandbox", UNKNOWN, "sandbox: a store path holds a newline "
                 "and cannot be probed")
            return finish(), None
        state, why = run_probe(root, settings, env, targets)
        if not done("sandbox", state, why):
            return finish(), None
        sealed_ok = True
    finally:
        # Any exit short of every check ready -- a refusal, or an exception --
        # leaves no sealed directory behind.
        if not sealed_ok:
            shutil.rmtree(sealed, ignore_errors=True)
    return finish(), (env, settings, sealed, arn)


def _print_rows(rows, stream):
    for row in rows:
        if row["state"] == "note":
            print(f"note     {row['why']}", file=stream)
        else:
            print(f"{row['state']:<8} {row['check']}: {row['why']}", file=stream)


def _command_problem(command):
    if not command:
        return "no command given after `--`; launch runs `claude` only"
    if os.path.basename(command[0]) != "claude":
        return f"launch runs `claude` only, not `{os.path.basename(command[0])}`"
    for arg in command[1:]:
        if any(arg == flag or arg.startswith(flag + "=") for flag in _SETTINGS_FLAGS):
            return (f"`{arg.split('=')[0]}` would replace the sealed settings; "
                    "launch supplies them itself")
    return ""


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="crew_unattended.py",
        description="Start an unattended claude session holding sealed, "
                    "owner-named read-only cloud credentials, or refuse.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("check", "launch"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--root", default=os.getcwd())
        cmd.add_argument("--environment", default=None)
        if name == "check":
            cmd.add_argument("--json", action="store_true")
    args, rest = parser.parse_known_args(argv)
    root = os.path.abspath(args.root)

    if args.cmd == "check":
        if rest:
            parser.error(f"unexpected arguments: {rest}")
        rows, launch = run_checks(root, args.environment)
        if launch:
            shutil.rmtree(launch[2], ignore_errors=True)
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            _print_rows(rows, sys.stdout)
        return 0 if launch else 1

    command = rest[1:] if rest[:1] == ["--"] else rest
    problem = _command_problem(command)
    if problem:
        print(f"refuse   command: {problem}", file=sys.stderr)
        return 2
    rows, launch = run_checks(root, args.environment)
    _print_rows(rows, sys.stdout if launch else sys.stderr)
    if not launch:
        print("crew_unattended: refused; nothing was started", file=sys.stderr)
        return 1
    env, settings, _sealed, arn = launch
    print(f"crew_unattended: launching as {arn}", flush=True)
    sys.stderr.flush()
    os.execvpe(command[0], [command[0], "--settings", settings] + command[1:], env)
    return 0  # reached only when execvpe is replaced in a test


if __name__ == "__main__":
    sys.exit(main())
