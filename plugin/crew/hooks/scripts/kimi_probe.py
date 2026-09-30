"""Can the Kimi Code CLI review right now? One of five states, never a guess.

    python3 kimi_probe.py [--model ID] [--json]

Prints `kimi: <state> - <reason>`. Exit 0 only for `ok`, 1 for every other
state, 2 for a usage error. The live stage SPENDS ONE REQUEST.

WHY IT EXISTS (T-0028). A provider on PATH is not a provider that can review:
a logged-out or out-of-quota CLI resolves on PATH and then fails at the first
call. `review_run.py` reserves a review round BEFORE it launches the reviewer,
so a quota wall hit after reservation spends a round for nothing -- which is
how a Codex quota error burned one. This probe is built to run BEFORE the round
is reserved, and only `ok` may launch. `review_run.py` does not launch Kimi yet:
that wiring is the review harness's, and lands as L-0527 (tooling only).
Until then the probe runs from `providers.sh --probe-kimi` or directly.

THE STATES, each its own value:

  ok                 a real `kimi -p` answered PROBE_OK, exit 0
  not-installed      no `kimi` on PATH
  not-authenticated  no config.toml; the resolved provider has neither an
                     `api_key` nor an `oauth` block with a file under
                     `<home>/credentials/`; no model given and no
                     `default_model`; or the live call answered 401 /
                     `invalid_authentication_error` / "No model configured"
  rate-limited       the live call answered with a Moonshot 429 code
                     (`exceeded_current_quota_error`, `rate_limit_reached_error`,
                     `engine_overloaded_error`) or the 2.1.1 bundle's quota
                     wording
  unknown            EVERYTHING ELSE: unrecognised output, exit 0 without
                     PROBE_OK, a timeout, an id no `type = "kimi"` alias serves,
                     an unparseable config.toml, `tomllib` unavailable, a launch
                     that raised. "Could not tell" never becomes `ok`.

THE MODEL. `-m` takes a config.toml ALIAS (`kimi-code/k3`), not the id (`k3`).
The id is resolved to the alias whose `model` equals it and whose provider has
`type = "kimi"`; the provider type is what proves the family is Kimi. An id
given AS an alias is accepted as that alias.

READ-ONLY. The live call gets the controls the review launch will get
(L-0527): `--agent-file` naming the agent that allows
Read, Grep and Glob and disallows Write, Edit and Bash, and an empty
`--skills-dir`. It runs in a throwaway directory, removed afterwards, rather
than in the caller's directory -- so it neither auto-loads that repository's
AGENTS.md nor lands a stray relative write there. `write_agent_file` is the ONE
definition of that agent, for the review launch to reuse.

SECRETS. The static stage reads config.toml for STRUCTURE only: whether a key
is present, never its value, and nothing under `credentials/` is opened --
only counted. Anything echoed from the CLI's stderr goes through `redact`
first. The child environment drops `KIMI_CODE_INFINITE_RETRY` (a failed request
would retry forever) and every `KIMI_MODEL_*` override, and sets
`KIMI_CODE_NO_AUTO_UPDATE=1`.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile

try:
    import tomllib as _tomllib  # Python 3.11+, stdlib
except ImportError:  # pragma: no cover - exercised only on 3.8-3.10
    _tomllib = None

STATES = ("ok", "not-installed", "not-authenticated", "rate-limited", "unknown")
PROBE_PROMPT = "Reply with exactly: PROBE_OK"
PROBE_MARKER = "PROBE_OK"
DEFAULT_TIMEOUT = 60
AGENT_FILE = "kimi-reviewer.md"
PROVIDER_NOT_A_NAME = "the model's provider reference is not a name"
NO_SKILLS = "kimi-no-skills"

_AUTH_MARKERS = re.compile(
    r"invalid_authentication_error|No model configured|kimi login|\bUnauthori[sz]ed\b",
    re.IGNORECASE)
_AUTH_STATUS = re.compile(r'\b401\b|"status_code":\s*401\b')
_QUOTA_MARKERS = re.compile(
    r"exceeded_current_quota_error|rate_limit_reached_error|engine_overloaded_error"
    r"|exceeded your current (?:token )?quota|check your account balance"
    r"|insufficient balance|recharge your account|please recharge"
    r"|account (?:is )?in arrears",
    re.IGNORECASE)
_QUOTA_STATUS = re.compile(r'"status_code":\s*429\b|\b429\b')
_SECRETS = re.compile(
    r"sk-[A-Za-z0-9_\-]{6,}|eyJ[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]+\.[A-Za-z0-9_\-]*"
    r"|(?i:bearer)\s+\S+")



# --- the Kimi stream-json parser -------------------------------------------
# Here rather than in review_verdict.py: the probe is feature code and the review
# harness is tooling (check-tooling-pr.py), so the harness imports this parser
# when it launches Kimi (L-0527), never the other way round.

def _kimi_text(content):
    """Assistant `content` as text: a string, or a list of `{"type": "text",
    "text": ...}` parts joined. None when a text part's `text` is not a string
    -- a malformed message (round 4 of T-0028: joining it raised TypeError, so
    the probe's classify crashed instead of reading unknown). Anything else is
    no text."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Round 5 of T-0028: a member that is not an object is malformed, not
        # skipped -- CLEAN beside an unparseable part was accepted.
        if not all(isinstance(p, dict) for p in content):
            return None
        texts = [p.get("text") for p in content if p.get("type") == "text"]
        if not all(isinstance(text, str) for text in texts):
            return None
        return "".join(texts)
    return ""


def _kimi_error(event):
    """The failure an event carries, or None. A `turn.step.retrying` meta
    event is NOT one: the CLI retries and may still complete the turn, and
    round 5 of T-0028 found one carrying its transient error as an object
    read as terminal."""
    if event.get("type") == "turn.step.retrying":
        return None
    detail = event.get("error")
    if isinstance(detail, dict):
        code, text = detail.get("code"), detail.get("message")
        return f"{code}: {text or ''}".rstrip(": ") if code else str(text or "error")
    if isinstance(detail, str) and detail:
        return detail
    kind = str(event.get("type") or "")
    if event.get("role") == "meta" and (kind.endswith((".failed", ".error"))
                                        or kind in ("error", "failed")):
        return str(event.get("error_message") or event.get("message") or kind)
    return None


def final_message(jsonl):
    """From `kimi -p ... --output-format stream-json` stdout, return
    (message, error), the same contract as `review_verdict.codex_final_message`.

    `message` is the last assistant text, or None. `error` is None only when
    at least one assistant text arrived, every non-blank line parsed as a JSON
    object, and no event carried a failure. Written against the shape the
    2.1.1 bundle's PromptJsonWriter emits, and checked against the owner's
    one captured run (tests/fixtures/kimi-stream-2.1.1/ok.jsonl). Only a
    `role: assistant` line is read: that run ends on a `session.resume_hint`
    meta line whose `content` is a string too. The stream has NO
    turn-completed record, so completion cannot be proven from stdout alone,
    and a thrown turn failure reaches stderr and the exit status instead. The
    exit status is therefore still required: `classify` reads `ok` only at
    exit 0."""
    message, error = None, None
    for line in (jsonl or "").split("\n"):  # "\n" only, as review_verdict.codex_final_message
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except ValueError:
            event = None
        if not isinstance(event, dict):
            if error is None:
                error = f"unparseable Kimi event line: {line[:120]!r}"
            continue
        failure = _kimi_error(event)
        if failure and error is None:
            error = failure
        if event.get("role") == "assistant":
            text = _kimi_text(event.get("content"))
            if text is None:
                if error is None:
                    error = "malformed content part"
            elif text.strip():
                message = text
    if error is None and message is None:
        error = "the Kimi event stream has no assistant message"
    return message, error


def launchable(state):
    """True for `ok` alone. Every other state -- `unknown` above all -- is a
    reason not to spend a round."""
    return state == "ok"


def redact(text):
    """Mask `sk-...` keys, JWT-shaped tokens and bearer values."""
    return _SECRETS.sub("[redacted]", text or "")


def kimi_env(base=None):
    """The environment a `kimi` child gets: the caller's, minus the infinite
    retry switch and every `KIMI_MODEL_*` override, plus no auto-update."""
    env = {k: v for k, v in (os.environ if base is None else base).items()
           if k != "KIMI_CODE_INFINITE_RETRY" and not k.startswith("KIMI_MODEL_")}
    env["KIMI_CODE_NO_AUTO_UPDATE"] = "1"
    return env


def write_agent_file(directory):
    """Write the read-only agent definition `kimi --agent-file` loads, and the
    empty directory passed as `--skills-dir`, into `directory`; return the
    agent file's path. The body is one fixed line: the review instructions
    travel in `-p` exactly as they do for codex and copilot, never in here."""
    os.makedirs(os.path.join(directory, NO_SKILLS), exist_ok=True)
    path = os.path.join(directory, AGENT_FILE)
    text = ("---\n"
            "name: crew-reviewer\n"
            "description: Read-only code reviewer for crew's review round.\n"
            "tools: [Read, Grep, Glob]\n"
            "disallowedTools: [Write, Edit, Bash]\n"
            "---\n"
            "You are a read-only code reviewer. Follow the user's message "
            "exactly; never modify files.\n")
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)
    return path


def read_only_flags(directory):
    """`--agent-file <dir>/kimi-reviewer.md --skills-dir <dir>/kimi-no-skills`,
    written into `directory` first. Every `kimi` launch crew makes carries
    these: the probe and the review alike."""
    return ["--agent-file", write_agent_file(directory),
            "--skills-dir", os.path.join(directory, NO_SKILLS)]


def kimi_home(env=None):
    env = os.environ if env is None else env
    return env.get("KIMI_CODE_HOME") or os.path.join(os.path.expanduser("~"), ".kimi-code")


def _result(state, reason, alias=None, exe=None):
    return {"state": state, "reason": reason, "alias": alias, "exe": exe}


def _table(value):
    return value if isinstance(value, dict) else {}


def resolve_alias(config, model_id):
    """(alias, None) or (None, (state, reason)). Pure."""
    models = _table(config.get("models"))
    providers = _table(config.get("providers"))
    if model_id:
        if model_id in models:
            candidates = [model_id]
        else:
            candidates = sorted(a for a, row in models.items()
                                if _table(row).get("model") == model_id)
        if not candidates:
            return None, ("unknown", f"no alias in config.toml serves model id "
                                     f"`{model_id}`; nothing is guessed")
    else:
        default = config.get("default_model")
        if not isinstance(default, str) or not default:
            return None, ("not-authenticated", "no model given and no default_model in "
                                               "config.toml - run `kimi login`")
        if default not in models:
            return None, ("unknown", "default_model names an alias config.toml does "
                                     "not define")
        candidates = [default]
    types, unnamed = [], False
    for alias in candidates:
        ref = _table(models[alias]).get("provider")
        if not isinstance(ref, str):
            # Round 4 of T-0028: an array or inline table reached
            # `providers.get` and raised TypeError.
            unnamed = True
            continue
        kind = _table(providers.get(ref)).get("type")
        if kind == "kimi":
            return alias, None
        types.append(str(kind))
    if unnamed:
        return None, ("unknown", PROVIDER_NOT_A_NAME)
    return None, ("unknown", "family cannot be proven: alias routes to provider type "
                             + ", ".join(sorted(set(types))))


def _credential_present(config, alias, home):
    """True or False; None when the alias's provider reference is not a name,
    which is "could not tell", never "no credential"."""
    return _credential_state(config, alias, home)[0]


def _credential_state(config, alias, home):
    """(present, reason): present is True, False, or None for could-not-tell,
    with the reason naming which. Round 5 of T-0028: an unreadable
    credentials directory read as "no credential" (not-authenticated); only a
    directory that does not exist proves absence."""
    ref = _table(_table(config.get("models")).get(alias)).get("provider")
    if not isinstance(ref, str):
        return None, PROVIDER_NOT_A_NAME
    provider = _table(_table(config.get("providers")).get(ref))
    key = provider.get("api_key")
    if isinstance(key, str) and key.strip():
        return True, None
    if not isinstance(provider.get("oauth"), dict):
        return False, None
    folder = os.path.join(home, "credentials")
    try:
        names = os.listdir(folder)
    except FileNotFoundError:
        return False, None
    except OSError as exc:
        return None, (f"the Kimi credentials directory could not be read "
                      f"({type(exc).__name__})")
    return any(os.path.isfile(os.path.join(folder, n)) for n in names), None


def _run(cmd, env, timeout, cwd=None):
    """(stdout, stderr, exit_code, timed_out), stdin closed."""
    try:
        done = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", env=env, cwd=cwd,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return "", "", None, True
    return done.stdout, done.stderr, done.returncode, False


def classify(stdout, stderr, code, timed_out, timeout=DEFAULT_TIMEOUT):
    """(state, reason) for one live probe call. Pure. Auth, then PROBE_OK,
    then quota; anything else is `unknown`.

    PROBE_OK is read BEFORE the quota markers (round 2 of T-0028): the CLI
    retries a transient 429 (a `turn.step.retrying` record) and may then
    finish the turn, which `final_message` reads as a
    clean answer -- so must the probe. It counts only at exit 0 from a stream
    that carried no failure record; a 429 that ended the call still reads
    `rate-limited`."""
    if timed_out:
        return "unknown", f"the probe did not answer within {timeout}s"
    message, error = final_message(stdout)
    blob = f"{stdout}\n{stderr}"
    if _AUTH_MARKERS.search(blob) or _AUTH_STATUS.search(stderr or "") \
            or '"status_code":401' in (stdout or "").replace(" ", ""):
        return "not-authenticated", "the Kimi CLI refused the credential - run `kimi login`"
    if code == 0 and error is None and message is not None \
            and message.strip() == PROBE_MARKER:
        return "ok", "answered PROBE_OK"
    if _QUOTA_MARKERS.search(blob) or _QUOTA_STATUS.search(stderr or "") \
            or '"status_code":429' in (stdout or "").replace(" ", ""):
        return "rate-limited", "the Kimi CLI answered with a quota or rate limit"
    detail = redact((stderr or "").strip())[:200]
    return "unknown", (f"exit {code}, no {PROBE_MARKER}"
                       + (f"; stderr: {detail}" if detail else ""))


def probe(model_id=None, which=shutil.which, home=None, runner=None,
          timeout=DEFAULT_TIMEOUT):
    """`{"state", "reason", "alias", "exe"}`. See the module docstring."""
    exe = which("kimi")
    if not exe:
        return _result("not-installed", "`kimi` is not on PATH")
    # Round 4 of T-0028: a relative PATH entry gave `bin/kimi`, which does not
    # resolve from the probe's temporary directory. Made absolute against the
    # cwd `which` searched from; the review launches this same path.
    exe = os.path.abspath(exe)
    home = home or kimi_home()
    path = os.path.join(home, "config.toml")
    # Round 5 of T-0028: only ENOENT proves there is no config; a lookup that
    # fails any other way, or a config.toml that is not a regular file, is
    # could-not-tell (os.path.isfile answered False for all three).
    try:
        mode = os.stat(path).st_mode
    except FileNotFoundError:
        return _result("not-authenticated", "no config.toml in the Kimi Code home - "
                                            "run `kimi login`", exe=exe)
    except OSError as exc:
        return _result("unknown", f"config.toml could not be checked ({type(exc).__name__})",
                       exe=exe)
    if not stat.S_ISREG(mode):
        return _result("unknown", "config.toml is not a regular file", exe=exe)
    if _tomllib is None:
        return _result("unknown", "tomllib is unavailable (Python < 3.11), so "
                                  "config.toml cannot be read", exe=exe)
    try:
        with open(path, "rb") as fh:
            config = _tomllib.load(fh)
    except (OSError, ValueError) as exc:
        return _result("unknown", f"config.toml could not be parsed ({type(exc).__name__})",
                       exe=exe)
    alias, refusal = resolve_alias(config, model_id)
    if refusal:
        return _result(refusal[0], refusal[1], exe=exe)
    present, why = _credential_state(config, alias, home)
    if present is None:
        return _result("unknown", why, alias=alias, exe=exe)
    if not present:
        return _result("not-authenticated", "the provider has no api_key and no stored "
                                            "OAuth credential - run `kimi login`",
                       alias=alias, exe=exe)
    try:
        workdir = tempfile.mkdtemp(prefix="crew-kimi-probe-")
    except OSError as exc:  # round 5 of T-0028: no scratch directory is `unknown`
        return _result("unknown", f"the probe could not create its scratch directory "
                                  f"({type(exc).__name__})", alias=alias, exe=exe)
    try:
        cmd = [exe, "-p", PROBE_PROMPT, "-m", alias, "--output-format", "stream-json",
               *read_only_flags(workdir)]
        stdout, stderr, code, timed_out = (runner or _run)(cmd, kimi_env(), timeout, workdir)
    except Exception as exc:  # pylint: disable=broad-except  # any launch failure is `unknown`
        return _result("unknown", f"the probe could not run: {type(exc).__name__}",
                       alias=alias, exe=exe)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)
    state, reason = classify(stdout, stderr, code, timed_out, timeout)
    return _result(state, reason, alias=alias, exe=exe)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", default=None,
                        help="a Kimi Code model id (k3, kimi-for-coding, ...) or alias")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    result = probe(args.model or None, timeout=args.timeout)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(f"kimi: {result['state']} - {result['reason']}")
    return 0 if launchable(result["state"]) else 1


if __name__ == "__main__":
    sys.exit(main())
