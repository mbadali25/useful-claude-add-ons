#!/usr/bin/env python3
"""Regression suite for the Rule of Two coverage invariant.

Every assertion about coverage is made against the RENDERED REPORT TEXT, not
against `compute_coverage`. That is deliberate. A coverage value computed
correctly can still be dropped on the way to the page, and the report is what
a human acts on. Testing the function alone would pass while the renderer
lied - which is exactly what happened to the title line, caught by this
plugin's own first self-review and now covered below.

Run:   python3 plugin/rule-of-two/scripts/_test/test_rule_of_two.py
Sabotage-check:
       python3 plugin/rule-of-two/scripts/_test/test_rule_of_two.py --sabotage

The sabotage run breaks the renderer and the evidence gate in turn and
asserts THE SUITE GOES RED for each. A regression suite that has never been
seen to fail is decoration; this is the proof it bites.

Builds no fixtures outside a temporary directory, touches no real config,
installs nothing, and launches no real `codex` process - the subprocess layer
is stubbed, so the suite tests this code rather than the local machine.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import rule_of_two as rot  # noqa: E402

FAILURES: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f" -- {detail}" if detail else ""))
        FAILURES.append(name)


REVIEW_A = "**VIABLE**\n\nReviewer A findings."
REVIEW_B = "**NOT VIABLE AS WRITTEN**\n\nReviewer B findings."


def state(claude_ran, codex_ran,
          claude_model: str = "fable",
          codex_model: str = "gpt-6-astra",
          claude_reason: str = "", codex_reason: str = "",
          claude_text: str = REVIEW_A, codex_text: str = REVIEW_B) -> dict:
    return rot.build_state(
        artifact="plugin/rule-of-two/",
        config=rot.DEFAULT_CONFIG,
        config_source="built-in defaults",
        claude_result={"ran": claude_ran, "model": claude_model,
                       "reason": claude_reason, "text": claude_text},
        codex_result={"ran": codex_ran, "model": codex_model,
                      "reason": codex_reason, "text": codex_text},
    )


# --------------------------------------------------------------------------
# Coverage, asserted on the rendered report
# --------------------------------------------------------------------------

def test_codex_missing_reports_one_review() -> None:
    """The load-bearing case: Codex absent must never read as two reviews."""
    print("codex missing -> reported as one review")
    s = state(True, False, codex_reason="no `codex` executable on PATH",
              codex_text="")
    report = rot.render_report(s)
    low = report.lower()

    check("coverage is ONE_REVIEW", s["coverage"] == rot.COVERAGE_ONE_REVIEW,
          s["coverage"])
    check("coverage_satisfied is False", s["coverage_satisfied"] is False)
    check("report says one review, not two", "one review, not two" in low)
    check("report never claims independence", "independent" not in low,
          "the word 'independent' appears in a single-reviewer report")
    check("report names why the second reviewer is missing",
          "no `codex` executable on path" in low)
    check("report carries the 'what is missing' section",
          "what is missing" in low)
    # The title is the line most likely to be pasted or skimmed alone.
    title = report.splitlines()[0]
    check("title does not carry the Rule of Two name",
          title.strip() != f"# Rule of Two review - {s['artifact']}", title)
    check("title says NOT the Rule of Two", "NOT the Rule of Two" in title,
          title)


def test_claude_missing_reports_one_review() -> None:
    """Symmetry: losing the Claude side is the same outcome, not a special case."""
    print("claude missing -> reported as one review")
    s = state(False, True, claude_reason="dispatch failed", claude_text="")
    report = rot.render_report(s)
    check("coverage is ONE_REVIEW", s["coverage"] == rot.COVERAGE_ONE_REVIEW)
    check("report says one review, not two",
          "one review, not two" in report.lower())
    check("report never claims independence",
          "independent" not in report.lower())
    check("title says NOT the Rule of Two",
          "NOT the Rule of Two" in report.splitlines()[0])


def test_unresolvable_family_is_could_not_tell() -> None:
    """Unresolvable families are 'could not tell', never 'independent'."""
    print("unresolvable family -> could not tell")
    s = state(True, True, codex_model="some-retired-model-name")
    report = rot.render_report(s)
    low = report.lower()

    check("family resolves to UNKNOWN",
          s["codex"]["family"] == rot.UNKNOWN_FAMILY, s["codex"]["family"])
    check("coverage is TWO_FAMILY_UNKNOWN",
          s["coverage"] == rot.COVERAGE_TWO_FAMILY_UNKNOWN, s["coverage"])
    check("coverage_satisfied is False", s["coverage_satisfied"] is False)
    check("report says 'could not tell'", "could not tell" in low)
    check("report never claims independence", "independent" not in low,
          "'independent' appears where the family check could not tell")
    check("title says the check is inconclusive",
          "inconclusive" in report.splitlines()[0])


def test_loose_prefix_does_not_resolve_confidently() -> None:
    """An unknown name must not buy a confident family - on either side.

    The first draft fixed this for the openai prefixes and left the anthropic
    aliases loose, so `sonnetting` and `fable-fiction` resolved confidently
    and rendered "the Rule of Two held". Both sides are asserted here for
    that reason: the bug was in the neighbour of the fix.
    """
    print("unknown names -> UNKNOWN, on both sides of the table")
    known = {
        "o3-mini": "openai", "gpt-6-astra": "openai", "codex-1": "openai",
        "gpt": "openai", "codex": "openai",
        "opus": "anthropic", "sonnet": "anthropic", "fable": "anthropic",
        "haiku": "anthropic", "claude-fable-5-1": "anthropic",
        "claude-opus-5": "anthropic",
    }
    for name, family in known.items():
        check(f"'{name}' resolves to {family}",
              rot.resolve_family(name) == family, rot.resolve_family(name))

    for name in ("o3nyx-experimental", "sonnetting", "fable-fiction",
                 "opus-not-a-real-model", "haiku-poems", "gptx",
                 "claudette", "some-retired-model-name"):
        check(f"'{name}' is UNKNOWN, not a confident guess",
              rot.resolve_family(name) == rot.UNKNOWN_FAMILY,
              rot.resolve_family(name))

    # And the rendered consequence, not just the function.
    s = state(True, True, claude_model="fable-fiction")
    check("an unknown alias renders as inconclusive, not independent",
          "independent" not in rot.render_report(s).lower())


def test_empty_model_is_unknown_not_blank() -> None:
    """An unset model is an unknown, not a value that quietly passes."""
    print("unset model -> UNKNOWN, not a silent pass")
    check("empty string is UNKNOWN",
          rot.resolve_family("") == rot.UNKNOWN_FAMILY)
    check("whitespace is UNKNOWN",
          rot.resolve_family("   ") == rot.UNKNOWN_FAMILY)
    check("None is UNKNOWN", rot.resolve_family(None) == rot.UNKNOWN_FAMILY)
    s = state(True, True, codex_model="")
    check("blank-model report never claims independence",
          "independent" not in rot.render_report(s).lower())


def test_same_family_is_not_independent() -> None:
    """Two Claude models are one perspective, whatever the report is called."""
    print("same family -> not independent")
    s = state(True, True, codex_model="claude-opus-5")
    report = rot.render_report(s)
    check("coverage is TWO_SAME_FAMILY",
          s["coverage"] == rot.COVERAGE_TWO_SAME_FAMILY, s["coverage"])
    check("coverage_satisfied is False", s["coverage_satisfied"] is False)
    check("report never claims independence",
          "independent" not in report.lower())
    check("report names the shared family", "anthropic" in report.lower())
    check("title says NOT the Rule of Two",
          "NOT the Rule of Two" in report.splitlines()[0])


def test_neither_ran() -> None:
    print("neither reviewer ran -> NO_REVIEW")
    s = state(False, False, claude_reason="x", codex_reason="y",
              claude_text="", codex_text="")
    report = rot.render_report(s)
    check("coverage is NO_REVIEW", s["coverage"] == rot.COVERAGE_NO_REVIEW)
    check("report says no review ran", "no review ran" in report.lower())
    check("report never claims independence",
          "independent" not in report.lower())
    check("title says no review ran",
          "No review ran" in report.splitlines()[0])


def test_happy_path_is_the_only_independent_one() -> None:
    """The positive case must still be reachable, or the guard is useless."""
    print("both ran, different families -> independent")
    s = state(True, True)
    report = rot.render_report(s)
    low = report.lower()
    check("coverage is TWO_CROSS_FAMILY",
          s["coverage"] == rot.COVERAGE_TWO_CROSS_FAMILY, s["coverage"])
    check("coverage_satisfied is True", s["coverage_satisfied"] is True)
    check("report claims two independent reviews",
          "two independent reviews" in low)
    check("report says the Rule of Two held", "rule of two held" in low)
    check("no 'what is missing' section", "what is missing" not in low)
    check("title carries the Rule of Two name",
          report.splitlines()[0] == f"# Rule of Two review - {s['artifact']}",
          report.splitlines()[0])


# --------------------------------------------------------------------------
# The evidence gate: what is allowed to count as a review
# --------------------------------------------------------------------------

def test_truthy_string_ran_is_not_a_run() -> None:
    """`ran` is model-authored. A truthy string must never buy a review."""
    print("non-boolean 'ran' -> did not run")
    for bogus in ("false", "true", 1, 0, None, "yes"):
        s = rot.build_state(
            "demo", rot.DEFAULT_CONFIG, "built-in defaults",
            {"ran": True, "model": "fable", "text": REVIEW_A},
            {"ran": bogus, "model": "gpt-6-astra", "text": REVIEW_B},
        )
        report = rot.render_report(s)
        check(f"ran={bogus!r} is not a successful run",
              s["coverage"] == rot.COVERAGE_ONE_REVIEW, s["coverage"])
        check(f"ran={bogus!r} report never claims independence",
              "independent" not in report.lower())


def test_empty_review_text_is_not_a_run() -> None:
    """'Ran and returned nothing' is not a review."""
    print("successful run with no text -> did not run")
    s = rot.build_state(
        "demo", rot.DEFAULT_CONFIG, "built-in defaults",
        {"ran": True, "model": "fable", "text": REVIEW_A},
        {"ran": True, "model": "gpt-6-astra", "text": "   \n  "},
    )
    report = rot.render_report(s)
    check("empty text is ONE_REVIEW",
          s["coverage"] == rot.COVERAGE_ONE_REVIEW, s["coverage"])
    check("report never claims independence",
          "independent" not in report.lower())
    check("reason says no review text was returned",
          "no review text" in s["codex"]["reason"].lower(),
          s["codex"]["reason"])


def test_malformed_result_is_not_a_run() -> None:
    """A result that is not an object is a reviewer that did not run."""
    print("malformed result object -> did not run")
    for bogus in ([], "a string", 42, None):
        s = rot.build_state(
            "demo", rot.DEFAULT_CONFIG, "built-in defaults",
            {"ran": True, "model": "fable", "text": REVIEW_A}, bogus,
        )
        check(f"{type(bogus).__name__} result is ONE_REVIEW",
              s["coverage"] == rot.COVERAGE_ONE_REVIEW, s["coverage"])
        check(f"{type(bogus).__name__} result renders without raising",
              "independent" not in rot.render_report(s).lower())


def test_missing_keys_do_not_crash_the_renderer() -> None:
    """The renderer must survive the degraded input it exists to report on."""
    print("result missing keys -> renders, does not raise")
    for missing in ({"ran": True}, {"model": "fable"}, {},
                    {"ran": False, "model": "gpt-6-astra"}):
        try:
            s = rot.build_state(
                "demo", rot.DEFAULT_CONFIG, "built-in defaults",
                {"ran": True, "model": "fable", "text": REVIEW_A}, missing)
            report = rot.render_report(s)
            ok, detail = True, ""
        except Exception as exc:  # noqa: BLE001 - the point is that none escape
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        check(f"renders with keys {sorted(missing)}", ok, detail)
        if ok:
            check(f"keys {sorted(missing)} claim no independence",
                  "independent" not in report.lower())


def test_missing_verdict_is_surfaced() -> None:
    """A review with no verdict ran, but did not answer the question."""
    print("review with no verdict -> flagged, not silently accepted")
    s = rot.build_state(
        "demo", rot.DEFAULT_CONFIG, "built-in defaults",
        {"ran": True, "model": "fable", "text": REVIEW_A},
        {"ran": True, "model": "gpt-6-astra",
         "text": "Some prose with no verdict token in it at all."},
    )
    report = rot.render_report(s)
    check("still counts as a run", s["coverage"] == rot.COVERAGE_TWO_CROSS_FAMILY)
    check("verdict_found is False", s["codex"]["verdict_found"] is False)
    check("report flags the missing verdict",
          "did not answer the question" in report.lower())
    check("a real verdict is not flagged",
          s["claude"]["verdict_found"] is True)


def test_verdict_is_a_line_not_a_substring() -> None:
    """Prose that merely contains the word is not a verdict.

    A substring search is worse than no check here: "This is unviable."
    contains VIABLE, and so does a sentence refusing to give a verdict. Both
    satisfied the first draft's flag - the flag whose whole job was to catch
    exactly that.
    """
    print("verdict detection -> whole line near the top, not a substring")
    not_verdicts = [
        "This is unviable.",
        "I cannot determine whether this is viable.",
        "The rubric says to return VIABLE or NOT VIABLE AS WRITTEN. "
        "I have no opinion.",
        "It may or may not be viable with changes, hard to say.",
        # An echoed option list. `re.search` takes the earliest match, so a
        # permissive pattern hands back the most favourable verdict to a
        # review that gave none.
        "I was asked to return one of:\n- VIABLE\n- VIABLE WITH CHANGES\n"
        "- NOT VIABLE AS WRITTEN\nI have not finished and offer no verdict.",
        # A quoted example of the required format.
        "I cannot review this artifact. The required format is:\n"
        "> **VIABLE**\nPlease provide the file.",
        # The verdict appears, but only after the reviewer has said something
        # else first. The rubric says it opens the report.
        "Some preamble about my approach.\n\n**VIABLE**",
    ]
    for text in not_verdicts:
        check(f"not a verdict: {text[:42]!r}",
              rot.find_verdict(text) == "", rot.find_verdict(text))

    verdicts = {
        "**VIABLE**\n\nrest": "VIABLE",
        "**VIABLE WITH CHANGES**\n\nrest": "VIABLE WITH CHANGES",
        "**NOT VIABLE AS WRITTEN**\n\nrest": "NOT VIABLE AS WRITTEN",
        "# Report\n\n**Viable with changes**\n": "VIABLE WITH CHANGES",
    }
    for text, expected in verdicts.items():
        check(f"verdict {expected} is found",
              rot.find_verdict(text) == expected, rot.find_verdict(text))

    # Longest-first matching: "VIABLE WITH CHANGES" must not read as "VIABLE".
    check("'VIABLE WITH CHANGES' is not truncated to 'VIABLE'",
          rot.find_verdict("**VIABLE WITH CHANGES**") == "VIABLE WITH CHANGES")

    buried = "\n".join(["filler"] * 40 + ["**VIABLE**"])
    check("a verdict far below the top is not counted",
          rot.find_verdict(buried) == "", rot.find_verdict(buried))


def test_disagreement_is_surfaced_not_adjudicated() -> None:
    """Two different verdicts are the payload, not a problem to smooth over."""
    print("reviewers disagree -> the report says so")
    s = rot.build_state(
        "demo", rot.DEFAULT_CONFIG, "built-in defaults",
        {"ran": True, "model": "fable", "text": "**VIABLE**\n\nA"},
        {"ran": True, "model": "gpt-6-astra",
         "text": "**NOT VIABLE AS WRITTEN**\n\nB"},
    )
    report = rot.render_report(s)
    check("both verdicts are parsed",
          (s["claude"]["verdict"], s["codex"]["verdict"])
          == ("VIABLE", "NOT VIABLE AS WRITTEN"))
    check("the report names the disagreement",
          "disagree on the verdict" in report.lower())
    check("the report says it was not adjudicated",
          "not been adjudicated" in report.lower())

    agree = rot.build_state(
        "demo", rot.DEFAULT_CONFIG, "built-in defaults",
        {"ran": True, "model": "fable", "text": "**VIABLE**\n\nA"},
        {"ran": True, "model": "gpt-6-astra", "text": "**VIABLE**\n\nB"})
    check("agreement is not reported as disagreement",
          "disagree on the verdict" not in rot.render_report(agree).lower())


# --------------------------------------------------------------------------
# Codex invocation, with the subprocess layer stubbed
# --------------------------------------------------------------------------

class FakeProc:
    def __init__(self, returncode: int, out: str):
        self.returncode = returncode
        self.stdout = out.encode("utf-8")


def with_fake_codex(returncode: int, log: str, last_message: str,
                    raises=None):
    """Stub `codex` so the suite tests this code, not the local machine."""
    real_run, real_which = subprocess.run, rot.shutil.which

    def fake_run(argv, **kwargs):
        if raises is not None:
            raise raises
        # run_codex passes the last-message path right after the flag.
        path = argv[argv.index("--output-last-message") + 1]
        Path(path).write_text(last_message, encoding="utf-8", newline="\n")
        return FakeProc(returncode, log)

    subprocess.run = fake_run
    rot.shutil.which = lambda name: "C:/fake/codex.exe"
    try:
        return rot.run_codex("gpt-6-astra", "prompt", 30, Path("."))
    finally:
        subprocess.run = real_run
        rot.shutil.which = real_which


BANNER = ("OpenAI Codex v0.153.4\n--------\nmodel: gpt-6-astra\n"
          "--------\ntokens used\n21,258\n")


def test_codex_banner_is_not_a_review() -> None:
    """Startup diagnostics must never be accepted as review findings."""
    print("codex exits 0 with only a banner -> did not run")
    result = with_fake_codex(0, BANNER, last_message="")
    check("banner-only run is ran=False", result["ran"] is False, str(result))
    check("reason names the missing final message",
          "no final message" in result["reason"], result["reason"])
    check("the banner is kept as log, not as review text",
          result["text"] == "" and "OpenAI Codex" in result["log"])


def test_codex_success_uses_last_message() -> None:
    """The review comes from --output-last-message, not from stdout."""
    print("codex exits 0 with a final message -> ran")
    result = with_fake_codex(0, BANNER, last_message=REVIEW_B)
    check("successful run is ran=True", result["ran"] is True, str(result))
    check("review text is the final message, not the banner",
          result["text"].strip() == REVIEW_B and "OpenAI Codex"
          not in result["text"])
    check("diagnostics are kept separately", "OpenAI Codex" in result["log"])


def test_codex_nonzero_exit_is_not_a_run() -> None:
    print("codex exits non-zero -> did not run, with the error quoted")
    log = BANNER + ('ERROR: {"type":"error","status":400,"error":'
                    '{"message":"model is not supported"}}\n')
    result = with_fake_codex(1, log, last_message="some partial text")
    check("non-zero exit is ran=False", result["ran"] is False)
    check("reason carries the exit code", "exited 1" in result["reason"],
          result["reason"])
    check("reason quotes the ERROR line",
          "not supported" in result["reason"], result["reason"])
    check("partial output is not presented as a review",
          result["text"] == "")


def test_codex_timeout_is_not_a_run() -> None:
    """A timeout is 'did not run', never 'ran and found nothing'."""
    print("codex times out -> did not run, and says so")
    result = with_fake_codex(
        0, "", "", raises=subprocess.TimeoutExpired(cmd="codex", timeout=30))
    check("timeout is ran=False", result["ran"] is False)
    # Diagnostics are worth most when the run stalls; an unbound `except`
    # threw them away exactly then.
    diagnostic = with_fake_codex(
        0, "", "", raises=subprocess.TimeoutExpired(
            cmd="codex", timeout=30,
            output=b"ERROR: useful timeout diagnostic\n"))
    check("a timeout keeps whatever output it captured",
          "useful timeout diagnostic" in diagnostic["log"],
          repr(diagnostic["log"]))
    # Asserting the reason TEXT, not just that a reason exists: a missing
    # binary also returns ran=False with a truthy reason, so a truthiness
    # check cannot tell the two apart and proves the path never ran.
    check("reason names the timeout", "timed out" in result["reason"],
          result["reason"])
    check("timeout report never claims independence",
          "independent" not in rot.render_report(rot.build_state(
              "demo", rot.DEFAULT_CONFIG, "d",
              {"ran": True, "model": "fable", "text": REVIEW_A},
              result)).lower())


def test_codex_tempfile_failure_is_not_a_run() -> None:
    """`run_codex` says it never raises. Make that true where it can raise.

    `mkstemp` raises when there is no usable temporary directory, and in the
    first draft it ran above the try block - so the failure escaped a
    function documented as never raising, aborting the report entirely
    instead of degrading to a reviewer that did not run.
    """
    print("temp file cannot be created -> did not run, no traceback")
    real_mkstemp, real_which = rot.tempfile.mkstemp, rot.shutil.which

    def boom(**kwargs):
        raise OSError("No usable temporary directory found")

    rot.tempfile.mkstemp = boom
    rot.shutil.which = lambda name: "C:/fake/codex.exe"
    try:
        result = rot.run_codex("gpt-6-astra", "p", 30, Path("."))
        raised, detail = False, ""
    except Exception as exc:  # noqa: BLE001 - the point is that none escape
        result, raised, detail = None, True, f"{type(exc).__name__}: {exc}"
    finally:
        rot.tempfile.mkstemp = real_mkstemp
        rot.shutil.which = real_which

    check("no exception escapes run_codex", not raised, detail)
    if not raised:
        check("tempfile failure is ran=False", result["ran"] is False)
        check("reason names the temporary file",
              "temporary file" in result["reason"], result["reason"])


def test_codex_missing_binary_is_not_a_run() -> None:
    print("codex binary absent -> did not run, with a reason")
    real_which = rot.shutil.which
    rot.shutil.which = lambda name: None
    try:
        result = rot.run_codex("gpt-6-astra", "p", 30, Path("."))
    finally:
        rot.shutil.which = real_which
    check("missing binary is ran=False", result["ran"] is False)
    check("reason names PATH", "PATH" in result["reason"], result["reason"])


# --------------------------------------------------------------------------
# Config
# --------------------------------------------------------------------------

def test_config_shapes() -> None:
    """Valid JSON that is not an object is a config error, not a traceback."""
    print("config loading -> every shape reported, none raises")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = root / rot.CONFIG_FILENAME

        cfg.write_text("[]", encoding="utf-8")
        try:
            merged, source = rot.load_config(root)
            ok, detail = True, source
        except Exception as exc:  # noqa: BLE001
            ok, detail = False, f"{type(exc).__name__}: {exc}"
        check("a JSON list does not raise", ok, detail)
        if ok:
            check("a JSON list falls back to defaults, and says why",
                  "must contain a JSON object" in detail, detail)

        cfg.write_text("{ not json", encoding="utf-8")
        merged, source = rot.load_config(root)
        check("invalid JSON falls back to defaults",
              merged["codex"]["pin"] == rot.DEFAULT_CONFIG["codex"]["pin"])
        check("invalid JSON names the file in the source",
              "unreadable" in source, source)

        cfg.write_text(json.dumps({"codex": {"pin": "gpt-9-test"}}),
                       encoding="utf-8")
        merged, source = rot.load_config(root)
        check("a partial override is merged, not replaced",
              merged["codex"]["pin"] == "gpt-9-test"
              and merged["claude"]["pin"] == rot.DEFAULT_CONFIG["claude"]["pin"])
        check("the source names the file it came from",
              source == str(cfg), source)


def test_config_value_types() -> None:
    """Validating the shapes and not the values left the crash in place.

    The first draft checked that the root and each section were objects, then
    handed the values straight to `subprocess` and `int()`. A null pin and a
    string timeout each raised from three frames down, on a file reported as
    a valid config source. Each of these is the neighbouring case of the fix
    that came before it.
    """
    print("config values -> coerced and reported, never a traceback")
    cases = [
        ({"codex": {"pin": None}}, "codex.pin"),
        ({"codex": {"pin": 123}}, "codex.pin"),
        ({"codex": {"timeout_seconds": "abc"}}, "timeout_seconds"),
        ({"codex": {"timeout_seconds": None}}, "timeout_seconds"),
        ({"codex": {"timeout_seconds": 0}}, "timeout_seconds"),
        ({"codex": {"timeout_seconds": -5}}, "timeout_seconds"),
        ({"claude": {"pin": []}}, "claude.pin"),
        ({"codex": "gpt-custom"}, "'codex' must be an object"),
        # An explicit null section is a user statement. Dropping it in
        # silence, while reporting the string form, was the hole in the
        # "say what you ignored" guarantee.
        ({"codex": None}, "'codex' must be an object"),
        ({"claude": None}, "'claude' must be an object"),
        # timeout_seconds in a section that has no such default: the branch
        # matched on the key NAME and then indexed a default that was not
        # there.
        ({"claude": {"timeout_seconds": "bad"}}, "claude.timeout_seconds"),
        # JSON 1e400 parses to float infinity, which int() refuses.
        ({"codex": {"timeout_seconds": 1e400}}, "timeout_seconds"),
        # A NUL passes every type check and then raises from inside
        # subprocess.
        ({"codex": {"pin": "gpt-6\x00astra"}}, "null character"),
    ]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cfg = root / rot.CONFIG_FILENAME
        for payload, expected_note in cases:
            cfg.write_text(json.dumps(payload), encoding="utf-8")
            label = json.dumps(payload)
            try:
                merged, source = rot.load_config(root)
                raised, detail = False, ""
            except Exception as exc:  # noqa: BLE001
                merged, source = None, ""
                raised, detail = True, f"{type(exc).__name__}: {exc}"
            check(f"{label} does not raise", not raised, detail)
            if raised:
                continue
            check(f"{label} is reported as ignored",
                  expected_note in source, source)
            check(f"{label} leaves a usable timeout",
                  isinstance(merged["codex"]["timeout_seconds"], int)
                  and merged["codex"]["timeout_seconds"] > 0,
                  repr(merged["codex"]["timeout_seconds"]))
            check(f"{label} leaves string models",
                  isinstance(merged["codex"]["pin"], str)
                  and isinstance(merged["claude"]["pin"], str))

        # A bad model value falls back to the documented default rather than
        # to an empty string, because an empty pin would make the reviewer
        # unrunnable for a typo. That is only acceptable because the
        # substitution is REPORTED - an unannounced fallback would be the
        # silent-safe-value bug this plugin exists to catch.
        cfg.write_text(json.dumps({"codex": {"pin": None}}), encoding="utf-8")
        merged, source = rot.load_config(root)
        check("a non-string pin falls back to the documented default",
              merged["codex"]["pin"] == rot.DEFAULT_CONFIG["codex"]["pin"],
              repr(merged["codex"]["pin"]))
        check("the substitution is reported, not silent",
              "codex.pin must be a string" in source, source)

        # A key with no default has no safe substitute, so it empties - and
        # an empty model resolves to UNKNOWN, which reports "could not tell".
        cfg.write_text(json.dumps({"claude": {"invented_key": 7}}),
                       encoding="utf-8")
        merged, source = rot.load_config(root)
        check("a bad value with no default becomes an empty string",
              merged["claude"]["invented_key"] == "",
              repr(merged["claude"].get("invented_key")))
        check("an empty model resolves to UNKNOWN, not a family",
              rot.resolve_family("") == rot.UNKNOWN_FAMILY)


def _record(tmp: Path, text: str, argv_extra: list[str],
            write_text_file: bool = True, name: str = "review.txt") -> dict:
    text_file = tmp / name
    if write_text_file:
        text_file.write_text(text, encoding="utf-8", newline="\n")
    elif text_file.exists():
        # Without this the "missing file" case reused a file an earlier call
        # in the same temp directory had already created, so the advertised
        # behaviour was asserted against a file that existed.
        text_file.unlink()
    out = tmp / "claude-result.json"
    rot.main(["--repo-root", str(tmp), "record-claude",
              "--model", "fable", "--text-file", str(text_file),
              "--out", str(out)] + argv_extra)
    return json.loads(out.read_text(encoding="utf-8"))


def test_record_claude_states_success_never_infers_it() -> None:
    """Success must be stated by the caller, not inferred from non-empty text.

    The first draft computed `ran = bool(text.strip())`, which re-opened one
    rung upstream exactly the hole `normalize_result` had closed: a file
    containing "dispatch failed: model unavailable" is non-empty, so a failed
    dispatch rendered a full "the Rule of Two held" report.
    """
    print("record-claude -> success is stated, not inferred")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        failed = _record(root, "dispatch failed: model unavailable",
                         ["--failed"])
        check("--failed is ran=False even with non-empty text",
              failed["ran"] is False, str(failed))
        check("--failed records a reason", bool(failed["reason"]))

        s = rot.build_state("demo", rot.DEFAULT_CONFIG, "d", failed,
                            {"ran": True, "model": "gpt-6-astra",
                             "text": REVIEW_B})
        report = rot.render_report(s)
        check("a failed dispatch renders as ONE_REVIEW",
              s["coverage"] == rot.COVERAGE_ONE_REVIEW, s["coverage"])
        check("a failed dispatch never claims independence",
              "independent" not in report.lower())

        ok = _record(root, REVIEW_A, ["--ran", "--model-id",
                                      "claude-fable-5-1"])
        check("--ran with real text is ran=True", ok["ran"] is True, str(ok))
        check("the requested model id is recorded",
              ok["model_id"] == "claude-fable-5-1")

        empty = _record(root, "   \n ", ["--ran"])
        check("--ran with an empty file is still ran=False",
              empty["ran"] is False, str(empty))
        check("the empty-file reason says so",
              "empty" in empty["reason"].lower(), empty["reason"])

        missing = _record(root, "", ["--failed", "--reason", "dispatch blew up"],
                          write_text_file=False, name="never-written.txt")
        check("a missing text file does not raise",
              missing["ran"] is False, str(missing))
        check("a missing text file keeps the caller's reason",
              "dispatch blew up" in missing["reason"], missing["reason"])

        # The case above passes on `--failed` alone, so it cannot show that a
        # missing file is handled. Pass `--ran` so ONLY the read failure can
        # decide the outcome.
        check("the missing file really is missing",
              not (root / "never-written.txt").exists())
        claimed = _record(root, "", ["--ran"], write_text_file=False,
                          name="never-written.txt")
        check("a missing file with --ran is still ran=False",
              claimed["ran"] is False, str(claimed))
        check("the reason names the unreadable file",
              "could not read" in claimed["reason"].lower(),
              claimed["reason"])

        # A failed reviewer's partial output must reach the page.
        partial = _record(root, "PARTIAL REVIEW BODY HERE",
                          ["--failed", "--reason", "stalled"])
        s2 = rot.build_state("demo", rot.DEFAULT_CONFIG, "d", partial,
                             {"ran": True, "model": "gpt-6-astra",
                              "text": REVIEW_B})
        rendered = rot.render_report(s2)
        check("a failed reviewer's partial text is rendered",
              "PARTIAL REVIEW BODY HERE" in rendered)
        check("the partial text is labelled as not a review",
              "not a review" in rendered.lower())


def test_record_claude_requires_an_explicit_outcome() -> None:
    """Neither flag must be an error, not a quiet default either way."""
    print("record-claude -> the outcome flag is required")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "review.txt").write_text(REVIEW_A, encoding="utf-8")
        # argparse prints its usage to stderr before exiting; swallow it so a
        # passing run's output stays readable.
        import contextlib
        import io
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                rot.main(["--repo-root", str(root), "record-claude",
                          "--model", "fable",
                          "--text-file", str(root / "review.txt"),
                          "--out", str(root / "out.json")])
            exited = False
        except SystemExit:
            exited = True
        check("omitting --ran/--failed is rejected", exited,
              "the outcome defaulted instead of being required")


def test_render_subcommand_survives_a_degraded_state_file() -> None:
    """`render` reads a file someone else wrote. It must not crash on it.

    The round-one fix that made the renderer survive degraded input was
    installed in `build_state`, which `cmd_render` never called - so the same
    KeyError still shipped on the neighbouring path.
    """
    print("render subcommand -> survives truncated and missing state files")
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        cases = {
            "no-derived-keys.json": {
                "artifact": "demo",
                "claude": {"ran": True, "model": "fable", "text": REVIEW_A},
                "codex": {"ran": True, "model": "gpt-6-astra",
                          "text": REVIEW_B}},
            "empty.json": {},
            "half.json": {"artifact": "demo", "claude": {"ran": True}},
            "not-an-object.json": [],
        }
        for name, payload in cases.items():
            path = root / name
            path.write_text(json.dumps(payload), encoding="utf-8")
            out = root / "report.md"
            try:
                rot.main(["render", "--state", str(path), "--out", str(out)])
                report, raised, detail = out.read_text(encoding="utf-8"), False, ""
            except Exception as exc:  # noqa: BLE001
                report, raised, detail = "", True, f"{type(exc).__name__}: {exc}"
            check(f"render survives {name}", not raised, detail)
            if not raised and name != "no-derived-keys.json":
                check(f"{name} claims no independence",
                      "independent" not in report.lower())

        try:
            rot.main(["render", "--state", str(root / "absent.json"),
                      "--out", str(root / "r.md")])
            raised, detail = False, ""
        except Exception as exc:  # noqa: BLE001
            raised, detail = True, f"{type(exc).__name__}: {exc}"
        check("render survives a state file that does not exist",
              not raised, detail)


def test_config_command_does_not_overstate_readiness() -> None:
    """An installed binary is discovery, not a working reviewer."""
    print("config -> reports discovery, not readiness")
    import contextlib
    import io
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        rot.main(["config"])
    payload = json.loads(buffer.getvalue())
    check("the key is named for what it measures",
          "codex_found" in payload and "codex_available" not in payload,
          str(sorted(payload)))
    check("authentication is explicitly not claimed",
          payload["codex_auth_verified"] is False)
    check("readiness text says what was not verified",
          "NOT verified" in payload["codex_readiness"]
          or "no executable" in payload["codex_readiness"],
          payload["codex_readiness"])


def test_non_ascii_review_does_not_fail_the_run() -> None:
    """A review full of en-dashes must not fail a run that already worked.

    Windows consoles default to cp1252. Printing the report raised
    UnicodeEncodeError *after* `--out` had written the file, so the finished
    report sat on disk while the command exited 1. Observed here on the real
    self-review, whose Codex half is full of en-dashes and curly quotes.
    """
    print("non-ASCII review -> assembles and prints without failing")
    import contextlib
    import io
    fancy = "**VIABLE**\n\nThe design holds — defects D1–D3 block; “quoted”."
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        for name, payload in (
            ("claude.json", {"ran": True, "model": "fable", "text": fancy}),
            ("codex.json", {"ran": True, "model": "gpt-6-astra",
                            "text": fancy}),
        ):
            (root / name).write_text(json.dumps(payload), encoding="utf-8")
        out = root / "report.md"
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                code = rot.main([
                    "--repo-root", str(root), "assemble",
                    "--artifact", "demo",
                    "--claude-result", str(root / "claude.json"),
                    "--codex-result", str(root / "codex.json"),
                    "--out", str(out)])
            raised, detail = False, ""
        except Exception as exc:  # noqa: BLE001
            code, raised, detail = 1, True, f"{type(exc).__name__}: {exc}"
        check("assemble does not raise on non-ASCII", not raised, detail)
        check("assemble exits 0 on non-ASCII", code == 0)
        if out.exists():
            body = out.read_text(encoding="utf-8")
            check("the em-dash survives into the written report",
                  "—" in body)
            check("the report claims two independent reviews",
                  "two independent reviews" in body.lower())


def test_build_prompt_carries_the_shared_method() -> None:
    """Both reviewers must be handed the same instructions."""
    print("build-prompt -> the shared rubric, not a retyped subset")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "prompt.txt"
        rot.main(["build-prompt", "--artifact", "plugin/demo/",
                  "--out", str(out)])
        body = out.read_text(encoding="utf-8")
        check("the prompt names the artifact", "plugin/demo/" in body)
        check("the prompt carries the method section",
              "## The method" in body)
        check("the prompt carries the local failure shapes",
              "one rung short of the" in body)
        check("the prompt carries the verdict shape",
              "NOT VIABLE AS WRITTEN" in body)
        check("the prompt carries the artifact rubric",
              "## The artifact rubric" in body)

        agent = (Path(rot.__file__).resolve().parents[1]
                 / "agents" / "reviewer-claude.md").read_text(encoding="utf-8")
        # Parity: the Claude agent must defer to the same file rather than
        # carrying its own copy of the method, or the two reviewers drift.
        check("the Claude agent defers to the same rubric file",
              "templates/rubric.md" in agent)
        check("the Claude agent does not carry its own failure-shape list",
              "pathlib.write_text" not in agent,
              "the agent duplicates the rubric's method; they will drift")


TESTS = [
    test_codex_missing_reports_one_review,
    test_claude_missing_reports_one_review,
    test_unresolvable_family_is_could_not_tell,
    test_loose_prefix_does_not_resolve_confidently,
    test_empty_model_is_unknown_not_blank,
    test_same_family_is_not_independent,
    test_neither_ran,
    test_happy_path_is_the_only_independent_one,
    test_truthy_string_ran_is_not_a_run,
    test_empty_review_text_is_not_a_run,
    test_malformed_result_is_not_a_run,
    test_missing_keys_do_not_crash_the_renderer,
    test_missing_verdict_is_surfaced,
    test_verdict_is_a_line_not_a_substring,
    test_disagreement_is_surfaced_not_adjudicated,
    test_codex_banner_is_not_a_review,
    test_codex_success_uses_last_message,
    test_codex_nonzero_exit_is_not_a_run,
    test_codex_timeout_is_not_a_run,
    test_codex_tempfile_failure_is_not_a_run,
    test_codex_missing_binary_is_not_a_run,
    test_config_shapes,
    test_config_value_types,
    test_record_claude_states_success_never_infers_it,
    test_record_claude_requires_an_explicit_outcome,
    test_render_subcommand_survives_a_degraded_state_file,
    test_config_command_does_not_overstate_readiness,
    test_non_ascii_review_does_not_fail_the_run,
    test_build_prompt_carries_the_shared_method,
]


def run(quiet: bool = False) -> int:
    FAILURES.clear()
    for test in TESTS:
        if quiet:
            import io
            import contextlib
            with contextlib.redirect_stdout(io.StringIO()):
                test()
        else:
            test()
    if not quiet:
        print()
    if FAILURES:
        if not quiet:
            print(f"FAILED: {len(FAILURES)} check(s)")
        return 1
    if not quiet:
        print("OK: all checks passed")
    return 0


# --------------------------------------------------------------------------
# Sabotage
# --------------------------------------------------------------------------

def _sabotage_banner():
    """The renderer always claims two independent reviews."""
    original = rot.render_banner
    rot.render_banner = lambda state: (
        "**Coverage: two independent reviews.** The Rule of Two held.")
    return lambda: setattr(rot, "render_banner", original)


def _sabotage_title():
    """The title always carries the Rule of Two name."""
    original = rot.render_title
    rot.render_title = lambda state: f"# Rule of Two review - {state['artifact']}"
    return lambda: setattr(rot, "render_title", original)


def _sabotage_evidence_gate():
    """Anything claiming to have run counts as a review."""
    original = rot.normalize_result

    def lax(raw, side_label):
        # Same key set as the real one, so this sabotage varies exactly one
        # thing: how `ran` is decided. A sabotage that also drops keys would
        # fail the suite for the wrong reason and prove nothing about the
        # guard it is aimed at.
        if not isinstance(raw, dict):
            raw = {}
        text = raw.get("text", "")
        verdict = rot.find_verdict(text) if isinstance(text, str) else ""
        return {"ran": bool(raw.get("ran")), "model": raw.get("model", ""),
                "model_id": raw.get("model_id", ""),
                "reason": raw.get("reason", ""), "text": text,
                "log": raw.get("log", ""), "verdict": verdict,
                "verdict_found": bool(verdict)}

    rot.normalize_result = lax
    return lambda: setattr(rot, "normalize_result", original)


def _sabotage_family_prefixes():
    """Aliases match as loose prefixes again, as they did in the first draft."""
    original_aliases = rot.FAMILY_ALIASES
    original_prefixes = rot.FAMILY_PREFIXES
    rot.FAMILY_ALIASES = ()
    rot.FAMILY_PREFIXES = (
        ("anthropic", ("claude-", "claude_", "opus", "sonnet", "haiku",
                       "fable")),
        ("openai", ("gpt", "o1", "o3", "o4", "codex")),
    )

    def restore():
        rot.FAMILY_ALIASES = original_aliases
        rot.FAMILY_PREFIXES = original_prefixes

    return restore


def _sabotage_verdict_substring():
    """Verdict detection goes back to a substring search anywhere in the text."""
    original = rot.find_verdict
    rot.find_verdict = lambda text: next(
        (t for t in ("VIABLE WITH CHANGES", "NOT VIABLE AS WRITTEN", "VIABLE")
         if isinstance(text, str) and t in text.upper()), "")
    return lambda: setattr(rot, "find_verdict", original)


SABOTAGES = [
    ("renderer always claims two independent reviews", _sabotage_banner),
    ("title always carries the Rule of Two name", _sabotage_title),
    ("evidence gate accepts any truthy 'ran'", _sabotage_evidence_gate),
    ("aliases match as loose prefixes", _sabotage_family_prefixes),
    ("verdict is a substring search again", _sabotage_verdict_substring),
]


def sabotage() -> int:
    """Break each guard on purpose; the suite must go red for every one.

    The three sabotages are the three ways this plugin has actually been
    seen to fail: a banner that does not reflect coverage, a title that
    keeps the name after the banner has withdrawn it, and an evidence gate
    that trusts a model-written `ran` field.
    """
    failed_to_catch = []
    for label, install in SABOTAGES:
        print(f"=== SABOTAGE: {label} ===")
        restore = install()
        try:
            code = run(quiet=True)
            caught = len(FAILURES)
        finally:
            restore()
        if code == 0:
            print("  NOT CAUGHT: the suite passed against a broken guard.")
            failed_to_catch.append(label)
        else:
            print(f"  caught - {caught} check(s) went red")
        print()

    if failed_to_catch:
        print("SABOTAGE CHECK FAILED: these guards are unprotected:")
        for label in failed_to_catch:
            print(f"  - {label}")
        return 1
    print(f"SABOTAGE CHECK PASSED: all {len(SABOTAGES)} sabotages were caught.")
    print()
    print("=== guards restored; the suite must go green again ===")
    return run()


if __name__ == "__main__":
    if "--sabotage" in sys.argv:
        sys.exit(sabotage())
    sys.exit(run())
