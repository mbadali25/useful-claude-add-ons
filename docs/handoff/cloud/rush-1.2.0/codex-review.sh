#!/usr/bin/env bash
# usage: codex-review.sh <worktree> <base-ref> <label> [extra-context-file]
# Runs gpt-6-sol (high) read-only over `git diff <base>...HEAD`; writes $S/reviews/<label>-<sha7>.json
set -u
WT=$1; BASE=$2; LABEL=$3; EXTRA=${4:-}
S=/tmp/claude-0/-home-user-useful-claude-add-ons/cf8010ca-0ad0-5d92-8922-7bbd28b697af/scratchpad
SHA=$(git -C "$WT" rev-parse --short=7 HEAD)
OUT=$S/reviews/$LABEL-$SHA.json
PROMPT="You are reviewing a pull request in this repository (cwd). Review ONLY the change: run \`git diff $BASE...HEAD\` and \`git log --oneline $BASE..HEAD\`, then read surrounding code as needed. Read CLAUDE.md first: its rules are the repo's policy (version bumps, matched install-script pairs, harness-alone rule, hook defaults, landmines).
Classify each finding:
- BLOCK: would ship a bug, break CI/gate, violate a CLAUDE.md 'Stop and ask' rule, data loss, or security issue.
- FIX: a real defect or missing test/doc the change needs before merge, but not catastrophic.
- NIT: style, wording, optional improvement.
Do not report pre-existing problems the diff did not introduce or touch. Verify each finding against the code before reporting it; no speculation.
verdict = BLOCK if any BLOCK, else FIX if any FIX, else CLEAN.
$( [ -n "$EXTRA" ] && cat "$EXTRA" )"
cd "$WT" && timeout 3000 codex exec -m gpt-6-sol -c model_reasoning_effort=high -s read-only --skip-git-repo-check \
  --output-schema $S/review-schema.json -o "$OUT" "$PROMPT" > "$S/reviews/$LABEL-$SHA.log" 2>&1
rc=$?
echo "rc=$rc out=$OUT"; [ -s "$OUT" ] && jq -r '"verdict=\(.verdict)  block=\([.findings[]|select(.severity=="BLOCK")]|length) fix=\([.findings[]|select(.severity=="FIX")]|length) nit=\([.findings[]|select(.severity=="NIT")]|length)"' "$OUT"
