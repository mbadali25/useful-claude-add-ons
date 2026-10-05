"""Start an unattended Claude session holding short-lived, owner-named cloud
credentials, with the machine's credential stores sealed -- or refuse (T-0044).

    python3 crew_unattended.py check  --root R [--environment NAME] [--json]
    python3 crew_unattended.py launch --root R [--environment NAME] -- claude [args...]

This is the boundary T-0005's guard cannot be. `cloud_guard.py` reads command
lines, so a renamed binary, `python -c` or a script file walks past it. What
holds whatever the command line says is what the process can authenticate as
and what it can read. So `launch` hands the session temporary credentials for
ONE identity the machine owner named, strips every inherited cloud and forge
credential variable, and denies the session's Bash and file tools every
credential store on the machine for reads and writes (`STORE_PATHS`: `~/.aws`
whole, `~/.azure`, `~/.terraform.d/credentials.tfrc.json`, `~/.config/gcloud`,
`~/.kube`, `~/.config/gh`, `~/.docker/config.json`, and crew's own machine
config so the session cannot rename its identity).

The session and the probe both start as
`<claude> --settings <sealed> --setting-sources user ...`, from `--root`, with
the same executable: a cloned repo's `.claude/settings.json` and
`.claude/settings.local.json` never load, so they cannot add excluded
commands, read allowances, hooks or an `env` block to the sealed session.

Checks, in order; the first that is not `ready` stops the chain:

  1. platform  native Windows has no sandbox probe here: unknown.
  2. config    `unattendedCloud` from the MACHINE file alone
               (`~/.claude/crew/config.json`). A repo copy is reported as
               ignored. `--environment NAME` needs a machine `nonProd` entry
               AND the repo's `environments.nonProd` classifying NAME as
               nonProd -- both layers agree, or it refuses.
  3. settings  fail closed on the settings files around the sealed ones: a
               repo file with a `sandbox` key or a `Read` allow rule, or a
               user file with `sandbox.excludedCommands`, an `allowRead` that
               could re-open a store, or `filesystem.disabled: true`. In a
               linked worktree the main checkout's local file is read too.
  4. version   `<claude> --version` must print a version at or above
               `MIN_CLAUDE_VERSION`: `--setting-sources` drops a source's
               sandbox entries only from 2.1.246 on. Older, unparseable, a
               non-zero exit or a timeout is `unknown`.
  5. export    `aws configure export-credentials --format process`, read into
               memory only. No SessionToken or Expiration is static keys:
               refuse. Under 15 minutes left: refuse.
  6. identity  `aws sts get-caller-identity` in the sealed environment must
               print an ARN that STARTS WITH the named identity prefix.
  7. sandbox   one headless `claude -p` call in the sealed settings, from the
               repo root, runs a probe script that tries to open every store
               root that exists and a bounded sample inside each. Its verdict
               is parsed from the stream-json TOOL RESULTS only, never from
               the model's prose.

Every check returns `(state, why)` with `state` one of `ready`, `refuse` or
`unknown`. `unknown` refuses exactly like `refuse` and keeps its own label:
"could not tell" is never printed as a verdict and never becomes `ready`.

Never: it never falls back to ambient credentials, never writes, copies or
logs a credential (the sealed directory, `crew-sealed-<pid>-*`, holds a
region-only AWS config and the sealed settings file, nothing else; the next
launch removes one whose process has exited), never writes to `~/.aws`, never
runs `aws sso login`.
"""

import argparse
import datetime
import json
import os
import re
import secrets
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile

try:
    import pwd  # Unix only; native Windows refuses before it is needed.
except ImportError:  # pragma: no cover - exercised by Windows CI collection
    pwd = None

import cloud_guard
import crew_config
import crew_state

READY, REFUSE, UNKNOWN = "ready", "refuse", "unknown"
CHECKS = ("platform", "config", "settings", "version", "export", "identity",
          "sandbox")

# `--setting-sources` makes Claude Code ignore an excluded source's
# `sandbox.filesystem` entries, `Edit` rules and `Read` deny rules when it
# builds the sandbox only from this version on (code.claude.com/docs/en/
# sandboxing, "Requires Claude Code v2.1.246 or later"). Below it, a repo's
# settings could still shape the sealed sandbox, so the launch refuses.
MIN_CLAUDE_VERSION = (2, 1, 246)
# `claude --version` prints `2.1.289 (Claude Code)`; the suffix is optional,
# anything else (a pre-release tag, extra words, a second line first) does
# not parse and is `unknown`.
_VERSION_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?: \(Claude Code\))?$")

VERSION_TIMEOUT = 30
EXPORT_TIMEOUT = 60
STS_TIMEOUT = 30
PROBE_TIMEOUT = 300
MIN_LIFETIME = datetime.timedelta(minutes=15)
DEFAULT_REGION = "us-east-1"
# The probe opens every store ROOT, plus a bounded sample of the files under a
# store directory: at most this many per directory and in all per store. The
# sandbox denies a path and everything under it, so the root is the real test;
# the sample catches a deny that stopped at the directory itself. A bound, not
# a walk of everything, so a store with thousands of cache files neither
# refuses forever nor overflows the Bash tool's output.
PROBE_SAMPLE_PER_DIR = 2
PROBE_SAMPLE_PER_STORE = 12

# Credential stores, relative to each home. `~/.aws` whole covers
# credentials, config, sso/cache and cli/cache.
STORE_PATHS = (
    ".aws", ".azure", os.path.join(".terraform.d", "credentials.tfrc.json"),
    os.path.join(".config", "gcloud"), ".kube", os.path.join(".config", "gh"),
    os.path.join(".docker", "config.json"),
    os.path.join(".claude", "crew", "config.json"),
    # Forge credentials git and ssh read on their own: SSH keys, git's
    # credential-store files (gitcredentials(7)).
    ".ssh", ".git-credentials", os.path.join(".config", "git", "credentials"),
    # Terraform's CLI config can hold an HCP Terraform token too.
    ".terraformrc")

# Inherited variables that carry, or point at, a cloud or forge credential.
# Dropped from the launched session's environment (and from the export's).
_STRIP_PREFIXES = ("AWS_", "AZURE_", "ARM_", "CLOUDSDK_", "GOOGLE_",
                   "TF_TOKEN_", "GIT_CONFIG_KEY_", "GIT_CONFIG_VALUE_")
_STRIP_NAMES = frozenset((
    "KUBECONFIG", "GITHUB_TOKEN", "GH_TOKEN", "GH_ENTERPRISE_TOKEN",
    "GITHUB_ENTERPRISE_TOKEN", "DOCKER_CONFIG", "DOCKER_AUTH_CONFIG",
    "TF_CLI_CONFIG_FILE", "TFE_TOKEN",
    # Git and SSH credential pointers: an askpass program or an agent socket
    # hands an inherited forge identity to `git` (gitcredentials(7)), and
    # environment-set config can name a credential helper.
    "GIT_ASKPASS", "SSH_ASKPASS", "SSH_AUTH_SOCK", "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT", "GITLAB_TOKEN", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_SYSTEM",
    "GIT_SSH", "GIT_SSH_COMMAND", "TERRAFORM_CONFIG",
    # Pointers that move a CLI's config (and its stored token) away from the
    # default path the stores deny: gh's own, and every XDG-config tool's.
    "GH_CONFIG_DIR", "XDG_CONFIG_HOME"))

# The launched session and the probe load the user's settings and the sealed
# `--settings` only: a cloned repo's `.claude/settings.json` and
# `.claude/settings.local.json` never load, so the repo cannot add
# `sandbox.excludedCommands`, `sandbox.filesystem.allowRead`, hooks (which run
# outside the sandbox) or an `env` block to the sealed session.
SETTING_SOURCES = "user"

_SEALED_PREFIX = "crew-sealed-"
_SEALED_RE = re.compile(r"^crew-sealed-(\d+)-")

# Flags that would replace or drop the sealed settings for the launched session.
_SETTINGS_FLAGS = ("--settings", "--setting-sources")

_GLOB_CHARS = ("*", "?", "[")

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
    if pwd is None:
        return ""
    try:
        return pwd.getpwuid(os.getuid()).pw_dir
    except (KeyError, OSError):
        return ""


# --- the pure core ------------------------------------------------------------

def stores(homes, machine_config):
    """The credential stores the session is denied, expanded per home."""
    out = []
    for home in homes:
        for rel in STORE_PATHS:
            path = os.path.join(home, rel)
            if path not in out:
                out.append(path)
    if machine_config and machine_config not in out:
        out.append(machine_config)
    return out


def probe_targets(store_paths):
    """Every store that exists, plus a bounded sample of the files inside a
    store directory (`PROBE_SAMPLE_PER_DIR` per directory, at most
    `PROBE_SAMPLE_PER_STORE` per store, walked in sorted order). The size is
    bounded by construction, so a large store never refuses the launch; a
    name holding a newline is not sampled, and a walk error only shortens the
    sample -- the store root itself is always probed."""
    out = []
    for store in store_paths:
        if not os.path.lexists(store):
            continue
        out.append(store)
        if not os.path.isdir(store) or os.path.islink(store):
            continue
        taken = 0
        for here, dirs, files in os.walk(store):
            dirs.sort()
            picked = [name for name in sorted(files)
                      if "\n" not in name and "\r" not in name]
            for name in picked[:PROBE_SAMPLE_PER_DIR]:
                if taken >= PROBE_SAMPLE_PER_STORE:
                    break
                out.append(os.path.join(here, name))
                taken += 1
            if taken >= PROBE_SAMPLE_PER_STORE:
                break
    return out


def probe_script(targets, nonce):
    """The one Bash command the probe session runs. It prints `NONCE <nonce>`
    FIRST, then per target `OPEN <i>` (some reader opened it), `SHUT <i>`
    (every reader was refused) or `ERR <i>` (could not tell) -- `<i>` the
    target's index, so the output stays short whatever the paths are -- and
    `END <nonce>` LAST. It prints no contents."""
    lines = [
        "echo NONCE " + nonce,
        "probe() { i=\"$1\"; t=\"$2\"",
        "  if [ -d \"$t\" ]; then ls -- \"$t\" >/dev/null 2>&1 && "
        "{ echo \"OPEN $i\"; return; }",
        "  else head -c1 -- \"$t\" >/dev/null 2>&1 && "
        "{ echo \"OPEN $i\"; return; }; fi",
        "  v=$(python3 -c 'import os,sys\n"
        "p=sys.argv[1]\n"
        "try:\n"
        "    os.listdir(p) if os.path.isdir(p) else open(p,\"rb\").read(1)\n"
        "    print(\"OPEN\")\n"
        "except OSError:\n"
        "    print(\"SHUT\")' \"$t\" 2>/dev/null)",
        "  case \"$v\" in OPEN) echo \"OPEN $i\";; SHUT) echo \"SHUT $i\";; "
        "*) echo \"ERR $i\";; esac; }",
    ]
    for index, target in enumerate(targets):
        lines.append(f"probe {index} " + shlex.quote(target))
    lines.append("echo END " + nonce)
    return "\n".join(lines)


def _tool_commands(stream_lines):
    """`{tool_use id: Bash command}` for every Bash `tool_use` block."""
    out = {}
    for line in stream_lines:
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") if isinstance(event, dict) else None
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if isinstance(block, dict) and block.get("type") == "tool_use" \
                    and block.get("name") == "Bash" and isinstance(block.get("id"), str):
                given = block.get("input")
                command = given.get("command") if isinstance(given, dict) else None
                out[block["id"]] = command if isinstance(command, str) else None
    return out


def _tool_results(stream_lines, errors=None, ids=None):
    """The text of every `tool_result` block in stream-json output. When
    `errors` is a list, each block's `is_error` flag (True when set) is
    appended to it, one per text; when `ids` is a list, its `tool_use_id`."""
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
            if errors is not None:
                errors.append(block.get("is_error") is True)
            if ids is not None:
                ids.append(block.get("tool_use_id"))
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


def judge_probe(stream_lines, nonce, targets, returncode=0, script=None):
    """`(state, why)` for the sandbox probe's stream-json output. A store
    reported OPEN refuses whatever else happened; otherwise a tool result
    flagged `is_error` or a probe process that exited nonzero is `unknown`,
    never `ready`, whatever markers its output holds. With `script` (the
    launch always passes it) only the result of a Bash `tool_use` whose
    command IS the probe script can vouch for `ready`: a model that ran
    anything else measured nothing."""
    errors, ids = [], []
    results = _tool_results(stream_lines, errors, ids)
    if not results:
        return UNKNOWN, "probe made no tool call, so nothing was measured"
    seen = {}
    rank = {"SHUT": 0, "ERR": 1, "OPEN": 2}
    lines = [line.strip() for text in results for line in text.splitlines()]
    for line in lines:
        word, _, rest = line.partition(" ")
        if word in rank and rest.isdigit() and int(rest) < len(targets):
            index = int(rest)
            # Worst wins: OPEN over ERR over SHUT, whatever the order.
            if rank[word] >= rank.get(seen.get(index), -1):
                seen[index] = word
    opened = [targets[i] for i, word in sorted(seen.items()) if word == "OPEN"]
    if opened:
        return REFUSE, f"sandbox: the session can read a store: OPEN {opened[0]}"
    if f"NONCE {nonce}" not in lines:
        first = next((line for line in lines if line), "")
        return UNKNOWN, f"sandbox: unavailable: {first or '(empty tool result)'}"
    if f"END {nonce}" not in lines:
        return UNKNOWN, ("sandbox: the probe output has no end marker, so it "
                         "ran short or was cut off")
    if any(errors):
        return UNKNOWN, "sandbox: the probe's tool call reported an error, so nothing is proven"
    if script is not None:
        commands = _tool_commands(stream_lines)
        ran = [commands.get(i) for i in ids]
        if not ran or any(command is None or command.strip() != script.strip()
                          for command in ran):
            return UNKNOWN, ("sandbox: the probe's Bash command was not the probe script, "
                             "so nothing was measured")
    if returncode != 0:
        return UNKNOWN, f"sandbox: the probe session exited {returncode}, so nothing is proven"
    for index, target in enumerate(targets):
        if index not in seen:
            return UNKNOWN, f"sandbox: store not reported by the probe: {target}"
        if seen[index] == "ERR":
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


def stripped_env(base):
    """`base` minus every variable that carries or points at a cloud or forge
    credential (`_STRIP_PREFIXES`, `_STRIP_NAMES`). Pure."""
    return {k: v for k, v in base.items()
            if not k.startswith(_STRIP_PREFIXES) and k not in _STRIP_NAMES}


def sealed_env(base, creds, region, sealed_dir):
    """The launched session's environment. Pure: `base` is not modified."""
    env = stripped_env(base)
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
        # An empty `credential.helper` resets git's helper list, so a helper
        # the user's ~/.gitconfig names (`store --file <anywhere>`, a script)
        # never answers git in the sealed session. Environment config wins
        # over every config file (git-config(1), GIT_CONFIG_COUNT).
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "credential.helper",
        "GIT_CONFIG_VALUE_0": "",
    })
    return env


def sealed_settings(store_paths, protected=()):
    """The `--settings` file: sandbox on, no escape hatch, filesystem
    isolation forced on, every store denied to sandboxed Bash for reads AND
    writes, and to the file tools as `Read(...)` and `Edit(...)` denies.
    `protected` are paths the session may read but must not change: the
    sealed directory (this file and the region-only AWS config) and the
    user settings file, so the session cannot rewrite its own identity or
    settings mid-run (Claude Code reloads settings files when they change).

    Sandbox paths use the standard convention (`/abs`); permission rules use
    `//abs` for an absolute path (code.claude.com/docs/en/permissions, "Read
    and Edit"). Both spellings go into both lists: a deny only narrows, so
    the extra spelling costs nothing if one convention ever changes.
    Claude Code consults only `Read` and `Edit` path rules -- a `Write(...)`
    rule is accepted and never read -- so `Edit` covers Write too."""
    deny_read, deny_write, deny = [], [], []
    for path in store_paths:
        for form in (path, "/" + path):
            deny_read.append(form)
            deny_write.append(form)
            deny.extend((f"Read({form})", f"Read({form}/**)",
                         f"Edit({form})", f"Edit({form}/**)"))
    for path in protected:
        for form in (path, "/" + path):
            deny_write.append(form)
            deny.extend((f"Edit({form})", f"Edit({form}/**)"))
    return {
        "sandbox": {"enabled": True, "failIfUnavailable": True,
                    "autoAllowBashIfSandboxed": True,
                    "allowUnsandboxedCommands": False,
                    "filesystem": {"disabled": False, "denyRead": deny_read,
                                   "denyWrite": deny_write}},
        "permissions": {"deny": deny},
    }


def _user_settings_path():
    base = os.environ.get("CLAUDE_CONFIG_DIR") or os.path.join(
        os.path.expanduser("~"), ".claude")
    return os.path.join(base, "settings.json")


def _git_top(root):
    here = os.path.realpath(root)
    while True:
        if os.path.lexists(os.path.join(here, ".git")):
            return here
        up = os.path.dirname(here)
        if up == here:
            return ""
        here = up


def _main_checkout(top):
    """`(main, why)` for the git root `top`. When `top/.git` is a file (a
    linked worktree), `main` is the main checkout: the parent of the common
    git directory its `gitdir:` names (through `commondir`). `main` is ""
    when `top` is not a linked worktree (`.git` a directory, or a gitdir with
    no `commondir`, as a submodule has). `why` names a `.git` file or
    `commondir` that cannot be read, which the caller treats as unknown."""
    dotgit = os.path.join(top, ".git")
    if not os.path.isfile(dotgit):
        return "", ""
    try:
        with open(dotgit, encoding="utf-8") as handle:
            first = handle.readline().strip()
    except (OSError, UnicodeDecodeError) as exc:
        return "", f"`{dotgit}` cannot be read ({type(exc).__name__})"
    if not first.startswith("gitdir:") or not first[7:].strip():
        return "", f"`{dotgit}` has no `gitdir:` line"
    gitdir = os.path.join(top, first[7:].strip())
    common_file = os.path.join(gitdir, "commondir")
    try:
        with open(common_file, encoding="utf-8") as handle:
            common = handle.readline().strip()
    except FileNotFoundError:
        if os.path.isdir(gitdir):
            return "", ""
        return "", f"`{dotgit}` names `{gitdir}`, which is not a directory"
    except (OSError, UnicodeDecodeError) as exc:
        return "", f"`{common_file}` cannot be read ({type(exc).__name__})"
    if not common:
        return "", f"`{common_file}` is empty"
    common = os.path.realpath(os.path.join(gitdir, common))
    return os.path.dirname(common), ""


def repo_settings_files(root):
    """`(files, why)`: the project and local settings files Claude Code
    would read for a session started in `root` -- `.claude/settings.json`
    from the working directory, `.claude/settings.local.json` from it and
    from the git root, and, in a linked worktree, from the MAIN checkout's
    root too (code.claude.com/docs/en/settings: "In a worktree, it uses the
    file at the main checkout's root"). `why` is non-empty when a worktree's
    main checkout cannot be found: could not tell which files load."""
    out = [os.path.join(root, ".claude", "settings.json"),
           os.path.join(root, ".claude", "settings.local.json")]
    top = _git_top(root)
    if top and os.path.realpath(top) != os.path.realpath(root):
        out.append(os.path.join(top, ".claude", "settings.local.json"))
    if top:
        checkout, why = _main_checkout(top)
        if why:
            return out, why
        if checkout and os.path.realpath(checkout) != os.path.realpath(top):
            out.append(os.path.join(checkout, ".claude", "settings.local.json"))
    return out, ""


def _load_settings(path):
    """`(obj, why)`: `obj` is None when absent; `why` names a file that exists
    but cannot be read as a JSON object."""
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None, ""
    except UnicodeDecodeError:
        return None, f"`{path}` is not UTF-8"
    except OSError as exc:
        return None, f"`{path}` cannot be read ({type(exc).__name__})"
    try:
        obj = json.loads(text)
    except ValueError:
        return None, f"`{path}` is not JSON"
    if not isinstance(obj, dict):
        return None, f"`{path}` is not a JSON object"
    return obj, ""


def _read_allow_rules(obj):
    perms = obj.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if not isinstance(allow, list):
        return []
    return [r for r in allow if isinstance(r, str)
            and (r.strip() == "Read" or r.strip().startswith("Read("))]


def _expand(entry, homes, base_dir):
    if entry == "~" or entry.startswith("~/"):
        return [os.path.normpath(home + entry[1:]) for home in homes]
    if entry.startswith("/"):
        return [os.path.normpath("/" + entry.lstrip("/"))]
    return [os.path.normpath(os.path.join(base_dir, entry))]


def _reopens_a_store(entry, homes, base_dir, store_paths):
    """True when a `sandbox.filesystem.allowRead` entry could re-open a store:
    a glob, or a path at or under one (the narrower rule wins, per
    code.claude.com/docs/en/sandboxing)."""
    if not isinstance(entry, str) or any(c in entry for c in _GLOB_CHARS):
        return True
    for path in _expand(entry, homes, base_dir):
        for store in store_paths:
            if path == store or path.startswith(store.rstrip("/") + "/"):
                return True
    return False


def _credential_env(obj):
    """The first `env` key in a settings object that the launch strips from the
    session's environment (`_STRIP_PREFIXES`, `_STRIP_NAMES`), or None. Claude
    Code applies a loaded settings file's `env` to its process, so such a key
    would put a credential, or a pointer at one, back after the strip. An
    `env` that is not an object is reported as itself: it cannot be judged."""
    env = obj.get("env") if isinstance(obj, dict) else None
    if env is None:
        return None
    if not isinstance(env, dict):
        return "env"
    for key in env:
        if str(key).startswith(_STRIP_PREFIXES) or key in _STRIP_NAMES:
            return key
    return None


def judge_settings(repo_files, user_file, homes, store_paths):
    """`(state, why)` for the settings files around the sealed `--settings`.

    The launch passes `--setting-sources user`, so a repo's project and local
    files do not load. This check fails closed anyway, in case they ever do:
    any `sandbox` key or `Read` allow rule in them refuses. The user file DOES
    load, and its lists merge with the sealed ones, so an `excludedCommands`
    entry (it runs unsandboxed), an `allowRead` that could re-open a store, or
    `filesystem.disabled: true` refuses, and so does an `env` key the launch
    strips (an AWS credential set there would replace the sealed one). A file
    that exists but cannot be read is `unknown`. `repo_files` and `user_file` are `(path, obj, why)`."""
    for path, obj, why in repo_files:
        if why:
            return UNKNOWN, f"settings: {why}"
        if obj is None:
            continue
        if "sandbox" in obj:
            return REFUSE, (f"settings: `{path}` sets `sandbox`; a repo may not "
                            "shape the sealed sandbox")
        key = _credential_env(obj)
        if key:
            return REFUSE, (f"settings: `{path}` sets `{key}` in `env`; a repo may not "
                            "put a credential into a sealed session")
        rules = _read_allow_rules(obj)
        if rules:
            return REFUSE, (f"settings: `{path}` allows `{rules[0]}`; a repo "
                            "may not widen reads in a sealed session")
    path, obj, why = user_file
    if why:
        return UNKNOWN, f"settings: {why}"
    key = _credential_env(obj)
    if key == "env":
        return UNKNOWN, f"settings: `{path}` `env` is not an object"
    if key:
        return REFUSE, (f"settings: `{path}` sets `{key}` in `env`; Claude Code applies it "
                        "to the session, replacing the sealed credentials or pointing past "
                        "them")
    box = obj.get("sandbox") if isinstance(obj, dict) else None
    if box is not None and not isinstance(box, dict):
        return UNKNOWN, f"settings: `{path}` `sandbox` is not an object"
    box = box or {}
    excluded = box.get("excludedCommands")
    if excluded:
        return REFUSE, (f"settings: `{path}` sets `sandbox.excludedCommands` "
                        f"({excluded!r}); an excluded command runs unsandboxed "
                        "and can read the stores")
    fs = box.get("filesystem") or {}
    if not isinstance(fs, dict):
        return UNKNOWN, f"settings: `{path}` `sandbox.filesystem` is not an object"
    if fs.get("disabled") is True:
        return REFUSE, (f"settings: `{path}` sets `sandbox.filesystem.disabled`; "
                        "the stores would not be denied")
    allow = fs.get("allowRead") or []
    if not isinstance(allow, list):
        return UNKNOWN, f"settings: `{path}` `sandbox.filesystem.allowRead` is not a list"
    base_dir = os.path.dirname(path)
    for entry in allow:
        if _reopens_a_store(entry, homes, base_dir, store_paths):
            return REFUSE, (f"settings: `{path}` `sandbox.filesystem.allowRead` "
                            f"entry {entry!r} could re-open a credential store")
    return READY, "settings: no settings file widens the sealed sandbox"


def run_settings(root, store_paths, homes):
    files, why = repo_settings_files(root)
    if why:
        return UNKNOWN, (f"settings: cannot find the main checkout of this "
                         f"worktree, so its local settings are unchecked: {why}")
    repo = []
    for path in files:
        obj, why = _load_settings(path)
        repo.append((path, obj, why))
    user = _user_settings_path()
    obj, why = _load_settings(user)
    return judge_settings(repo, (user, obj, why), homes, store_paths)


# --- the probes ---------------------------------------------------------------

def _run(argv, env, timeout, cwd=None):
    """`(proc, why)`; `proc` is None and `why` names the failure when the
    process could not be run or timed out. argv list, never a shell."""
    try:
        # Output that is not UTF-8 is `unknown` (below), never a traceback and
        # never a replacement character a judge could still read as valid.
        proc = subprocess.run(argv, env=env, cwd=cwd, capture_output=True,
                              text=True, encoding="utf-8", errors="strict",
                              timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except subprocess.TimeoutExpired:
        return None, f"timed out after {timeout}s"
    except UnicodeDecodeError:
        return None, f"`{os.path.basename(argv[0])}` wrote output that is not UTF-8"
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
    env = stripped_env(base)
    proc, why = _run(["aws", "configure", "export-credentials", "--profile",
                      profile, "--format", "process"], env, EXPORT_TIMEOUT)
    if proc is None:
        return UNKNOWN, f"export: {why}", None
    if proc.returncode != 0:
        # Never its stderr: a failing credential command may print a secret.
        return UNKNOWN, (f"export: `aws configure export-credentials --profile {profile}` "
                         f"exited {proc.returncode} (run it by hand to see why)"), None
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
        # Never its stderr: a failing credential command may print a secret.
        return UNKNOWN, (f"identity: `aws sts get-caller-identity` exited "
                         f"{proc.returncode} (run it by hand to see why)"), ""
    try:
        obj = json.loads(proc.stdout)
    except ValueError:
        return UNKNOWN, "identity: STS output is not JSON", ""
    state, why = judge_identity(obj, identity)
    return state, why, (obj.get("Arn", "") if state == READY else "")


def judge_version(returncode, stdout):
    """`(state, why)` for `claude --version`. Ready only for a clean exit
    whose first non-blank line parses as a version at or above
    `MIN_CLAUDE_VERSION`; everything else is `unknown`, since the sealed
    settings cannot be shown to keep a repo's sandbox entries out."""
    floor = ".".join(str(n) for n in MIN_CLAUDE_VERSION)
    if returncode != 0:
        return UNKNOWN, f"version: `claude --version` exited {returncode}"
    line = _first_line(stdout)
    match = _VERSION_RE.match(line)
    if not match:
        return UNKNOWN, (f"version: cannot parse `claude --version` output "
                         f"{line[:80]!r}; need {floor} or later")
    got = tuple(int(part) for part in match.groups())
    text = ".".join(str(n) for n in got)
    if got < MIN_CLAUDE_VERSION:
        return UNKNOWN, (f"version: Claude Code {text} is older than {floor}, "
                         "below which `--setting-sources` does not keep a "
                         "repo's sandbox settings out of the sealed session")
    return READY, f"version: Claude Code {text}"


def run_version(exe, root, env):
    """The version of the SAME executable the probe and the launch use."""
    if exe is None:
        return UNKNOWN, "version: `claude` is not on PATH, so nothing can be probed"
    proc, why = _run([exe, "--version"], env, VERSION_TIMEOUT, cwd=root)
    if proc is None:
        return UNKNOWN, f"version: `claude --version` {why}"
    return judge_version(proc.returncode, proc.stdout)


def sealed_flags(settings_path):
    """The flags the launch AND the probe put first: the sealed settings, and
    no project or local settings source."""
    return ["--settings", settings_path, "--setting-sources", SETTING_SOURCES]


def run_probe(exe, root, settings_path, env, targets):
    """The probe runs the SAME executable the launch will exec, from the
    same directory, with the same leading flags."""
    nonce = secrets.token_hex(16)
    script = probe_script(targets, nonce)
    prompt = _PROBE_PROMPT.format(script=script)
    proc, why = _run([exe, "-p", prompt] + sealed_flags(settings_path) + [
                      "--output-format", "stream-json", "--verbose",
                      "--max-turns", "2", "--allowedTools", "Bash"],
                     env, PROBE_TIMEOUT, cwd=root)
    if proc is None:
        return UNKNOWN, f"sandbox: probe {why}"
    return judge_probe(proc.stdout.splitlines(), nonce, targets, proc.returncode, script)


# --- the chain ----------------------------------------------------------------

def _read_machine():
    path = crew_state.GLOBAL_CONFIG_PATH
    try:
        with open(path, encoding="utf-8-sig") as handle:
            text = handle.read()
    except FileNotFoundError:
        return None
    except (OSError, UnicodeDecodeError):
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
    """The sealed directory, named for this process: `exec` keeps the pid, so
    the launched session runs under it and a later launch can tell a sealed
    directory still in use from a stale one (`sweep_stale_sealed`)."""
    sealed = tempfile.mkdtemp(prefix=f"{_SEALED_PREFIX}{os.getpid()}-")
    os.chmod(sealed, 0o700)
    config = os.path.join(sealed, "aws-config")
    settings = os.path.join(sealed, "settings.json")
    _write_new(config, f"[default]\nregion = {region}\n")
    protected = [sealed, _user_settings_path()]
    _write_new(settings, json.dumps(sealed_settings(store_paths, protected),
                                    indent=2) + "\n")
    return sealed, settings


def _pid_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True  # it exists but is not ours to signal: leave it
    return True


def sweep_stale_sealed(tmpdir=None):
    """Remove `crew-sealed-<pid>-*` directories this user owns whose process
    has exited. A launched session replaced the launcher with `exec`, so no
    process is left to clean up after it; the next launch does. A directory
    whose pid is alive (the session, or a reused pid) is left alone -- its
    settings file may be in use. Returns the paths removed."""
    tmpdir = tmpdir or tempfile.gettempdir()
    removed = []
    try:
        names = os.listdir(tmpdir)
    except OSError:
        return removed
    for name in names:
        match = _SEALED_RE.match(name)
        if not match:
            continue
        pid = int(match.group(1))
        if pid == os.getpid() or _pid_alive(pid):
            continue
        path = os.path.join(tmpdir, name)
        try:
            info = os.lstat(path)
        except OSError:
            continue
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid():
            continue
        shutil.rmtree(path, ignore_errors=True)
        removed.append(path)
    return removed


def _write_new(path, text):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def resolve_exe(name, path_var):
    """The absolute file `name` names: itself when it holds a separator, else
    its first hit on `path_var`. `None` when there is none. The probe and the
    exec both use this one file, so what was probed is what is started."""
    if os.sep in name or (os.altsep and os.altsep in name):
        full = os.path.abspath(name)
        return full if os.path.isfile(full) and os.access(full, os.X_OK) else None
    found = shutil.which(name, path=path_var if path_var is not None
                         else os.defpath)
    return os.path.abspath(found) if found else None


def run_checks(root, environment, exe=None):
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

    homes = _homes()
    store_paths = stores(homes, crew_state.GLOBAL_CONFIG_PATH)
    state, why = run_settings(root, store_paths, homes)
    if not done("settings", state, why):
        return finish(), None

    if exe is None:
        exe = resolve_exe("claude", os.environ.get("PATH"))
    state, why = run_version(exe, root, stripped_env(dict(os.environ)))
    if not done("version", state, why):
        return finish(), None

    state, why, creds = run_export(target["profile"], dict(os.environ))
    if not done("export", state, why):
        return finish(), None

    targets = probe_targets(store_paths)
    sealed, settings = _make_sealed(target["region"], store_paths)
    env = sealed_env(dict(os.environ), creds, target["region"], sealed)
    sealed_ok = False
    try:
        state, why, arn = run_identity(target["identity"], env)
        if not done("identity", state, why):
            return finish(), None
        if any("\n" in t or "\r" in t for t in targets):
            done("sandbox", UNKNOWN, "sandbox: a store path holds a newline "
                 "and cannot be probed")
            return finish(), None
        state, why = run_probe(exe, root, settings, env, targets)
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
    root = os.path.realpath(args.root)
    sweep_stale_sealed()

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
    exe = resolve_exe(command[0], os.environ.get("PATH"))
    if exe is None:
        print(f"refuse   command: `{command[0]}` is not an executable file or "
              "on PATH", file=sys.stderr)
        return 2
    if not os.path.isdir(root):
        print(f"refuse   command: --root `{root}` is not a directory",
              file=sys.stderr)
        return 2
    rows, launch = run_checks(root, args.environment, exe)
    _print_rows(rows, sys.stdout if launch else sys.stderr)
    if not launch:
        print("crew_unattended: refused; nothing was started", file=sys.stderr)
        return 1
    env, settings, sealed, arn = launch
    try:
        # The probe ran from `root`; the session starts there too, whatever
        # directory the launcher was started from.
        os.chdir(root)
    except OSError as exc:
        shutil.rmtree(sealed, ignore_errors=True)
        print(f"refuse   command: cannot enter --root ({type(exc).__name__}); "
              "nothing was started", file=sys.stderr)
        return 1
    print(f"crew_unattended: launching as {arn}", flush=True)
    sys.stderr.flush()
    os.execvpe(exe, [command[0]] + sealed_flags(settings) + command[1:], env)
    return 0  # reached only when execvpe is replaced in a test


if __name__ == "__main__":
    sys.exit(main())
