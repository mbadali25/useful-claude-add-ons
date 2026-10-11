# L-0789 - STATE AT HANDOFF

Written 2026-10-11 15:02 CDT by the L-0789 lane, on the coordinator's (ac5b48330c1347c0d) wind-down instruction.
Nothing here is an approval. `.work/` is gitignored: this folder exists only on this laptop unless it is copied.

## Where it stands
- PR #604, branch `L-0789-diagram-reanchor`, OPEN, not merged. Local head = pushed head = PR head =
  `b129d3030c507851d2a81fb7d2b8d65f48d35257`. Worktree `/repos/personal/uca-L-0789` clean, kept.
- CI on b129d3030: 30 pass, `verify-gate` skipping (as on every PR here). gh reported mergeable UNKNOWN at 15:01
  (it was MERGEABLE earlier; main has moved, see below).
- Scope base: `.crew/.scope-base` in the worktree holds
  `{"L-0789": {"base": "987ea4fb89087bfe35fcc5f2883ba37fd69d26ba", "from": "HEAD", "recordedAt": "2026-10-11T14:08:45+00:00"}}`.
- spec.md, plan.md, selfcheck.md (approved via cli, self-check stamped) are copied here from the worktree.
- Review: NO round spent. Scratch `.work/review/L-0789-diagram-reanchor--yzOS6H` in the worktree, bundle id
  f7367b2a5e20, base 987ea4fb, head b129d3030; copied to `evidence/review-scratch-yzOS6H/`. Codex probe was OK;
  `review_run.py` exited 9 (gate UNVERIFIED) and reserved nothing.

## Gate on b129d3030 (`verify-gate.sh --all` through heavy-run, ended 11:05 CDT)
rc=2, 2086s across 115 rule commands. Log: `evidence/l0789-verify-all-b129d3030.log`.
- rules[16] ran (732s) and FAILED: `2 failed, 19683 passed, 283 skipped in 731.30s`. The two:
  `plugin/crew/tests/test_crew_context_wrappers.py::test_bash_flavour_emits_and_logs_nothing_when_inject_is_false[config0-False]`
  and `[None-False]`. Same two fail on clean origin/main 987ea4fb (`main-repro-987ea4fb.log`: 2 failed, 20 passed).
  The "permanently over budget ... deferred to CI" line for rules[16] is a stale record entry from an earlier
  Stop-budget run on the same sha, kept because the rule failed; it is not a deferral in the --all run.
- rules[16] wallclock half (never reached by the gate because of `|| exit 1`), run alone through heavy-run:
  `74 passed, 6 skipped, 22946 deselected in 180.55s`, rc=0. `evidence/l0789-rule16-wallclock-b129d3030.log`.
- rules[29]: skipped in the gate because `mcp-servers/node_modules` was absent (npm was on PATH). After
  `npm --prefix mcp-servers ci` the rule's exact command: rc=0, `# fail 0` in all six packages (14, 6, 6, 6, 69, 7
  tests). `evidence/l0789-rule29-b129d3030.log`.
- rules[28] (ai-connect): NOT RUN, blocked on L-0790 at the time.
- Not run: `scripts/_test/drift-detection.sh`.
- No full gate has recorded a pass on this head.

## What changed on main since (measured 15:01 CDT)
origin/main is a656ef84f, "Merge pull request #605 from mbadali25/L-0790-hermetic-firewall-test"; crew is still
1.2.30 there. #604's base was 987ea4fb. L-0790 has therefore landed: per the owner decision in HANDOFF.md, after
merging main rules[28] runs as nobody (`sudo -n true` must fail; save and diff /etc/ufw/user.rules and user6.rules),
never as root.

## Open items for whoever resumes (as relayed by the coordinator unless marked measured)
- The one Codex round waits for #584 on main and a gate that can pass. `--allow-unverified` is NOT approved for #604.
- Version clash: commit b129d3030 says crew 1.2.31. #597 holds 1.2.31, #584 1.2.32, #600 1.2.33. Re-check
  origin/main's version right before merging and take the next free one.
- Content conflict on `docs/diagrams/data-flow-crew-config-ratchet.mmd` with #603, which re-anchors the same
  diagram (not measured by this lane; reported by the coordinator).
- /crew:done so far (measured before the park): check 3 and check 5 pass, trailers clean; check 4 no longer names
  the two diagrams, the 8 code maps and the graph read stale from README.md / plugin/crew/README.md (read as the
  L-0764 case, to be confirmed); check 1 needs the review receipt, check 2 the gate.
- Step 7, owed after merge: L-0710's done-waiver.md and INDEX note, L-0789 to done in INDEX and Kanban (both say
  review, with the hold noted), tell "main" the PR, SHA and version, remove the worktree, keep the branch.

## Exact next step
1. In `/repos/personal/uca-L-0789`: confirm clean at b129d3030, `git fetch`, merge origin/main once #584 is on it;
   resolve the version (next free) and regenerate "What's new"; re-run `render.sh`, `diagram_check.py`,
   `crew_diagrams.py check`.
2. `npm --prefix mcp-servers ci` if node_modules is absent, then
   `env -u TMPDIR CLAUDE_PROJECT_DIR=$PWD /root/crew-tmp/heavy-run bash plugin/crew/hooks/scripts/verify-gate.sh --all </dev/null`
   (check `free -g` first); rules[28] as nobody.
3. Only on a recorded pass: rebuild the review bundle (the old one is for b129d3030) and run the one Codex round,
   `review_run.py --provider codex --model gpt-6-sol --authors claude`.
4. /crew:done, version re-check, `gh pr merge 604 --merge` on the coordinator's go, then step 7.

## Related
- L-0791 (direction, not started): the redraw ticket, `.work/tickets/L-0791/direction.md`.
- Main's scheduled CI run 38145816635 on 987ea4fb8 failed on two elapsed-time tests (read-only report sent to the
  coordinator; extract in the session scratchpad, see the path list in the handoff message).
