---
name: github
description: >
  Work with GitHub repositories through the `gh` CLI and the REST API: read and
  change branch protection and repository rulesets, export a repo's merge gate to
  a file before touching it, and restore it from that export. Use this skill
  whenever the user mentions GitHub branch protection, a protected branch, a
  ruleset or repository rules, required reviews or required status checks, "turn
  the merge gate off so this can merge", `gh api`, a merge blocked by "Required
  status check is expected" or "Changes must be made through a pull request", or
  a 403/404 from `repos/{owner}/{repo}/branches/{branch}/protection` — even if
  they only say "let me merge this" and the remote points at github.com.
---

# GitHub branch protection and rulesets

Everything here goes through `gh api`, so `gh` owns authentication — do not build
tokens or curl calls by hand. Confirm the CLI is usable first:

```bash
gh auth status
gh repo view --json nameWithOwner,defaultBranchRef
```

Every call below needs **admin on the repository**. There is no read-only scope
for branch protection or rulesets, so a token that lists PRs fine will still fail
here, and it fails in a way that looks like "nothing is configured" (see below).

## The one thing to get right: GitHub gates a branch two ways

A repository can carry **both** at once, and they are independent:

| | Classic branch protection | Rulesets |
|---|---|---|
| Endpoint | `repos/{o}/{r}/branches/{b}/protection` | `repos/{o}/{r}/rulesets` |
| Scope | one branch, named in the URL | `conditions.ref_name` patterns |
| Owned by | the repository | the repository, **or the org or enterprise** |
| Turned off by | `DELETE` (there is no "disabled" state) | `DELETE` per ruleset |
| Turned back on by | `PUT` with the whole document | `POST` a fresh object |
| Can be several | no — one document per branch | yes — many, all enforced together |

**Reading one and not the other reports a gate as off while it is on.** The UI
shows them in two different places, so a repo migrated to rulesets often still
has a classic document nobody remembers.

### Settled: the export captures both, always

This was the open question in `docs/guard-overrides.md`. The answer is **both, in
one document, with a per-surface state** — not "whichever the repo uses", and not
"rulesets because they are newer". `scripts/merge_gate.sh` records:

```json
{ "classic":  { "state": "present|absent|unreadable", "detail": "...",
                "protection": {...}, "required_signatures": {...} },
  "rulesets": { "state": "read|unreadable", "detail": "...",
                "values": [...], "unreadable": [...] } }
```

`unreadable` is a third value, never folded into `absent`. It stops `disable`
before anything is deleted (exit 3) and makes `enable --from-export` refuse the
file outright.

The export is re-read from disk and checked against what the API declared before
a single `DELETE` is sent: the ruleset count must account for every row the list
returned, and `classic.state: "present"` must carry an actual protection object.
Either mismatch aborts with nothing written and nothing deleted — an export that
validates clean and then cannot be restored is the worst of the failure modes,
because the delete has already happened by the time anyone finds out.

**Why that distinction is load-bearing, with the evidence:** reading a protected
branch you do not own answers

```
404 {"message":"Not Found"}
```

and reading an *unprotected* branch answers

```
404 {"message":"Branch not protected"}
```

Same status code. `repos/cli/cli/branches/trunk/protection` gives the first from
a token without admin, and that branch is protected. Only the exact
`Branch not protected` body means the surface is empty. Anything else — another
404, a 403, a 5xx — is `unreadable`.

The second trap is in the ruleset list. `GET repos/{o}/{r}/rulesets` returns rows
with **no `rules` and no `conditions`** (verified against
`repos/facebook/react/rulesets`). An export built from the list looks complete,
restores a ruleset with the right name and no protection in it, and nothing in
the file says so. Every ruleset is fetched by id.

## `scripts/merge_gate.sh`

```bash
scripts/merge_gate.sh status  myorg my-repo
scripts/merge_gate.sh export  myorg my-repo gate-backup.json --branch main
scripts/merge_gate.sh disable myorg my-repo --branch main --dry-run
scripts/merge_gate.sh disable myorg my-repo --branch main --export-to gate-backup.json
scripts/merge_gate.sh enable  myorg my-repo --from-export gate-backup.json
```

With no `--branch`, the target is resolved from the repo's `.default_branch`; if
the API does not return one the script stops and asks for `--branch` rather than
guessing.

| Exit | Meaning |
|---|---|
| 0 | did what was asked |
| 1 | an API or IO failure; the message quotes what the API said |
| 2 | usage |
| 3 | **nothing was deleted** — see the three causes below |
| 4 | **partial writes** — the summary names exactly what landed |

Exit 3 has three causes, all of them "this run cannot tell, so it refuses":

1. A ruleset whose `conditions.ref_name` entries the script cannot evaluate — a
   selector GitHub added after this was written. It will not guess.
2. A ruleset that gates the branch but whose `source_type` is `Organization` or
   `Enterprise`. `DELETE` on the repo endpoint cannot remove it, so disabling
   everything else would leave the gate partly on while reporting success.
   Turn it off where it is defined, or pass `--allow-inherited` to remove what
   the repo does own and accept that the rest stays. **`--allow-inherited` turns
   that refusal into exit 0 on a branch that is still gated**, so the run also
   prints a `WARNING:` on stderr naming how many stand. Never report such a run
   as "the gate is off" on the exit code alone.
3. A gate surface that could not be read at all.

In every case the export is still written, because it is the evidence for what
could and could not be read.

### There is no preset — `enable` restores or does nothing

This is the deliberate divergence from `skills/bitbucket/scripts/merge_gate.sh`,
whose `enable` with no `--from-export` applies a four-check preset. Here
`enable` without `--from-export` **exits 2 and changes nothing**. A preset would
invent a gate rather than put back the one that was removed, and
`docs/guard-overrides.md` settled that `preset` binds to nothing on the GitHub
side. Keep the export: it is the only way back.

### `--dry-run` sends nothing at all

Bitbucket's `disable --dry-run` exports first and then prints a per-object plan.
This one **makes no request and writes no file** — not even the export — so it
cannot enumerate live objects. It prints the resolved target and the exact call
sequence instead. That is less information on purpose; do not "fix" it into
reading the API first.

### What a restore does and does not put back

- Classic protection goes back as one `PUT`. The GET and PUT shapes are not the
  same document — GET returns actors as objects and carries `url` keys PUT
  rejects — so the script converts, rather than echoing the GET body back, which
  answers 422.
- **"Require signed commits" has its own endpoint** and is not part of the
  protection document. `DELETE .../protection` takes it down and
  `PUT .../protection` does not put it back; the script restores it separately.
- Rulesets are **POSTed fresh, so every restored ruleset gets a new id.**
  Anything that referenced the old id has to be re-pointed. A ruleset of the same
  name that is already there is reported as `already-present` and not duplicated.
- An inherited (org or enterprise) ruleset in the export is `nothing-to-do`: it
  was never removed here, so there is nothing to restore.

## Safety rails

- **Never run `disable` or `enable` against a repository the user did not name.**
  Confirm the owner/repo and the branch back to them first.
- `disable` deletes live protection. Show `--dry-run` output if the user is
  unsure, and tell them where the export landed before reporting the run done.
- Never claim a run turned *the* merge gate off. Say which surfaces it removed
  and name anything left standing — an inherited ruleset, a push ruleset, an
  `evaluate`-mode ruleset.
- `scripts/merge_gate.sh` skips rulesets whose `target` is `push` or `tag`: those
  are write protection, not merge checks, and `disable` must not quietly open a
  branch to direct pushes.
- Ruleset ref patterns are matched with bash globbing, whose `*` crosses `/`
  where GitHub's does not. The judgement errs toward "covering", and every object
  judged covering is printed before it is deleted — read the plan.
- Never force-push or delete a branch without explicit confirmation.

Offline checks for the script: `scripts/_test/merge_gate.sh` — no network, no
credentials, a stubbed `gh` via `GH_CMD`.
