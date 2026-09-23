---
name: stack-bash
description: |
  Bash-specific pitfalls, checks and verify.json wiring - quoting, pipeline exit codes,
  cross-platform Git Bash surprises. Use when the repo has *.sh files, or the user asks to
  write or review a shell script, explain why a pipeline "passed" despite a failing command,
  or hits a Windows/Git Bash path-mangling or line-ending problem.
---

# Stack: Bash

## When this applies

Any repo with `*.sh` files. Say which shell the script targets - `#!/usr/bin/env bash` and
`#!/bin/sh` are not interchangeable; `sh` on many systems is `dash`, which lacks arrays,
`[[ ]]`, and process substitution. A script that works under `bash` and is invoked as `sh
script.sh` silently runs under the stricter dialect.

## Pitfalls that cost time

- **An unquoted variable is word-split and glob-expanded.** `rm $file` deletes more than one
  path the moment `$file` contains a space or an unexpected `*`. Quote every expansion:
  `"$file"`, `"${arr[@]}"`.
- **A pipeline's exit code is the *last* command's**, not the first failure. `grep foo bad.log
  | sort` reports `sort`'s success even when `grep` errored. `set -o pipefail` fixes this repo-
  wide; per-pipeline, read `${PIPESTATUS[0]}` right after.
- **`set -e` does not stop everything.** It does not fire inside a condition
  (`if cmd; then`), inside a pipeline's non-last stage without `pipefail`, or inside a
  command substitution used as an argument. A script that "has `set -e` so it's safe" still
  needs its actual failure paths checked.
- **A subshell (anything after `|`, `(...)`, or `$(...)`) cannot write back to the parent's
  variables.** `cat file | while read -r line; do count=$((count+1)); done; echo "$count"`
  prints the value from before the loop - feed the loop with `< <(...)` process substitution
  instead of a pipe when the body must mutate outer state.
- **`[ ]` and `[[ ]]` are not the same test.** `[ $a == $b ]` glob-matches and word-splits
  unquoted operands; `[[ ]]` does neither and supports `=~`. Prefer `[[ ]]` in bash; `[ ]` (or
  `test`) is what portable `/bin/sh` scripts are stuck with.
- **A trap set once is replaced, not added to.** `trap cleanup EXIT` followed later by another
  `trap ... EXIT` silently drops the first handler - chain them explicitly if both must run.
- **Cross-platform (Git Bash on Windows) surprises that have already cost real time in this
  repo**: `MSYS_NO_PATHCONV` rewrites a POSIX-looking path (`/c/repos/...`) into a Windows one
  before a tool ever sees it, so the same command behaves differently depending on who set
  that variable in the calling environment; a `pathlib`/text-mode write of a `.sh` file
  converts `\n` to `\r\n` on Windows, which then dies on the shebang as `bad interpreter:
  ...^M` - write shell scripts with `newline="\n"` and confirm with `od -c`, not by eye.

## Verification

Run the script's actual entry point, not just a syntax check - `bash -n file.sh` catches
parse errors only, never a runtime path. Report exit codes, never the tail of the output.

## verify.json rule to propose

```json
{
  "paths": ["**/*.sh"],
  "run": [
    "sh -c 'command -v shellcheck >/dev/null 2>&1 || { echo \"TOOL MISSING: shellcheck is not on PATH, so the lint pass DID NOT RUN. This is a missing tool, not a passing or failing check. Install shellcheck to check locally.\" >&2; exit 77; }; shellcheck $(git ls-files \"*.sh\")'"
  ],
  "reach": "local",
  "why": "shellcheck catches the quoting and pipeline-exit-code defects above before review"
}
```

Nothing in this repo writes rules into `verify.json` on a skill's behalf (see
`crew-verification`) - add by hand.

## LSP

None decided for this stack.
