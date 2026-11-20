"""R-10: the provider registry (`review_providers.py`), one probe per attempt,
and a limit that confers no authority.

Every case runs against a throwaway repo under tmp_path with fake `codex`,
`copilot` and `kimi` binaries written here (kimi's from kimi_fixtures), each
logging one line per invocation tagged `probe` or `review` by its prompt.
Nothing here calls a real provider or reads real config: HOME and USERPROFILE
point into tmp_path.

An ATTEMPT (spec D12) is one /crew:review walk for one provider: that
provider's `--probe`, if the walk issues one, plus ONE `run` invocation of
review_run.py, including its single in-process retry. "No double probe" is at
most one probe call per provider per attempt.

The byte-identical strings (T3) were recorded from origin/main a29b816f with
the same fakes and the same models report, then written here as templates
whose only holes are the tmp paths.
"""
import argparse
import json
import os
import shlex
import subprocess
import sys
import textwrap

import pytest

import context  # noqa: F401  pylint: disable=unused-import
import kimi_probe
import review_ledger
import review_limit
import review_providers
import review_run
from kimi_fixtures import fake_kimi_bin, kimi_home
from review_fixtures import NO_BACKOFF, bundle, init_repo

_SCRIPTS = os.path.join(context._ROOT, "hooks", "scripts")  # pylint: disable=protected-access
_RUN = os.path.join(_SCRIPTS, "review_run.py")
_LEDGER = os.path.join(_SCRIPTS, "review_ledger.py")
_LIMIT = "You've hit your usage limit. Try again at 3:45 PM."

# A fake `codex` / `copilot`. __NAME__ is replaced per binary. Each call is one
# JSON line in $FAKE_LOG. FAKE_PROBE picks how a probe call answers (ok | limit
# | fail | hang); FAKE_REVIEW is a comma-separated sequence for review calls
# (clean | turnfail | fail | limit), counted per binary, the last repeating.
_FAKE = r'''
import json, os, re, sys, time
NAME = "__NAME__"
argv = sys.argv[1:]
prompt = argv[-1] if NAME == "codex" else argv[argv.index("-p") + 1]
m = re.search(r"instructions are in the file (.+?)\. Read that file", prompt)
if m:
    with open(m.group(1), encoding="utf-8") as fh:
        prompt = fh.read()
kind = "probe" if prompt == os.environ["FAKE_PROBE_PROMPT"] else "review"
log = os.environ["FAKE_LOG"]
with open(log, "a", encoding="utf-8") as fh:
    fh.write(json.dumps({"name": NAME, "kind": kind, "argv": argv}) + "\n")
if kind == "probe":
    mode = os.environ.get("FAKE_PROBE", "ok")
else:
    modes = os.environ.get("FAKE_REVIEW", "clean").split(",")
    state = log + "." + NAME + ".n"
    n = int(open(state, encoding="utf-8").read()) if os.path.exists(state) else 0
    with open(state, "w", encoding="utf-8") as fh:
        fh.write(str(n + 1))
    mode = modes[min(n, len(modes) - 1)]
LIMIT = "You've hit your usage limit. Try again at 3:45 PM."
if mode == "hang":
    time.sleep(60)
    sys.exit(0)
if mode == "fail":
    sys.stderr.write("boom: something nobody has seen\n")
    sys.exit(1)
if kind == "probe":
    body = "OK"
else:
    parts = sorted(set(re.findall(r"part-\d{3}-of-\d{3}\.patch", prompt)))
    body = "\n".join("READ|" + p for p in parts) + "\nCLEAN"
if NAME == "copilot":
    if mode == "limit":
        sys.stderr.write(LIMIT + "\n")
        sys.exit(1)
    print(body)
    sys.exit(0)
def emit(events):
    print("\n".join(json.dumps(e) for e in events))
if mode == "limit":
    emit([{"type": "thread.started"}, {"type": "error", "message": LIMIT},
          {"type": "turn.failed", "error": {"message": LIMIT}}])
    sys.exit(1)
events = [{"type": "thread.started"}, {"type": "turn.started"},
          {"type": "item.completed", "item": {"type": "agent_message", "text": body}}]
events.append({"type": "turn.failed", "error": {"message": "stream died"}}
              if mode == "turnfail" else {"type": "turn.completed"})
emit(events)
'''

# The models report /crew:review --prepare writes (crew_config.py --models --json).
_REPORT = {"qaProviders": {"codex": {"model": "gpt-6-astra", "reasoningEffort": "high"},
                           "kimi": {"model": "k3"}, "copilot": {"model": "gpt-6-astra"}},
           "qa": [{"role": "review", "provider": None}],
           "qaFallThrough": [{"provider": p, "eligible": True}
                             for p in ("codex", "kimi", "copilot", "claude")]}
_QA = {"provider": "auto", "order": ["codex", "kimi", "copilot", "claude"],
       "fallback": "gpt-6.1-sol", "codex": {"model": "gpt-6-astra"}, "kimi": {"model": "k3"},
       "roles": {"review": {"provider": "codex", "model": "gpt-6-astra"}}}
_FAMILY = ("--authors", "claude", "--author-source", "config")


def _fakes(directory):
    directory.mkdir(parents=True, exist_ok=True)
    for name in ("codex", "copilot"):
        script = directory / name
        script.write_text(f"#!{sys.executable}\n" + textwrap.dedent(_FAKE).replace(
            "__NAME__", name), encoding="utf-8", newline="\n")
        script.chmod(0o755)
        (directory / f"{name}.cmd").write_text(f'@"{sys.executable}" "%~dp0{name}" %*\r\n',
                                               encoding="utf-8", newline="")
    fake_kimi_bin(directory)
    return directory


class Lane:  # pylint: disable=too-few-public-methods
    """A repo with a cut bundle, a scratch holding models.json, the fakes."""

    def __init__(self, tmp_path, qa=None, report=None):
        self.repo = init_repo(tmp_path / "r")
        (self.repo / "change.txt").write_text("change\n", encoding="utf-8")
        self.scratch = tmp_path / "scratch"
        bundle(self.repo, self.scratch)
        (self.scratch / "models.json").write_text(json.dumps(report or _REPORT),
                                                  encoding="utf-8")
        (self.repo / ".crew").mkdir(exist_ok=True)
        (self.repo / ".crew" / "config.json").write_text(json.dumps({"qa": qa or _QA}),
                                                         encoding="utf-8")
        # .crew/ is not part of the change under review.
        (self.repo / ".git" / "info" / "exclude").write_text(".crew/\n", encoding="utf-8")
        self.bin = _fakes(tmp_path / "bin")
        self.home = tmp_path / "home"
        self.home.mkdir()
        self.kimi_home = kimi_home(tmp_path / "kimi-home")
        self.work = tmp_path / "work"

    def run(self, *argv, log="calls.jsonl", **env):
        full = dict(os.environ)
        full["PATH"] = str(self.bin) + os.pathsep + full.get("PATH", "")
        full.update(FAKE_LOG=str(self.bin / log), FAKE_PROBE_PROMPT=review_run.PROBE_PROMPT,
                    FAKE_KIMI_DUMP=str(self.bin / "kimi.jsonl"),
                    KIMI_CODE_HOME=str(self.kimi_home), HOME=str(self.home),
                    USERPROFILE=str(self.home), **env)
        return subprocess.run(
            NO_BACKOFF + ["--root", str(self.repo), "--ticket", "T1", "--scratch",
                          str(self.scratch), "--work-dir", str(self.work), *argv],
            capture_output=True, text=True, stdin=subprocess.DEVNULL, check=False, env=full,
            cwd=str(self.repo), timeout=180)

    def calls(self, log="calls.jsonl"):
        """Every fake call so far, oldest first: {"name", "kind"}."""
        found = []
        path = self.bin / log
        if path.exists():
            found += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                      if line]
        dump = self.bin / "kimi.jsonl"
        if dump.exists():
            for line in dump.read_text(encoding="utf-8").splitlines():
                argv = json.loads(line)["argv"]
                prompt = argv[argv.index("-p") + 1] if "-p" in argv else ""
                found.append({"name": "kimi", "kind": "probe" if prompt ==
                              kimi_probe.PROBE_PROMPT else "review"})
        return found

    def count(self, name, kind, log="calls.jsonl"):
        return sum(1 for c in self.calls(log) if c["name"] == name and c["kind"] == kind)

    def rounds_used(self):
        return review_ledger.status(str(self.repo), "T1")["rounds_used"]

    def head(self):
        """`python3 <review_run.py> --root R --ticket T1 --scratch S`, as `next:` quotes it."""
        return " ".join(shlex.quote(w) for w in ("python3", _RUN, "--root", str(self.repo),
                                                  "--ticket", "T1", "--scratch",
                                                  str(self.scratch)))


def _field(result, key):
    for line in result.stdout.splitlines():
        if line.startswith(key + "="):
            return line[len(key) + 1:]
    return None


def _next(result):
    lines = [line for line in result.stdout.splitlines() if line.startswith("next: ")]
    assert len(lines) == 1, result.stdout + result.stderr
    return lines[0][len("next: "):]


@pytest.fixture(name="lane")
def _lane(tmp_path):
    return Lane(tmp_path)


# --- T1: the registry, and the names review_run keeps ---------------------------------------

# review_run.command_for's argv at a29b816f (review_run.py:835-848), per provider.
_ARGV = {
    "codex": ["EXE", "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check",
              "-C", "ROOT", "--model", "M", "-c", "model_reasoning_effort=E", "PROMPT"],
    "copilot": ["EXE", "-p", "PROMPT", "--model", "M", "--deny-tool", "write", "--deny-tool",
                "shell", "-s"],
    "kimi": ["EXE", "-p", "PROMPT", "-m", "M", "--output-format", "stream-json",
             "--agent-file", os.path.join("SCR", "kimi-reviewer.md"),
             "--skills-dir", os.path.join("SCR", "kimi-no-skills")],
}


def test_registry_keeps_the_public_tuples_and_every_row_is_whole():
    assert review_run.LAUNCHED == ("codex", "copilot", "kimi")
    assert review_run.PROVIDERS == ("codex", "copilot", "kimi", "claude")
    assert review_run.RETRY_KEPT == ("out.txt", "stderr.txt", "codex-events.jsonl")
    for name in review_run.LAUNCHED:
        row = review_providers.ROWS[name]
        assert all(callable(f) for f in (row.command, row.final, row.limit)), name
    assert [r.probe for r in review_providers.REGISTRY] == [
        "standalone", "standalone", "in-launch", "in-session"]
    assert [r.name for r in review_providers.REGISTRY if r.walk_probes] == ["codex"]


def test_command_for_is_todays_argv_for_every_provider(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    got = {p: review_run.command_for(p, "EXE", "ROOT", "PROMPT", "M", "E", "SCR")
           for p in review_run.LAUNCHED}

    assert got == _ARGV
    assert review_run.command_for("codex", "EXE", "ROOT", "PROMPT", "", "") == [
        "EXE", "exec", "--json", "--sandbox", "read-only", "--skip-git-repo-check", "-C",
        "ROOT", "PROMPT"]


def test_a_row_family_is_crew_states_family():
    for name in review_run.PROVIDERS:
        for model in ("gpt-6-astra", "claude-sonnet-5", "k3", ""):
            assert review_providers.ROWS[name].family(model) == \
                review_run.crew_state.family(name, model or None)


# --- T3: the default path is byte-identical to main -----------------------------------------

def _walks(report=None):
    report = report or _REPORT
    head = " ".join(shlex.quote(w) for w in ("python3", _RUN, "--root", ".", "--ticket", "T1",
                                              "--scratch", "SCR"))
    tail = "--authors claude --author-source config"
    ledger = shlex.quote(_LEDGER)
    none_left = (f"no provider left to run: record it with python3 {ledger} --ticket T1 "
                 "--no-reviewer --reason \"<why>\" (INCOMPLETE, refunded), a same-family Claude "
                 "read only on the owner's word")
    claude = (f"step 2c: run {head} --provider claude --reserve-only {tail} (add --same-family "
              "\"<reason>\" only on the owner's word), dispatch crew:reviewer on SCR/prompt.txt, "
              "SCR/diff.txt and SCR/manifest.json, save its output as SCR/out.txt, then run "
              f"{head} --provider claude --round '<ROUND>' --output SCR/out.txt --exit-code 0 "
              f"{tail}")
    want = {
        ("codex",): f"probe Codex: {head} --provider codex --model gpt-6-astra --effort high "
                    f"--probe {tail}",
        ("kimi",): f"run {head} --provider kimi --model k3 --effort high {tail}",
        ("copilot",): f"run {head} --provider copilot --model gpt-6-astra --effort high {tail}",
        ("claude",): claude,
        (): none_left,
    }
    return report, want, none_left


def test_t3_the_default_walk_says_what_main_said():
    report, want, none_left = _walks()
    for order, text in want.items():
        ctx = review_run.Context(".", "T1", "SCR", report, "claude", "config")
        assert ctx.walk(list(order)) == text, order
    ctx = review_run.Context(".", "T1", "SCR", report, "claude", "config")
    ctx.models["copilot"] = ""
    assert ctx.walk(["copilot"]) == "copilot skipped: qa.copilot.model not set; " + none_left
    assert ctx.walk(["copilot", "kimi"]) == ("copilot skipped: qa.copilot.model not set; "
                                             + want[("kimi",)])


@pytest.mark.parametrize("mode,extra,code,probe,detail,what", [
    ("ok", (), 0, "ok", "OK", None),
    ("limit", (), 5, "limited", _LIMIT, 5),
    ("fail", (), 6, "failed", "the Codex event stream has no completed turn", 6),
    ("hang", ("--probe-timeout", "2"), 7, "unknown", "no answer within 2s", 7),
])
def test_t3_the_codex_probe_says_what_main_said(lane, mode, extra, code, probe, detail, what):
    result = lane.run("--provider", "codex", "--model", "gpt-6-astra", "--probe", *_FAMILY,
                      *extra, FAKE_PROBE=mode)

    tail = "--authors claude --author-source config"
    if what is None:
        want = (f"Codex answers: run {lane.head()} --provider codex --model gpt-6-astra "
                f"--effort high {tail}")
    else:
        want = (f"Codex gave no usable answer: quote PROBE_DETAIL, then run {lane.head()} "
                f"--resolve-run --provider codex --model gpt-6-astra --probe-status {what} {tail}")
    assert (result.returncode, result.stdout.splitlines(), result.stderr) == (
        code, [f"PROBE={probe}", f"PROBE_DETAIL={detail}", "next: " + want], ""), result.stderr
    assert (lane.count("codex", "probe"), lane.rounds_used()) == (1, 0)


_FELL_TO_KIMI = (
    "qa.review: FELL BACK -- pinned model `gpt-6-astra` on codex is unavailable; looking for a "
    "provider outside the claude author family, starting with the fallback `claude-sonnet-5`"
    "\\x0aqa.review: skipped claude `claude-sonnet-5` -- it speaks as the `claude` family that "
    "wrote this diff, which is not an independent review\\x0aqa.review: running kimi `k3` "
    "(kimi family) instead, from the qa.order walk\n")
_FELL_TO_CODEX = (
    "qa.review: FELL BACK -- pinned model `gpt-6-astra` on codex is unavailable; looking for a "
    "provider outside the claude author family, starting with the fallback `gpt-6.1-sol`"
    "\\x0aqa.review: running codex `gpt-6.1-sol` (gpt family) instead, from the fallback\n")


@pytest.mark.parametrize("status", [0, 5, 6, 7])
def test_t3_resolve_run_with_and_without_provider_says_what_main_said(tmp_path, status):
    tail = "--authors claude --author-source config"
    outputs = []
    for named in (True, False):
        lane = Lane(tmp_path / str(named))
        flags = ("--provider", "codex") if named else ()
        result = lane.run("--resolve-run", *flags, "--probe-status", str(status), "--model",
                          "gpt-6-astra", *_FAMILY)
        head = lane.head()
        want = {
            0: ["RUN_PROVIDER=codex", "RUN_MODEL=gpt-6-astra",
                f"next: probe Codex: {head} --provider codex --model gpt-6-astra --effort high "
                f"--probe {tail}"],
            5: ["FALLBACK=kimi k3", "RUN_PROVIDER=kimi", "RUN_MODEL=k3",
                f"next: run {head} --provider kimi --model k3 --effort high {tail}"],
            6: ["FALLBACK=codex gpt-6.1-sol", "RUN_PROVIDER=codex", "RUN_MODEL=gpt-6.1-sol",
                f"next: probe Codex: {head} --provider codex --model gpt-6.1-sol --effort high "
                f"--probe {tail}"],
        }
        want[7] = want[5]
        err = {0: "", 5: _FELL_TO_KIMI, 6: _FELL_TO_CODEX, 7: _FELL_TO_KIMI}[status]
        assert (result.returncode, result.stdout.splitlines(), result.stderr) == (
            0, want[status], err), (named, result.stdout + result.stderr)
        assert lane.calls() == []
        outputs.append(result.stdout.replace(str(lane.repo), "R").replace(
            str(lane.scratch), "S").replace(str(tmp_path / str(named)), "T"))
    assert outputs[0] == outputs[1]


def test_t3_probe_with_no_provider_is_todays_usage_error(lane):
    result = lane.run("--probe")

    assert result.stderr == ("review-run: error: the following arguments are required: "
                             "--provider (review_run.py --help lists the flags)\n")
    assert result.stdout.splitlines()[-1] == "next: fix the arguments (usage above) and run again"
    assert (result.returncode, lane.calls()) == (2, [])


# --- No double probe (T4-T9) ----------------------------------------------------------------

def test_t4_a_codex_attempt_probes_once_and_reviews_once(lane):
    probed = lane.run("--provider", "codex", "--model", "gpt-6-astra", "--probe", *_FAMILY)
    review = lane.run("--provider", "codex", "--model", "gpt-6-astra", *_FAMILY)

    assert (probed.returncode, review.returncode) == (0, 0), review.stdout + review.stderr
    assert (lane.count("codex", "probe"), lane.count("codex", "review")) == (1, 1)


def test_t5_a_retried_codex_round_never_probes_and_keeps_its_events(lane):
    lane.run("--provider", "codex", "--model", "gpt-6-astra", "--probe", *_FAMILY)
    first = lane.run("--provider", "codex", "--model", "gpt-6-astra", *_FAMILY,
                     FAKE_REVIEW="turnfail,turnfail")

    assert "review: retry: round 1 was a tool failure; retrying once" in first.stdout, (
        first.stdout + first.stderr)
    assert (lane.count("codex", "probe"), lane.count("codex", "review")) == (1, 2)
    assert (lane.scratch / "codex-events.jsonl.round1").is_file()
    assert "turn.failed" in (lane.scratch / "codex-events.jsonl.round1").read_text(
        encoding="utf-8")

    # A second /crew:review is a NEW attempt, with its own probe budget of one.
    lane.run("--provider", "codex", "--model", "gpt-6-astra", "--probe", *_FAMILY,
             log="attempt2.jsonl")
    second = lane.run("--provider", "codex", "--model", "gpt-6-astra", *_FAMILY,
                      log="attempt2.jsonl")

    assert second.returncode == 0, second.stdout + second.stderr
    assert (lane.count("codex", "probe", "attempt2.jsonl"),
            lane.count("codex", "review", "attempt2.jsonl")) == (1, 1)


def test_t6_a_kimi_attempt_defers_the_probe_to_its_own_launch(lane):
    probed = lane.run("--provider", "kimi", "--model", "k3", "--probe", *_FAMILY)

    assert (probed.returncode, _field(probed, "PROBE"), lane.calls()) == (0, "deferred", [])

    review = lane.run("--provider", "kimi", "--model", "k3", *_FAMILY)

    assert review.returncode == 0, review.stdout + review.stderr
    assert (lane.count("kimi", "probe"), lane.count("kimi", "review")) == (1, 1)


def test_t7_ma2_kimi_first_walks_to_a_run_with_no_probe_and_probes_once(lane):
    report = dict(_REPORT, qaFallThrough=[{"provider": p, "eligible": True}
                                          for p in ("kimi", "codex")])
    ctx = review_run.Context(str(lane.repo), "T1", str(lane.scratch), report, "claude", "config")

    walk = ctx.walk(ctx.order())

    assert walk.startswith("run ") and "--probe" not in walk and "--provider kimi" in walk
    review = lane.run("--provider", "kimi", "--model", "k3", *_FAMILY)
    assert review.returncode == 0, review.stdout + review.stderr
    assert (lane.count("kimi", "probe"), lane.count("kimi", "review")) == (1, 1)


def test_t8_a_copilot_probe_is_one_call_and_its_run_probes_nothing_more(lane):
    probed = lane.run("--provider", "copilot", "--model", "gpt-6-astra", "--probe", *_FAMILY)

    assert (probed.returncode, _field(probed, "PROBE"), lane.count("copilot", "probe")) == (
        0, "ok", 1), probed.stdout + probed.stderr
    assert _next(probed).startswith("Copilot answers: run ")

    review = lane.run("--provider", "copilot", "--model", "gpt-6-astra", *_FAMILY)

    assert review.returncode == 0, review.stdout + review.stderr
    assert (lane.count("copilot", "probe"), lane.count("copilot", "review")) == (1, 1)


@pytest.mark.parametrize("mode,code,outcome", [("limit", 6, "failed"), ("fail", 6, "failed"),
                                               ("hang", 7, "unknown")])
def test_t8_a_failing_copilot_probe_is_never_limited(lane, mode, code, outcome):
    """Copilot has no documented limit text: even Codex's limit words on its
    stderr are a failure, never `limited`."""
    result = lane.run("--provider", "copilot", "--model", "gpt-6-astra", "--probe",
                      "--probe-timeout", "2", *_FAMILY, FAKE_PROBE=mode)

    assert (result.returncode, _field(result, "PROBE")) == (code, outcome), result.stdout
    assert _next(result).startswith("Copilot gave no usable answer: quote PROBE_DETAIL, then "
                                    "run ")
    assert "--resolve-run --provider copilot --model gpt-6-astra" in _next(result)


def test_t9_a_copilot_probe_without_a_model_is_refused_with_no_call(lane):
    result = lane.run("--provider", "copilot", "--probe", *_FAMILY)

    assert (result.returncode, lane.calls()) == (2, [])
    assert "copilot needs --model" in result.stderr


# --- A limit confers no authority (must-block / must-allow) ---------------------------------

def _limit_marker(lane, provider="codex"):
    """A limit marker that applies to the NEXT round (round == rounds_used)."""
    if provider is None:
        path = review_limit.marker_path(str(lane.repo), "T1")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"ticket": "T1", "round": lane.rounds_used(), "error": _LIMIT,
                       "at": "2026-11-19T00:00:00+00:00"}, handle)
        return
    review_limit.record(str(lane.repo), "T1", lane.rounds_used(), provider, None, _LIMIT)


def test_mb1_a_codex_limit_does_not_let_a_claude_round_reserve(lane):
    _limit_marker(lane)

    result = lane.run("--provider", "claude", "--reserve-only", "--authors", "claude",
                      "--note", "codex-probe=5")

    assert (result.returncode, "review-run: same-family:" in result.stderr,
            lane.rounds_used()) == (2, True, 0), result.stdout + result.stderr


def test_ma1_the_explicit_same_family_choice_still_runs_it_labelled(lane):
    _limit_marker(lane)

    result = lane.run("--provider", "claude", "--reserve-only", "--authors", "claude",
                      "--note", "codex-probe=5", "--same-family", "codex limit")

    row = review_ledger.status(str(lane.repo), "T1")["rounds"][0]
    assert (result.returncode, row.get("same_family")) == (0, True), result.stderr


def _resolve(tmp_path, qa, status, provider="codex", authors="claude", model="gpt-6-astra",
             report=None):
    lane = Lane(tmp_path, qa=qa, report=report)
    result = lane.run("--resolve-run", "--provider", provider, "--probe-status", str(status),
                      "--model", model, "--authors", authors, "--author-source", "config")
    return dict(line.split("=", 1) for line in result.stdout.splitlines()
                if "=" in line and line.split("=", 1)[0].isupper()), result


def _qa(order, fallback="claude-sonnet-5", pin=("codex", "gpt-6-astra")):
    return {"provider": "auto", "order": list(order), "fallback": fallback,
            "codex": {"model": "gpt-6-astra"}, "kimi": {"model": "k3"},
            "copilot": {"model": "gpt-6-astra"},
            "roles": {"review": {"provider": pin[0], "model": pin[1]}}}


@pytest.mark.parametrize("status", [5, 6, 7])
def test_mb2_mb3_a_limited_or_failed_codex_never_resolves_to_the_author_family(tmp_path,
                                                                               status):
    keys, result = _resolve(tmp_path, _qa(("codex", "claude")), status)

    assert (keys.get("FALLBACK"), keys.get("RUN_PROVIDER")) == ("INCOMPLETE", ""), (
        result.stdout + result.stderr)
    assert "--no-reviewer" in _next(result) and "--provider claude" not in _next(result)


def test_ma3_a_limited_codex_resolves_to_a_different_family(tmp_path):
    keys, result = _resolve(tmp_path, _qa(("codex", "kimi")), 5)

    assert (keys.get("RUN_PROVIDER"), keys.get("RUN_MODEL")) == ("kimi", "k3"), (
        result.stdout + result.stderr)


def test_ma4_a_pinned_codex_that_is_limited_is_an_error_not_a_fall_back(tmp_path):
    report = dict(_REPORT, qa=[{"role": "review", "provider": "codex"}])
    qa = {"provider": "auto", "order": ["codex", "kimi"], "codex": {"model": "gpt-6-astra"}}
    _keys, result = _resolve(tmp_path, qa, 5, report=report)

    assert _next(result) == ("qa.provider pins codex and the probe gave exit 5: that is an "
                             "error, not a cue to fall back; quote PROBE_DETAIL and stop"), (
        result.stdout + result.stderr)


@pytest.mark.parametrize("authors,pinned,fell,run", [
    # The pin itself speaks as an author family: barred, never fallen back to.
    ("gpt", "gpt-6-astra", "none - no copilot pin fell back", ""),
    # A cross-family pin that failed falls back past every author family.
    ("gpt", "claude-sonnet-5", "kimi k3", "kimi"),
    ("gpt kimi", "claude-sonnet-5", "INCOMPLETE", ""),
])
def test_mb5_a_failed_copilot_never_resolves_to_its_authors_family(tmp_path, authors, pinned,
                                                                   fell, run):
    barred = set(authors.split())
    report = dict(_REPORT, qaFallThrough=[
        {"provider": p, "eligible": review_run.crew_state.family(p, m) not in barred}
        for p, m in (("copilot", pinned), ("codex", "gpt-6-astra"), ("kimi", "k3"))])
    keys, result = _resolve(tmp_path, _qa(("copilot", "codex", "kimi"), "gpt-6.1-sol",
                                          ("copilot", pinned)), 6,
                            provider="copilot", authors=authors, model=pinned, report=report)

    assert (keys.get("FALLBACK"), keys.get("RUN_PROVIDER")) == (fell, run), (
        result.stdout + result.stderr)
    assert not any(f"--provider {p} " in _next(result) for p in ("codex", "copilot"))


@pytest.mark.parametrize("marker", [None, "codex"])
def test_mb4_a_barred_codex_probe_makes_no_call_whatever_the_marker(lane, marker):
    if marker:
        _limit_marker(lane, marker)

    result = lane.run("--provider", "codex", "--probe", "--authors", "gpt")

    assert (result.returncode, "review-run: same-family:" in result.stderr,
            _field(result, "PROBE"), lane.calls()) == (2, True, None, []), result.stdout


@pytest.mark.parametrize("flags", [
    pytest.param(("--authors", "kimi"), id="a-same-family"),
    pytest.param(("--author-source", "unknown", "--authors", "claude"), id="b-unknown-claude"),
    pytest.param(("--author-source", "unknown", "--authors", "gpt"), id="b-unknown-gpt"),
])
def test_mb6_a_refused_kimi_probe_says_kimi_and_never_deferred(lane, flags):
    result = lane.run("--provider", "kimi", "--model", "k3", "--probe", *flags)

    assert (result.returncode, "review-run: same-family:" in result.stderr, lane.calls()) == (
        2, True, []), result.stdout + result.stderr
    assert not any(line.startswith("PROBE=") for line in result.stdout.splitlines())
    said = _next(result)
    assert said.startswith("Kimi was refused by the family guard") and "Codex" not in said


@pytest.mark.parametrize("flags,warned,family", [
    pytest.param(("--authors", "unknown"), False, "--authors unknown --author-source ''",
                 id="a-authors-unknown"),
    pytest.param((), True, "--authors '' --author-source ''", id="b-no-authors"),
])
def test_ma7_an_allowed_kimi_probe_answers_deferred_with_no_call(lane, flags, warned, family):
    result = lane.run("--provider", "kimi", "--model", "k3", "--probe", *flags)

    assert (result.returncode, _field(result, "PROBE"), _field(result, "PROBE_DETAIL"),
            lane.calls()) == (
        0, "deferred", "kimi probes inside its own launch, before any round is reserved",
        []), result.stdout + result.stderr
    assert "same-family" not in result.stderr
    assert ("review-run: family guard NOT applied: no --authors given" in result.stderr) is warned
    assert _next(result) == ("Kimi probes inside its own launch (PROBE=deferred, nothing was "
                             f"called): run {lane.head()} --provider kimi --model k3 --effort "
                             f"high {family}")


_STATUSES = (0, 5, 6, 7)


@pytest.mark.parametrize("provider,model", [("codex", "gpt-6-astra"), ("copilot", "gpt-6-astra"),
                                            ("copilot", "claude-sonnet-5"), ("kimi", "k3"),
                                            ("claude", "")])
def test_ma5_the_family_guard_reads_no_probe_outcome(tmp_path, provider, model):
    lane = Lane(tmp_path)
    for authors, source in (("claude", "config"), ("gpt", "config"), ("kimi", "config"),
                            ("", "config"), ("claude", "unknown"), (None, None)):
        answers = set()
        for marker in (False, True):
            if marker:
                _limit_marker(lane)
            for status in _STATUSES:
                args = argparse.Namespace(
                    provider=provider, model=model, authors=authors, author_source=source,
                    same_family=None, root=str(lane.repo), ticket="T1", probe_status=status,
                    note=f"codex-probe={status}")
                refusal, label = review_run.family_guard(args)
                answers.add((refusal is None, label))
        assert len(answers) == 1, (provider, model, authors, source, answers)


def test_ma6_an_old_marker_is_codexs_and_never_copilots(lane):
    _limit_marker(lane, None)

    codex = lane.run("--provider", "codex", "--model", "gpt-6-astra", "--probe", *_FAMILY)
    copilot = lane.run("--provider", "copilot", "--model", "gpt-6-astra", "--probe", *_FAMILY)

    assert (codex.returncode, _field(codex, "PROBE"), lane.count("codex", "probe")) == (
        5, "limited", 0), codex.stdout
    assert (copilot.returncode, _field(copilot, "PROBE"), lane.count("copilot", "probe")) == (
        0, "ok", 1), copilot.stdout + copilot.stderr


def test_ma6_a_codex_marker_never_answers_for_copilot(lane):
    _limit_marker(lane, "codex")

    copilot = lane.run("--provider", "copilot", "--model", "gpt-6-astra", "--probe", *_FAMILY)

    assert (copilot.returncode, lane.count("copilot", "probe")) == (0, 1), copilot.stdout


def test_resolve_run_refuses_a_provider_with_no_standalone_probe(lane):
    for provider in ("kimi", "claude"):
        result = lane.run("--resolve-run", "--provider", provider, "--probe-status", "5")
        assert result.returncode == 2 and "has none to read" in result.stderr, result.stderr
