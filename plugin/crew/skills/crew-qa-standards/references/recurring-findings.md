# Recurring review findings

The defect classes reviewers kept finding in this marketplace's crew changes, each keyed by the
paths it applies to. `recurring_findings.py` prints the sections whose `applies-to` globs meet the
paths a change touches: to the implementer from the spec's Touch list (`/crew:implement` step 2),
and, through `review_block`, from a review bundle's changed files. It is a list of probes, not a
gate, and it does not bound a review.

Format, read by `recurring_findings.parse`: `## RF-NN <title>`, then `applies-to: <JSON list of
globs>`, then `seen: <one line>`, then one to four `- ` probe lines. Sections stay in priority order
(JUDGEMENT, not the order of the counts: the 2026-10-01 QA evaluation's two targets,
fail-open and tests, come first), because the printed block drops whole
sections from the end past its line cap.
Only the sections are printed; this introduction and the provenance below never are.

## RF-01 An unknown collapses into the safe-looking value
applies-to: ["**/*.py", "**/*.sh", "**/*.ps1"]
seen: about 134 of 539 BLOCK/FIX findings (GEN-01, GEN-05, PYTHON-10, PYTHON-11)
- For each read, parse, probe or child process the diff adds: what does a missing file, an unreadable one, malformed JSON, a wrong type (`True` for `1`, `None`, a string) or a tool that exits non-zero with empty output produce? It must surface as could-not-tell or a refusal, never as absent, clean, off, `{}` or a pass.
- An `except` that returns a default, an `os.path.exists`/`lexists` that hides `PermissionError`, or a `2>/dev/null` / `|| true` / empty `catch {}` turns a failure into an answer: find each one and follow where its value goes.
- A malformed config or state file is never rewritten as if empty, and an unknown key in a closed contract is refused, not ignored.
- An "unknown" carries into every line derived from it: no summary, verdict or exit code that reads it as known.

## RF-02 A test that cannot fail
applies-to: ["**/*.py", "**/*.sh", "**/*.ps1"]
seen: about 154 of 539 BLOCK/FIX findings (GEN-04, GEN-12)
- For each new branch or guard, name the mutation that removes it and the test that goes red; a guard that blocks needs a sabotage entry and both must-block and must-allow cases.
- Assert the exact property: no widened range, no substring the input already contains, no check of a helper in isolation when the bug lives in how it is called.
- Every wait in a test is bounded, and a skip fires only when the tool is truly unusable, with the reason printed, so a supported machine never silently loses the case.
- An acceptance check or CHANGELOG claim the diff relies on is run at the final HEAD, with its real result ("15 of 20" is not "20 of 20").

## RF-03 What the change says is not true at this commit
applies-to: ["**/*.md", "**/*.mmd", "**/*.py", "**/*.sh", "**/*.ps1"]
seen: about 176 of 539 BLOCK/FIX findings (GEN-09)
- Re-check every number, version, path, line citation and "untouched"/"always"/"never" in the changed docs, docstrings, comments and CHANGELOG against the code at HEAD.
- Instructions a model will follow match the parser they feed (Touch bullets, verdict lines), quote `"${CLAUDE_PLUGIN_ROOT}"` for paths with spaces, and do not contradict another step of the same file.
- Every document that describes the changed behaviour moves in the same change: README, command and skill files, guides and their rebuilt outputs, code map, diagrams.

## RF-04 Processes, waits and races
applies-to: ["**/*.py", "**/*.sh", "**/*.ps1"]
seen: about 212 of 539 BLOCK/FIX findings, keyword-matched and broad (GEN-02, PYTHON-07)
- No signal to a PID that may already be reaped (PID reuse), and cleanup reaches grandchildren after their leader exits; native Windows has no `SIGKILL` or `killpg`.
- Every wait, read and child process has a bound, and a timeout is a failure with a message, not a hang or a pass.
- Check-then-use on a file, ref or lock is a race: act on the bytes that were checked, and key a lock by its holder, not only by its resource.

## RF-05 PowerShell and Bash twins drift apart
applies-to: ["**/*.ps1", "**/*.sh", "**/*.cmd", "**/*.bat"]
seen: about 66 of 539 BLOCK/FIX findings (GEN-08)
- A fix in one twin is made in the other the same way; native Windows runs the `.ps1`, so a Bash-only fix leaves Windows unfixed.
- PowerShell traps: `0..-1` yields two indices, `Start-Process` passes `[bool]` as the string `"True"`, an empty `$env:X` is not an absent one, and an empty `catch {}` fails open.
- A Bash `"$!"` inside a double-quoted string expands in the outer shell; a script written from Python on Windows keeps LF (`newline="\n"`).

## RF-06 A plugin changed without its version and registration
applies-to: ["plugin/**", "skills/**", "**/.claude-plugin/*.json", "**/PLUGINS.md", "**/marketplace.json"]
seen: about 38 of 539 BLOCK/FIX findings (CLAUDE.md "Stop and ask")
- A content change under a plugin needs a version bump in its `plugin.json`, the marketplace entry and the catalog row, at the point the repository's release rule sets (a standards overlay may put it at land, not on the build branch).
- Every place that states a version or a count agrees with the declared one, and the marketplace checker exits 0 where the release rule says it must.

## RF-07 A guard or matcher that can be walked around
applies-to: ["**/*guard*", "**/*gate*"]
seen: about 55 of 539 BLOCK/FIX findings (GEN-05, GEN-06)
- Enumerate the shapes the guard must see: aliases, launchers, quoting, a switch before the argument, a target built at runtime, a prefix or tail match where an exact one was meant.
- A shape the matcher does not recognise is could-not-tell (deny or ask), never allowed by default.

## Provenance

Counted 2026-10-01 on the Linux host over 625 unique finding lines (539 BLOCK/FIX) from 54 review
ledgers (`<git-common-dir>/crew/review/*.json`, which record finding text since L-0510) and 177
reviewer `out.txt` files from the lanes' review scratch folders, test fixtures excluded. Classes are
keyword matches over each finding's path and text, so they overlap and the counts are approximate;
the probes are JUDGEMENT, written from reading samples of each class. Those sources are
machine-local, which is why this file, not they, is what every reviewer reads. To refresh: re-count,
re-rank, and keep each section to four probes.
