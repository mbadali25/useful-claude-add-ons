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

1. **Resolve Python, the plugin root, and a scratch directory.** Git Bash
   ships without `python3`, so resolve it and fail loudly rather than exiting
   quietly. `${CLAUDE_PLUGIN_ROOT}` is set only when the plugin is
   **installed**; it is empty in a plain checkout of this repository, and an
   unset one expands to nothing, so every command below would silently run
   `/scripts/rule_of_two.py` and fail on a path nobody wrote. Fall back to
   finding the script's own directory:

   ```bash
   PY=""
   for c in python3 python py; do command -v "$c" >/dev/null 2>&1 && { PY="$c"; break; }; done
   [ -n "$PY" ] || { echo "no python3/python/py on PATH" >&2; exit 1; }

   ROOT="${CLAUDE_PLUGIN_ROOT:-}"
   if [ -z "$ROOT" ]; then
     d="$PWD"
     while :; do
       if [ -f "$d/plugin/rule-of-two/scripts/rule_of_two.py" ]; then
         ROOT="$d/plugin/rule-of-two"; break
       fi
       if [ -f "$d/scripts/rule_of_two.py" ] && [ -f "$d/templates/rubric.md" ]; then
         ROOT="$d"; break
       fi
       parent="$(dirname "$d")"
       [ "$parent" = "$d" ] && break   # a drive root: dirname stops moving
       d="$parent"
     done
   fi
   [ -n "$ROOT" ] || { echo "cannot find rule-of-two: install the plugin, or run from a checkout containing plugin/rule-of-two/" >&2; exit 1; }

   SCRATCH="$(mktemp -d)"
   ```

   Use `"$ROOT"` for every invocation below, never a bare
   `${CLAUDE_PLUGIN_ROOT}`.

   **Nothing here needs `PYTHONIOENCODING`.** A review is full of en-dashes
   and curly quotes and a Windows console is cp1252, but `rule_of_two.py`
   reconfigures its own stdout and stderr to UTF-8 on startup
   (`_make_stdout_safe` in `plugin/rule-of-two/scripts/rule_of_two.py` - named
   rather than cited by line, because the line moves and a citation that stops
   resolving is a defect this plugin's own rubric hunts), so
   printing a finished report cannot fail the run that produced it. If you
   ever see a `UnicodeEncodeError` from these commands, that function has
   regressed - setting the variable would hide the regression rather than fix
   it.

2. **Show the configuration and the coverage you are starting from.**

   ```bash
   "$PY" "$ROOT/scripts/rule_of_two.py" --repo-root . config
   ```

   Report the two models and where the config came from. If `codex_found` is
   false, say so now - the user should know before the Claude review runs that
   this is heading for a one-reviewer report, not after. Report `codex_found`
   as discovery and nothing more, and quote `codex_readiness` rather than
   paraphrasing it: `codex_auth_verified` is `false` on every run, because
   authentication, model existence and entitlement all fail at dispatch rather
   than at discovery. Read the key names out of the payload you just printed -
   this file names only keys `config` actually emits, and the suite asserts
   that, because the previous name for `codex_found` outlived its rename here
   for a whole release.

3. **Dispatch the Claude reviewer**, on the model the config names.

   `dispatch_order_claude` from step 2 gives two aliases, pin first. Dispatch
   the `rule-of-two:reviewer-claude` subagent with the **pin** as an explicit
   model override, passing the artifact path unchanged. Tell it nothing about
   what you expect it to find.

   **This half needs the plugin installed.** The subagent type
   `rule-of-two:reviewer-claude` is registered by the plugin, so in a plain
   checkout it does not exist and the dispatch fails. The fallback in step 1
   gets the *script* half running from a checkout; it cannot conjure a
   subagent type. If the dispatch fails for that reason, record it with
   `--failed --reason "rule-of-two:reviewer-claude is not registered; the
   plugin is not installed"` and let the report say what it says - a
   one-reviewer report is the honest outcome, and inlining the rubric into
   some other agent would make the two reviewers incomparable.

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
   "$PY" "$ROOT/scripts/rule_of_two.py" --repo-root . \
     record-claude --ran --model "<the alias that ran>" \
     --model-id "<the matching *_model_id from config>" \
     --text-file "$SCRATCH/claude-review.txt" \
     --out "$SCRATCH/claude-result.json"
   ```

   **`--model-id` must be the id that belongs to the alias you just used**,
   copied from the same section of the `config` payload - `pin` with
   `pin_model_id`, `fallback` with `fallback_model_id`. Pasting the other
   family's id is checked for now: the two are resolved to families and
   compared, and a disagreement downgrades coverage to
   `TWO_FAMILY_UNVERIFIED`, prints the contradiction in the banner, and
   withdraws the Rule of Two name from the title. An id that resolves to no
   known family does the same thing - unknown is not corroboration. Omitting
   the flag is not an error; nothing is then claimed about the id.

   **`--ran` and `--failed` are mutually exclusive and one is required.** You
   must state the outcome; the helper will not infer it from the file being
   non-empty, because a file containing "dispatch failed: model unavailable"
   is also non-empty and used to render a full "the Rule of Two held" report.
   If the dispatch failed on both aliases, pass
   `--failed --reason "<why>"`. That is a reviewer that did not run, and the
   report will say so.

4. **Build the Codex prompt** with the helper. Do not assemble it by hand:

   ```bash
   "$PY" "$ROOT/scripts/rule_of_two.py" \
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
   "$PY" "$ROOT/scripts/rule_of_two.py" --repo-root . \
     codex --prompt-file "$SCRATCH/codex-prompt.txt" \
     --out "$SCRATCH/codex-result.json"
   ```

   This redirects stdin from devnull, applies a timeout, and takes the review
   from `--output-last-message` rather than from stdout - Codex prints a
   startup banner naming the model and the sandbox, and an earlier version of
   this plugin accepted that banner as a review because it was non-empty. Do
   not replace this with a bare `codex exec` call.

   A missing binary, a timeout, a non-zero exit, and a run that produced no
   **Codex runs under `-s read-only` and reviews statically.** It cannot
   execute the artifact's tests or scripts - a read-only sandbox cannot even
   create the temporary directory a suite needs - so the rubric's step 3 is
   not available to it, while the Claude reviewer is permitted to run things.
   That asymmetry is deliberate and is **printed under the coverage banner**
   by `render_method_note`, so a reader is never handed two reports as though
   they were produced the same way. Do not raise the sandbox to
   `workspace-write` against this checkout, and do not delete the note the
   script prints.

   A missing binary, a timeout, a non-zero exit, and a run that produced no
   final message are all recorded as `"ran": false` with a reason. That is
   correct - none of them produced a review. Do not retry more than once, and
   do not substitute a second Claude reviewer for the missing Codex one. Two
   Claude models are one perspective wearing two names, and the script will
   say so.

6. **Assemble the report.**

   ```bash
   "$PY" "$ROOT/scripts/rule_of_two.py" --repo-root . \
     assemble --artifact "<the path>" \
     --claude-result "$SCRATCH/claude-result.json" \
     --codex-result "$SCRATCH/codex-result.json" \
     --out "$SCRATCH/report.md" --state-out "$SCRATCH/state.json"
   ```

7. **Present it.** Lead with the title and coverage banner exactly as
   rendered - both are derived from coverage, and both are the script's to
   write, as is the method note directly beneath them. Then the two verdicts.

   The reviewers' own section headings are pushed down two levels on the way
   into the report, so each body nests under its `## Reviewer A (Claude)` /
   `## Reviewer B (Codex)` container instead of colliding with it. Do not
   "fix" the extra `#` characters back out: two `## Defects` at the same level
   as the reviewer sections makes the second reviewer's findings read as a
   sibling of the first's.

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
