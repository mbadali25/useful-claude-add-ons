"""The review providers, one row each (R-10): what `review_run.py` needs to
know about a provider, in one place instead of `provider == "codex"`
branches.

A row is frozen and holds no decision. It names the provider (`name`, and
`display` for the `next:` lines), whether `review_run.py` launches it as a
process (`launched`; `claude` runs inside the session), the binary it
resolves (`executable`), and how it is probed:

  standalone  `review_run.py --probe` makes one minimal real call through the
              row's `command` (codex, copilot). `walk_probes` says whether
              /crew:review's default walk issues that probe: codex only, so
              the default path is what it was before the registry.
  in-launch   the provider probes inside its own `run`, before the round is
              reserved and inside the fingerprint window (kimi; L-0514,
              L-0527). `--probe` makes no call for it and answers `deferred`,
              so one attempt never probes it twice.
  in-session  nothing to probe (claude).

`command(exe, root, prompt, model, effort, scratch)` is the argv,
`final(stdout)` is `(message, error)` with `review_verdict.
codex_final_message`'s contract, and `limit(error, stderr)` is the usage-limit
line or None. Only Codex has documented limit text (`review_limit`), so every
other row's `limit` is None: a failing Copilot probe is `failed` or
`unknown`, never `limited`. `events_file` is the raw stream a round keeps
beside out.txt (codex's `codex-events.jsonl`), and the in-process retry keeps
it as `<name>.round<N>` too (`review_run.RETRY_KEPT`).

LIMIT CONFERS NO AUTHORITY. No row, and nothing in the probe path, takes,
returns or writes a same-family decision. `family` delegates to
`crew_state.family`, the one rule every guard already reads; a probe outcome
(ok, limited, failed, unknown, deferred) is never an input to
`review_run.family_guard`, and a same-family read still needs the operator's
explicit `--same-family`.

Imports `crew_state`, `kimi_probe`, `review_limit` and `review_verdict`
only, never `review_run`: `review_run` reads this module.
"""
import dataclasses
import typing

import crew_state
import kimi_probe
import review_limit
import review_verdict

STANDALONE, IN_LAUNCH, IN_SESSION = "standalone", "in-launch", "in-session"


@dataclasses.dataclass(frozen=True)
class Provider:  # pylint: disable=too-many-instance-attributes
    """One review provider. See the module docstring."""
    name: str
    display: str
    launched: bool
    executable: typing.Optional[str]
    probe: str
    walk_probes: bool
    needs_model: bool
    events_file: typing.Optional[str]
    command: typing.Optional[typing.Callable] = None
    final: typing.Optional[typing.Callable] = None
    limit: typing.Optional[typing.Callable] = None

    def family(self, model):
        """`crew_state.family` for this provider: no second family rule."""
        return crew_state.family(self.name, model or None)


def _codex_command(exe, root, prompt, model, effort, scratch=None):  # pylint: disable=unused-argument
    cmd = [exe, "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
           "-C", root]
    if model:
        cmd += ["--model", model]
    if effort:
        cmd += ["-c", f"model_reasoning_effort={effort}"]
    return cmd + [prompt]


def _copilot_command(exe, root, prompt, model, effort, scratch=None):  # pylint: disable=unused-argument
    return [exe, "-p", prompt, "--model", model, "--deny-tool", "write",
            "--deny-tool", "shell", "-s"]


def _kimi_command(exe, root, prompt, model, effort, scratch=None):  # pylint: disable=unused-argument
    return [exe, "-p", prompt, "-m", model, "--output-format", "stream-json",
            *kimi_probe.read_only_flags(scratch)]


def _raw_final(stdout):
    """Copilot prints its answer as plain text: all of stdout, no error."""
    return stdout, None


def _codex_limit(error, stderr):
    return review_limit.limit_line(error or "", stderr)


def _no_limit(error, stderr):  # pylint: disable=unused-argument
    """No documented limit text for this provider: never `limited`."""
    return None


REGISTRY = (
    Provider("codex", "Codex", True, "codex", STANDALONE, True, False, "codex-events.jsonl",
             _codex_command, review_verdict.codex_final_message, _codex_limit),
    Provider("copilot", "Copilot", True, "copilot", STANDALONE, False, True, None,
             _copilot_command, _raw_final, _no_limit),
    Provider("kimi", "Kimi", True, "kimi", IN_LAUNCH, False, False, None,
             _kimi_command, kimi_probe.final_message, _no_limit),
    Provider("claude", "Claude", False, None, IN_SESSION, False, False, None),
)
ROWS = {row.name: row for row in REGISTRY}
NAMES = tuple(row.name for row in REGISTRY)
LAUNCHED = tuple(row.name for row in REGISTRY if row.launched)
STANDALONE_PROBES = tuple(row.name for row in REGISTRY if row.probe == STANDALONE)
EVENTS_FILES = tuple(row.events_file for row in REGISTRY if row.events_file)


def row(name):
    """The row for `name`; the codex row when `name` is None or empty (an
    old caller that names no provider meant Codex, D11)."""
    return ROWS[name or "codex"]
