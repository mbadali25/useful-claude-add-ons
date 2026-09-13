---
description: Two adversarial reviewers from different model families tear apart an agent, skill or plugin
argument-hint: <path to an agent, skill or plugin>
allowed-tools: Agent, Bash, Read, Glob, Grep
---

Review the artifact at: $ARGUMENTS

If `$ARGUMENTS` is empty, ask which artifact to review and stop. Do not guess
at a path, and do not default to the current directory - a review of the
wrong thing costs more than a question.

This is a **Rule of Two** review: one Claude reviewer and one Codex reviewer,
from different model families, reading the same artifact against the same
rubric without seeing each other's findings.

**The rule that governs every step below: if only one reviewer runs, the
report says so, plainly, in its own title and banner.** Never present a
single-reviewer result under the Rule of Two name. You do not have to
remember this - `rule_of_two.py` computes the coverage and derives both the
title and the banner from it, and it is the only thing allowed to write
either. Do not write a title or banner yourself, and do not edit the ones it
produces.

# Steps

1. **Resolve Python and a scratch directory.** Git Bash ships without
   `python3`, so resolve it and fail loudly rather than exiting quietly:

   ```bash
   PY=""
   for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
   [ -n "$PY" ] || { echo "no python3/python/py on PATH" >&2; exit 1; }
   SCRATCH="$(mktemp -d)"
   ```

2. **Show the configuration and the coverage you are starting from.**

   ```bash
   "$PY" "${CLAUDE_PLUGIN_ROOT}/scripts/rule_of_two.py" --repo-root . config
   ```

   Report the two models and where the config came from. If
   `codex_available` is false, say so now - the user should know before the
   Claude review runs that this is heading for a one-reviewer report, not
   after.

3. **Dispatch the Claude reviewer**, on the model the config names.

   `dispatch_order_claude` from step 2 gives two aliases, pin first. Dispatch
   the `rule-of-two:reviewer-claude` subagent with the **pin** as an explicit
   model override, passing the artifact path unchanged. Tell it nothing about
   what you expect it to find.

   If that dispatch fails because the model is unavailable, retry **once**
   with the fallback alias. Do not fall back for any other reason - a
   reviewer that ran and returned a thin report has still run, and retrying
   it on a different model would quietly swap the model the report names.
   Record which alias actually produced the report.

   Then write the result with the helper, which exists so you never hand-author
   this JSON - a multi-paragraph report embedded in a shell string gets
   mangled, and a hand-typed `"ran"` is the least trustworthy field in the
   system:

   ```bash
   # $SCRATCH/claude-review.txt holds the subagent's report verbatim
   "$PY" "${CLAUDE_PLUGIN_ROOT}/scripts/rule_of_two.py" --repo-root . \
     record-claude --ran --model "<the alias that ran>" \
     --model-id "<the matching *_model_id from config>" \
     --text-file "$SCRATCH/claude-review.txt" \
     --out "$SCRATCH/claude-result.json"
   ```

   **`--ran` and `--failed` are mutually exclusive and one is required.** You
   must state the outcome; the helper will not infer it from the file being
   non-empty, because a file containing "dispatch failed: model unavailable"
   is also non-empty and used to render a full "the Rule of Two held" report.
   If the dispatch failed on both aliases, pass
   `--failed --reason "<why>"`. That is a reviewer that did not run, and the
   report will say so.

4. **Build the Codex prompt** with the helper. Do not assemble it by hand:

   ```bash
   "$PY" "${CLAUDE_PLUGIN_ROOT}/scripts/rule_of_two.py" \
     build-prompt --artifact "<the path>" --out "$SCRATCH/codex-prompt.txt"
   ```

   It emits `templates/rubric.md` plus the artifact path - the same file
   `rule-of-two:reviewer-claude` is told to follow. That is the point, and it
   is why this is a function rather than shell you retype: the two reports
   are comparable only if both reviewers were told to do the same work. If
   one is told to run the test suite and the other is not, a difference
   between them can be procedure rather than judgement, and nobody reading
   the two reports can tell which.

5. **Run the Codex reviewer.**

   ```bash
   "$PY" "${CLAUDE_PLUGIN_ROOT}/scripts/rule_of_two.py" --repo-root . \
     codex --prompt-file "$SCRATCH/codex-prompt.txt" \
     --out "$SCRATCH/codex-result.json"
   ```

   This redirects stdin from devnull, applies a timeout, and takes the review
   from `--output-last-message` rather than from stdout - Codex prints a
   startup banner naming the model and the sandbox, and an earlier version of
   this plugin accepted that banner as a review because it was non-empty. Do
   not replace this with a bare `codex exec` call.

   A missing binary, a timeout, a non-zero exit, and a run that produced no
   final message are all recorded as `"ran": false` with a reason. That is
   correct - none of them produced a review. Do not retry more than once, and
   do not substitute a second Claude reviewer for the missing Codex one. Two
   Claude models are one perspective wearing two names, and the script will
   say so.

6. **Assemble the report.**

   ```bash
   "$PY" "${CLAUDE_PLUGIN_ROOT}/scripts/rule_of_two.py" --repo-root . \
     assemble --artifact "<the path>" \
     --claude-result "$SCRATCH/claude-result.json" \
     --codex-result "$SCRATCH/codex-result.json" \
     --out "$SCRATCH/report.md" --state-out "$SCRATCH/state.json"
   ```

7. **Present it.** Lead with the title and coverage banner exactly as
   rendered - both are derived from coverage, and both are the script's to
   write. Then the two verdicts.

   Where the reviewers disagree, say so explicitly and do not adjudicate. A
   disagreement between two families is the most informative thing in the
   report, and flattening it into a consensus throws away what you paid two
   reviews for. They can disagree on the verdict itself; report both verdicts
   as they stand rather than picking the one you find more persuasive.

   Offer to save the report to a path the user names. It is a report to act
   on later, not a gate; nothing here blocks anything.

# Handing findings to crew

Optional, and only if the user asks. `crew` is referenced, never required -
this plugin runs standalone and must never fail because crew is absent.

Check with `command -v claude >/dev/null && [ -d .crew ]`, or simply look for
a `.crew/` directory. If crew is present, offer to turn the blocking defects
into crew tickets. If it is not, say the findings are yours to act on and
stop - do not suggest installing crew.

# What must never happen

- A report titled or headlined as a Rule of Two review when only one reviewer
  ran.
- A title or coverage banner written by you instead of by `rule_of_two.py`.
- A hand-authored `claude-result.json`. Use `record-claude`.
- A second Claude model standing in for Codex.
- The two reviews merged into a single consensus verdict.
- Any edit to the artifact under review. This command reviews; it never fixes.
