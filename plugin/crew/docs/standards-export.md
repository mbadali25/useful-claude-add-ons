# Exporting the standards to PR-side reviewers

A repo opts in with `export: ["review", "agents", "bugbot"]` (any non-empty
subset) in `.crew/standards.md`'s front matter. `crew_standards.py export --root .
--write` then publishes every standard of every set, each with its `applies-to`,
as `docs/review-rules/<SET>.md` (one file per set, each under `EXPORT_MAX_CHARS`
because Bugbot truncates a rule at 30,000 characters), plus `REVIEW.md` and
`.cursor/BUGBOT.md` (the always-on sets in full, the stack sets as ids, names and
a link) and a marked `## Code Review Rules` block in a hand-written `AGENTS.md`.
Rule, Self-check and Supplements only, never Why or Earned by. `--dry-run` reports
sizes; `--check` fails when an output is stale, missing, hand-edited or orphaned.
A file over budget is refused, never truncated; a crew-generated `AGENTS.md`
(`crew:generated`) is refused with the reason, as is a symlink or a non-regular file on an
export path; a hand-written file at an output path is never overwritten.

**Regenerate** with `export --write` after an approved proposal edits
`.crew/standards.md`, and after `claude plugin update` changes a plugin set: the
digest covers the plugin's set bytes, so an opted-in repo goes stale with no path
in the repo changing. Freshness is as of the last check, and a rule that reaches
the script through `$CLAUDE_PLUGIN_ROOT` exits 77 (SKIP, not coverage) where the
variable is unset. A reader that does not follow links sees ids and names for the
stack sets, not their rules.
