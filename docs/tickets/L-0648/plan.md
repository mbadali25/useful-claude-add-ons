# L-0648 plan (implementing session, 2026-10-05, rush/g4-deploy)

Built after T-0062 and L-0664 on this branch (L-0664 was built first so promote-gate.ps1 already
resolves python): both flavours call one helper, so the rule cannot drift between them.

1. RED: `test_promote_gate_github.py` (L-0647's file) gains every acceptance case on the real gates
   over the effective-tree fixture, both flavours (`ps1` slow, skipped without pwsh).
2. `_promote_github.py`: for each matched environment with `github` entries, the entry whose
   canonical prefix (as `crew_ghdeploy.py check` builds it) is the longest substring of the command,
   ignoring case; with `shaInput`, the command's inputs (T-0009's `dispatch_read`, told the shell)
   must hold it exactly once, `[0-9a-f]{40}`, equal to `--full`. Prints `block<TAB>why`; exit 4 for a
   malformed `github`. No second validator: only what the prefix needs is read.
3. promote-gate.sh / .ps1: the matcher's strict reading refuses a `github` that is not an object or
   a non-empty list of objects (exit 4 / Deny-UnreadableMap); after the judged tree's HEAD is known,
   the helper runs and each `block` stops (incident lane included); a failing helper blocks. The ps1
   with no python and a matched `github` entry blocks.
4. near-miss is T-0062's/L-0664's dispatch read (fits no declared environment); tested here.
5. Mutations in `ghdeploy_mutations.py`, one per refusing branch per flavour plus two must-allow.
   Docs: promote.md (no net growth), github-deploy.md, crew-verification section 4, README.
