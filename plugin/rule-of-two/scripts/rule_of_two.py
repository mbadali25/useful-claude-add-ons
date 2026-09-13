#!/usr/bin/env python3
"""Rule of Two - the mechanical half of a two-family adversarial review.

This script owns everything that must not be left to a model's judgement:
resolving the two configured reviewers, deciding whether each one actually
ran, resolving both to model families, and rendering the report - title and
coverage banner included.

The load-bearing rule, and the reason this is code rather than prose:

    "Only one reviewer ran" is its own reported outcome.

A report that silently loses the second family while keeping the Rule of Two
name is the defect this plugin exists to avoid. So COVERAGE is an explicit
enum, UNKNOWN is a real value rather than a missing one, and the renderer is
the thing under test - a coverage value computed correctly can still be
dropped on the way to the page.

Two results from this plugin's first self-review shaped the code below, and
both were "the guard trusted its input":

  * `ran` arrived from a model-authored JSON file and was coerced with
    `bool()`, so the string "false" read as a successful review. Now
    `normalize_result` requires the literal `True` and requires review text
    to go with it; anything else is a reviewer that did not run, with a
    reason saying so.
  * Codex's startup banner was captured as review text, because stderr was
    merged into stdout and the result only had to be non-empty. Now the
    review comes from `--output-last-message` and the diagnostics are kept
    separately as `log`.

Stdlib only. No dependency on crew, its config, or its provider order.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Pin-then-fallback is configurable rather than hardcoded, because model names
# churn and a hardcoded fallback is the next name to churn.
#
# Note the two spellings on the Claude side. They are different namespaces and
# they are NOT interchangeable: `pin` / `fallback` are dispatch aliases (what
# the Agent tool and agent frontmatter accept), while `*_model_id` is the full
# id a CLI `--model` flag takes. The command dispatches on the alias; the id is
# recorded so the report can say which model was actually asked for.
DEFAULT_CONFIG = {
    "claude": {
        "pin": "fable",
        "fallback": "opus",
        "pin_model_id": "claude-fable-5-1",
        "fallback_model_id": "claude-opus-5",
    },
    "codex": {
        "pin": "gpt-6-astra",
        "fallback": "",
        "timeout_seconds": 900,
    },
}

CONFIG_FILENAME = ".rule-of-two.json"

# Verdict detection. Their absence does not make a review "not run" - that
# would be brittle - but it is surfaced, because a review with no verdict has
# not answered the question it was asked.
#
# Matched as a WHOLE LINE, near the top, not as a substring anywhere. A
# substring search is worse than no check: "This is unviable." contains
# "VIABLE", and "I cannot determine whether this is viable." contains it too,
# so a review explicitly refusing to give a verdict satisfied the flag whose
# entire job was to catch that. Both were reproduced against the first draft.
VERDICT_RE = re.compile(
    r"^[*_\s]*(VIABLE WITH CHANGES|NOT VIABLE AS WRITTEN|VIABLE)[*_\s.:!]*$",
    re.IGNORECASE,
)

# The rubric says the verdict opens the report. Only headings are skipped
# over, so the verdict must be the FIRST line of actual content.
VERDICT_SEARCH_LINES = 20


def find_verdict(text: str) -> str:
    """Return the review's own verdict, or "" if it did not give one.

    Only the first line of real content can be the verdict. This is the third
    version of this function and each earlier one was too permissive in a
    different way, which is worth spelling out because the pattern is the
    point:

      * v1 searched for the token as a SUBSTRING anywhere. "This is
        unviable." matched, and so did a sentence refusing to give a verdict.
      * v2 matched a whole line but allowed `-` and `>` in the leading
        characters. So a bulleted echo of the three options matched - and
        `re.search` takes the earliest, which is the most favourable one - as
        did a quoted example of the required format. A review explicitly
        declining to answer was rendered as having passed the artifact.

    Both v1 and v2 were fixes that made the flag actively supply the answer
    it existed to say was missing. Leading `-` and `>` are therefore gone:
    a list item and a block quote are someone quoting the question, not
    answering it.
    """
    if not isinstance(text, str):
        return ""
    for raw in text.splitlines()[:VERDICT_SEARCH_LINES]:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue  # blank lines and headings sit above the verdict
        match = VERDICT_RE.match(line)
        # The first content line decides, whatever it is. If it is not a
        # verdict, this review did not open with one, and nothing further
        # down counts.
        return match.group(1).upper() if match else ""
    return ""


def config_paths(repo_root: Path) -> list[Path]:
    """Where config is looked for, nearest first. Never crew's config."""
    home = Path(os.path.expanduser("~"))
    return [
        repo_root / CONFIG_FILENAME,
        home / ".claude" / "rule-of-two" / "config.json",
    ]


def load_config(repo_root: Path) -> tuple[dict, str]:
    """Return (config, source). Shallow-merges over DEFAULT_CONFIG.

    Every shape assumption is checked. Valid JSON that is not an object - a
    bare list, a string, a number - is a configuration error reported as one,
    not an AttributeError from three frames down.
    """
    merged = {k: dict(v) for k, v in DEFAULT_CONFIG.items()}
    for path in config_paths(repo_root):
        if not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            return merged, f"built-in defaults ({path} is unreadable: {exc})"
        if not isinstance(raw, dict):
            return merged, (
                f"built-in defaults ({path} must contain a JSON object, "
                f"found {type(raw).__name__})"
            )
        notes = []
        for section in ("claude", "codex"):
            if section not in raw:
                continue
            value = raw[section]
            # `None` is checked here, AFTER membership, not before the dict
            # branch. Skipping it early meant an explicit `"codex": null` was
            # dropped in silence while `"codex": "str"` was reported - a user
            # statement discarded with no note, in the one function whose
            # comment promises to say what it ignored.
            if not isinstance(value, dict):
                notes.append(f"'{section}' must be an object, found "
                             f"{type(value).__name__}; kept defaults")
                continue
            merged[section].update(value)
        notes.extend(_coerce_config(merged))
        source = str(path)
        if notes:
            # Say which settings were ignored and why. A file silently
            # accepted while half its settings were dropped is the same
            # failure this plugin polices: a check that looks like it
            # happened.
            source = f"{source} (ignored: {'; '.join(notes)})"
        return merged, source
    return merged, "built-in defaults"


def _coerce_config(merged: dict) -> list[str]:
    """Force every value to the type the rest of the code assumes.

    Validating only the root and section shapes left the values that actually
    reach `subprocess` and `int()` unchecked, so `{"codex": {"pin": null}}`
    was accepted as valid config and then raised a TypeError from three
    frames down. A bad value now degrades to the honest outcome the design
    already has - an empty model resolves to UNKNOWN and reports "could not
    tell" - instead of a traceback.
    """
    notes: list[str] = []
    for section in ("claude", "codex"):
        for key, value in list(merged[section].items()):
            if key not in DEFAULT_CONFIG[section]:
                # A setting nothing reads. Saying so beats dropping it in
                # silence: `claude.timeout_seconds` looks like it should
                # work, and a user who writes it deserves to be told it does
                # not rather than to wonder why nothing changed.
                notes.append(f"{section}.{key} is not a recognised setting")
            default = DEFAULT_CONFIG[section].get(key)
            # `timeout_seconds` is keyed on having an INTEGER default, not on
            # its name. Matching the name alone crashed with a KeyError when
            # a user put `timeout_seconds` in the claude section, which has
            # no such default - the branch assumed a key its own guard had
            # not established.
            if isinstance(default, int) and not isinstance(default, bool):
                try:
                    coerced = int(value)
                except (TypeError, ValueError, OverflowError):
                    # OverflowError is not hypothetical: JSON's 1e400 parses
                    # to float infinity, which int() refuses.
                    notes.append(f"{section}.{key} must be an integer, found "
                                 f"{value!r}")
                    merged[section][key] = default
                    continue
                if coerced <= 0:
                    notes.append(f"{section}.{key} must be positive, found "
                                 f"{coerced}")
                    merged[section][key] = default
                else:
                    merged[section][key] = coerced
                continue
            if not isinstance(value, str):
                notes.append(f"{section}.{key} must be a string, found "
                             f"{value!r}")
                merged[section][key] = default if isinstance(default, str) else ""
                continue
            if "\x00" in value:
                # A NUL passes every type check and then raises ValueError
                # from deep inside subprocess. Reject it where it is still a
                # config problem rather than a dispatch crash.
                notes.append(f"{section}.{key} contains a null character")
                merged[section][key] = default if isinstance(default, str) else ""
    # Keys with an integer default must end up as integers even when the
    # section never mentioned them.
    for section in ("claude", "codex"):
        for key, default in DEFAULT_CONFIG[section].items():
            merged[section].setdefault(key, default)
    return notes


# --------------------------------------------------------------------------
# Model families
# --------------------------------------------------------------------------

# Deliberately tiny. This plugin has exactly two reviewers, fixed to different
# families by construction; the only question it asks is "are these two
# actually different, and did both run". It is NOT a solver searching a
# provider list for an independent candidate. If this ever needs to grow into
# one, revisit the standalone decision rather than growing this table.
#
# Re-measure rather than trusting a count written here: the tables are
# FAMILY_ALIASES and FAMILY_PREFIXES below, and a stated number goes stale the
# moment either changes.
#
# Two tables, not one, and the split is the whole point. Dispatch aliases are
# whole words and are matched EXACTLY; model ids are matched by a prefix that
# carries its own separator. Collapsing them into one prefix table is the
# defect that shipped in the first draft: `sonnet` as a bare prefix resolved
# `sonnetting` to anthropic, and `fable` resolved `fable-fiction`, so an
# unknown alias bought a confident family and a "the Rule of Two held" report.
# That is the same loose-prefix bug that had already been fixed on the openai
# side one edit earlier - fixed for `o3-`, left standing for `sonnet`. The
# neighbouring case, exactly where this repo says to look.
FAMILY_ALIASES = (
    ("anthropic", ("opus", "sonnet", "haiku", "fable")),
    ("openai", ("gpt", "codex")),
)

FAMILY_PREFIXES = (
    ("anthropic", ("claude-", "claude_")),
    ("openai", ("gpt-", "gpt_", "o1-", "o3-", "o4-", "codex-", "codex_")),
)

UNKNOWN_FAMILY = "UNKNOWN"


def resolve_family(model) -> str:
    """Map a model id or dispatch alias to a family, or UNKNOWN.

    UNKNOWN is a real value that must survive into every line derived from
    it. It is never silently treated as "probably fine".

    Aliases match exactly; ids match on a prefix carrying its separator
    (`o3-`, never `o3`). Anything else is UNKNOWN. For a guard whose thesis
    is that "could not tell" must be its own outcome, erring toward UNKNOWN
    is the only defensible direction: a wrong family reads as a passed check,
    while an unknown one reads as the open question it is.
    """
    if not isinstance(model, str) or not model.strip():
        return UNKNOWN_FAMILY
    name = model.strip().lower()
    for family, aliases in FAMILY_ALIASES:
        if name in aliases:
            return family
    for family, prefixes in FAMILY_PREFIXES:
        for prefix in prefixes:
            if name.startswith(prefix):
                return family
    return UNKNOWN_FAMILY


# --------------------------------------------------------------------------
# Result validation
# --------------------------------------------------------------------------

def normalize_result(raw, side_label: str) -> dict:
    """Turn an untrusted reviewer result into a trusted one.

    The Claude side's result is written by a model mid-command, which is the
    least reliable input in the system, and it decides the headline. So:

      * `ran` must be the literal boolean True. The string "true", the
        string "false", 1, and None are all "did not run" - a truthy string
        must never buy a successful review.
      * A successful run must carry review text. "Ran and returned nothing"
        is not a review, and calling it one is how a single-family report
        ends up wearing the Rule of Two name.
      * A malformed result is a reviewer that did not run, with a reason
        that says the result was malformed - never a silent pass.
    """
    blank = {"ran": False, "model": "", "model_id": "", "reason": "",
             "text": "", "log": "", "verdict": "", "verdict_found": False}

    if not isinstance(raw, dict):
        return {**blank,
                "reason": f"{side_label} result is not a JSON object "
                          f"(found {type(raw).__name__})"}

    def as_str(key: str) -> str:
        value = raw.get(key)
        return value if isinstance(value, str) else ""

    model = as_str("model").strip()
    model_id = as_str("model_id").strip()
    text = as_str("text")
    log = as_str("log")
    reason = as_str("reason").strip()
    ran = raw.get("ran")

    if ran is not True:
        if ran is not False:
            reason = (
                f"{side_label} result has a non-boolean 'ran' ({ran!r}); "
                f"treating as did not run"
            )
        return {"ran": False, "model": model, "model_id": model_id,
                "reason": reason or "no reason recorded",
                "text": text, "log": log, "verdict": "",
                "verdict_found": False}

    if not text.strip():
        return {"ran": False, "model": model, "model_id": model_id,
                "reason": f"{side_label} reported a successful run but "
                          f"returned no review text",
                "text": "", "log": log, "verdict": "", "verdict_found": False}

    verdict = find_verdict(text)
    return {"ran": True, "model": model, "model_id": model_id, "reason": "",
            "text": text, "log": log, "verdict": verdict,
            "verdict_found": bool(verdict)}


# --------------------------------------------------------------------------
# Coverage - the load-bearing enum
# --------------------------------------------------------------------------

COVERAGE_TWO_CROSS_FAMILY = "TWO_CROSS_FAMILY"
COVERAGE_TWO_SAME_FAMILY = "TWO_SAME_FAMILY"
COVERAGE_TWO_FAMILY_UNKNOWN = "TWO_FAMILY_UNKNOWN"
COVERAGE_ONE_REVIEW = "ONE_REVIEW"
COVERAGE_NO_REVIEW = "NO_REVIEW"


def compute_coverage(claude_ran: bool, codex_ran: bool,
                     claude_family: str, codex_family: str) -> str:
    """Decide the coverage outcome. Order matters: 'did it run' first.

    A family comparison over a reviewer that never ran is meaningless, so the
    run check is asked first and the family check never rescues it.
    """
    ran = [claude_ran, codex_ran]
    if not any(ran):
        return COVERAGE_NO_REVIEW
    if not all(ran):
        return COVERAGE_ONE_REVIEW
    if UNKNOWN_FAMILY in (claude_family, codex_family):
        return COVERAGE_TWO_FAMILY_UNKNOWN
    if claude_family == codex_family:
        return COVERAGE_TWO_SAME_FAMILY
    return COVERAGE_TWO_CROSS_FAMILY


def coverage_is_satisfied(coverage: str) -> bool:
    """True only when the Rule of Two actually held."""
    return coverage == COVERAGE_TWO_CROSS_FAMILY


# --------------------------------------------------------------------------
# Codex invocation
# --------------------------------------------------------------------------
#
# crew calls codex from a shell snippet inside a command prompt
# (plugin/crew/commands/review.md:297) with no stdin redirect and no timeout.
# That is the anti-pattern, not the pattern: `codex exec` reads stdin, so an
# inherited stdin hangs until something closes it - a ten-minute stall that
# looks intermittent. Redirect from devnull and set an explicit timeout, and
# map a timeout to "did not run" rather than "ran and found nothing".


def codex_available() -> tuple[bool, str]:
    """Whether a `codex` executable is FOUND. Not whether it will work.

    This is `shutil.which` and nothing more. It says nothing about
    authentication, about whether the configured model still exists, or
    about the account being entitled to it - all three fail at dispatch, not
    here. Callers must not report this as readiness; the key it is published
    under is named `codex_found` for that reason.
    """
    path = shutil.which("codex")
    if not path:
        return False, "no `codex` executable on PATH"
    return True, path


def run_codex(model: str, prompt: str, timeout_seconds: int,
              cwd: Path) -> dict:
    """Run one codex review. Returns a raw result dict; never raises.

    The review text comes from `--output-last-message`, NOT from stdout.
    stdout carries the startup banner, the sandbox and model lines, and the
    token count, and an earlier version of this function accepted all of that
    as a review because it only checked that the stream was non-empty. A
    banner is not a finding. The combined stream is kept as `log` so a failed
    run can still be diagnosed.
    """
    available, detail = codex_available()
    if not available:
        return {"ran": False, "reason": detail, "model": model,
                "text": "", "log": ""}

    # Inside the guarded region, not before it. `mkstemp` raises when there is
    # no usable temporary directory, and creating the file above the try block
    # let that escape a function documented as never raising - which turns a
    # degraded reviewer into an aborted report, exactly when the report is how
    # anyone would find out.
    try:
        handle, last_message_path = tempfile.mkstemp(
            prefix="rule-of-two-", suffix=".txt")
        os.close(handle)
    except (OSError, ValueError) as exc:
        return {"ran": False,
                "reason": f"could not create a temporary file for codex "
                          f"output: {exc}",
                "model": model, "text": "", "log": ""}

    argv = [
        "codex", "exec",
        "-m", model,
        "-s", "read-only",
        "--skip-git-repo-check",
        "--output-last-message", last_message_path,
        prompt,
    ]
    try:
        with open(os.devnull, "rb") as devnull:
            proc = subprocess.run(
                argv,
                stdin=devnull,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                cwd=str(cwd),
                timeout=timeout_seconds,
                check=False,
            )
        log = proc.stdout.decode("utf-8", errors="replace")
        returncode = proc.returncode
    except subprocess.TimeoutExpired as exc:
        _cleanup(last_message_path)
        # Bind the exception and keep whatever it captured. A stall is
        # exactly when someone needs the diagnostics, and discarding them
        # here left the failure renderer with nothing to show.
        partial = exc.output or b""
        if isinstance(partial, str):
            partial = partial.encode("utf-8", errors="replace")
        return {"ran": False,
                "reason": f"codex timed out after {timeout_seconds}s",
                "model": model, "text": "",
                "log": partial.decode("utf-8", errors="replace")}
    except (OSError, ValueError) as exc:
        # ValueError, not just OSError: a model string carrying a NUL raises
        # "embedded null character" from inside subprocess, and an
        # OSError-only handler let it escape a function documented as never
        # raising.
        _cleanup(last_message_path)
        return {"ran": False, "reason": f"could not start codex: {exc}",
                "model": model, "text": "", "log": ""}

    try:
        review = Path(last_message_path).read_text(
            encoding="utf-8", errors="replace")
    except OSError:
        review = ""
    _cleanup(last_message_path)

    if returncode != 0:
        first = next((ln for ln in log.splitlines()
                      if ln.strip().startswith("ERROR")), "").strip()
        why = f"codex exited {returncode}"
        if first:
            why = f"{why}: {first}"
        return {"ran": False, "reason": why, "model": model,
                "text": "", "log": log}

    if not review.strip():
        return {"ran": False,
                "reason": "codex exited 0 but wrote no final message",
                "model": model, "text": "", "log": log}

    return {"ran": True, "reason": "", "model": model,
            "text": review, "log": log}


def _cleanup(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Rendering - the thing under test
# --------------------------------------------------------------------------

def render_title(state: dict) -> str:
    """The H1. It carries the Rule of Two name ONLY when the rule held.

    A correct banner under a title reading "Rule of Two review" still leaves
    the wrong four words at the top of the page, in the line most likely to
    be pasted, screenshotted, or skimmed on its own.
    """
    artifact = state["artifact"]
    coverage = state["coverage"]
    if coverage == COVERAGE_TWO_CROSS_FAMILY:
        return f"# Rule of Two review - {artifact}"
    if coverage == COVERAGE_ONE_REVIEW:
        return f"# Single-reviewer review, NOT the Rule of Two - {artifact}"
    if coverage == COVERAGE_TWO_SAME_FAMILY:
        return f"# Same-family review, NOT the Rule of Two - {artifact}"
    if coverage == COVERAGE_TWO_FAMILY_UNKNOWN:
        return (f"# Two reviews, cross-family check inconclusive - "
                f"{artifact}")
    return f"# No review ran - {artifact}"


def render_banner(state: dict) -> str:
    """The coverage banner. Every report opens with this.

    The word "independent" appears here ONLY when two reviewers from
    different families both actually ran. In every other outcome it is
    absent entirely - including the negative phrasing, because a reader
    skimming for the word finds it either way.
    """
    coverage = state["coverage"]
    claude = state["claude"]
    codex = state["codex"]

    if coverage == COVERAGE_TWO_CROSS_FAMILY:
        return (
            f"**Coverage: two independent reviews.** "
            f"{claude['model']} ({claude['family']}) and "
            f"{codex['model']} ({codex['family']}) both ran, and resolve to "
            f"different model families. The Rule of Two held."
        )

    if coverage == COVERAGE_TWO_FAMILY_UNKNOWN:
        pairs = ", ".join(
            f"{side['model'] or '(unset)'} -> {side['family']}"
            for side in (claude, codex)
        )
        return (
            f"**Coverage: two reviews ran, but the cross-family check could "
            f"not tell.** At least one model did not resolve to a known "
            f"family ({pairs}). Treat this as an unanswered question, not as "
            f"a passed check - the Rule of Two is NOT established here."
        )

    if coverage == COVERAGE_TWO_SAME_FAMILY:
        return (
            f"**Coverage: two reviews ran, but both are the same family "
            f"({claude['family']}).** {claude['model']} and {codex['model']} "
            f"share a family, so this is one perspective wearing two names. "
            f"The Rule of Two did NOT hold."
        )

    if coverage == COVERAGE_ONE_REVIEW:
        ran = claude if claude["ran"] else codex
        missing = codex if claude["ran"] else claude
        return (
            f"**Coverage: THIS IS ONE REVIEW, NOT TWO.** Only "
            f"{ran['model']} ({ran['family']}) ran. The second reviewer, "
            f"{missing['model'] or '(unset)'}, did not run: "
            f"{missing['reason'] or 'no reason recorded'}. "
            f"Read everything below as a single-family opinion. The Rule of "
            f"Two did NOT hold."
        )

    return (
        "**Coverage: NO REVIEW RAN.** Neither reviewer produced output "
        f"(claude: {claude['reason'] or 'no reason recorded'}; "
        f"codex: {codex['reason'] or 'no reason recorded'}). "
        "There are no findings below, and nothing here has been checked."
    )


def _log_tail(log: str, lines: int = 12) -> str:
    kept = [ln for ln in log.splitlines() if ln.strip()][-lines:]
    return "\n".join(kept)


def render_report(state: dict) -> str:
    """Assemble the full report. Title and banner both derive from coverage."""
    claude = state["claude"]
    codex = state["codex"]

    lines = [
        render_title(state),
        "",
        render_banner(state),
        "",
    ]

    for label, side in (("Reviewer A (Claude)", claude),
                        ("Reviewer B (Codex)", codex)):
        status = "ran" if side["ran"] else "DID NOT RUN"
        detail = "" if side["ran"] else f" ({side['reason']})"
        # The model is what the orchestrator asked for and recorded, not
        # something this script observed the provider serve. Say "requested"
        # rather than implying it was attested.
        asked = side.get("model_id", "")
        asked = f", requested as `{asked}`" if asked else ""
        verdict = f" - verdict: **{side['verdict']}**" if side.get(
            "verdict") else ""
        lines.append(f"- {label}: alias `{side['model'] or '(unset)'}`"
                     f"{asked} - {status}{detail}{verdict}")
    lines.append(f"- Config source: {state.get('config_source', 'unknown')}")

    if claude["ran"] and codex["ran"]:
        a, b = claude.get("verdict", ""), codex.get("verdict", "")
        if a and b and a != b:
            lines.append("")
            lines.append(
                f"**The two reviewers disagree on the verdict: "
                f"{a} against {b}.** That disagreement is the most "
                f"informative thing in this report. Read both; it has not "
                f"been adjudicated, and it should not be."
            )
    lines.append("")

    for label, side in (("Reviewer A (Claude)", claude),
                        ("Reviewer B (Codex)", codex)):
        lines.append(f"## {label}")
        lines.append("")
        if side["ran"]:
            if not side.get("verdict_found", False):
                lines.append(
                    "> This review carries none of the rubric's three "
                    "verdicts. It ran, but it did not answer the question it "
                    "was asked - weigh it accordingly."
                )
                lines.append("")
            lines.append(side["text"].strip())
        else:
            lines.append(f"_Did not run: {side['reason']}._")
            partial = side.get("text", "").strip()
            if partial:
                # A failed reviewer can still have produced something. It was
                # kept in state and never rendered, which threw away evidence
                # at the one moment it was worth most.
                lines.append("")
                lines.append("Partial output, which is NOT a review and does "
                             "not count toward coverage:")
                lines.append("")
                lines.append("```")
                lines.append(partial)
                lines.append("```")
            tail = _log_tail(side.get("log", ""))
            if tail:
                # The diagnostics were paid for. Dropping them exactly when
                # someone needs to know why a reviewer failed is the one
                # moment they are worth most.
                lines.append("")
                lines.append("<details><summary>Last lines of its "
                             "output</summary>")
                lines.append("")
                lines.append("```")
                lines.append(tail)
                lines.append("```")
                lines.append("")
                lines.append("</details>")
        lines.append("")

    if not coverage_is_satisfied(state["coverage"]):
        lines.append("## What is missing")
        lines.append("")
        lines.append(
            "This report does not carry two cross-family opinions. Whatever "
            "it says about the artifact, it has not been checked the way the "
            "Rule of Two claims to check things. Fix the coverage before "
            "acting on the verdict as though it were."
        )
        lines.append("")

    return "\n".join(lines)


def hydrate_state(state) -> dict:
    """Rebuild a state dict's derived fields from its raw halves.

    `cmd_render` reads a state file written by someone else - truncated,
    hand-edited, or produced by an older version - and the round-one fix
    that made the renderer survive degraded input lived in `build_state`,
    which `render` never called. So the same `KeyError` the fix removed from
    one caller still crashed its neighbour. Both callers go through here now.
    """
    if not isinstance(state, dict):
        state = {}
    return build_state(
        artifact=str(state.get("artifact") or "(unnamed artifact)"),
        config=DEFAULT_CONFIG,
        config_source=str(state.get("config_source") or "unknown"),
        claude_result=state.get("claude"),
        codex_result=state.get("codex"),
    )


def build_state(artifact: str, config: dict, config_source: str,
                claude_result, codex_result) -> dict:
    claude = normalize_result(claude_result, "Reviewer A (Claude)")
    codex = normalize_result(codex_result, "Reviewer B (Codex)")
    claude_family = resolve_family(claude["model"])
    codex_family = resolve_family(codex["model"])
    coverage = compute_coverage(
        claude["ran"], codex["ran"], claude_family, codex_family)
    return {
        "artifact": artifact,
        "config_source": config_source,
        "coverage": coverage,
        "coverage_satisfied": coverage_is_satisfied(coverage),
        "claude": {**claude, "family": claude_family},
        "codex": {**codex, "family": codex_family},
    }


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_config(args) -> int:
    config, source = load_config(Path(args.repo_root))
    available, detail = codex_available()
    payload = {
        "config_source": source,
        "config": config,
        "dispatch_order_claude": [
            config["claude"].get("pin", ""),
            config["claude"].get("fallback", ""),
        ],
        "families": {
            "claude_pin": resolve_family(config["claude"].get("pin", "")),
            "claude_fallback": resolve_family(
                config["claude"].get("fallback", "")),
            "codex_pin": resolve_family(config["codex"].get("pin", "")),
        },
        # Named for what it measures. `codex_available` invited callers to
        # report an installed binary as a working reviewer; authentication,
        # model existence and entitlement all fail later, at dispatch.
        "codex_found": available,
        "codex_detail": detail,
        "codex_auth_verified": False,
        "codex_readiness": (
            "executable found; authentication and model availability NOT "
            "verified - they fail at dispatch, not here"
            if available else "no executable found"
        ),
    }
    print(json.dumps(payload, indent=2))
    return 0


def cmd_record_claude(args) -> int:
    """Write the Claude reviewer's result file.

    This exists so the orchestrating model never hand-writes JSON. A
    multi-paragraph report embedded in a shell string gets mangled, and a
    hand-typed `"ran"` is the single least trustworthy field in the system.

    Success is STATED, never inferred. An earlier version computed
    `ran = bool(text.strip())`, which re-opened one rung upstream exactly the
    hole `normalize_result` had just closed: a text file containing
    "dispatch failed: model unavailable" is non-empty, so a failed dispatch
    rendered a full "the Rule of Two held" report. The caller must now pass
    `--ran` or `--failed`, and non-empty text is an additional necessary
    condition rather than the whole test.
    """
    def read(path: str) -> tuple[str, str]:
        if not path:
            return "", ""
        try:
            return Path(path).read_text(encoding="utf-8", errors="replace"), ""
        except OSError as exc:
            return "", f"could not read {path}: {exc}"

    text, text_err = read(args.text_file)
    log, _ = read(args.log_file)

    claimed = args.ran and not args.failed
    reason = args.reason.strip()
    if text_err:
        ran, reason = False, reason or text_err
    elif not claimed:
        ran = False
        reason = reason or "the caller reported the Claude dispatch failed"
    elif not text.strip():
        ran = False
        reason = reason or ("the caller reported a successful dispatch but "
                            "the review file is empty")
    else:
        ran, reason = True, ""

    result = {"ran": ran, "model": args.model, "model_id": args.model_id,
              "reason": reason, "text": text, "log": log}
    Path(args.out).write_text(json.dumps(result, indent=2),
                              encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("text", "log")}, indent=2))
    return 0


def cmd_build_prompt(args) -> int:
    """Emit the Codex reviewer's prompt: the shared rubric, plus the artifact.

    Deterministic, so it is a function rather than shell the orchestrating
    model retypes. It also keeps the two reviewers' instructions identical -
    `templates/rubric.md` carries the whole method, and `reviewer-claude.md`
    reads the same file. If one reviewer were told to run the test suite and
    the other were not, a difference between their reports could be procedure
    rather than judgement, and nobody could tell which.
    """
    rubric = (Path(__file__).resolve().parents[1]
              / "templates" / "rubric.md")
    body = (
        f"{rubric.read_text(encoding='utf-8')}\n"
        f"---\n\n"
        f"The artifact under review is: {args.artifact}\n\n"
        f"Follow the method and the section order above exactly. Start with "
        f"the bold verdict on its own line.\n"
    )
    Path(args.out).write_text(body, encoding="utf-8", newline="\n")
    print(f"wrote {args.out} ({len(body)} chars) for artifact {args.artifact}")
    return 0


def cmd_codex(args) -> int:
    config, _ = load_config(Path(args.repo_root))
    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    result = run_codex(
        model=args.model or config["codex"]["pin"],
        prompt=prompt,
        timeout_seconds=int(config["codex"].get("timeout_seconds", 900)),
        cwd=Path(args.repo_root),
    )
    payload = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8", newline="\n")
    print(json.dumps({k: v for k, v in result.items()
                      if k not in ("text", "log")}, indent=2))
    return 0


def cmd_render(args) -> int:
    try:
        raw = json.loads(Path(args.state).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raw = {"artifact": args.state,
               "claude": {"ran": False,
                          "reason": f"state file unreadable: {exc}"},
               "codex": {"ran": False,
                         "reason": f"state file unreadable: {exc}"}}
    report = render_report(hydrate_state(raw))
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8", newline="\n")
    print(report)
    return 0


def cmd_assemble(args) -> int:
    config, source = load_config(Path(args.repo_root))

    def load(path: str):
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            # A missing or corrupt result file is a reviewer that did not
            # run, reported as one. It is never a reason to abort the
            # report - the report is how anyone finds out.
            return {"ran": False, "model": "", "text": "", "log": "",
                    "reason": f"result file {path} could not be read: {exc}"}

    state = build_state(args.artifact, config, source,
                        load(args.claude_result), load(args.codex_result))
    report = render_report(state)
    if args.out:
        Path(args.out).write_text(report, encoding="utf-8", newline="\n")
    if args.state_out:
        Path(args.state_out).write_text(
            json.dumps(state, indent=2), encoding="utf-8", newline="\n")
    print(report)
    return 0


def _make_stdout_safe() -> None:
    """Stop a non-ASCII review from failing a run that already succeeded.

    Windows consoles default to cp1252, and a review written by either model
    routinely contains en-dashes and curly quotes. `print(report)` then raises
    UnicodeEncodeError - AFTER `--out` has written the file - so the report
    exists on disk and the command still exits 1. A caller checking the exit
    code concludes the review failed while holding the finished report, which
    is the "check the artifact, not the summary" trap from the other side.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass  # already safe, or not reconfigurable; printing still works


def main(argv=None) -> int:
    _make_stdout_safe()
    parser = argparse.ArgumentParser(prog="rule_of_two")
    parser.add_argument("--repo-root", default=".")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("config").set_defaults(func=cmd_config)

    p_rec = sub.add_parser("record-claude")
    p_rec.add_argument("--model", required=True)
    p_rec.add_argument("--model-id", default="")
    p_rec.add_argument("--text-file", required=True)
    p_rec.add_argument("--log-file", default="")
    p_rec.add_argument("--out", required=True)
    p_rec.add_argument("--reason", default="")
    # Mutually exclusive and required: the caller must STATE the outcome.
    # Defaulting either way is how an unknown collapses into a safe value.
    outcome = p_rec.add_mutually_exclusive_group(required=True)
    outcome.add_argument("--ran", action="store_true")
    outcome.add_argument("--failed", action="store_true")
    p_rec.set_defaults(func=cmd_record_claude)

    p_prompt = sub.add_parser("build-prompt")
    p_prompt.add_argument("--artifact", required=True)
    p_prompt.add_argument("--out", required=True)
    p_prompt.set_defaults(func=cmd_build_prompt)

    p_codex = sub.add_parser("codex")
    p_codex.add_argument("--prompt-file", required=True)
    p_codex.add_argument("--model", default="")
    p_codex.add_argument("--out", default="")
    p_codex.set_defaults(func=cmd_codex)

    p_render = sub.add_parser("render")
    p_render.add_argument("--state", required=True)
    p_render.add_argument("--out", default="")
    p_render.set_defaults(func=cmd_render)

    p_asm = sub.add_parser("assemble")
    p_asm.add_argument("--artifact", required=True)
    p_asm.add_argument("--claude-result", required=True)
    p_asm.add_argument("--codex-result", required=True)
    p_asm.add_argument("--out", default="")
    p_asm.add_argument("--state-out", default="")
    p_asm.set_defaults(func=cmd_assemble)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
