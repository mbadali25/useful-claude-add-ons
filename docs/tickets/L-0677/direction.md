# L-0677 direction: `crew_memory.py save` - write the vault note, then turn the native memory into a pointer          status: direction   risk: med
Split from T-0084. Filed as L-0677.
## Ask
The owner asked (2026-09-27) for native Claude Code memories to become one-line pointers into the Obsidian vault note, built into crew and working on any host and shell, with the full text kept when there is no vault. T-0084's first slice lands the pointer format and a read-only resolver. This child is the writer: given a native memory file that holds its full text, write or update the vault note, and only then replace the native body with the pointer.
Checked against origin/main `155fe6d8` (crew 1.0.322) on 2026-10-04. The owner was not available; defaults are the recommended options and the questions are in the parent's direction.md, "Open questions for the owner".
## Options
1. **Recommended, taken: `save` in crew's own `crew_memory.py`, note first, pointer second.** The note is written with an exclusive create (or an append for an existing note that belongs to this memory), read back, and only then is the native file replaced through a temp file and `os.replace`. Every refusal leaves the native file byte-identical.
2. Write the pointer first and the note second. Simpler ordering, but a crash between the two leaves a dangling pointer, which the direction forbids. Rejected.
3. Delegate the note write to the `obsidian-vault` CLI. Needs a second plugin installed; the owner asked for crew. Rejected (open question 1 in the parent).
## Recommendation
Option 1. Dry run by default, `--apply` to write. The writer's vault is the single writable vault on this host, chosen by the rule `obsidian-vault` uses for its own writers: the one role-`primary` vault, never a `recall` or `ignore` vault, never a substitute for a primary that is not on disk.
## Approval
Status `direction`. Owner go for the hand-off: 2026-10-04.
