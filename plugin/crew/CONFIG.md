# crew configuration reference

Every key crew reads, which of the two layers may set it, what it defaults to,
and where the code that acts on it lives.

**This file is derived from the code, not from the templates' comments.** Every
claim below is either a `file::symbol` you can grep for, a file plus the config
key named beside it, or a value printed by running the function named beside it.
Where a claim rests only on a comment, it says so.
Where no consumer could be found, it says "no consumer found" and never
"unused" — see [Keys with no consumer found](#keys-with-no-consumer-found),
which is the most load-bearing section here.

**Citations name symbols, never line numbers, and that is deliberate.** This
document used to cite `path:line`. When the citations were last measured, **11
of 13 checkable line numbers were wrong** — every one of them still landing on
real code, in the wrong function, which is the shape that survives a citation
check and does not survive reading. A line number here buys precision that lasts
until the next commit to grow the file above it. A symbol name is greppable, and
it breaks loudly when the symbol is renamed instead of quietly pointing at a
stranger. For a key-reference row, the key in the first column is the anchor:
it was verified to appear in the cited script for all 23 rows.

Re-derive the tables with:

```bash
python3 -c "import sys; sys.path.insert(0, 'plugin/crew/hooks/scripts'); \
import crew_config as c, json; \
print(json.dumps(c.default_config(), indent=1)); \
print(json.dumps(c.leaf_paths(c.default_global_config()), indent=1))"
```

---

## 1. The two layers

| Layer | File | Read by |
|---|---|---|
| repo | `.crew/config.json` in the repository root - or, in a linked worktree with neither `.crew/config.json` nor `.crew/crew.json`, the main checkout's (`crew_common.repo_config_dir`) | `crew_state.load_config` |
| machine-global | `~/.claude/crew/config.json` | `crew_config.py::read_global_config` |

Both are optional. `read_global_config` **never raises**: an absent, malformed,
or non-object global file returns `{}` and is indistinguishable from no file at
all. That contract is load-bearing — `resolve_config` is reached from a
`SessionStart` hook, and a broken file in `~/.claude/` must not wedge every
session on the machine.

Nothing in `crew_config` ever writes the global file except
`crew_config.py::write_global_config`, which its own docstring names as
the only function in crew that writes outside the repo.

### How the two are merged

`crew_config.py::resolve_config` is the single resolver. Read it as five
steps, in this order:

```python
repo_cfg = crew_state.load_config(root)
global_cfg, _ = filter_global(read_global_config())
repo_cfg = without_null_shadows(repo_cfg, global_cfg)
merged = crew_state.merge_defaults(default_config(), global_cfg)
merged = crew_state.merge_defaults(merged, repo_cfg)
if "schema" in repo_cfg:
    merged["schema"] = repo_cfg["schema"]
else:
    merged.pop("schema", None)
return merged
```

So precedence is **repo beats global beats shipped default**, with two
structural exceptions, both visible above: the global layer is pruned before it
is consulted at all (§2), and `schema` is lifted out of the merge entirely
(§4).

**And eight exceptions that are not visible above, because they do not go
through this function at all: `install.policy` (§15) and the seven
`guards.*` (§16).**
Each resolves to the *lower* of the two layers rather than to the repo's, so a
cloned repo cannot widen what the machine owner allowed. Anything reading one
through `resolve_config` gets the precedence answer and is wrong;
`crew_config.py::resolve_ratcheted` is the only correct reader, and
`resolve_install_policy` and `resolve_guard` are its two thin wrappers.
`crew_state.py::RATCHETED_KEYS` is the list, and it is the only list.

**Resolve through this function, never by re-reading `.crew/config.json`.**
That file is one layer of three and does not know about the `roles` tables at
all. `skills/crew-review/SKILL.md` carries the scar: reading it directly made
both `qa.roles.review` and every value in `~/.claude/crew/config.json`
invisible to the only command that actually runs a review.

### Null shadowing

`/crew:init` writes `templates/config.template.json`, which spells out **every**
key including the ones whose default is `null`. `merge_defaults` treats an
explicit `null` as a supplied value, so it beat the global layer — and the
global file therefore did nothing for any repo that had been initialised, which
is every managed repo.

`crew_config.py::null_shadows` and `without_null_shadows`
(`crew_config.py`) fix that on the read path. The rule is deliberately
narrow, and the narrowness is the point:

- A repo `null` is dropped **only** where the global layer supplies a real
  value at that path (`_layer_supplies`, `crew_config.py::_layer_supplies`).
- A repo `null` with nothing underneath it is left alone. `context.reserveTokens:
  null` still means *off* and does not silently become `100000`.

It is not fixed inside `merge_defaults` because `crew_upgrade.upgrade_config`
shares that function, and changing null semantics there would rewrite users'
files on migration rather than only resolving them for a read
(`crew_config.py`, a comment).

---

### In a linked worktree

Since crew 1.0.69 (T-0088) every Python reader of the repo config opens
`crew_common.repo_config_file(root, name)`, which resolves the `.crew/`
directory in this order:

1. The worktree's own `.crew/` when it holds `config.json` **or** `crew.json`.
   Both files are then read from there and nothing is inherited, even when
   they are partial: the two checkouts' files are never merged.
2. `.git` a directory, or missing: the repository's own `.crew/`, with no git call.
3. `.git` a file (a linked worktree or a submodule): `git rev-parse
   --git-dir --git-common-dir`, each path joined to the worktree's top (no
   `--path-format`, which git before 2.31 does not know). A submodule (git-dir equals
   common-dir) or a bare common directory (not named `.git`) has no main
   checkout and reads its own `.crew/`. Otherwise the main checkout's `.crew/`,
   when it holds either file.
4. When git cannot answer, the source is `unknown`: the worktree's own `.crew/`
   is read (nothing inherited), and `/crew:status` and `/crew:config --explain`
   print that git could not tell.

**A lane made before crew 1.0.69 has a config of its own already.** Every
SessionStart heal on crew 1.0.68 or earlier wrote a default `.crew/config.json`
into a lane worktree that had none, so rule 1 applies and nothing is inherited.
`/crew:status` and `/crew:config --explain` name that case: a linked worktree
whose own file is in force while the main checkout also has one prints `the
main checkout's (<path>) is not read`. If the lane's file is a default nobody
edited, delete it (and `.crew/crew.json`, if present) to inherit; from 1.0.69
the heal path creates nothing there again.

The writers never follow it: `crew_platform` (heal and `platform-sync`),
`crew_autoclear_setup`, `crew_migrate`, `/crew:init` and the machine-global writer
keep their own-path behaviour, and the heal path creates nothing in a worktree
that inherits a config, or in one where git could not tell. The shell and PowerShell readers (`verify-gate.sh`, `_common.sh`, `notify.sh`, `handoff-read.sh`, `handoff-write.sh`, `promote-gate.ps1`, `scope-guard.ps1`, `cloud-guard.ps1` and `auto-clear.ps1`) are not
routed yet and read only the worktree's own file.

## 2. The invariant

> **What the global file may WRITE is exactly what the global layer may SUPPLY.**

One definition, `default_global_config()` (`crew_config.py::default_global_config`), enforced from
both directions:

| Direction | Function | Mechanism |
|---|---|---|
| READ — what a global file may supply | `filter_global` | `_prune` keeps only keys present in `default_global_config()`, and returns the dropped paths as `ignored` |
| WRITE — what a guided flow may set | `plan_global_write` | refuses any path for which `is_global_path` is false, by name, with the full allowed list in the message |

`is_global_path` agrees with `filter_global` by construction — both stop
descending at a template **leaf**.

**Measured, not argued.** `leaf_paths(default_global_config())` yields **72**
leaves. `leaf_paths(default_config())` yields **130**, so **58** are repo-only.
For all 130, `filter_global` and `is_global_path` (which `plan_global_write`
refuses on) agree on whether the path is settable. (Measured with `leaf_paths`
on T-0061's branch after merging main 34d9f267; the repo-only
`tickets.baseBranch` is the one T-0061 added. This paragraph said 68 / 123 / 55
until then, behind main's 72 / 129 / 57. 122 / 67 / 55 on T-0072's branch, which added the repo-only
`autopilot.deploy`; 122 / 68 / 54 on main after T-0023 added `route.enabled` to
both layers; 121 / 67 / 54 before either.
66 / 119 before crew 1.0.42 merged T-0005, which added
`environments.prodUnattended` to both layers and the repo-only
`environments.nonProd`; this paragraph said 117 at that point, not counting
T-0004's repo-only `autopilot.mode` and `autopilot.maxPhases`. 65 / 116 before
T-0006 added `resume.auto` to both layers, §14a;
63 / 114 before the Windows burn-in added
`context.autoClear.onlyRepos` and `onlySessions` to both layers; this paragraph
still said 60 / 106 at that point, so the cloud-guard and scope-guard keys had
moved the counts without it. 45 / 86 before schema 6 added the six `guards.*`, the two
`github.mergeGate` keys and the repo-only `production.databases` /
`production.hosts`; 44 / 85 before schema 5 added `install.policy`; 59 / 102
before crew 0.19.92 added the seventh guard, `guards.roleWrites`, in both
layers; 60 / 103 before crew 0.20.19 added the context hook's three repo-only
`memory.*` keys.
All six of schema 6's keys are settable in both layers, so they moved the first
two numbers and not the third — the same shape `install.policy` and
`guards.roleWrites` had. Re-measure rather than trusting these: they are a
fact about one commit.)

### The one asymmetry, and it matters

The two rules agree on **which paths**. The write path additionally rejects
**values** the read path only reports:

- `plan_global_write` runs `crew_config.py::validate_providers` on the
  *merged result*, and raises `ProviderError` for a bad `qa.provider`,
  `dev.provider`, a bad name inside `qa.order`, or a bad provider in
  `qa.roles.<r>` / `dev.roles.<r>`.
- `resolve_config` **never raises**. A bad provider already on disk is reported
  by `crew_config.py::provider_problems` and nothing more.

A reader who takes "exactly what" to mean "identical behaviour" will be
surprised the first time a write is refused for a value a file on disk is
allowed to hold. That asymmetry is deliberate: refuse at the boundary where the
value enters, report at the boundary that must not crash a session hook
(`crew_config.py`, a comment stating exactly this).

### Open tables

`leaf_paths` treats an **empty dict as a leaf**. `qa.roles` and `dev.roles` ship
as `{}`, so everything beneath them is settable in either layer without crew
enumerating the role names:

```
dev.roles.some-role-invented-in-2030.model    # allowed by both rules
```

Confirmed by running `is_global_path` on exactly that path.

### Refused by both layers

Checked by running both predicates. Each of these is a fact about one
repository or one checkout, so a global file that set it would quietly hand the
same answer to every repo on the machine:

`schema`, `tier`, `roles`, `tracker`, `jira.project`, `verifyGate`,
`graph.out`, `graph.enabled`, `graph.tool`, `graph.mode`, `graph.commitHook`,
`obsidian.*`, `sdp.*`, `platform.*`, `context.*`, `emergency.*`.

`graph.obsidian.confirmed` gets a paragraph of its own in
`plan_global_write`'s docstring: it is consent to write into the user's own
notes outside the repo, not a capability, so no guided flow can grant it. **That
key no longer exists in `default_config()`** — see §12.1.

### What a guided write does

`plan_global_write` is pure and returns `(merged, changes)`. Two rules it
enforces in code rather than prose:

- **Merge, never replace.** Every key the existing file carries that `updates`
  does not name survives byte-for-byte, *including keys this module has never
  heard of*.
- A change to `pm.authority` that **widens** is flagged with
  `widens_authority`, computed by `crew_state.authority_rank`, not by equality.
  The comment at `crew_config.py` records why: the equality form was
  correct only while `act` was the top tier, and with three tiers it was wrong
  in *both* directions — `act → autonomous` computed `False` (the widest grant
  crew offers shipping unannounced) and `autonomous → act` computed `True` (a
  warning on the safe direction, which is what teaches users to click past it).

---

## 3. Reading the tables

- **Default** is the value `default_config()` actually returns, printed by
  running it. For every one of the 44 global-settable keys,
  `default_global_config()` returns the same value — verified by comparison, so
  there is no second default to keep in your head.
- A **list is a leaf.** `qa.order` and `notify.events` are replaced wholesale,
  never merged element-wise (`leaf_paths`, `crew_config.py::leaf_paths`).
- **The tables list the keys `default_config()` DECLARES.** As of 0.19.11 that
  is every key any crew code is known to read — ten were in use and declared by
  nothing until then, and §12.3 records what that cost and how it was found.
  "Known to read" is the honest limit: the search that found those ten is the
  same grep the consumer column rests on, and §13 says what that cannot see.
- **Consumer** is a `path:line` that reads the key to decide something. A
  Markdown citation is a real consumer here — crew is a prose-driven
  architecture and an agent executing a command file is the code path. Where the
  only references are the default block, the upgrade template, a pasted sample
  JSON, or a test asserting the default, the entry says **no consumer found**.

---

## 4. `schema`

| | |
|---|---|
| Type | integer |
| Current value | `7` (`crew_state.SCHEMA_CURRENT`, dumped by execution) |
| Layer | **repo only**, and exempt from inheritance *structurally* |

`schema` is absent from `default_global_config()`, so `filter_global` prunes it
from a global file and `plan_global_write` refuses to write it. But it gets a
second, stronger guarantee: even if it somehow survived the merge,
`resolve_config` overwrites it from the repo file or **pops it entirely** (see
the five-step block in §1). A resolved config therefore carries a `schema` only
when the repo file carried one.

This is the only key in the file handled outside the merge.

---

## 5. `pm.authority`

**Retired in crew 1.0.** The PM agent that honoured this key was deleted;
`crew_config.py` still reads and ratchets it so a 0.20 config resolves and
`/crew:migrate` can carry it to `crew.json`'s `retired.pm`. Nothing dispatches
on it any more.

| | |
|---|---|
| Type | string enum |
| Values | `report-only` (default), `act`, `autonomous` |
| Layer | global-settable |
| Consumer | `crew_state.normalise_authority` / `authority_rank`; `crew_config.py`; `/crew:migrate` (carries it to `retired.pm`) |

`crew_state.AUTHORITIES` is `["report-only", "act", "autonomous"]` (dumped by
execution). `authority_rank` returns `report-only` 0, `act` 1, `autonomous` 2 —
and **0 for `None` and for any unrecognised string**. A typo in a permissions
field fails closed, to the least permissive tier.

The tiers are a **floor**, not a set: anything `act` may do, `autonomous` may
do.

What each tier grants, quoted verbatim from `_WIDENING_NOTES`
(`crew_config.py`) — this is the string crew itself prints on a widening:

- **`report-only`** — "the PM reports and recommends only. This is the narrowest
  tier and nothing widens into it."
- **`act`** — "the PM will dispatch roles itself and report after. It still asks
  you to choose when a decision is open. Removal, deletion and offboarding still
  stop for an explicit yes."
- **`autonomous`** — "the PM will dispatch roles itself AND stop asking you to
  choose - where it would put a decision to you it takes the option it would
  have recommended and says which. Offboarding a role, deleting a codemap or
  diagram, rewriting .crew/metrics.md, and destroying git history or tracked
  work still stop for an explicit yes."

### The stop-list, at every tier

`crew_state.AUTONOMOUS_STOPS` (dumped by execution) is the machine-readable form
of that last sentence. Four entries, id and description verbatim:

| id | needs an explicit yes |
|---|---|
| `offboard-role` | offboarding a role, or removing one from the roster |
| `delete-map` | deleting a codemap file or a diagram |
| `rewrite-metrics` | rewriting `.crew/metrics.md` |
| `git-destruction` | destroying git history or tracked work - force-push, branch delete, history rewrite, or `rm` of a tracked file |

Since 1.0.41 the list also binds `/crew:autopilot` (§20): `commands/autopilot.md`
names every id, and `test_crew_autopilot.py::test_command_names_every_autonomous_stop`
iterates this tuple against that file, so an id added here without the command
naming it fails the suite.

`_WIDENING_NOTES` is keyed on **every** member of `AUTHORITIES` on purpose, so a
tier added without a note is a `KeyError` at the point of use rather than a
warning that silently describes the wrong thing (`crew_config.py`, a
comment naming that as the failure that produced the table).

---

## 6. `pm.ticketGranularity`

| | |
|---|---|
| Type | string enum |
| Values | `session`, `system` (default), `change` |
| Layer | global-settable |
| Consumer | `crew_state.normalise_granularity`, called at `crew_state.py::normalise_granularity` |

`crew_state.TICKET_GRANULARITIES` is `["session", "system", "change"]` (dumped
by execution). Normalised once in `crew_state.collect` alongside `pm.authority`,
so every consumer downstream reads a value guaranteed to be one of the three
and none of them re-decides what a typo means (`crew_state.py`, a
comment).

`system` files one ticket per session and opens a second only when the work
reaches another **registered marketplace entry**. A repo with no marketplace
declares no system boundary; the documented behaviour is that it falls back to
`session` and says so rather than inventing a boundary from the directory tree.

---

## 7. `docs.theme` and `docs.reportTheme`

| | Layer | Default | Consumer |
|---|---|---|---|
| `docs.theme` | global-settable | `null` | `crew_state.py`; `crew-house-style/SKILL.md` |
| `docs.reportTheme` | global-settable | `null` | `crew-house-style/SKILL.md` (prose only) |

Both are doc-builder theme-pack names, passed as `--brand <name>`.

### What `null` means

Quoted verbatim from `crew_upgrade.py::DOCS_BLOCK`, the comment above `DOCS_BLOCK`:

> Both keys' `None` now mean ONE thing -- "I have no answer, ask the next
> authority". For `reportTheme` that authority is `theme`; for `theme` it is
> doc-builder's own five-step resolution.

So `null` is **not** "no theme". A null `docs.theme` passes no `--brand` flag at
all and lets doc-builder resolve; a null `docs.reportTheme` means "follow
`docs.theme`", which is why a findings report in a branded repo does not come
out unbranded.

### The one-shot rewrite

`crew_upgrade.py` carries two constants, applied together:

```python
_DOCS_THEME_REWRITTEN_FROM = "neutral"
_DOCS_THEME_REWRITTEN_UNTIL_SCHEMA = 4
```

A `docs.theme` of `"neutral"` in a config below schema 4 is rewritten to `null`
on upgrade. This is the **single documented exception** to crew's rule of
carrying a user's value forward untouched, and the justification given in
`crew-setup/SKILL.md` is that `docs.theme` **had never had a consumer**,
so no value in it could be a preference anyone formed by watching it work.
Leaving `"neutral"` would have meant every upgraded repo passing an explicit
`--brand neutral` that overrode an installed brand pack — de-branding documents
that come out correctly branded today, with nothing in the config changed to
explain it.

A user who did mean neutral sets it again and it is honoured.

**Read §9 with this in mind.** It is the precedent for every zero-consumer key
in this file.

### Why there is no `docs.reportBuilder`

Recorded because the absence is a decision, and an undocumented absence reads as
an oversight that the next person helpfully fixes.

`docs.reportTheme` overrides `docs.theme` for one genre, so a `reportBuilder`
overriding *which skill builds* a findings report is the obvious next key. It is
deliberately not added.

**There is only one builder for the key to choose between.** `skills/report-builder/`
is a deprecated stub — its frontmatter reads "Do NOT use this skill", and it ships a
lone `SKILL.md` with no scripts; `skills/solomon-doc-builder/` is a brand pack, a
`SKILL.md` over `assets/` and likewise no scripts; every builder script in this repo
lives in `skills/doc-builder/scripts/`. So "a different report builder" is, in every
case anyone has actually wanted, a different *brand pack* — and that is selected by
name with `docs.reportTheme`, which already works.

**Which builder runs is derived, not preferred.** The routing table in
`crew-house-style/SKILL.md` picks a skill from the format the reader needs and
from what is installed. doc-builder is scoped to branded findings reports and
screenshot SOPs, and explicitly does *not* take DOCX and PDF over generally —
`crew-house-style/SKILL.md` gives the reason as a property of the tools rather
than a preference: doc-builder's `--to-docx`/`--to-pdf` run through Microsoft
Word over COM, and `anthropic-office-skills` needs neither, so routing every
DOCX and PDF to doc-builder would break crew's document path on Linux and macOS.
A config key cannot express that, because the right answer changes with the
machine. A user who set `reportBuilder: doc-builder` on a Mac would be
configuring a failure.

**It would be a third authority over a question that already has two.** Format
and installed-set decide today, and they cannot disagree — one narrows the
other. Adding a preference creates a conflict with no documented resolution, and
the first person to hit it has to guess whether their config or their platform
wins.

**A key with no consumer is a bug in this file's own terms.** See §9, and see
the `docs.theme` rewrite above: the single documented exception to carrying a
user's value forward exists *because* `docs.theme` had never had a consumer, so
no value in it could be a preference anyone formed by watching it work. Adding
`reportBuilder` with nothing reading it manufactures that same problem again,
and the next schema bump inherits it.

**What to do instead of adding it.** If doc-builder is genuinely wrong for a
repo's reports, that is a routing-table change in `crew-house-style/SKILL.md`,
where it is visible to every reader and covered by `tests/test_docs_routing.py`
— not a per-repo key that changes behaviour invisibly.

This entry is the answer to "should there be a `reportBuilder`?". If the case
changes, change this section; do not add the key beside it and leave this
standing.

---

## 8. `bitbucket.mergeGate` and `github.mergeGate`

| Key | Type | Default | Layer |
|---|---|---|---|
| `bitbucket.mergeGate.enabled` | boolean | `false` | global-settable |
| `bitbucket.mergeGate.branch` | string or `null` | `null` | global-settable |
| `bitbucket.mergeGate.preset` | string | `"standard"` | global-settable |
| `github.mergeGate.enabled` | boolean | `false` | global-settable |
| `github.mergeGate.branch` | string or `null` | `null` | global-settable |

Written by `crew_upgrade.py::BITBUCKET_BLOCK` and `crew_upgrade.py::GITHUB_BLOCK`.
`github.mergeGate` arrived with schema 6 (§16).

**These two blocks say a repo HAS a gate. `guards.mergeGate` (§16) says whether
crew may TOUCH it, and that one ships as `block`.** Both have to agree before
anything happens: `enabled: true` with `guards.mergeGate: block` means the gate
is reported as *not checked*, never as checked and fine.

### The GitHub block is the Bitbucket one minus `preset`, deliberately

The asymmetry is the decision, not an oversight. `bitbucket.mergeGate.preset`
binds to nothing — the subsection below records why it stays unwired rather
than bound to a hardcoded literal — so copying it into a second block would be
shipping that defect again, on purpose, in a place where the reason for it does
not even apply: `skills/github/scripts/merge_gate.sh` refuses to invent a gate
at all. Its `enable` **requires** `--from-export`, and a bare `enable` is
answered with "This script has no preset and will not invent a merge gate".

Three more differences the two scripts do not share, stated here because a
Bitbucket-shaped command fails against GitHub silently in each case, and
`commands/gate.md` is where they are documented in full:

- GitHub has a read-only `status <owner> <repo> [--branch NAME]`; Bitbucket has
  none, so a Bitbucket "status" is an `export` — a real API call.
- GitHub's `export` is **branch-scoped** (`--branch`), because classic branch
  protection is per-branch in the URL. Bitbucket's is repo-wide.
- GitHub's `enable` rejects `--branch` as a **usage error** (exit 2). Bitbucket
  accepts it and **ignores** it under `--from-export`.

GitHub's export captures **both** gate surfaces in one document — classic
branch protection and rulesets — each with its own state, and `unreadable` is a
state of its own. That matters more than it looks: a classic read without admin
answers 404 `Not Found`, the same status as an unprotected branch, and only the
exact message `Branch not protected` means absent. `enable --from-export`
hard-refuses an export holding an unreadable surface, because restoring half a
gate while reporting success is worse than restoring none.

Rationale, from `crew-setup/SKILL.md` — this is prose, and it is the
only statement of intent in the repo:

> off by default, because a gate that arrived switched on would start failing
> merges nobody asked it to watch. `branch: null` means the repo's main branch
> is resolved from the Bitbucket API rather than assumed to be `main` — a repo
> on `master` or a Gitflow `develop` would otherwise get a gate that looks
> configured and guards nothing.

### A correction to the docstring

`default_global_config()`'s docstring (`crew_config.py::default_global_config`) says
`mergeGate.branch` "stays null in both layers because the branch is [a
per-checkout fact]". Measured: `is_global_path("bitbucket.mergeGate.branch")`
returns **True**, and `plan_global_write` accepts it. The docstring is
describing the **default value**, not settability. A global file may set that
branch for every repo on the machine, which is very likely not what the
docstring's reasoning wants.

### The consumer, and what each default means

`/crew:promote` is the first consumer. `commands/promote.md`'s
`## The Bitbucket merge gate` section reads `enabled` and `branch` and turns
them into flags for `skills/bitbucket/scripts/merge_gate.sh`.

**That script still does not read crew config at all**, and the sentence this
subsection used to carry stays true: the *command* does the reading and passes
flags. Same shape as `crew-house-style` passing `--brand` to doc-builder — the
other entry's interface is referenced, never reimplemented, and crew owns no
part of it.

§9's rule is that whoever writes the first consumer decides what the default
**means**, in the same change. That decision, per key:

**`enabled: false` means promote does nothing at all** — no `merge_gate.sh`
subcommand, no Bitbucket API call, not even the read-only `export`. Because
`false` and "apply the disabled state" are opposite actions against a live
repo: `disable` deletes branch restrictions, so reading the shipped default as
an instruction would strip protections from every repo that never asked crew
for a gate. A default may not be the thing that removes a protection. The only
safe reading of "off" is silence.

**`branch: null` means promote passes no `--branch` and lets the script ask the
API.** `merge_gate.sh` resolves `.mainbranch.name`, and dies
asking for `--branch` when it cannot. Because the alternative — promote
substituting `main` — is wrong, and silently wrong, on a repo still on `master`
or on a Gitflow `develop`: the gate would look configured and watch a branch
nobody merges into. The script dying is the better outcome, because it keeps
"could not tell" a visible failure rather than an unknown wearing the label of
an answer.

**`preset: "standard"` means nothing today, and promote says so rather than
binding it.** `merge_gate.sh` has **no `--preset` flag**. The preset a bare
`enable` applies is one hardcoded JSON literal, `PRESET` at
`merge_gate.sh`, and nothing selects it. Two moves were available and both
are wrong. Letting `"standard"` quietly mean "whatever `PRESET` holds" invents
a binding: the word would read as a value that was honoured, and would go on
reading that way after `PRESET` changed underneath it — §9's own trap, one
layer out. Adding the flag is a change to `skills/bitbucket`, a separate
marketplace entry with its own version and its own regression suite, so it is a
different diff and not this one. So the key stays unwired, promote states at
the point it shows an `enable` command that the key selects nothing, and
`preset` stays on §9's list until a `--preset` flag exists to bind it to.

---

## 9. Keys with no consumer found

A key nothing reads is not a footnote in this repo. It is the shape of a known,
expensive bug: `docs.theme` had no consumer for four releases, shipped
`"neutral"` on a premise nobody had tested, and cost a mandatory one-shot
migration in `crew_upgrade.py` to undo (§7).

**Six keys are in that shape today.** Each was checked by an exhaustive grep
over every tracked file for the key name, then by reading each hit. Re-measure
it that way rather than trusting the number: this list was eight until
`/crew:promote` became the first consumer of `bitbucket.mergeGate.enabled` and
`.branch`, and it will move again the same way.

**They are being left exactly as they are, defaults included, and that is a
decision rather than an oversight.** Nothing reads them, so no behaviour is
wrong today. Flipping the five non-null defaults to `null` would be a second
mandatory `upgradeNeeded` prompt for every crew repo on every machine, inside
one week, in exchange for no change in behaviour at all.

**The requirement this places on the future change, which is the part that
matters:**

> Whoever writes the first consumer for one of these keys decides what its
> default *means*, at that moment, and must say so in the same change.

That is precisely the step `docs.theme` skipped. Its `"neutral"` was chosen
before anything read it, so when a consumer finally arrived the default was
already wrong for every installed repo, and undoing it cost a one-shot
migration in `crew_upgrade.py` (§7). The trap is not the unread key; it is
inheriting a default that was never a decision. A consumer landing on
`bitbucket.mergeGate.preset: "standard"` or `graph.tool: "graphify"` inherits
exactly that, unless the change that adds the consumer states what the value
means and why it is right.

So: do not "tidy" these defaults now, and do not add a consumer without
settling the default in the same diff.

| Key | Every reference it has |
|---|---|
| `bitbucket.mergeGate.preset` | `crew_upgrade.py` (writes it), `crew-setup/SKILL.md` (sample JSON and rationale), both templates, `tests/test_crew_config.py` + `tests/test_upgrade.py` (assert the default and the layering). `commands/promote.md` **names it in order to say it selects nothing** — there is no `--preset` flag to bind it to (§8) |
| `graph.enabled` | `crew_upgrade.py` (writes it), `crew-graph/SKILL.md` (a table describing it) |
| `graph.tool` | as above, `crew-graph/SKILL.md` — which reads "Always `\"graphify\"` today" |
| `graph.mode` | as above, `crew-graph/SKILL.md` — "Always `\"code-only\"` today" |
| `graph.commitHook` | as above, `crew-graph/SKILL.md` |
| `jira.project` | `crew-setup/SKILL.md` (writes it, and its sample JSON), `crew_config.py` (docstrings and one printed sentence), both templates. `commands/jira-sync.md` never mentions it |

The `graph` block's **only** key any crew code reads is `graph.out`, at
`crew_state.py`. Verified by grepping every tracked `.py`, `.sh` and `.ps1`
for `get("graph")` and `["graph"]`: the other hits are `crew_state.py` and
the since-deleted `pm_brief.py`, which read `knowledge["graph"]` — the *state* dict
`read_knowledge` builds, not the config block — and `crew_upgrade.py`,
which drops the removed `obsidian` sub-block.

The `bitbucket` block is read by no crew **code** — verified the same way,
grepping for `get("bitbucket")` and `["bitbucket"]` across every tracked file,
whose only hits are the two places in `crew_config.py` writing the defaults in.
Its consumer is prose: `commands/promote.md` (§8), with a committed regression
test in `tests/test_promote_merge_gate.py`. `preset` is on this list because
promote names it only to say it binds to nothing.

`jira.project` is the one on this list that most looks like it should work.
`/crew:jira-sync` gates on `crew_tracker.py resolve` saying `jira` (`commands/jira-sync.md`) and
then caches `jira.cloudId` — a key `default_config()` does not declare
at all, and that nothing reads back either. So the Jira block ships two keys and
crew consumes neither. `jira.cloudId` is counted in §12.3 rather than here,
because being undeclared is the larger of its two problems.

**What this does and does not say.** It says: nothing in this repository today
reads these six values to decide anything, so changing one changes nothing.
It does **not** say they are unused — a consumer may live in a tool outside this
repo, or be planned. It also does not say they should be removed; `docs.theme`'s
history says the expensive move is shipping a *non-null* default for a key with
no consumer, and five of these six default to `true`, `false`, `"graphify"`,
`"code-only"` or `"standard"` — non-null values nobody has ever exercised.

### Keys whose only consumer is prose

Real consumers, listed separately only because a grep for code will not find
them:

| Key(s) | Consumer |
|---|---|
| `sdp.portal`, `sdp.noteVisibility`, `sdp.closeOnDone` | `commands/sdp-sync.md` |
| `secondOpinion.provider`, `.sendsCode`, `.keyEnv` | `agents/planner.md`, `commands/plan.md`, `skills/crew-providers/SKILL.md` |
| `docs.reportTheme` | `skills/crew-house-style/SKILL.md`, with a committed regression test in `tests/test_docs_routing.py` that binds it to the findings-report genre |
| `bitbucket.mergeGate.enabled`, `.branch` | `commands/promote.md`, `## The Bitbucket merge gate` — the flags it passes to `skills/bitbucket/scripts/merge_gate.sh`, with a committed regression test in `tests/test_promote_merge_gate.py`. `.preset` is **not** here: see §8 and §9 |
| `pm.maxDispatches` | `agents/pm.md` ("Stop after `pm.maxDispatches` roles in one pass"). Also coerced to `int` at `crew_state.py` |

---

## 10. Global-settable keys

Settable in **either** layer; repo wins — **except `install.policy`, the
seven `guards.*` and `change.requireForProduction`, where the narrower of the
two layers wins instead** (§15, §16, §17). For the first eight "narrower"
means a smaller capability, with one of the eight (`guards.roleWrites`)
narrower meaning something slightly different again — see §18; for
`change.requireForProduction` the narrower value is `true`, so a repo may
turn that one **on** and never off — §17.
`production.databases` and `production.hosts` are deliberately **not** here:
they are repo-only, and §16 says why. Defaults are identical in `default_config()` and
`default_global_config()` except where the generated table prints two.

The table below is generated from the code (T-0048); the counts it states
replace the hand-counted ones this heading used to carry.

<!-- generated:config-keys-global begin -->
74 of 132 keys are settable in the machine-global file (generated; 58 are repo-only, section 11).
Regenerate with `python3 docs/guides/crew/src/config_reference.py --write` from the marketplace repository, whose
`docs/guides/crew/src/configuration-reference.md` is the full reference
(summaries and arrival versions). Do not edit the table by hand.

| Key | Layer | Values | Default |
|---|---|---|---|
| `qa.provider` | both | `auto` \| `claude` \| `codex` \| `copilot` \| `kimi` | `"auto"` |
| `qa.order` | both | list of: `claude` \| `codex` \| `copilot` \| `kimi` | `["codex", "kimi", "copilot", "claude"]` |
| `qa.fallback` | both | not validated - read by `commands/review.md` (expects model id) | `"claude-sonnet-5"` |
| `qa.codex.model` | both | not validated - read by `commands/review.md` (expects string or null) | `null` |
| `qa.codex.reasoningEffort` | both | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | `null` |
| `qa.copilot.model` | both | not validated - read by `commands/review.md` (expects string or null) | `null` |
| `qa.kimi.model` | both | not validated - read by `commands/review.md` (expects string or null) | `null` |
| `qa.roles` | both | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | `{}` |
| `dev.provider` | both | `claude` \| `codex` \| `copilot` \| `kimi` | `"claude"` |
| `dev.fallback` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects model id) | `"claude-sonnet-5"` |
| `dev.codex.model` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | `null` |
| `dev.codex.reasoningEffort` | both | `none` \| `minimal` \| `low` \| `medium` \| `high` \| `xhigh` \| `max` (listed in `commands/review.md`; not validated) | `null` |
| `dev.copilot.model` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | `null` |
| `dev.kimi.model` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | `null` |
| `dev.roles` | both | object of role pins; each pin's provider is checked (checked in `hooks/scripts/crew_config.py`) | `{}` |
| `worktree.root` | both | not validated - read by `hooks/scripts/crew_state.py` (expects path or null) | `null` |
| `secondOpinion.provider` | both | not validated - read by `commands/plan.md` (expects string) | `"none"` |
| `secondOpinion.mode` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string) | `"cli"` |
| `secondOpinion.model` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string or null) | `null` |
| `secondOpinion.keyEnv` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects string) | `"GEMINI_API_KEY"` |
| `secondOpinion.sendsCode` | both | not validated - read by `skills/crew-providers/SKILL.md` (expects boolean) | `false` |
| `memory.mode` | both | not validated - read by `skills/crew-memory/SKILL.md` (expects string) | `"repo"` |
| `memory.vaultPath` | both | not validated - read by `hooks/scripts/crew_recall.py` (expects path or null) | `null` |
| `context.autoClear.enabled` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_autocycle.py`) | `null` |
| `context.autoClear.method` | both | `auto` \| `none` \| `notify` \| `tmux` \| `xdotool` \| `wtype` \| `sendkeys`; per OS: linux: auto, none, notify, tmux, xdotool, wtype; macos: auto, none, notify, tmux; windows: auto, none, notify, sendkeys; windows-bash: auto, none, notify, tmux, sendkeys | `"auto"` |
| `context.autoClear.windowTitle` | both | not validated - read by `hooks/scripts/auto-clear.ps1` (expects string or null) | `null` |
| `context.autoClear.command` | both | not validated - read by `hooks/scripts/crew_autocycle.py` (expects string) | `"/clear"` |
| `context.autoClear.delaySeconds` | both | number (coerced in `hooks/scripts/crew_autocycle.py`) | `3` |
| `context.autoClear.minHandoffLines` | both | number (coerced in `hooks/scripts/crew_autocycle.py`) | `5` |
| `context.autoClear.onlyRepos` | machine-only | list of absolute repo paths, or null (coerced in `hooks/scripts/crew_autocycle.py`) | `null` |
| `context.autoClear.onlySessions` | machine-only | list of session ids, or null (coerced in `hooks/scripts/crew_autocycle.py`) | `null` |
| `resume.auto` | machine-arms | `null` \| `true` \| `false` (checked in `hooks/scripts/crew_resume.py`) | `null` |
| `resume.typeDelaySeconds` | both | whole seconds; fraction cut, negative or non-number reads as the default (coerced in `hooks/scripts/crew_autocycle.py`) | `2` |
| `resume.readyTimeoutSeconds` | both | whole seconds; fraction cut, negative or non-number reads as the default (coerced in `hooks/scripts/crew_autocycle.py`) | `15` |
| `notify.provider` | both | not validated - read by `hooks/scripts/notify.sh` (expects string) | `"none"` |
| `notify.urlEnv` | both | not validated - read by `hooks/scripts/notify.sh` (expects string or null) | `null` |
| `notify.tokenEnv` | both | not validated - read by `hooks/scripts/notify.sh` (expects string or null) | `null` |
| `notify.chatId` | both | not validated - read by `hooks/scripts/notify.sh` (expects string or null) | `null` |
| `notify.events` | both | not validated - read by `hooks/scripts/notify.sh` (expects list of event names) | `["phase", "gate", "waiting"]` |
| `shellRoute.mode` | both | `auto` \| `wsl` \| `powershell` \| `gitbash` | `null` (repo), `"auto"` (machine) |
| `shellRoute.distro` | both | not validated - read by `hooks/scripts/crew_shell.py` (expects string or null) | `null` |
| `pm.enabled` | both | not validated - read by `hooks/scripts/crew_state.py` (expects boolean) | `true` |
| `pm.mode` | both | not validated - read by `hooks/scripts/crew_state.py` (expects string) | `"adaptive"` |
| `pm.quietLines` | both | integer (coerced in `hooks/scripts/crew_state.py`) | `8` |
| `pm.maxLines` | both | integer (coerced in `hooks/scripts/crew_state.py`) | `40` |
| `pm.authority` | both, widening warned | `report-only` \| `act` \| `autonomous` | `"report-only"` |
| `pm.ticketGranularity` | both | `session` \| `system` \| `change` | `"system"` |
| `pm.maxDispatches` | both | integer (coerced in `hooks/scripts/crew_state.py`) | `3` |
| `docs.theme` | both | not validated - read by `skills/crew-house-style/SKILL.md` (expects string or null) | `null` |
| `docs.reportTheme` | both | not validated - read by `skills/crew-house-style/SKILL.md` (expects string or null) | `null` |
| `bitbucket.mergeGate.enabled` | both | not validated - read by `commands/promote.md` (expects boolean) | `false` |
| `bitbucket.mergeGate.branch` | both | not validated - read by `commands/promote.md` (expects string or null) | `null` |
| `bitbucket.mergeGate.preset` | both | not validated - read by `commands/promote.md` (expects string) | `"standard"` |
| `github.mergeGate.enabled` | both | not validated - read by `commands/promote.md` (expects boolean) | `false` |
| `github.mergeGate.branch` | both | not validated - read by `commands/promote.md` (expects string or null) | `null` |
| `install.policy` | both, ratchet | `manual` \| `ask` \| `auto` (ratchet: narrower layer wins; listed narrowest first) | `"manual"` |
| `guards.terraformApply` | both, ratchet | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | `"block"` |
| `guards.forcePush` | both, ratchet | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | `"block"` |
| `guards.adminMerge` | both, ratchet | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | `"block"` |
| `guards.mergeGate` | both, ratchet | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | `"block"` |
| `guards.cloudDestructive` | both, ratchet | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | `"block"` |
| `guards.sqlDestructive` | both, ratchet | `block` \| `ask` \| `allow` (ratchet: narrower layer wins; listed narrowest first) | `"block"` |
| `guards.prodDatabase` | both, ratchet | `none` \| `read` \| `full` (ratchet: narrower layer wins; listed narrowest first) | `"none"` |
| `guards.prodServer` | both, ratchet | `none` \| `read` \| `full` (ratchet: narrower layer wins; listed narrowest first) | `"none"` |
| `guards.roleWrites` | both, ratchet | `block` \| `report` \| `off` (ratchet: narrower layer wins; listed narrowest first) | `"off"` |
| `guards.cloudGuard` | both, ratchet | `block` \| `report` \| `off` (ratchet: narrower layer wins; listed narrowest first) | `"off"` |
| `environments.prodUnattended` | both, ratchet | `false` \| `true` (ratchet: narrower layer wins; listed narrowest first) | `false` |
| `change.requester` | both | not validated - read by `hooks/scripts/crew_change.py` (expects string or null) | `null` |
| `change.implementor` | both | not validated - read by `hooks/scripts/crew_change.py` (expects string or null) | `null` |
| `change.requireForProduction` | both, ratchet | `true` \| `false` (ratchet: narrower layer wins; listed narrowest first) | `false` |
| `change.sdpTemplate` | both | not validated - read by `hooks/scripts/crew_change.py` (expects string) | `"Change Management Request"` |
| `change.jiraIssueType` | both | not validated - read by `hooks/scripts/crew_change.py` (expects string) | `"Change"` |
| `change.category` | both | not validated - read by `hooks/scripts/crew_change.py` (expects string or null) | `null` |
| `route.enabled` | both | `false` \| `true` (checked in `hooks/scripts/crew_route.py`) | `false` |
<!-- generated:config-keys-global end -->

`crew_state.QA_PROVIDERS` and `DEV_PROVIDERS` are both
`["claude", "codex", "copilot", "kimi"]` (dumped by execution). `qa.provider`
additionally accepts `"auto"`; a `dev.provider` of `"auto"` is **not** valid —
`crew_config.py::validate_providers` checks `qa.provider` against
`QA_PROVIDERS + ["auto"]` and `dev.provider` against `DEV_PROVIDERS` alone.

The three numeric `pm.*` keys are coerced with `int_or` once, in
`crew_state.py::collect`, because they come from a
hand-edited JSON file and an unguarded comparison against a string is a
`TypeError` that takes out every session in the repo.

### The provider keys are also where `roles` pins live

`qa.roles` and `dev.roles` are open tables, so
`dev.roles.<role>.provider` and `.model` are settable in either layer without
crew enumerating role names. A role pin **wins over** the provider block for
that role — `/crew:review` resolves `review`'s model that way
(`skills/crew-review/SKILL.md`, the `qm()` helper).

---

## 11. Repo-only keys

Refused in the global file by `plan_global_write`, and pruned out of it by
`filter_global` if some other tool wrote one. Each is a fact about one
repository or one checkout.

`verify.stopBudgetSeconds` (§19) is read by the verify gate and declared by
neither default, so the generated table, which lists declared keys, cannot
show it: its default is `60`.

<!-- generated:config-keys-repo begin -->
58 of 132 keys are repo-only (generated; 74 are global-settable, section 10).
Regenerate with `python3 docs/guides/crew/src/config_reference.py --write` from the marketplace repository, whose
`docs/guides/crew/src/configuration-reference.md` is the full reference
(summaries and arrival versions). Do not edit the table by hand.

| Key | Layer | Values | Default |
|---|---|---|---|
| `schema` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | `7` |
| `tier` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | `0` |
| `roles` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects list of role names) | `["explorer", "reviewer"]` |
| `tracker` | repo | `files` \| `obsidian` \| `jira` \| `sdp` | `"files"` |
| `jira.project` | repo | not validated - read by `commands/jira-sync.md` (expects string or null) | `null` |
| `jira.cloudId` | repo | not validated - read by `commands/jira-sync.md` (expects string or null) | `null` |
| `sdp.portal` | repo | not validated - read by `commands/sdp-sync.md` (expects string or null) | `null` |
| `sdp.noteVisibility` | repo | not validated - read by `commands/sdp-sync.md` (expects string) | `"private"` |
| `sdp.closeOnDone` | repo | not validated - read by `commands/sdp-sync.md` (expects boolean) | `false` |
| `obsidian.vaultPath` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | `null` |
| `obsidian.boardDir` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects path or null) | `null` |
| `obsidian.board` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects file name) | `"Board.md"` |
| `obsidian.columns.backlog` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects string) | `"Backlog"` |
| `obsidian.columns.ready` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects string) | `"Ready"` |
| `obsidian.columns.inProgress` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects string) | `"In Progress"` |
| `obsidian.columns.review` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects string) | `"Review"` |
| `obsidian.columns.done` | repo | not validated - read by `hooks/scripts/crew_tracker.py` (expects string) | `"Done"` |
| `memory.inject` | repo | not validated - read by `hooks/scripts/crew_context.py` (expects boolean) | `true` |
| `memory.recall.vaults` | repo | not validated - read by `hooks/scripts/crew_recall.py` (expects list of vault names) | `[]` |
| `memory.recall.maxChars` | repo | positive integer (coerced in `hooks/scripts/crew_recall.py`) | `800` |
| `verifyGate` | repo | not validated - read by `hooks/scripts/verify-gate.sh` (expects boolean) | `true` |
| `context.enabled` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects boolean) | `true` |
| `context.warnAt` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects number) | `0.5` |
| `context.budgetTokens` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects integer or null) | `null` |
| `context.reserveTokens` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects integer or null) | `0` |
| `context.handoffPath` | repo | not validated - read by `hooks/scripts/crew_autocycle.py` (expects path) | `".work/HANDOFF.md"` |
| `context.keepTranscripts` | repo | not validated - read by `hooks/scripts/handoff-write.sh` (expects integer) | `5` |
| `context.autoClear.unsafeFocus` | repo | not validated - read by `hooks/scripts/auto-clear.sh` (expects boolean) | `false` |
| `context.autoWrapUp` | repo | not validated - read by `hooks/scripts/context-watch.sh` (expects boolean) | `true` |
| `context.autoResume` | repo | not validated - read by `commands/migrate.md` (expects boolean) | `true` |
| `context.staleHandoff.maxAgeHours` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | `72` |
| `context.staleHandoff.maxCommitsBehind` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects integer) | `3` |
| `emergency.standDown` | repo | not validated - read by `hooks/scripts/_common.sh` (expects boolean) | `true` |
| `emergency.ttlMinutes` | repo | integer (coerced in `hooks/scripts/crew_incident.py`) | `120` |
| `emergency.maxTtlMinutes` | repo | integer (coerced in `hooks/scripts/crew_incident.py`) | `480` |
| `platform.os` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | `null` |
| `platform.wsl` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects boolean or null) | `null` |
| `platform.shell` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | `null` |
| `platform.windowsHostIp` | repo | not validated - read by `hooks/scripts/crew_platform.py` (expects string or null) | `null` |
| `graph.enabled` | repo | not validated - read by `skills/crew-graph/SKILL.md` (expects boolean) | `true` |
| `graph.tool` | repo | not validated - read by `skills/crew-graph/SKILL.md` (expects string) | `"graphify"` |
| `graph.out` | repo | not validated - read by `hooks/scripts/crew_state.py` (expects path) | `"graphify-out"` |
| `graph.mode` | repo | not validated - read by `skills/crew-graph/SKILL.md` (expects string) | `"code-only"` |
| `graph.commitHook` | repo | not validated - read by `skills/crew-graph/SKILL.md` (expects boolean) | `false` |
| `production.databases` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | `[]` |
| `production.hosts` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | `[]` |
| `cloud.awsProfiles` | repo | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | `[]` |
| `cloud.awsRegions` | repo | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | `[]` |
| `cloud.azureSubscriptions` | repo | not validated - read by `hooks/scripts/cloud_guard.py` (expects list of names) | `[]` |
| `environments.nonProd` | repo | not validated - read by `hooks/scripts/crew_config.py` (expects list of globs) | `[]` |
| `scope.mode` | repo | `off` \| `report` \| `block` \| `auto` | `"off"` |
| `scope.allowCliApproval` | repo | `false` \| `true` (checked in `hooks/scripts/crew_ticket.py`) | `false` |
| `autopilot.mode` | repo | `off` \| `plan` (checked in `hooks/scripts/crew_autopilot.py`) | `"off"` |
| `autopilot.maxPhases` | repo | positive integer (checked in `hooks/scripts/crew_autopilot.py`) | `12` |
| `autopilot.deploy` | repo | `none` \| `nonprod` \| `all` | `"none"` |
| `autopilot.approval` | repo | `human` \| `self` \| `risk` | `"risk"` |
| `autopilot.questions` | repo | `human` \| `self` \| `risk` | `"risk"` |
| `tickets.baseBranch` | repo | branch name or null (checked in `hooks/scripts/scope_base.py`) | `null` |
<!-- generated:config-keys-repo end -->

`context.reserveTokens: null` means *off*, and survives as `null` — this is the
case `null_shadows` is deliberately narrow to protect (§1).

`platform.*` is written by `crew_platform.py`, which stamps the detected
machine facts into the repo config. That is why it is repo-only despite
describing a machine: the value records what *this checkout* resolved, and a
global override would make every repo on the box report the first one's answer.

`tickets.baseBranch` (T-0061) names the branch ticket branches are cut from,
for a repository that integrates on `development` rather than `main`. `null`
keeps the old default: `origin/HEAD`'s target, then `origin/main`, then `main`.
A value is tried as given when it contains `/`, then as `origin/<value>`, then
as `<value>`, and the first that names a commit is the base branch. When none
does, or `.crew/config.json` does not parse, the scope base is **could not
tell**: `scope_base.py --record` writes nothing and exits 1, `--base` and
`--changed` print nothing and exit 3, and the completion audit fails. It never
falls back to `origin/HEAD`. The key is read from the resolved repo config
(`crew_common.repo_config_file`), like `scope.mode`: a worktree with no
`.crew/` of its own reads the main checkout's.

`shellRoute.*` (T-0040) is a preference, not a detected fact, so it is not in
`platform.*`: platform-sync rewrites `platform.shell` every SessionStart. It is
settable on both layers, because which shell is fast is a fact about the
machine and a repo may still override it. The probe's answer is not config: it
lives in the machine-local cache `~/.claude/crew/shell-route.json`, written only
by `crew_shell.py probe --write` and `measure --write`. `shellRoute` is not
`route`: `route` routes plain-text prompts to `/crew:` commands, and
`shellRoute` picks the shell a job runs in.

---

## 12. Drift found while deriving this

Three gaps between what the repo says about config and what the code does.
None is fixed here — this file is a reference, and each of these is a separate
change with its own review. Item 3 is the one that affects behaviour.

1. **RESOLVED 0.19.11 — `plugin/crew/README.md` §11's sample `.crew/config.json`
   had drifted to 59 leaves against the real 85.** Parsed and compared
   leaf-by-leaf at the time: twelve keys it showed were absent from
   `default_config()` and twenty-eight it omitted, including the whole `dev`
   block, `docs.*`, `bitbucket.*`, `platform.*`, `qa.order`, `qa.roles` and
   `worktree.root`.

   Fixed by **deleting the sample**, not by correcting it. It drifted because it
   was a second copy of something derived elsewhere — the same failure as the
   `UPDATE.md` mirrors and the six stale schema numbers, all of which passed a
   green `validate-prompts.py`. A duplicate that agrees today is a duplicate
   that disagrees later, and correcting it would only have reset the clock.
   §11 now points here. This file is generated from the functions, and
   `tests/test_crew_config.py` holds the drift gates that keep the two
   committed templates and `crew-setup/SKILL.md` honest.

   Three of the twelve — `graph.obsidian.dir`, `.layout` and `.confirmed` — were
   genuinely removed in 0.16.13; `crew_upgrade.py` drops them from an
   existing config and says so, and `crew-graph/SKILL.md` states the
   removal correctly.

2. **`crew_config.py`**, on `bitbucket.mergeGate.branch` — see §8. The
   docstring's "stays null in both layers" describes the default value, and
   reads as a statement about settability, which it is not. Still open: it is a
   comment, and correcting it is a change to `crew_config.py` rather than to
   this reference.

3. **RESOLVED 0.19.11 — ten keys were in use and declared by no default.** Kept
   because how it was found is worth more than the fact that it is fixed.

   Nine were read by a hook script — the six `context.autoClear.*` at
   `auto-clear.ps1`, `context.autoWrapUp` at `context-watch.ps1`,
   `context.autoResume` at `handoff-read.ps1`, and
   `context.autoClear.unsafeFocus` at `auto-clear.sh`. The tenth,
   `jira.cloudId`, is written by `commands/jira-sync.md` and read back by
   nothing, so it is also in §9.

   They worked. `merge_defaults` carries an undeclared repo-layer key straight
   through, which is exactly why nobody noticed. What they lacked was
   visibility: `leaf_paths` could not see them, so they appeared in no key
   listing and in no `/crew:config --explain` output — measured, not assumed —
   and `is_global_path` refuses any path absent from the global template, so
   all ten were **silently un-settable in the global layer**.

   **The first pass found nine of the ten, and missed `unsafeFocus` for a
   reason worth keeping.** Every default was derived by reading the `.ps1`
   consumers, on a Windows machine. `unsafeFocus` is Wayland-only and appears
   only in `auto-clear.sh`. The PR body for that pass carried an honest-looking
   limit — "Linux not exercised" — which was disclaiming the exact gap that hid
   the defect instead of spending two minutes reading the `.sh` counterparts.
   Reading them is what found it. **A disclaimer is not a substitute for the
   check it describes.**

   Fixed in 0.19.11: all ten declared, and `context.autoClear` made globally
   settable because how a terminal is driven to accept a keystroke is a fact
   about the machine — `crew_platform.py::concerns` already validates `method`
   per platform. `unsafeFocus` is the exception and gets §14.

---

## 13. Where this file could be wrong

- **Consumer citations are the fallible part.** They were found by grep, then
  each one read. A key read through a variable rather than a literal would be
  missed. The six "no consumer found" entries in §9 were each re-checked by an
  exhaustive grep over every tracked file for the key name, reading every hit —
  that is the strongest check made here, and it is still a grep.
- **Line numbers move.** Grep the expression, not the number.
- **The defaults and enums are not fallible in the same way** — they were
  printed by executing `default_config()`, `default_global_config()`,
  `leaf_paths`, `is_global_path`, `crew_state.AUTHORITIES`,
  `TICKET_GRANULARITIES`, `QA_PROVIDERS`, `DEV_PROVIDERS` and
  `AUTONOMOUS_STOPS`. Re-run the snippet at the top of this file to confirm
  against any later revision.

---

## 14. `context.autoClear`, and the one key inside it that is not machine-wide

`context.autoClear` is the only block shared between the two layers: six of its
seven leaves are settable in `~/.claude/crew/config.json`, and every other key
under `context` is repo-only. The argument is that how a terminal is driven to
accept a keystroke is a fact about the machine, in the same sense provider
availability is — `crew_platform.py::concerns` validates `method` against what
*this* platform can actually deliver and reports one it cannot honour.

**Crew neither causes nor tunes Claude Code's own auto-compact.** That
built-in behaviour fires whenever Claude Code itself decides to; nothing in
this block, in `context-watch`, or in auto-clear influences when or whether
it happens. This block only decides what happens *after* a handoff is
written and verified — whether, and how, to act on it.

### `context.autoClear` is machine-global by design, and reaches every crew repo

`context.autoClear` lives in `crew_config.py`'s machine-global layer because
*how a terminal is driven to accept a keystroke* is a fact about the machine,
not the repository — the same reasoning `method` gets above. Since it is a
machine-wide switch, the OWNER DECISION (crew 1.0 F4, reversing the file-based
gate this section used to describe) is that it works in *any* crew repo, not
only ones that have run `/crew:init` far enough to have written a
`.crew/config.json` of their own. "Crew repo" is read the same way both
senders now agree: `.crew/` the DIRECTORY exists. `auto-clear.sh`/
`auto-clear.ps1` gate on it directly; `context-watch.sh`/`.ps1` gate their OWN
handover to auto-clear the same way, while their OWN context-window warnings
and wrap-up prompts keep requiring a real `.crew/config.json` underneath —
sizing a token budget against nothing is not a warning worth printing, so that
half of each hook stays exactly as strict as before.

**The never-create rule holds regardless.** A repo with no `.crew/` at all —
a fresh checkout, since the directory itself is git-ignored in this very repo
— gets nothing: no `.crew/`, no `.crew/.autoclear.log`, not even a silent
read that could be observed. Nothing here creates `.crew/`; the directory
gate only ever widens what happens once something else (`/crew:init`, a
worktree copy, or any other hook) has already made it exist.

**Required order in both senders, unchanged from before F4:** is `.crew/` a
directory at all → is auto-clear armed (the machine's `enabled`, then
`onlyRepos`/`onlySessions`) → only then may anything be written, even a log
line. `.crew/config.json`'s presence or absence plays no part in that order
any more. The ordering matters for a second reason beyond "is this a crew
repo": the enabled/narrowing check must ALSO run before anything is written,
or a disabled or narrowed-out repo stops being silent — it starts leaving a
`.crew/.autoclear.log` behind (even one line saying "refusing") the moment it
falls through to a refusal path instead of the silent `off` one. Both
`auto-clear.sh` and `auto-clear.ps1` special-case `off` (the enabled check,
then the `onlyRepos`/`onlySessions` narrowing) as an unconditional, silent
`exit 0` reached *before* the log file or its logging function is armed —
never a `note()`/`Write-CrewAutoClearNote` call. See `plugin/crew/tests/test_auto_clear_order.py`
for the regression tests pinning this order in both flavours.

**What this replaces.** The previous account here described a "deliberate
trade-off": the machine's `enabled: true` armed nothing in a repository until
it had run `/crew:init` far enough to gain a `.crew/config.json`, and a repo
that wanted the machine switch to reach it before that point had no option
but to write one anyway — a minimal, otherwise-pointless per-repo
`context.autoClear` stanza duplicated into a config that existed only to
satisfy the file gate (`solomon/aws-managed-services` carried exactly this
workaround). That duplication is no longer needed: the directory alone is
enough, and a repo's own `context.autoClear` config is back to doing only
what it always meant to do — narrow or switch OFF what the machine turned
on, never manufacture a "not initialised" refusal the machine did not ask
for.

### `method`

| Value | What it does | Where it can run |
|---|---|---|
| `"auto"` *(default)* | Picks per platform, below. | everywhere |
| `"tmux"` | Types into the `$TMUX_PANE` that is an ancestor of the hook. Exact — no focus involved. | Linux, macOS, WSL, Git Bash on Windows |
| `"xdotool"` | Types into the one X11 window owned by an ancestor process (or matching `windowTitle`). | Linux with `xdotool` installed |
| `"wtype"` | Refused outright — see `unsafeFocus`, above. | Wayland (declared, never granted) |
| `"notify"` | Types nothing. Prints a `systemMessage` saying the handoff is written and verified and it is safe to run the configured `command` yourself. Never claims anything was cleared or compacted, because nothing was. | everywhere |
| `"sendkeys"` | `System.Windows.Forms.SendKeys` against the one window owned by an ancestor process (or matching `windowTitle`), confirmed still foreground at send time. **Opt-in only — `auto` never chooses it.** Windows Terminal hosts every tab in ONE OS window, so the foreground-window check alone cannot tell which tab is showing: when the target window is owned by Windows Terminal, `auto-clear.ps1` also asks UI Automation how many tabs it has. It types only when that check finds **exactly one tab** — a window with one tab has that tab selected by definition, so that case needs no further proof. Two or more tabs **always declines**, however confidently a tab's shell-set name matches `windowTitle` or reads as selected: there is no tab-to-pid mapping, so a "proven" match is still a guess about which tab is this session's, and a wrong guess types into someone else's work. UI Automation being unavailable, throwing, or finding zero tab elements declines the same way and for the same reason — "could not tell" is never treated as safe. Every decline **falls back to `notify`**, logging why to `.crew/.autoclear.log`; it never falls back to sending regardless. A non-Windows-Terminal console host (e.g. `conhost`) has no tabs to disambiguate and is unaffected by any of this. | native Windows only |
| `"none"` | Refused outright, deliberately. | everywhere |

**`auto`'s per-platform pick, an OWNER DECISION:** a tmux pane if `$TMUX` names
one and `tmux` is on PATH; else an X11 window if `$DISPLAY` is set and
`xdotool` is on PATH; else **`notify`** on native Windows (`$OS` is
`Windows_NT`, present in every process tree there — cmd, PowerShell, Git
Bash alike — and absent inside WSL, which has its own init); else refused
(`"no usable method"`). `auto` **never** resolves to `sendkeys`: typing into
a window this hook found itself is a risk `auto` does not get to accept on
your behalf. Request `sendkeys` by name to opt in to it.

### What the widening costs

`windowTitle` narrows SendKeys down to one window when owner-pid resolution
alone cannot: `auto-clear.ps1` tries the ancestor terminal process's own pid
first, and only reaches for `windowTitle` when that pid owns zero or several
windows (the exact decline text is "the terminal that owns this session (pid
N) has N windows and nothing narrows them to one - set
context.autoClear.windowTitle"). On Windows Terminal specifically, this is
not a rare fallback — **it is effectively mandatory as soon as more than one
Windows Terminal window is open on the desktop.** Windows Terminal hosts
every WINDOW (not just every tab) on one desktop inside a single process, so
every one of a user's open Windows Terminal windows reports the SAME owning
pid. The owner-pid walk then matches all of them, not just this session's,
and declines unless `windowTitle` narrows the match to one — measured
2026-09-24: four Windows Terminal windows open on one desktop all reported
pid 14164. A repo that never sets `windowTitle` will work the day someone
tests it with exactly one Windows Terminal window open, and silently stop
working (declining, never sending into the wrong window — but doing nothing
either) the day a second one opens.

Machine-global is the right home for `windowTitle` — a terminal's title is a
property of the machine — but **a wrong global value now aims keystrokes at
the wrong window in every repo on that machine rather than in one.** That is
the trade, taken deliberately.

**`--dry-run`'s delay line never states a number for `notify`.** `notify`
types nothing, so `delaySeconds` buys it nothing; both `auto-clear.sh` and
`auto-clear.ps1` print `delay: n/a (notify sends no keystroke)` there instead
of echoing the configured value (or a hardcoded `0`, which `auto-clear.ps1`
did until this was fixed) — either would read as a real wait that
`delaySeconds` controls, which for `notify` it never does. A keystroke
method (`tmux`, `xdotool`, `sendkeys`) still echoes the configured delay
verbatim.

Its default is `null` where the scripts fall back to `""`. The two are
behaviourally identical (`if ($a.windowTitle)` is false for either, and
`auto-clear.sh` does the same), and `null` wins the tiebreak: `""` can read
to a human as a *deliberate* blank, and on this particular key that misreading
is dangerous.

### `unsafeFocus` is declared, and deliberately not granted

`context.autoClear.unsafeFocus` is the seventh leaf and the only one refused in
the global layer. `is_global_path("context.autoClear.unsafeFocus")` returns
`False`, and `filter_global` reports it by name.

It is **consent, not capability**. Setting it `true` accepts that `wtype` types
into whatever currently has focus, which Wayland offers no way to check
(`auto-clear.sh`). The rest of the block describes the machine; this one
accepts a risk. One `true` in a machine-global file would accept blind
keystroke injection for every repo on the box.

That distinction is not invented here. `graph.obsidian.confirmed` is refused by
`plan_global_write` and pruned by `filter_global` for exactly the same reason,
stated in `plan_global_write`'s own docstring: consent to act outside the repo
is not a capability a guided flow may hand over. Same reasoning, same
treatment.

Implemented as an `AUTOCLEAR_CONSENT_KEYS` exclusion over the one
`AUTOCLEAR_DEFAULTS` literal, rather than as a second hand-maintained copy of
the block, and covered by a test that goes red if the exclusion is dropped —
because dropping it is the tidy-up a future reader will reach for.


## 14a. `resume.auto` — auto-resume after `/clear`, armed by the machine only

T-0006. When it is armed, a SessionStart after `/clear` or a manual
`/compact` reads the handoff's `resume:` line and works out whether that
command may be resumed (`crew_resume.py::decide`). **Nothing starts on its
own yet**: the 2026-09-25 spike (Claude Code 2.1.282) proved an interactive
session drops SessionStart `initialUserMessage`, so the context hook names
the exact command and the reason it did not start, and the human presses
Enter or types it. T-0013 is the typing fallback (§14b).

| Where | Value | Effect |
|---|---|---|
| `~/.claude/crew/config.json` | `"resume": {"auto": true}` (the boolean) | arms it — the ONLY place it can be switched on |
| `~/.claude/crew/config.json` | absent, `null`, `false`, `"true"` (a string), anything else | off |
| `.crew/crew.json` **or** `.crew/config.json` | `false` | vetoes a machine `true`, from either file |
| `.crew/crew.json` or `.crew/config.json` | `true` | **nothing** — a repo can veto, never grant |

A cloned repo must not be able to start unattended work on someone else's
machine, so `crew_resume.py::settings` reads the arming value from the
machine file alone and the repo files only for a veto — the rule
`context.autoClear.enabled` follows (`crew_autocycle.py::settings`).
`resolve_config`'s repo-over-global precedence is deliberately not used.
Both repo files are read because the hooks' config split is real: the guards
read `.crew/config.json` and `/crew:migrate` writes `.crew/crew.json`. A
malformed machine file is off; a malformed repo file vetoes nothing.

**`context.autoResume` stays unread.** It defaulted `true` historically and is
still `true` in old configs; reviving it would have armed every one of them.
`resume.auto` is a new key so that no existing config can arm it.

When armed, a `startup` or `resume` source is `off` and adds nothing to the
injected context. On `clear` and `compact`, `decide` returns `wait` — with
the reason in the injected context — for: a `compact` whose PreCompact was not a typed `/compact` (both `handoff-write`
flavours record the trigger per session, in a repo with either
`.crew/config.json` or `.crew/crew.json`, and remove the session's previous
record first, without needing python, so a compact whose own record never
lands is not manual; absent, unreadable, older than 600 s, or not replaceable is not manual,
and records and orphaned `.tmp` files older than a day are pruned); no handoff, or one archived
as stale, or one judged stale that could not be archived; the handoff is the
automatic PreCompact skeleton (its Changed files list is bare `git` output, so
a file named `resume: ...` would otherwise be read as the line); no `resume:`
line, `resume: none`, or a line the grammar refuses; a `branch:` or `head:`
that does not match the checkout; a missing `.work/tickets/<id>/` or
`.work/autopilot/<slug>.json`; a command not installed in the plugin; a
`handoff-author.json` that could not be read; no record of which session wrote
this handoff; the handoff changed since its author session wrote it; the
handoff was written by another session; this session's process could not be
identified; a `<git-common-dir>/crew/resume-state.json` that cannot be read,
is not the shape `record_run` writes, or whose directory cannot be searched
(an unknown, never "nothing resumed"; fix the permissions or move it aside to
reset); a handoff already passed to `record_run`; a progress fingerprint that
cannot be computed (an unreadable `.work/INDEX.md`, one whose directory
cannot be searched, or an unlistable ticket directory counts as "cannot be
computed", never as progress); and the same command a second time with no
progress since. A `decide` that raises is `wait` with reason `internal
error`, and the handoff is still injected.

**Which session wrote the note (T-0042).** On an armed machine, a
PostToolUse Write, Edit or MultiEdit of the configured handoff makes the
context hook record `{sha256, session_id, process, at}` for this worktree in
`<git-common-dir>/crew/handoff-author.json` (temp file then `os.replace`,
under a lock; before the `memory.inject` gate, so injection off still binds).
An unarmed machine writes no such file. `decide` then waits unless the note's
sha matches the record and: after `compact`, the payload's `session_id` equals
the recorded one (it is stable across `/compact`); after `clear`, the Claude
Code process does (`session_id` changes across `/clear`). The process is the
nearest ancestor whose `/proc/<pid>/comm` is exactly `claude`, identified by
pid and start time (T-0042 spike, Claude Code 2.1.283). With no `/proc` —
native Windows, macOS — the process is unknown and every `clear` waits with
"this session's process could not be identified"; `compact` is unaffected.
A note written without Write/Edit/MultiEdit (by Bash, by hand, or before the
machine was armed) has no record and waits. A recorder that cannot read the
note, or whose write fails, leaves no entry for the worktree, never the
previous one.

**The stuck marker.** When a PreCompact can neither remove nor blank this
session's old record (python's `write_precompact_record`, or either shell
flavour's keyed removal), it leaves `precompact-<key>.stuck` beside it, and a
`compact` for that session is not manual while the marker exists or cannot be
stat'ed. The next record that lands clears it; one older than a day is pruned
with the records. `.stuck` is not `.json`, so the shells' `precompact-*.json`
sweeps never remove it. The `os.access` check stays as a second refusal.

**Accepted risks.** A full disk or quota can let an old record survive with no
marker: if the record cannot be replaced and the marker cannot be created
while the directory is still writable, an old `manual` record lives for up to
600 s. The same holds when the PreCompact payload has no readable session id
(the `precompact-*.json` sweep can fail with no key to mark). Two sessions
writing the handoff in the same instant can attribute it to the wrong one;
the record hashes the bytes it reads under a lock, which narrows the window
but does not close it.

**Unchanged, and reported to the owner:** a malformed repo file still vetoes
nothing. It is the same class as round 4's FIX (an unreadable veto reads as no
veto), but T-0006's approved plan chose it, so T-0042 reports it rather than
changing it; TODO.md tracks the decision. The `crew_resume.py decide` CLI applies
`crew_state.handoff_staleness` itself, read-only, and waits on a stale note.
`record_run` asks the consumed-once and loop guards again under its lock and
refuses (`ok: false`) a handoff already recorded, the same command with no
progress, a run with no fingerprint, or a state file it cannot read, which it
never overwrites: of two senders holding the same `run`, only the first may type.
If the opt-in cannot even be confirmed (the module or the machine file cannot
be read), the answer is `off`, so an unarmed machine sees exactly the
pre-T-0006 output.

## 14b. Typing the resume command (T-0013)

Where the terminal can be driven, an armed machine TYPES the command
`decide` rendered into its own session. On the SessionStart after `/clear`
or a manual `/compact`, before its per-event claim, the context hook runs
its own flavour's sender in resume mode (`auto-clear.sh --resume`,
`auto-clear.ps1 -Resume`) and names what happened in the context:
`Auto-resume: typing /crew:done T-0001 into this session in 2s (method
tmux); ...`, or T-0006's line plus `Auto-resume was not typed: <reason>.`

Consent is `resume.auto` (§14a); `context.autoClear.enabled` is not needed.
The rest of `context.autoClear` is read as the machine's description of its
terminal, exactly as for `/clear`: `method`, `windowTitle`, `onlyRepos`,
`onlySessions`. No new hook is registered.

| Key (machine file only) | Default | Effect |
|---|---|---|
| `resume.typeDelaySeconds` | `2` | wait before the tmux ready probe starts; the only wait on Windows |
| `resume.readyTimeoutSeconds` | `15` | how long the tmux probe waits for an idle, empty input line before it types nothing |

Both are read from `~/.claude/crew/config.json` only
(`crew_autocycle.resume_typing`); a repo copy is declared, because every
global key is a repo key, but never read. A fractional number is cut to its
whole part (`7.5` is `7`); any other value that is not a whole number, or is
negative, is the default.

Order, first refusal wins, and each is logged to `.crew/.autoclear.log`
(off is silent: not armed, or outside `onlyRepos`/`onlySessions`):
`decide` did not return `run`; no usable method, `$TMUX` unset, or a pane
that is not an ancestor of the hook; `wtype`; `xdotool` (no probe can see an
X11 input line); `sendkeys` on the bash flavour or `tmux` on the PowerShell
one; `auto` on native Windows is `notify`, which types, claims and records
nothing. Then the per-handoff marker
`<git-common-dir>/crew/resume-typed-<handoff sha256[:16]>` is claimed with
`O_EXCL`/`CreateNew` (taken: refuse), then `crew_resume.py record` runs
(failed: refuse, nothing typed), then the detached sender starts. tmux:
sleep `typeDelaySeconds`, poll `capture-pane -p -e` every 250 ms up to
`readyTimeoutSeconds` for the `❯` line between two rule lines holding only
whitespace once dim runs (the placeholder) and escapes are removed, with no
`esc to interrupt` on screen; a non-empty line refuses at once; then
`CREW_AUTOCLEAR_INHIBIT`; then the text, 0.5 s, and Enter (text and Enter
in one read, over ~60 characters, are taken as a paste). sendkeys: the
existing child, with the delay, the focus check, the tab recheck, the
inhibit check, then `SendWait`.

**The default and its limit.** The T-0013 spike (Claude Code 2.1.282, tmux,
77 `/clear` and 66 `/compact` runs) saw the input ready 0.134 s after
SessionStart at worst; ceil(2 x 0.134) is below the floor of 2. A delay is a
guess, not a proof. tmux has a probe; Windows has none, so on a loaded
machine a key can still land before the input box is ready: the focus and
tab rechecks catch a wrong window, not an unready box. On `/compact` the
probe waits for every SessionStart hook to finish, so `readyTimeoutSeconds`
must exceed the slowest one on the machine. Whether SendWait's per-character
input hits the same paste rule was not measured.

## 15. `install.policy`

What crew may do when a skill it routes to is **not installed**. Added by schema
5, which is the only thing that schema cut.

| Value | What crew does |
|---|---|
| `manual` *(default)* | Names the missing skill and the command. Runs nothing. |
| `ask` | Offers to install, and runs the command only after an explicit yes. |
| `auto` | Installs without asking. |

Read it with `crew_config.py --install-plan <name>`, which prints the action,
the command, and both layers' values.

### It resolves to the narrower layer, not the repo's

This was the one key that does not follow §1's precedence rule; since schema 6
it is one of **seven** (§16), and the rule now lives in one table,
`crew_state.RATCHETED_KEYS`, rather than in a bespoke pair of functions per key.
The reason is the threat model rather than taste. **crew reads config out of cloned
repositories.** A repo file travels inside somebody else's clone; the global
file is this machine's owner saying how much they trust crew here. Under
precedence, a repo shipping `install.policy: auto` would override an owner who
chose `manual`, and crew would start running commands because of a file the user
never wrote.

So the effective value is the **lower-ranked of the two layers**
(`crew_state.effective_ratcheted`, which `effective_install_policy` is now a
thin wrapper on). Neither layer can widen what the other allows: a repo may ask
for *less* than the machine permits and is obeyed, and may ask for more and is
refused.

Absent counts as `manual` on either side, which has a consequence worth stating
plainly because it surprises people: **`auto` requires both layers to say
`auto`.** Setting it in a repo alone does nothing. When a layer is holding the
value down, `--install-plan` says which one — a value that quietly does nothing
is worse than one refused out loud, which is the same rule
`default_global_config` applies to the keys it ignores.

### `auto` can only ever run a command from crew's own source

`auto` is defensible exactly as long as no string a repo author controls can
become a command. Two properties enforce that, and both are asserted in
`tests/test_install_policy.py`:

- **The command is looked up, never built.** `crew_state.INSTALLABLE` maps a
  plugin name to a literal argv tuple. `install_plan` consults that table
  **before** it consults the policy, so a name crew does not ship gets `report`
  and a null command *at every policy including `auto`*. There is no code path
  from a config value to a command string.
- **Commands are argv tuples, not strings.** Nothing is handed to a shell, so
  quoting cannot be escaped out of.

Adding an installable plugin is therefore a change to crew's source that goes
through review — which is precisely the property a runtime lookup would not
have.

### The migration is behaviour-neutral, and had to be

Bumping `SCHEMA_CURRENT` makes **every crew repo on every machine** report
`upgradeNeeded`, so this migration is mandatory. It lands the key as `manual`,
which is what crew already did at schema 4: nothing. Nobody's machine starts
installing anything because they upgraded.

### Why schema 5 carries one key

The obvious economy is to bundle: a schema bump prompts every repo on every
machine and costs the same for one key or six. The user ruled against it on
2026-09-12, and the evidence is in this file — `docs.theme` (§7) shipped ahead
of a consumer and cost a **mandatory migration with a one-shot value rewrite**
to undo, and §9 lists the keys still waiting for one. A key added ahead of a
need has cost more here than a second bump would cost to pay. If a real key
turns up later it gets its own bump.

Schema 6 carries six, and that is the rule being honoured rather than broken:
every one of them has a consumer landing in the same change (§16). The rule was
never "one key per bump"; it was "no key without a consumer".

---

## 16. `guards` — the configurable guardrails

Seven keys, one block, one ratchet, **three vocabularies**. What crew's
command guard does about each dangerous action it recognises, how much of
production crew may reach, and — since crew 0.19.92 — whether a dispatched
role may write outside the scope its own agent file declares. The third
vocabulary, `guards.roleWrites`, is different enough from the other six to
earn its own section: see §18, not the tables immediately below.

| Key | Type | Default | Layer | Read by |
|---|---|---|---|---|
| `guards.terraformApply` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.forcePush` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.adminMerge` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.mergeGate` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `commands/gate.md`, `commands/promote.md` |
| `guards.prodDatabase` | `none` \| `read` \| `full` | `"none"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.prodServer` | `none` \| `read` \| `full` | `"none"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.roleWrites` | `block` \| `report` \| `off` | `"off"` | both, **narrower wins** | `hooks/scripts/role-write-guard.sh`, `.ps1` |
| `guards.cloudDestructive` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.sqlDestructive` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/cloud_guard.py` (while `guards.cloudGuard` is on) |
| `guards.cloudGuard` | `block` \| `report` \| `off` | `"off"` | both, **narrower wins** | `hooks/scripts/cloud-guard.sh`, `.ps1` -> `cloud_guard.py` |
| `production.databases` | list of globs | `[]` | **repo only** | `crew_config.py::production_patterns` |
| `production.hosts` | list of globs | `[]` | **repo only** | `crew_config.py::production_patterns` |
| `cloud.awsProfiles` | list of globs | `[]` | **repo only** | `cloud_guard.py::cloud_pins` |
| `cloud.awsRegions` | list of globs | `[]` | **repo only** | `cloud_guard.py::cloud_pins` |
| `cloud.azureSubscriptions` | list of globs (id or name) | `[]` | **repo only** | `cloud_guard.py::cloud_pins` |
| `environments.nonProd` | list of globs | `[]` | **repo only** | `cloud_guard.py::environments_config` |
| `environments.prodUnattended` | `true` \| `false` | `false` | both, **true only when both say `true`** | `cloud_guard.py::environments_config`, `crew_autopilot.deploy_allowed` |

Read one with `crew_config.py --guard <name> [--json]`, which prints the
decision, both layers' values and which one is holding it down. The two shell
flavours call exactly that CLI — see "one resolver, two flavours" below.

### What each value does

| Value | What crew does |
|---|---|
| `block` *(default)* | Refuses, exactly as the guard did before these keys existed. |
| `ask` | Refuses, prints the **exact** command, and names the one marker file that approves **that** command. Creating it and re-running lets it through for 15 minutes; the next command asks again, and so does the same command tomorrow. |
| `allow` | Runs it, prints what it let through, and appends a row to `.crew/guard.log`. |

### Production access — `prodDatabase`, `prodServer`, and `production.*`

Two guards with their own vocabulary, in the same block and on the same
ratchet.

| Value | What crew does |
|---|---|
| `none` *(default)* | Refuses every command aimed at a declared production target. |
| `read` | Permits what the guard can **positively classify** as read-only. Everything else — including everything it cannot classify — is refused. |
| `full` | Permits anything, and appends a row to `.crew/guard.log` for each one. |

**`ask` is not a value here, and its absence is a decision.** The other four
guards answer "may crew do this one dangerous thing", where a per-command yes
means something. These answer "how much of production may crew reach", which is
a standing posture. An `ask` would mean a marker file per distinct SQL string —
a prompt nobody reads by the tenth query, which is consent theatre rather than
consent.

**The level is global; what is production is not.** `guards.prodDatabase` and
`guards.prodServer` are settable in both layers and ratchet like the rest:
"this machine may read production" is the same sentence in every checkout.
`production.databases` and `production.hosts` are **repo-only** — absent from
`default_global_config()`, pruned out of a global file by `filter_global` and
**reported** there. `prod-db-*` names one cluster in one repo and something else
in the next, so a machine-global list would carry one repo's hostnames into
every other repo on the machine: refusing innocent commands in one place and,
worse, passing dangerous ones in another because the list describes the wrong
estate.

**With no patterns declared the guard matches nothing.** That is what lets the
strictest possible level ship as the default without changing anybody's
behaviour: an upgraded repo gains two keys whose combined effect is "refuse
access to the empty set". Declaring a pattern is the act that turns them on.
It also means an empty `production` block is not a misconfiguration to warn
about — it is the normal state of a repo that has no production estate.

**Unknown is a write, and that is the whole value of `read`.**
`crew_guards.py::classify_access` answers `read` only when it can prove it,
from named lists rather than from a "looks harmless" heuristic:

- **SQL** (`psql`, `mysql`, `mariadb`, `sqlcmd`, `mongosh`, `redis-cli`,
  `sqlite3`, `cqlsh`) — every statement in the payload must open with
  `SELECT`, `SHOW`, `EXPLAIN`, `DESCRIBE`/`DESC` or `ANALYZE`, and none may
  contain `INTO`. `WITH` is deliberately absent: `WITH x AS (...) DELETE FROM
  ...` is a write that opens with a read-looking keyword. A client invoked with
  **no** `-c`/`-e`/`--query` payload is an interactive session and therefore
  unclassifiable.
- **Remote shell** (`ssh`, `plink`) — there must BE a remote command, and every
  segment of it, split on `;` `&&` `||` `|` and `&`, must name a read-only
  program: `cat`, `head`, `tail`, `less`, `ls`, `stat`, `grep`, `wc`, `sort`,
  `cut`, `awk`, `sed`, `df`, `du`, `free`, `uptime`, `uname`, `hostname`,
  `whoami`, `id`, `ps`, `top`, `netstat`, `ss`, `journalctl`, `dmesg`, `echo`,
  `which`, `env` — or a PowerShell `Get-*` / `Test-*` / `Measure-*` /
  `Show-*` / `Find-*` / `Select-*` verb. `systemctl`, `docker`, `kubectl` and
  `ip` are read-only only on a named subcommand (`systemctl status`, never
  `systemctl restart`). Any redirect, and `sed -i`, make it a write.
- **AWS** — `aws <service> <verb>` is a read only on a `describe-`, `list-`,
  `get-`, `search-`, `lookup-`, `batch-get-` or `scan-` verb. `aws ssm
  start-session` is not on that list, and an interactive session is exactly the
  case `read` must refuse.

Everything else is a write: an unrecognised tool, a command with an unbalanced
quote, a bare login. A classifier that answered "probably fine" would make
`read` a slower `full`, and the commands it cannot read are precisely the ones
a reader would most want it to refuse.

**The guards are silent when nothing matches.** Unlike the other four, these
two fire on ordinary commands — every `ssh`, every `psql` reaches them. A crew
banner above each one is how a guard becomes noise people switch off, so the
line is printed only when a declared pattern actually matched. The row in
`.crew/guard.log` is written by `crew_config.py --record` either way, so
"nothing is silent" still holds where it means anything.

**The older, unconfigurable `prod` rule stays** — the one that blocks when
`prod` or `production` is the whole argument, or its first or last
hyphen-joined segment, to `psql`/`mysql`/`sqlcmd`/`mongo`/`az`/`aws`/`gcloud`.
It is skipped for a command **only** when a declared `production.*` pattern
already matched it, because then the configured level has answered the same
question with better information. Leaving both in would mean
`guards.prodDatabase: full` still refused `prod-db-1` — a key that reads as
configurable and is not. With nothing declared, that rule behaves exactly as it
did before schema 6.

**No python is a stand-down; a failed resolver is a refusal.** Without any
python crew can read no config at all, so refusing every `ssh` in every repo
would be the guard people switch off — and the unconfigurable rule above still
blocks on its own regex with no python, so the floor does not move. A python
that IS present and then fails is crew broken on the question of whether this
command targets production, and that blocks, loudly, in both flavours.


**`ask` is a marker, not a prompt, and it had to be.** A `PreToolUse` hook has
no interactive stdin — exit 2 blocks and the retry blocks again — so an `ask`
implemented as a question would have been `block` wearing a different name: a
key with no reachable behaviour. The marker is
`.crew/.approved-guard-<name>-<sha256(command)[:16]>`, the same shape and the
same directory as `promote-gate.sh`'s `.crew/.approved-<env>-<sha>`, which
is the repo's existing answer to this exact problem. Keying it on a digest of
the command is what keeps it one-shot in the sense that matters: a marker
naming only the guard would be a standing grant, and approving one force push
would silently approve every later one.

The marker is **not consumed on read**. Both hook flavours are registered on
Windows, so one command can be judged twice; deleting the marker on the first
read would refuse the second. It is the user's to remove.

**It expires 15 minutes after it is created** (`GUARD_APPROVAL_TTL` in
`crew_guards.py`, read by `crew_config.py::_approval_is_live`). Not consuming
it on read answers "can one command be judged twice"; it does not answer "how
long is a yes good for", and the two are separate properties. This marker is
gitignored (`.crew/*`, and it is not on the `codemap/` / `endpoints.json` /
`verify.json` un-ignore list) and nothing prunes it, so an approval with no
time bound is a
standing per-command `allow` that outlives the session, the task and the
person who gave it — `ask` in the config, `allow` on disk. The design note
asks `ask` to stop for a yes *at that moment*, and a file with no expiry is
not that moment. `promote-gate.sh`'s marker needs no bound because its key is
a commit sha, so the next commit invalidates it; keying on the command text
gives up that natural expiry, so the bound has to be explicit. A marker dated
in the *future* expires the same way: crew cannot date that yes, and an
approval it cannot date is not one. Both shells print the window, taken from
the resolver's `reason` field rather than restated in bash and PowerShell.

**Under `allow` nothing is silent.** The stderr line goes with the session; the
row in `.crew/guard.log` is the durable half, and it is written for every
decision rather than only the permissive ones — a log recording half of what a
guard did is a log you cannot reason from. Tabs and newlines in the command are
normalised out before the row is written, the same way
`_common.sh::crew_incident_log` does it, so a crafted command cannot
forge a row.

### `block` did not preserve everything, and that is stated rather than implied

`guards.terraformApply` and `guards.forcePush` at `block` are exactly what the
guard already did. **Two things are new refusals**, and no default can turn a
new refusal into an old one:

- **`guards.adminMerge`.** No crew guard refused `gh pr merge --admin` before
  schema 6, in either flavour — measured against `origin/main`, both exited 0.
- **`tofu`.** `guards.terraformApply` now covers OpenTofu as well as Terraform.
  The rule named one of two drop-in-compatible binaries and refused nothing
  when the other was installed.

Both were bypasses rather than features, and the upgrade report says so out
loud. A user told only "the default is block, so nothing changed" will meet a
command that ran yesterday being refused today and go looking for a bug in
their tooling.

**Scope, stated rather than implied:** `adminMerge` matches `gh pr merge`
carrying `--admin` in any argument position. It does **not** match a
hand-rolled `gh api -X PUT .../pulls/N/merge`, which reaches the same endpoint
without the flag. That gap is left open deliberately — a rule wide enough to
catch every `gh api` call to a merge URL is wide enough to block *reading* one,
and a guard that fires on reads is a guard people switch off.

### `forcePush: allow` honours the value everywhere, and names the branch

The design note (`docs/guard-overrides.md`) left open whether `allow` should
still refuse `main`/`master` outright. **Settled: it honours the value
everywhere** — the machine owner chose it, and a guard that keeps one secret
refusal is a guard whose configuration cannot be trusted. The compensation is
that `ask` and `allow` both print the target branch before acting, from
`crew_config.push_target`.

`unknown` is its own answer there and never collapses into a plausible-looking
`main`. A bare `git push --force` takes its branch from the upstream config,
which is not on the command line, so crew genuinely cannot tell — and
substituting a guess is the "unknown wearing the label of a check that
happened" failure this file keeps returning to.

### `environments.*` — which terraform targets may run unattended (crew 1.0.42)

Read by the cloud guard alone, and only while `guards.cloudGuard` is armed. It
lets `terraform`/`tofu apply` of a **non-destroying saved plan**, and
`workspace new` / `workspace select -or-create`, run with nobody attending
when the target is non-production — and keeps a destroy from ever doing so.

```json
{ "environments": { "nonProd": ["dev", "qa", "staging", "*-staging"],
                    "prodUnattended": false } }
```

**Three environment values, never two.** `nonProd` is a name matching a
`nonProd` glob (fnmatch, case-insensitive). `prod` is a name matching none.
`unknown` is everything crew cannot settle: no signal, a signal that is not a
literal (`TF_WORKSPACE=$WS`), signals that classify differently, or an
`environments` block it cannot read. **`unknown` is narrower than `prod`**:
`prodUnattended` allows `prod`, and nothing allows `unknown` unattended.

The names come from, and must all agree after classification:
`TF_WORKSPACE` (inline, `env`, `export`, `$env:`, then the hook's own
environment); else a literal `workspace select|new X` earlier in the same
command; else `<payload cwd>/<-chdir>/<TF_DATA_DIR or .terraform>/environment`
— used only when nothing in the command changes directory or switches
workspace, and a **missing file is unknown, not `default`** (terraform writes
no file for `default`, measured on 1.16.3, so the default workspace is always
unknown this way). Plus `-var environment=X` / `TF_VAR_environment`, and a
saved plan's sidecar. `-var-file`, `*.tfvars` and HCL are never read.

A directory change in **any** spelling makes the workspace file unusable:
`cd`/`pushd`/`Set-Location`, `env -C DIR`/`-CDIR`/`--chdir=DIR`, `sudo
-D`/`--chdir`/`-R`, `wsl --cd`/`~`, `pwsh -WorkingDirectory`/`-wd`, `parallel
--wd`, `chroot`/`unshare -w`/`nsenter -w`, a sourced file or `.ps1`, and .NET's
`CurrentDirectory`. An environment change crew cannot read makes
`TF_WORKSPACE` itself unknown: `source`/`.` of a file, `export $(...)`, `eval`
or `iex` of text built at run time (or fed from the pipeline), `set -a`,
`read`, any PowerShell `env:` drive write or `SetEnvironmentVariable`, and an
`||` chain (the next command runs only if this one failed). A plan, sidecar,
workspace file or `azureProfile.json` that is not a regular file (a FIFO, a
device) is never read: it is unknown, not a hang past the hook's budget.

**A terraform line is judged only when every word on it is a plain
literal.** Before any of the reading below, the raw command text is checked:
if it names `terraform`, `terragrunt` or `tofu` anywhere — each word read with
its quotes and escapes taken out, `$'...'` decoded, an expansion read as "could
be anything" and a brace list expanded — then every word must match
`^[A-Za-z0-9_./:=@%+,-]+$` and every operator between words must be `;`,
`&&`, `||`, `|`, `&`, `>`, `>>`, `>&`, `&>`, `<` (PowerShell's `*>` too).
Otherwise the line is **could not tell** — a quote, `$`, backquote,
backslash, glob, brace, `<(`, heredoc, here-string, comment or control
character on it, or a PowerShell `@` splat — and it is asked about when someone attends, denied when
nobody does and denied under `block`; a live one-shot marker for that exact
text still lets it through under `ask`/`allow`. Nothing else below is
consulted for it (guard.log policy `could-not-tell`). Unusual quoting on a
terraform line is asked about, not allowed; unattended, it is refused — which
includes `terraform apply "p.tfplan"`. A read-only subcommand (`terraform plan
2>$null`, `terraform workspace select "staging"`) and a line that only
mentions terraform (a commit message quoting it) are not gated for their
quoting (below). Plain lines are read exactly as before.

**Destroy is `yes`, `no` or `unknown`, and unknown counts as yes.** `yes`:
`destroy`, `apply -destroy`, `apply -replace`, `run-all destroy` (and
terragrunt's `destroy-all`, `stack run destroy`, `graph destroy`, and `exec --
terraform destroy`), `workspace delete`, a saved plan whose sidecar lists a delete. `no`: only a saved plan
whose sidecar lists none, `workspace new`, `select -or-create`. Everything
else is `unknown` — an apply with no saved plan, any terragrunt apply
(`apply-all`, `stack run apply` and `graph apply` included), a plan
with no sidecar, a stale one (the plan's sha256 changed), a malformed or
unreadable one, a plan path that is not a literal, a plan over 64 MiB, and a
saved-plan apply that is **not the only command** in the invocation. The plan
is hashed when the hook runs, before the command does, so anything beside the
apply — `terraform plan -out`, `cp`, a nested shell, an output redirect to
anything but `/dev/null`, a command substitution anywhere the shell runs one
(an unquoted heredoc body, `${...}`, `$((...))`) — could replace the plan
after crew read it. A quoted heredoc (`<<'EOF'`) is literal and counts for
nothing; PowerShell's `2>&1` is a redirection, not a command. Run the plan
and summarize steps first, then the apply on its own.

**The sidecar.** The hook cannot run `terraform show` (15 seconds, and it
must not run terraform at all), so a saved plan is summarised first, outside
it:

```bash
terraform plan -out p.tfplan
python3 "${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_tfplan.py" summarize p.tfplan
terraform apply p.tfplan    # a separate command, on its own
```

`summarize` writes `.crew/tfplan/<sha256 of the plan bytes>.json` with the
workspace, the `environment` variable and every address whose actions include
`delete`. The workspace is the one the **plan** is bound to, read out of the
plan file itself (its `backend.workspace`), never `workspace show` — a plan
made under `TF_WORKSPACE=production` in a directory with staging selected is
a production plan. When it cannot be read it is `null`, which the hook reads
as unknown. It writes nothing when `show` fails or times out, and never creates
`.crew/`. A plan with no changes has no `resource_changes` at all and is
refused, so its apply asks.

**The decision**, applied after `guards.terraformApply` has been ratcheted:

| policy | destroy yes/unknown | nonProd | prod, `prodUnattended` both layers | prod | unknown env |
|---|---|---|---|---|---|
| `block` | deny | deny | deny | deny | deny |
| `ask`, no live marker | ask | **allow**, logged | **allow**, logged + on screen | ask | ask |
| `ask`, live marker | allow (that command) | allow | allow | allow | allow |
| `allow` | **ask — BREAKING in 1.0.42** | allow | allow | allow | allow |

`ask` is denied when nobody is attending, as everywhere in this guard. The
guard.log policy column says why: `env:nonProd:<name>`,
`env:prod-unattended:<name>`, `env:prod:<name>`, `env:unknown`, `destroy:ask`,
and `could-not-tell` for a terraform line that is not all plain literals
(asked under `ask` and `allow` whatever its environment, denied under `block`).
"A terraform line" means one that runs terraform, terragrunt or tofu as a
command -- its command word, or a command inside `bash -c`, `eval`, `pwsh -c`
or a substitution -- not one that mentions the word in a message, a search or
a file name (README, "Cloud guard"); PowerShell lines follow the same rule. A
line that runs terraform in a way the parser does not follow (an alias, a
binary the same line copies or links and runs by its new name, zsh's
`=terraform`, a script runner such as `flock` or `ssh`, PowerShell's
`Set-Alias` or `Start-Process`) is `could-not-tell` even when every word is
plain; a read-only subcommand (`plan`, `show`, `output`, `fmt`, ...) and the
arguments of a program that is not terraform (`cp -r terraform
"$BACKUP_DIR"`) are not gated for their quoting. Options before the
subcommand are skipped as terraform and terragrunt read them (`terragrunt
--working-dir infra destroy` is a destroy).

**What the guard does not catch.** It catches terraform, terragrunt and tofu
written directly: bare or path-qualified, behind the listed wrappers
(`aws-vault exec`, `unbuffer` and `sem` among them; an option a listed
`xargs`, `parallel`, `sem`, `aws-vault` or `unbuffer` does not know makes the
line `could-not-tell`, and so does a `workspace select` that `xargs` or
`parallel` may append `-or-create` to), inside
`bash|sh|zsh -c` and `eval`, with global options before the subcommand, and
PowerShell's `&`, `.`, `terraform.exe`, `Start-Process` and `Invoke-Expression`
(a script that is not a literal string, or a parameter crew does not know,
is `could-not-tell`, and on a line naming terraform so is any PowerShell form
it does not read whole: a splat, a call whose command word is not a plain name,
an alias definition, or a group given to Invoke-Expression or to terraform).
`terragrunt exec -- cmd` is unwrapped like any listed wrapper. It does not try to
catch a program renamed by alias, function, symlink or copy, `env -S` escape
strings, BusyBox applets, git `!` aliases, an interpreter (`python -c`, `node
-e`), a script file, a wrapper it does not list (`strace`, `systemd-run`),
a program that runs another (`git bisect run`, `rg --pre`) or a container's
entrypoint. No command-line guard can: unattended work must run interpreters
and scripts. The real boundary is the credentials an unattended run holds,
which is T-0044. README, "What the guard does not catch", lists the commands.

**The always-stops.** A destroy is never applied unattended at any setting —
`terraformApply: allow` and `prodUnattended: true` included. So is an apply of
a plan crew cannot read, which means **`terraform apply -auto-approve` with no
saved plan now asks under `allow`**. Approve one command with the
`.approved-guard-terraformApply-<hash>` marker the refusal names, or summarise
a saved plan. An unknown environment is never unattended either.

**`prodUnattended` ratchets, and only the literal `true` counts.** It is true
only when the repo's `.crew/config.json` **and** the machine-global file both
say `true`; `"true"`, `1` and `null` are false. A cloned repo cannot grant
itself unattended production. `nonProd` is **repo only**, for `production.*`'s
reason — `staging` names one workspace in one checkout — so `filter_global`
prunes and reports a global list. A malformed block (`nonProd: "dev"`, a
non-bool `prodUnattended`) makes every environment unknown and forces an armed
guard to `block` mode.

**At the defaults nothing changes except the destroy rule.** With `nonProd`
empty and `prodUnattended` false, every name is `prod` or `unknown` and `ask`
asks as before. `workspace delete` is a destroy, so it is a finding in every
armed state, the layer engaged or not. `workspace new|select -or-create` are
judged only once the layer is engaged (a `nonProd` glob, or `prodUnattended`
true); then they are **new** findings: denied under `block`, and under `ask`
denied unattended for a prod or unknown target.

**Not a promotion gate.** `prodUnattended` does not stand down
`promote-gate.sh`'s `requireHuman` (`promote-gate.sh`, the `requireHuman`
check), which still applies independently: fully unattended production also
needs that off. `.crew/verify.json` stays promote-gate's list of environments,
read from the session's project directory even when the deploy runs from a
linked worktree (whose HEAD and cleanliness are what the gate then checks);
`crew_config.py --check` warns when a `nonProd` glob covers one it marks
`requireHuman: true`.

### The ratchet is one table, not five copies

`install.policy` shipped its ratchet as a bespoke `effective_install_policy`
plus a bespoke `resolve_install_policy`. Four guards arriving beside it would
have been four more pairs — five mechanisms for one rule. One mechanism can be
wrong; five can disagree, and then only one of them gets fixed.

So: `crew_state.RATCHETED_KEYS` maps each ratcheted key to its `(tiers,
normalise, rank)` triple, `crew_state.effective_ratcheted` is the only place
that takes the minimum, and `crew_config.resolve_ratcheted` is the only place
that reads both layers raw and reports `heldDownBy`. The two old names survive
as thin wrappers so their callers and tests did not have to be rewritten to
prove the generalisation happened.

**`pm.authority` is deliberately not in that table.** It ratchets for the
*widening warning* on `/crew:config --set` (`crew_config._RATCHETED`, which is
a different table with different membership); its two layers still resolve by
ordinary precedence, because a repo raising its own PM's authority grants
capability inside that repo rather than on the machine. Neither table is
derived from the other, on purpose.

An unknown value fails closed to `block` on whichever layer carries it
(`normalise_guard_policy`), and both sides are normalised **before** they are
ranked — so a typo costs capability rather than granting it, and a widening
*from* an unknown still reads as a widening.

### Writing the repo layer, and the enum check both writers share

`/crew:config`'s menu (T-0075) writes `.crew/config.json` through one path,
`crew_config.plan_repo_write` / `write_repo_config` (CLI
`crew_config.py --set PATH=JSON --repo [--apply]`). It does not change what
either layer means on read; it marks what a repo edit changes **in force**:

- A **ratcheted** key compares `effective_ratcheted` before and after, by rank.
  Repo `guards.forcePush` `block` -> `allow` under a machine `allow` prints
  `! guards.forcePush widens to`; the same edit under a machine `block` does
  not widen, and prints `held down by the machine-global layer at block`
  instead.
- `pm.authority` resolves by precedence, so its before-value is the repo's own,
  else the machine's, ranked by `_RATCHETED`.
- Three repo-only consents are marked by value: `context.autoClear.unsafeFocus:
  true`, `autopilot.mode: "plan"` and `verifyGate: false`
  (`crew_config._REPO_WIDENING`).

Every update is judged per LEAF (`crew_config.leaf_updates`, recursive), by
the one predicate both planners and the menu share, `value_allowed(dotted,
layer, value)`: a whole-block value is expanded, so
`context={"autoClear": {"unsafeFocus": true}}` is judged as
`context.autoClear.unsafeFocus` and refused at the machine layer
(`MACHINE_REFUSED` names the two consent keys), and one good leaf does not
carry a bad one. A block set to `{}`, or replaced by a scalar, is refused off
an open table (`guards: {}` refused, `qa.roles.review: {}` is "no pin").

Each judged leaf is also what is WRITTEN (`crew_config.assignments`, review
round 3): a block value is written leaf by leaf, so the block's untouched
siblings, unknown keys included, survive, and a widening is marked on the leaf
that widens (`{"guards": {"forcePush": "allow"}}` prints
`! guards.forcePush widens to`). A value at an open role table (`qa.roles`,
`dev.roles`) is written one ENTRY at a time, each entry a whole pin, so the
other roles' pins survive and a new pin never inherits the old one's model.

It refuses, naming the key and the reason: a path that is not a leaf of
`default_config()` (unknown keys, and a block emptied or replaced by a scalar,
such as `scope: {}`, that would drop a leaf the per-key rules guard),
`platform.*`, `schema`,
`scope.mode`, `scope.allowCliApproval`, `context.autoClear.onlyRepos` /
`.onlySessions`, and anything but exactly `false` or `null` for
`context.autoClear.enabled` or `resume.auto` (only the machine file arms
those). That test is by identity (`crew_config.is_repo_veto`), not `in (False,
None)`: `0 == False` in Python, and the readers (`crew_autocycle`,
`crew_resume`) compare with `is False`, so a written `0` would veto nothing. It
refuses to write when the file is absent or does not parse, rather than
creating a config from one key or overwriting the only copy -- and the menu
reads the file the same strict way, so over an absent or unparseable
`.crew/config.json` every repo row is read-only with that refusal as its
reason, rather than offered and then refused at Save.

**Enum values are checked on both writers.** `crew_config.enum_values` returns
the tuple each reader normalises against — the `RATCHETED_KEYS` tiers,
`AUTHORITIES`, `TICKET_GRANULARITIES`, `auto` + `QA_PROVIDERS`, and
`DEV_PROVIDERS` — and a value outside it is refused. This is a behaviour
change for the global `--set`: it used to write `pm.authority: "bogus"` and
read it back as `report-only`.

**The null rule** (`crew_config.null_means`). At the repo layer a `null` on a
veto-only key clears the veto, and on a key the machine file may set it
inherits the machine value (`without_null_shadows` drops it on read); either
layer, a `null` on an open key (no tuple) is unset. A `null` on an enum key at
the machine layer is refused: it is outside every tuple its reader normalises
against. A legacy `null` already in a file is tolerated; the rule judges what
is being written now. Each change carries its meaning (`null`), and the dry
run prints it.

**The merged file is judged whole** (`crew_config.merged_problems`): every
untouched known leaf of the file the write would produce is checked for what
its presence means at that layer (`_content_problem`): an enum value outside
its tuple (a legacy `null` tolerated), a consent key (`MACHINE_REFUSED`) in
the machine file, and a veto-only key holding anything but `false`/`null` in
the repo file. One already there refuses an unrelated write as `pre-existing
...`: an enum value says `fix that key first` (it can be fixed in the same
write), the other two `remove it by hand first` (no crew writer sets or
removes them). Unknown keys are never judged. JUDGEMENT: refusals of a write
are not refusals of content, so a `REPO_REFUSED` key in the repo file
(`/crew:init` and platform-sync write them) and a repo-only key in the
machine file (pruned by `filter_global` on every read) do not block a write.
Then `validate_providers` runs on the merged file at both layers, wrapped as
the layer's refusal. `qa.order` must be a list of QA providers or `null`: any
other shape (`1`, `true`, `"codex"`, an object) is refused at both layers with
exit 2, never a traceback, including when it is already in the file an
unrelated write merges onto (the menu then shows the rows it blocks read-only,
naming `qa.order`). A path past a template leaf (`pm.authority.a`) and an
object at a leaf (`pm.authority={"a": 1}`, `notify.chatId={}`) are refused at
both layers, on the update and when already in the file (`pre-existing`,
fixable in the same write). `qa.roles` and `dev.roles`, and each entry under
them, must be an object or `null`: a string, number, boolean or array there is
refused with exit 2 at both layers, the file included, since the reader drops
it and `qa.roles=1` would silently wipe every pin.

**Compare-and-swap, both files.** `write_global_config` and
`write_repo_config` re-run their plan on the bytes read inside
`crew_config_files.update_json`: an `O_CREAT|O_EXCL` lock file beside the
config (`<file>.lock`, the review ledger's construction; 3 s wait, then a
refusal naming the lock and the PID inside it), a strict read, and a
sibling-fsync-replace that keeps CRLF and a UTF-8 BOM. `--set` prints the
digest (sha256) of the bytes it planned against, `absent` when there is no
file, and `--apply --expect <digest|absent>` refuses a file that changed, or
appeared, since (`RepoWriteConflict` / `GlobalWriteConflict`, subclasses of
the refusals, so every existing `except` still catches them). Without
`--expect` the merge is onto the file under the lock. A repo write's widening
marks read the machine file, so `--set --repo` also prints `machine digest:`
and `--expect-global <digest|absent>` binds it: `write_repo_config` reads the
machine file once under the machine lock (always taken, creating its
directory when absent, never the file; taken before the repo lock, the one
nesting order) and refuses one that changed since. The machine writer now refuses an unparsable or non-object global file
instead of replacing it from the read path's `{}` collapse. A foreign writer
(an editor's save) is not serialised by the lock. An OS error from either
lock, the machine directory or the write itself is refused with exit 2,
nothing written and the path named, never a traceback.

### One resolver, two flavours

`guard.sh` and `guard.ps1` both shell out to `crew_config.py --guard`. Neither
implements config layering itself. The two files drift independently — three
bypasses fixed in #132 were open in both — and the layering rule whose entire
point is that a cloned repo cannot widen it must not have two implementations,
either of which could be the one that forgets to ratchet.

`Test-EnvArgHit` in `guard.ps1` *is* a deliberate reimplementation of its bash
counterpart, and the difference is the cost: it is a tokenizer that runs on
every command, where a subprocess would be a per-command tax. The guard
resolver runs only after a rule has already matched, so it costs nothing on the
common path.

**Fail closed, loudly.** No python, a `crew_config` that raises, a line the
shell cannot parse — every one of them is `block` with the reason said out
loud. Unlike the `prod`-argument rule, which degrades to a cruder regex, config
layering has no cruder form: "could not check" is its own outcome here and
never collapses into "checked, and fine".

### `guards.mergeGate` is read by a command, not by the guard

"May crew take a live repository's merge gate down" is not a shape a regex over
a command line can recognise, so this one key is read by `/crew:gate` and
`/crew:promote` rather than by `guard.sh`. It lives in the same block and the
same ratchet anyway — a fifth key somewhere else with its own layering rule is
how the two rules come to disagree.

It is a separate, lighter guard from `adminMerge`: `adminMerge` bypasses a
protection without touching it, and `mergeGate` removes and restores the
protection itself.

---

## 17. `change` — change requests, and the ratchet that runs backwards

| | |
|---|---|
| Keys | `requester`, `implementor`, `requireForProduction`, `sdpTemplate`, `jiraIssueType`, `category` |
| Layer | **both**, all six |
| Schema | 7 (`crew_upgrade.SCHEMA_7_KEYS`) |
| Consumers | `commands/change.md`, `commands/promote.md`, `skills/crew-change/SKILL.md`, `hooks/scripts/crew_change.py` |

| Key | Type | Default | What it decides |
|---|---|---|---|
| `change.requester` | string or `null` | `null` | the template's `Requester name`; asked per request when null |
| `change.implementor` | string or `null` | `null` | the template's `Implementor of Change`, and answer 2 |
| `change.requireForProduction` | boolean | `false` | whether `/crew:promote production` gate 1 needs an approved change |
| `change.sdpTemplate` | string | `"Change Management Request"` | the ServiceDesk Plus template a change is filed against |
| `change.jiraIssueType` | string | `"Change"` | the Jira issue type a change is filed as |
| `change.category` | string or `null` | `null` | the template's `Category`; asked per request when null |

`requester` and `implementor` are facts about a person, and `sdpTemplate`,
`jiraIssueType` and `category` are facts about the desk that person files into
— which is why the whole block is in the machine-global template as well as the
repo one. A repo with its own category still overrides it; that is the ordinary
precedence rule, and it applies to five of the six keys.

### `requireForProduction` is the sixth, and it ratchets the other way round

It is in `crew_state.RATCHETED_KEYS` alongside `install.policy` and the six
`guards.*`, and it uses the same `effective_ratcheted` — the narrower of the
two layers wins. What is different is which value is narrower:

| Key | Tiers, least to most permissive |
|---|---|
| `install.policy` | `manual` < `ask` < `auto` |
| `guards.*` (four) | `block` < `ask` < `allow` |
| `guards.prod*` (two) | `none` < `read` < `full` |
| `change.requireForProduction` | `true` < `false` |

Requiring a change request takes a capability **away** from a promotion, so
`true` is the floor. `min(rank(repo), rank(global))` then means exactly what
the design asked for and nothing had to be added to say it: **a repo may turn
the requirement ON, and may never turn it off.** A machine-global `true` is not
defeated by a `false` in a repo somebody cloned; a repo's own `true` holds on a
machine that said nothing.

`sabotage.py`'s one-character `min` → `max` mutation covers this key along with
the other seven, which is the point of the table — a bespoke resolver for an
eighth key would have been an eighth thing that could be wrong on its own.

### The default is `false` and the floor is `true`, and they are not the same

This was the only ratcheted key in crew where "absent" and "unreadable" did
not resolve to the same value; `guards.roleWrites` (§18) is the second, added
in 0.19.92 for a mirror-image reason — there the FLOOR is the safe value and
the DEFAULT has to be the permissive one, because CLAUDE.md requires a new
blocking hook to ship disabled. Both halves below are load-bearing for this
key:

- **Absent, or an explicit `null`, resolves to `false`.** Schema 7 lands on
  every existing repo, and a mandatory migration that switched a production
  requirement on for everyone would be indefensible. A key nobody set is a
  requirement nobody asked for.
- **A value that is not a boolean resolves to `true`.** `"yes"`, the string
  `"false"`, `1`, a dict: crew cannot tell what was meant, and "could not tell"
  must not wear the label of "not required". The promotion stops and names the
  key — a refusal somebody notices within the minute, rather than a gate that
  quietly was not there.

`crew_guards.normalise_require_for_production` tests `isinstance(value, bool)`
rather than truthiness and rather than `isinstance(value, int)`. `True` and
`False` are `int` subclasses in Python, so an `int` check would have accepted
`0` as "not required" — the one direction this function must never fail in.

### What `true` actually does is prose

The key and the ratchet are code. What promote DOES about them is
`commands/promote.md`, and nothing enforces it: no hook fires on
`/crew:change`, and `promote-gate.sh` does not read `change.requireForProduction`
at all. That file's "What is enforced, and what is not" section says so by
name, in the same paragraph as the merge gate, deliberately — an unenforced
requirement that is described as enforced is worse than one honestly labelled.

### The ten-question gate is not prose

`hooks/scripts/crew_change.py` is, and it is the one part of this feature that
is mechanical. `/crew:change new` exits non-zero unless every one of questions
1–9 has an answer that is neither empty nor on `crew_change.PLACEHOLDERS`;
`close` does the same for question 10. There is no config key that relaxes it,
on purpose: the template's own rule is that missing information results in
denial, and a switch to turn that off would be a switch to file requests that
get denied.

---

## 18. `guards.roleWrites` — mechanical enforcement of a role's write scope

Added in crew 0.19.92. `agents/pm.md:49-53` says, in prose, "You do not write
application code, tests, docs..." — and on 2026-09-19 it did exactly that for
four hours, because prose is not enforcement and nothing in the harness read
that sentence. This key and the `PreToolUse` hook it configures are the
mechanical version: a `Write` or `Edit` from a role outside its declared
scope is refused before it reaches the filesystem, rather than relied on to
not happen.

| | |
|---|---|
| Key | `guards.roleWrites` |
| Values | `block` \| `report` \| `off`, least to most permissive |
| Default | `"off"` |
| Layer | both, **narrower wins** (same ratchet as every other `guards.*` key) |
| Read by | `hooks/scripts/role_write_guard.py`, via `hooks/scripts/role-write-guard.sh` / `.ps1` |
| Hook | `PreToolUse`, matcher `Write\|Edit`, registered once per shell flavour |

### What each value does

| Value | What crew does |
|---|---|
| `off` *(default)* | The hook exits before reading the policy table at all. Every write is allowed; nothing is logged. |
| `report` | Every write is allowed — including one outside the calling role's scope — and every decision is appended to `.crew/guard.log`, so an operator can see what `block` *would* have refused before turning it on. |
| `block` | A write outside the calling role's declared scope is refused (`PreToolUse` exit 2, with a message on stderr naming the role, the path and what that role may write); a write inside scope is allowed. Both are logged. |

### The default is `off`, and the floor is `block` — the second key in this file where those two differ (§17 was the first)

Every other `guards.*` key's default equals its floor: an absent key and a
malformed value both collapse to the narrowest tier. This key splits them on
purpose, and the split runs in the OPPOSITE direction from
`change.requireForProduction`'s:

- **Absent, or an explicit `null`, resolves to `off`.** CLAUDE.md's own rule
  for a new hook that can block a turn is that it "defaults to OFF in the
  menu" until a human turns it on. An absent key is every repo that has never
  set it — which, the day this shipped, is every repo that exists — and none
  of them may go from "no such hook" to "blocking Write calls" by upgrading
  the plugin alone.
- **A value that does not name `block`, `report` or `off` resolves to
  `block`, the floor.** A typo in a hand-edited config is not the same fact
  as "nobody opted in" — CLAUDE.md's own recurring bug is exactly this,
  an unknown collapsing into the safe-looking (here: permissive) value. So a
  malformed value fails toward MORE refusal, not less, the same direction
  every other guard's `normalise_*` function fails in.

`crew_guards.normalise_role_writes` is the one function that knows this
split; `role_writes_rank` ranks through it first, so `effective_ratcheted`'s
`min(...)` still means what it means everywhere else in this file: neither
layer can widen past what the other allows, and a repo cloned with
`guards.roleWrites: off` cannot override a machine-global `block`.

### A THIRD case, beside absent and malformed-VALUE: the file itself is unreadable

Reported and fixed 2026-09-19, one commit after this key first shipped.
`normalise_role_writes` above only ever sees a raw VALUE that `_dig` already
pulled out of a parsed config — it has no way to tell "the repo file never
set `guards.roleWrites`" apart from "the repo file could not be parsed at
all", because `crew_state.load_config` collapses BOTH to `{}` before
`normalise_role_writes` is ever called. That collapse is correct for
`install.policy` and the other six `guards.*` keys, which have always failed
OPEN on a bad config file (`read_global_config`'s own docstring: "a broken
global file must look exactly like no global file at all"). `roleWrites`
cannot inherit it: with no global override, replacing a repo's
`guards.roleWrites: block` config with invalid JSON — or with
`{"guards": 42}` — made `resolve_guard`'s effective answer `off` and let
`pm` write application code straight through, which is CLAUDE.md's own named
recurring bug landing on the one guard here that can least afford it.

`crew_config.layer_state(path)` gives `role_write_guard.py` the one extra
bit `load_config` throws away, classifying ONE config file as `"absent"`,
`"ok"` or `"corrupt"`. `"absent"` is every off-by-default repo or machine
that exists — stays `off`, unchanged. `"corrupt"` is present but
unreadable as this key needs: not valid JSON, not a JSON object, or a
`guards` key that IS PRESENT (`"guards" in parsed`, not
`parsed.get("guards") is not None`) and is not itself an object — which
covers an explicit `"guards": null` too, closing a gap the first draft of
this fix had (`.get()` cannot tell an explicit `null` from a key that was
never mentioned). A DIRECTORY at the config path is also `"corrupt"`, not
`"absent"` — `load_config`'s own `text is None` collapse could not tell
those two apart either, and the first draft of this fix inherited that
same blind spot from it. A DANGLING SYMLINK at the config path — pointing
at a target that has been moved or deleted — is `"corrupt"` too, found
one round later: presence is checked with `os.path.lexists`, not
`os.path.exists() or os.path.isdir()` (that second draft's own form),
because both of those FOLLOW a symlink to check its target, so a
dangling link answered `False` to both — the same "absent" a genuinely
unset key gets — even though something IS configured at that path and
cannot be read, which is exactly what `"corrupt"` means. `lexists` checks
the link itself, which also makes the directory case above redundant to
special-case separately; one check now covers a plain file, a directory,
and a dangling symlink alike.

`role_write_guard.py` calls `layer_state` on BOTH layers — the repo's
`.crew/config.json` and `GLOBAL_CONFIG_PATH` — and if EITHER is
`"corrupt"`, forces the effective policy to `block` UNCONDITIONALLY, not
only when the ratchet's own answer happens to be `off`. That second part
is load-bearing on its own: a corrupt repo config with a VALID,
non-`off` global policy (say `report`) resolves to `report` through the
ordinary ratchet — `report` never blocks anything — so a repo that used
to say `block` and got corrupted would silently downgrade to a policy
that never refuses, unless the corruption check runs regardless of what
the ratchet already computed. `layer_state` is a narrow, second read of
the config file(s), deliberately NOT wired into `load_config`,
`resolve_ratcheted` or any of the other eight ratcheted keys: widening the
collapse-detection to every guard was a bigger change than the one guard
that needed it, for behaviour the other seven have always had on purpose.
A malformed VALUE inside an otherwise-valid `guards` object (a non-string
`roleWrites`, or a string naming no known policy) is still
`normalise_role_writes`'s job alone, unchanged — this function's whole
purpose is the shape `normalise_role_writes` structurally cannot see.

### The policy table is in the hook script, not in this file

`hooks/scripts/role_write_guard.py` partitions every `agents/*.md` into three
buckets, decided by that file's own `tools:` frontmatter — not by its prose,
which is exactly the gap this hook exists to close:

- a role whose `tools:` line names neither `Write` nor `Edit` may not write
  anywhere, regardless of path (`explorer`, `researcher`, `reviewer`,
  `security` — the whole crew 1.0 roster; re-derive rather than trusting
  this list, and `tests/test_role_write_guard.py` does exactly that on every
  run);
- `pm` may write only under `.crew/**`, `TODO.md`, `.work/**` and
  `docs/diagrams/**`. crew 1.0 ships no `pm` agent; the branch stays for a
  repo-local agent of that name until the guard is retired (`TODO.md`);
  everyone else whose `tools:` line grants both Write and Edit is
  unrestricted by this hook — no shipped agent does, since 1.0.

`tests/test_role_write_guard.py::test_policy_table_matches_the_agent_files`
parses every agent file's `tools:` line and asserts the script's three sets
are exactly the partition that produces, so a `tools:` grant added or removed
with the table left alone fails a test rather than drifting silently.

### Scope is judged on the real path, not the one the tool call named

Reported and fixed 2026-09-19. `pm`'s scope check runs against the REAL,
filesystem-resolved path, never the lexical string a `Write`/`Edit` call
names: `.crew/link/app.py` matches `.crew/**` as text, but if `.crew/link`
is a symlink or a Windows junction pointing at `src/`, the write actually
lands in `src/app.py` once the tool opens it, regardless of what the
allowed-looking string said. `role_write_guard._resolve_real_target` walks
up to the deepest existing ancestor of the target (the file itself may not
exist yet — `Write` creates it) and resolves THAT, following any symlink or
junction earlier in the chain, before the scope comparison runs. Tested with
both link kinds actually created on disk — a POSIX symlink and a Windows
junction via `mklink /J`, the latter needing no elevated privileges — rather
than simulated, and SKIP-labelled wherever a given machine or user cannot
create one.

**A second round found the resolver itself had a gap, and it was the most
serious finding across this whole series.** `_resolve_real_target` started
by calling `os.path.abspath` on the raw path, and `abspath` collapses a
literal `..` LEXICALLY — before any symlink in the path is resolved.
`.crew/link/../app.py`, with `.crew/link` a symlink to `src/subdir`,
lexically normalised to `.crew/app.py`: a string that fnmatches
`.crew/**` and classified as in scope. The OS does not resolve that path
the same way — it follows `.crew/link` to `src/subdir` FIRST and applies
`..` against the RESOLVED parent afterward, landing in `src/app.py`. The
classification and the actual write disagreed, and the classification
was the permissive one: a symlink `pm` itself could stage under a path it
is trusted to write let it escape to anywhere that symlink's target's
parent could reach, just by adding `..` after it. Fixed by never calling
`abspath`/`normpath` on the raw path at all — `_resolve_real_target` now
walks the path one component at a time, resolving whatever exists on
disk as it goes, and a `..` pops the RESOLVED parent built up so far,
never a lexical one, mirroring how the kernel itself walks a path.
Verified with both a POSIX symlink and a Windows junction, driven end to
end through the real hook scripts, not simulated.

### `..` after a symlink is a platform-specific rule, not one algorithm

Reported and fixed 2026-09-19, one round after the resolve-then-pop fix
above shipped. That fix is correct on POSIX and **actively wrong on
Windows** — not merely imprecise. Win32's own path canonicaliser collapses
a literal `..` LEXICALLY, in the path string, before the filesystem or
reparse-point layer ever sees it: a junction sitting exactly where `..`
pops past it is never traversed at all. Resolve-then-pop computed the
opposite answer from real Windows in both directions:

- `src\link\..\new.py`, with `src\link` a junction to `.crew\subdir` (in
  scope): Windows collapses `src\link\..` to `src` before the junction is
  ever consulted, so the write really lands at `src\new.py` — out of
  scope, must block. Resolve-then-pop followed the junction first, landed
  in `.crew`, and wrongly allowed it.
- `.crew\link\..\app.py`, with `.crew\link` a junction to `src` (out of
  scope): Windows never consults the junction either, so the write really
  lands at `.crew\app.py` — in scope, must allow. Resolve-then-pop
  followed the junction to `src` first and wrongly blocked it.

A second, independent gap in the same walk: it split the raw path only on
`os.sep` (`\`), so a target spelled with forward slashes
(`C:/repo/.crew/link/new.py`, which tools commonly send even on Windows)
never broke into more than one component — the walk never walked
anything, and a junction anywhere in such a path went unresolved
regardless of the ordering question above.

`_resolve_real_target` now dispatches on `os.name`.
`_resolve_real_target_windows` splits on both `\` and `/`, collapses `..`
lexically first into a `..`-free path (mirroring Win32's own
canonicaliser), then walks that path resolving whatever junction or
symlink exists at each step. `_resolve_real_target_posix` is the original
resolve-then-pop walk from the paragraph above, unchanged — that ordering
is correct on a real POSIX host, where the kernel resolves each component,
including a symlink, DURING the walk and applies `..` AFTER, against the
resolved parent. Verified against both directions on a real Windows
junction, plus a real forward-slash target and a mixed-separator target,
all driven end to end through both `role-write-guard.sh` and
`role-write-guard.ps1`. The POSIX ordering has no equivalent always-running
direct unit test on this machine: `_resolve_real_target_posix`'s path
arithmetic assumes a POSIX root, a Windows drive letter breaks that
reconstruction, `os.path.lexists` never fires true against a real Windows
disk path built that way, and the walk silently degrades to pure lexical
popping — the very bug this function exists to prevent, reproduced by the
test harness rather than the code, so a "passing" test built that way
would prove nothing. Real POSIX coverage is instead an end-to-end test
correctly skipped when `os.name == "nt"`, live on any actual POSIX crew
installation.

### A different drive is proven outside the repo, not merely unverifiable

Reported and fixed 2026-09-19. `os.path.relpath` raises `ValueError` when
the two paths it compares are on different Windows drives, and that
exception used to reach the SAME catch-all as every other "cannot
resolve this" case, collapsing to `None` — "cannot classify", which `pm`
reads as out of scope and refuses. A different drive is not the same
fact as "cannot tell": it is PROVEN to be outside the repo root, the same
way a same-drive `../`-prefixed escape is. `_real_repo_relative` now
returns the sentinel `".."` for this one case specifically — the exact
string the outside-repo check already treats as a resolved escape — so a
`D:` target with the repo on `C:` gets `allow`, logged `outside-repo:
...`, instead of an incorrect refusal.

### A `\?\` extended-length path is never classified at all

Reported and fixed 2026-09-19. An earlier fix (not written up as its own
subsection here, since it shipped bundled with several others in the
same round — see `.crew/verify.json`'s history for that round) NORMALISED
Windows' `\?\` extended-length prefix away before classification:
`os.path.relpath` treats `\?\C:\repo\...` and `C:\repo` as different
mounts and raises, which read as "cannot classify" and incorrectly
refused a legitimate, in-scope write, so the fix stripped the prefix and
classified the bare remainder like any other path.

Codex round 5 found that normalising is itself unsound, not merely the
raising it replaced. `\?\` exists specifically so Win32 will SKIP its own
path normalisation for that one call — trailing dots and spaces are
preserved on disk, and a literal `..` component is never collapsed — so
stripping the prefix and classifying the remainder with this module's
ordinary (normalising) path handling answers a question about a
DIFFERENT path than the one Windows actually opens.
`\?\C:\repo\.crew.\app.py` (note the trailing dot on `.crew.`, a real,
distinct directory outside every scope `pm` is granted) stripped to
`C:\repo\.crew.\app.py`, which this module's own path handling then
further normalised to `C:\repo\.crew\app.py` — in scope, on the string
alone — while Windows itself opens a directory literally named `.crew.`,
never `.crew`. `pm` could reach any trailing-dot or trailing-space
sibling of a permitted directory this way, with the hook's own log
showing the innocuous, normalised `.crew/app.py` rather than what was
actually written.

No classifier built to be faithful to ordinary Windows path semantics
can also be faithful to a syntax whose entire purpose is bypassing those
semantics, so this module does not try. `_is_extended_length_prefix_path`
now short-circuits `main` before `_repo_relative`/`_real_repo_relative`/
`classify` ever run for such a path, and the decision is by role alone,
matching the same "scoped role" set the outermost exception handler
already treats as restricted: `pm` and every `_DENY_ROLES` member fail
CLOSED (`block`) unconditionally, regardless of `guards.roleWrites`'
configured policy; every other role, and a call with no `agent_type` at
all, allows — Claude Code itself never emits an extended-length path for
a `Write`/`Edit` call, so there is nothing here worth refusing for a role
this table already trusts with `Write`/`Edit` generally. Verified with a
real, on-disk `.crew.` directory (an ordinary, non-extended-length
`mkdir` call silently strips the trailing dot and collides with the
already-existing `.crew`, so even the test fixture needs the
extended-length form to create the directory it is testing against),
driven end to end through both `role-write-guard.sh` and
`role-write-guard.ps1`.

### A target outside the repo root entirely is not this guard's business

Reported and fixed 2026-09-19, a probe finding on the first commit — and
tightened by a second probe on the first fix, below. This guard's whole
purpose is the REPO's write scope, so `pm` writing to a harness-sanctioned
location OUTSIDE the repo — the scratchpad under
`AppData/Local/Temp/claude/<session>/scratchpad`, which every role including
`pm` is told to use — is not a scope violation at all; it was refused
anyway, because "outside every allowed prefix" and "outside the repo
entirely" collapsed to the same "not in scope" answer. Fixed with
`role_write_guard._is_outside_repo`, checked on the same REAL,
symlink/junction-resolved path (`_real_repo_relative`'s output) the in-scope
pattern match above already uses — a parent-relative escape (`os.path.
relpath` prefixes a result with `..` when the target lands outside `root`)
means the write is `allow`, logged `outside-repo: ...`.

**The first fix judged this on the LEXICAL path instead — what the tool
call SAID it was writing, never where the write actually lands — and a
second probe found that was the wrong side of the line.** `.crew/escape ->
/elsewhere`, a symlink STAGED inside `.crew/` (a prefix `pm` is trusted to
write) whose target is OUTSIDE the repo root entirely, is named lexically
INSIDE the repo, so the lexical version refused it — but the write itself
touches nothing under the repo at all, which is exactly the case this
exception exists for, symlink or not. There is no "but the tool call named
a path inside the repo" carve-out any more: the guard's business is where
the write actually lands. **The case that is still refused is a different
one** — `.crew/escape -> src/`, a symlink staged the same way but whose
target is ANOTHER IN-REPO directory outside `pm`'s permitted prefixes.
`_is_outside_repo` is `false` for `src/app.py` (still under the repo root),
so the ordinary `_pm_in_scope` pattern match above still runs and still
refuses it. `_DENY_ROLES` gets NONE of this exception either way: its
restriction is "no `Write`/`Edit` at all", not "confined to the repo", so an
outside-repo write is a different, stronger rule that role has no exception
from.

### What "unknown" means here

Two distinct unknowns reach this hook, and CLAUDE.md's rule applies to both:
an unknown must not wear the label of a decision, so both **allow**, but each
is named differently in `.crew/guard.log` rather than merged into one
unreadable "allow" row — `no-agent-type` (the hook fired with no `agent_type`
field at all — the main thread, or an older Claude Code build) and
`unknown-role:<value>` (an `agent_type` this table has no entry for: a
built-in agent, a different plugin's agent, or a typo).

**`agent_type`'s exact wire form for a plugin-scoped subagent was not
observed live against a real dispatched subagent in the session that built
this hook** — see the commit report for what was and was not verified. The
Claude Code hooks documentation describes the field only as "Agent name (for
example `"Explore"` or `"security-reviewer"`)"; this repo's own agents were
observed elsewhere in that session listed as `crew:pm`, `crew:analyst`, etc.
`role_write_guard._normalise_role` strips everything up to and including the
LAST `:` before matching, so both `"crew:pm"` and `"pm"` resolve to `"pm"`.
If the real wire form turns out to be neither, the hook still fails to the
allowing side: an unmatched value is `unknown-role`, logged and let through,
never a strand.

### Why this lives beside the other guards rather than as its own block

`install`, the six command/production guards and `change.requireForProduction`
already established the pattern this key needed: a value settable in both
layers, ratcheted to the narrower one, read through
`crew_config.py::resolve_guard` and nothing else. A bespoke
`resolve_role_writes` would have been a sixth mechanism for the rule §16's own
header states — "one mechanism can be wrong; two can disagree, and then only
one of them gets fixed." Adding `"roleWrites"` to `crew_guards.ALL_GUARD_NAMES`
and one branch to `crew_guards.guard_tiers` was the whole cost of reusing it.

### Without Python, a restricted role's write is always blocked

`role_write_guard.py` is what actually reads `guards.roleWrites` (both
layers, ratcheted) and pm's own path allowances. `role-write-guard.sh` /
`.ps1` are thin wrappers around it, and when no python interpreter can be
found or launched, neither wrapper falls back to re-implementing that
policy read itself — an earlier fallback tried to (parsing `roleWrites`
per layer with a bare regex, and pm's path allowances lexically), and
carried its own defects doing it: a dangling config symlink read as
absent rather than corrupt, bypassing fail-closed; the lexical pm-scope
check accepted `..` traversal and symlink escapes a real filesystem walk
would have caught; and the regex policy reader accepted truncated or
otherwise corrupt JSON as a clean `"off"`.

Rather than re-fix each of those, the no-python fallback in both flavours
now does less: it tells a restricted role (`explorer`, `researcher`,
`reviewer`, `security`, `pm`) from an unrestricted one — a floor that
needs no config to apply — and fails **closed** on the restricted side,
or on any role it cannot read at all (an unparseable payload, a non-string
`agent_type`, ...). It never reads `guards.roleWrites` and never applies
pm's path allowances. **Practically:** `off` and `report` only take
effect when python is available; without it, a restricted role's write is
refused regardless of what either config layer says, until python is
installed and the real classifier can run.

## 19. `verify.stopBudgetSeconds` and the Stop gate's per-rule record

`verifyGate` and `verify.stopBudgetSeconds` are the only two config keys this
gate reads (§10/§11 tables above). Everything else about how a Stop turn is
verified is NOT a config setting — it is per-rule fields inside
`.crew/verify.json` (`reach`, `env`, `requiresCleanTree`, `seconds`) and a
machine-local record the gate keeps for itself. Documented here rather than
invented as new config keys, because that is what it actually is.

**The single marker used to mean "everything passed."** Before crew 0.19.93,
`.crew/.verify-verified-at` (the sha baseline) and `.crew/.verify-gate.fingerprint`
(the unchanged-turn skip) were written ONLY when every matched rule ran clean.
A rule priced over `verify.stopBudgetSeconds` on its own — permanently, not as
a fluke of this turn's ordering — was deferred on EVERY Stop, so neither ever
advanced again: the baseline froze, and every OTHER rule re-matched and
re-ran from that same old commit, forever. That was the actual 7+ minute Stop
gate defect this section exists to explain the fix for.

**The per-rule record replaces "everything or nothing."**
`.crew/.verify-gate.record.json` (machine-local, gitignored, never tracked —
see the `.crew/*` ignore policy in root `CLAUDE.md`) now tracks status per
rule, keyed by a content hash of that rule's `paths`/`run` so it survives
`.crew/verify.json` being reordered:

- A rule that is PERMANENTLY over budget on its own no longer blocks the sha
  marker or the fingerprint. It is recorded as `"chronic"` instead, and the
  gate prints `NOT VERIFIED ON THIS TREE` for it on every subsequent Stop —
  whether or not that rule's own files changed this turn — until
  `/crew:verify --all` actually runs it clean.
- A rule that would fit `verify.stopBudgetSeconds` alone but lost to this
  turn's contention (another rule's cost crowded it out) is "acute", not
  chronic, and still blocks the sha marker exactly as before this feature —
  that case really is unverified for THIS commit, not permanently
  unverifiable, and freezing the baseline is the correct answer for it.
- **Pricing**. A rule's cost is its declared `seconds`, or the
  smaller of that and a measurement of it on this machine
  (`.crew/.verify-gate.timings.json`), never the larger: a stale
  over-statement stops reading as chronic once one clean run measures it.
- **The tree-pass cache**. At Stop, a command that passed is credited,
  not re-run, while the tree is byte-for-byte the tree it passed on
  (`.crew/.verify-gate.passes.json`, keyed on HEAD, every ref,
  `.crew/verify.json`, `.crew/config.json` and every tracked and untracked
  path's bytes, type and mode). A rule all of whose commands are credited
  costs nothing, so an acute deferral on an unchanged tree runs what it has
  not run yet instead of the same rules again. `/crew:verify --all` never
  credits; it runs everything and saves its passes. If the tree changes
  during a run that credited something, the credits are withdrawn and the
  run does not count as verified. Any edit anywhere, or a fetch, empties it; ignored files (`node_modules`, a
  venv) are not in the key, as they are not in the fingerprint. Set
  `CREW_VERIFY_FRESH=1` in the environment to run everything for one run.
- A rule declaring `"reach"` other than `"local"` is recorded as
  `"reach_declared"` and never runs on Stop — only under `/crew:verify --all`
  and the merge gate. Declaring `"reach": "local"` runs on Stop with NO
  inspection at all; that is the human saying so, and the gate takes the word
  for it.
- A rule naming no `"reach"` is classified by `verify_record.scan_reach`,
  which as of crew 0.19.9x (Codex round 6) STOPS MODELLING SHELL. Rounds 4-5
  each read further INTO a command's shell syntax to decide whether a
  wrapper it named was safe — follow the script, split it into the segments
  a shell would run separately, open a `$( ... )` substitution's own
  contents — and each round of review found a shape that defeated whatever
  the previous round had just taught the scanner to read: subshell
  parentheses glued to a path, `-n` granted by mere PRESENCE anywhere in the
  token list rather than its actual position, a command hidden inside a
  substitution the segmenter never knew to open. Five rounds of "read one
  layer deeper" is not a fixable bug; it is the wrong approach. So this scan
  no longer parses shell at all:
  - if the command string contains ANY shell metacharacter — anything that
    could combine, substitute, quote, glob, redirect or comment:
    `` ( ) $ ; & | < > ` " ' \ { } * ? [ ] ~ # ! ``, a newline, or a tab — it is
    deferred unconditionally as `"reach_syntax"`, reason `shell syntax in an
    undeclared rule — declare "reach": "local" (or network/host) to run it
    on Stop`. No exception, not even `2>&1` or a trailing `#` comment: a
    character on the list means "declare reach", full stop.
  - only once nothing on that list is present does whitespace-only
    splitting become safe (there is no quoting left to get wrong). A reach
    verb (`ssm`, `ssh`, `curl`, `aws`, `az`, `gh`, `psql`, `mysql`) anywhere
    → `"reach_undeclared"`, reason `remote verb <v>`.
  - otherwise, if the first token is a recognised interpreter
    (`bash`/`sh`/`dash`/`zsh`/`pwsh`/`powershell`/`python`/`python3`/`py`/
    `node`/`ruby`/`perl`): `-n` grants the parse-only exemption ONLY when it
    is EXACTLY the second token and there is EXACTLY ONE token after it
    (`bash -n a.sh` is parse-only; `bash a.sh -n` and `bash -n a.sh b.sh`
    are not); `-m` as the second token names a MODULE, never a file, and is
    always local (`python3 -m pytest x -q` is local); `-c`/`-Command`/
    `-File` as the second token name inline code or a script argument and
    always defer as `"reach_wrapper"`; any other token from the second
    position onward that resolves to an existing file under the repo also
    defers as `"reach_wrapper"`.
  - otherwise (not a recognised interpreter): any token at all that
    resolves to an existing file under the repo defers as `"reach_wrapper"`.
  - none of the above: runs undeclared.
  - `default`/`always` commands in `.crew/verify.json` go through this SAME
    classification on Stop — they have no `"reach"` field of their own to
    declare, so a deferred command named there is excluded from the
    fallback exactly like an undeclared rule would be, never reintroduced
    through it.
- `/crew:verify --stamp-reach` (`hooks/scripts/verify_reach.py`, L-0562)
  declares `reach` on undeclared rules from this same classification:
  `local` where the gate already runs the rule, `network` where it defers
  it for a remote verb. Syntax- and wrapper-deferred rules are left for a
  person (`--set N=...`). `reach` is hashed into the rule key, so it also
  moves each stamped rule's timings-cache and record entries to the new key;
  applying it changes neither what Stop runs nor what it costs in the
  checkout that ran it. The caches are machine-local and gitignored, so
  another checkout or worktree that pulls the stamped map prices those
  rules afresh: run `/crew:verify --all` once there.
- A rule declaring `"requiresCleanTree": true` is recorded as
  `"clean_tree_required"` and is never run on Stop either, for the same
  reason: the working tree is dirty by definition during ordinary work, so a
  rule that refuses on a dirty tree is a permanent red there and a real
  check only under `--all` against a clean checkout.
- A rule declaring `"coveredBy": "<id>"` (L-0572) names another rule's
  `"id"` as running a superset of its checks. Under `--all` or `--ci` only, its
  commands run last and are recorded as `covered` - clean, but never cached
  as a timing - when every command of that rule exited 0 earlier in the same
  run, a whole-tree snapshot taken before the first command still matches,
  and `PYTEST_ADDOPTS` is empty. Anything else runs it: a superset that
  failed, exited 77 or was killed, did not match, or changed the tree; a
  command `always` or an undeclared rule also names; an invalid declaration
  (unknown or duplicate id, itself, a chain, a superset with no runnable
  command, a different `env`), which is ignored with a named notice. Stop
  mode never credits. This repo declares `rules[9]` (the full crew suite)
  `crew-suite` and its pytest-only subsets `coveredBy` it.
- A rule whose command exits 77 is recorded as `"skipped"` — the
  `_verify/smoke.sh` and GNU automake convention for "skipped, environment
  absent". Not a pass, not a fail: it does not fail the Stop turn and it is
  not recorded as verified either.

**`--price` writes `seconds` into `.crew/verify.json` itself, so it is an
operator command, never something a hook runs.** `.crew/verify.json` is
TRACKED in this repo (`git ls-files .crew/` lists it, per the ignore policy
in root `CLAUDE.md`), so an automatic `--price` would dirty a committed file
on every Stop. `verify-gate.sh --price [path] [--force]` /
`verify-gate.ps1 -Price [-PriceTarget path] [-PriceForce]` is reachable only
by typing the flag; the Stop hook (`hooks.json`) never passes it.

**`--ci` / `-Ci` is the gate as a pull request's CI job (crew 1.0.232), and
it is not a spelling of `--all`.** Its scope is the whole map with no budget
and no fingerprint skip, over TRACKED files only (`git ls-files`, staged
deletions and renames included): a CI workspace's untracked files (a crew
checkout, a `.venv`, build output) are not the change and do not trip
`"unmapped": "fail"`. Its reach filter is Stop's: a `"reach_declared"` rule,
an undeclared one `scan_reach` will not clear, and an `always`/`default`
command it will not clear are named and not run, because a CI runner has
none of the credentials or network paths they were written against. One
`verify-gate --ci:` line counts them; they do not fail the run, and they run
only under `--all`. A `"requiresCleanTree"` rule RUNS, because a CI checkout
is the clean tree it was sent to. A failing command, a command exiting 77
(`a skip is not a pass in CI`) and any deferral exit 2.

Under `--ci`, every path that would end having checked nothing exits 2 with
a named `verify-gate --ci:` reason, where Stop exits 0: `verifyGate: false`,
no map and no `_verify/smoke.sh`, a project directory the gate cannot enter,
no tracked files (not a git work tree, or git refused the checkout), zero
commands to run (every matched rule reach-excluded, nothing matched and
`always`/`default` added nothing, or every command blank), a lock held by
another gate run, and the `.ps1` run off Windows (use the `.sh` there). The
Stop-only stand-downs do not apply: `--ci` reads no stdin (so a
`stop_hook_active` payload cannot end it), the emergency lane does not stand
it down (an `.crew/incident.json` is named and the rules run), and the
`.deploy-in-flight` check is skipped without touching the marker.

`--ci` never writes `.crew/.verify-verified-at` or the fingerprint, even on a
full pass, and the pass line says why. It still writes the gate's other
machine-local files: the per-rule record (synced with `all` false), and the
timings and tree-pass caches as on any run. Arguments are checked strictly
in every mode: the `.sh` accepts only `--all` and `--ci` (in any position)
and `--price` (first only), so `-ci`, `--CI` or `--ci=1` is a usage error rather than a
Stop run in CI; the `.ps1` refuses an argument PowerShell's binder would
have passed through (`-Bogus`, `--ci=1`, a bare word). `--ci` with `--all`
or `--price` (`-Ci` with `-All` or `-Price`) is a usage error too. Run it from the job's checkout:
`bash <crew>/hooks/scripts/verify-gate.sh --ci`.

**The map comes from the PR head, so a PR can weaken its own gate.** `--ci`
reads `.crew/verify.json` from the checkout it is verifying: a PR that drops
a rule, narrows its `paths` or declares it `network` changes what its own
job checks. (`verifyGate: false` cannot do it: `--ci` fails on that.) With no
map, a passing `_verify/smoke.sh` passes, unscoped and unfiltered as on Stop.
Review a `.crew/verify.json` change as code, and do not treat a green `--ci`
job as evidence about a map the same PR rewrote.

**Environment pinning is unconditional, not a config key either.** Every rule
command the gate runs gets `ENV`, `AWS_PROFILE`, `AWS_DEFAULT_PROFILE`, `AWS_DEFAULT_REGION`,
`AWS_REGION`, `AZURE_SUBSCRIPTION_ID`, `ARM_SUBSCRIPTION_ID`, `KUBECONFIG`,
`TF_WORKSPACE` and `TF_VAR_environment` unset, unless that rule's own `"env"` object
declares values for them — in which case exactly those are set instead, and
the gate prints what it pinned. There is no `verify.envPinning: false` escape
hatch; a rule that genuinely needs a variable declares it, in the map, next
to the command that needs it.

**Unknown never resolves to the permissive value, in any of this.** A
`.crew/.verify-gate.record.json` that cannot be read is treated as empty —
losing only history, never fabricating a clean rule that never ran (see
`verify_record.py`'s module docstring). A `.crew/config.json` that cannot be
read leaves `verify.stopBudgetSeconds` at its compiled default (60) rather
than removing the budget. See `commands/verify.md` for the full mechanism and
`hooks/scripts/verify_record.py` / `verify_price.py` for the code.

**Limitation (1.0): the gate does not reap background processes a rule
leaves behind; a rule must not background work — a rule that does can keep
running (and writing) after the gate returns.** Per-rule process-group
tracking and kill-on-signal shipped, then was descoped from crew 1.0 after
five consecutive review rounds each found the previous round's fix one case
short (disk fill by an orphan writer, escape on gate kill, an unlocked
registry, pid/pgid reuse in both p- and g-mode, a session-id proof that is
not ownership, a leader-exited group) — see CHANGELOG 1.0.21 and TODO.md.
Rule output is still captured through a temp file rather than a pipe, so a
backgrounded grandchild cannot wedge the gate's own read of that rule's
output (see `verify-gate.sh`'s rule-loop comment) — what is gone is the
gate reaching in afterward to kill what a rule left running.

---

## 20. `autopilot` — `/crew:autopilot`, off until `plan`

`/crew:autopilot` (T-0004, since 1.0.41) drives one ticket through the
lifecycle phases `crew_autopilot.next_phase` names from disk, following each
phase command's procedure in-session, and stops wherever a person is needed.
`crew_ticket.py assign` (T-0019; the `/crew:autopilot assign` route lands with
L-0611) mints one ticket from a staged direction, with no key of its own, and
that ticket is approved under `autopilot.approval` like any other. Its block is **repo only**: absent from `default_global_config()`, so
`filter_global` prunes it from the machine file. Whether one checkout may be
driven is a fact about that checkout.

| Key | Default | Read by | What an unexpected value does |
|---|---|---|---|
| `autopilot.mode` | `"off"` | `crew_autopilot.settings`, through `crew_config.resolve_config` | Only the exact string `"plan"` arms it. `"Plan"`, `"plan "`, `true`, `"on"`, `null` — anything else — reads as `off`, and `settings` prints which value it saw. A typo must not arm a driver. |
| `autopilot.maxPhases` | `12` | `crew_autopilot.settings`; `next_phase` stops once the session's phase count reaches it | Anything but a positive integer (`0`, `-3`, `"12"`, `true`, `2.5`) reads as `12`, with a warning. |
| `autopilot.deploy` | `"none"` | `crew_autopilot.settings`; `crew_autopilot.deploy_allowed` (T-0072) | Only the exact strings `"none"`, `"nonprod"` and `"all"` are read as themselves. `"All"`, `"all "`, `"prod"`, `true`, `1`, `null` — anything else — read as `none`, with a warning naming the value. Set only in the machine file, it takes effect nowhere (repo only). |
| `autopilot.approval` | `"risk"` | `crew_autopilot.approval_policy` (T-0010): whether `crew_autopilot.py approve` may record the plan approval itself | Anything but exactly `human`, `self` or `risk` (`"Self"`, `true`, `null`) reads as `human`, with a warning. `human` always stops. A `.crew/config.json` that exists but is not a readable JSON object, or an `autopilot` value that is not an object, reads as `unknown` (could not tell): `approve` refuses, and `mode` reads `off`. An absent file or block reads the default. |
| `autopilot.questions` | `"risk"` | `crew_autopilot.question_policy` (T-0010): whether autopilot takes the researched recommendation for an open question | Same: anything else reads as `human`, which always stops; an unreadable config or non-object block reads as `unknown`, and a question stops. |

**Which file.** `.crew/config.json`, through `resolve_config` — the file
`crew_ticket.cli_approval_allowed` already reads, so the approval policy T-0010
adds reads the same one. `/crew:migrate` writes `.crew/crew.json`, which crew
does not read for this key; an `autopilot` block found only there is reported
by `settings` ("move it to .crew/config.json") rather than read as `off` with
no word. `settings` prints `mode`, `maxPhases` and `deploy` on its first text
line, `approval` and `questions` on its second, and all five with `--json`.

**The two policies (T-0010).** `autopilot.approval` decides the
plan-approval phase: `human` always stops for `/crew:approve`; `self` lets
`crew_autopilot.py approve --root . --ticket <id>` record the approval at any
risk; `risk` does so only when the spec's header line says `risk: low` (an
absent or unparseable risk is `high`, never `low`). At **every** setting the
approval also needs `scope.allowCliApproval` exactly `true`, autopilot armed,
and a readable review ledger. A NEEDS_REPLAN ledger does not refuse: approving
a different successor plan is the only way out of it, and the ledger still
refuses a plan approved before (`approve` then exits 3 and says so). The
receipt says `approved_via:
"autopilot"` and `approved_by: "autopilot:<policy>"`, and `crew_ticket.accepted`
re-asks the policy on every read: turn the policy to `human`, set
`allowCliApproval` false, or edit the spec, and the scope guard and the
completion audit stop honouring it. The scope guard allows exactly the bare
command `python3 [-B] <path>/crew_autopilot.py approve [--root .] --ticket <ID>`
and only while the policy says yes; `crew_ticket.py approve` stays refused.
`autopilot.questions` decides an open question: autopilot researches it
(crew:explorer for the repo, crew:researcher outside), writes
`.work/tickets/<id>/questions.md` (2-4 options per question, the
recommendation first, each with a `Cost:` line, and a `Research:` line), and
`crew_autopilot.py questions-check` validates it and says `take` or `stop`.
`self` takes the recommendation, `risk` only on `risk: low`, `human` stops; a
`taken: Option <id> by autopilot (<policy>)` line records each one under the
policy that took it. The check refuses a `taken:` line naming a policy that
never takes (only `self` or `risk` does), and any `taken:` line while the
policy in force says `stop`; switching between `self` and `risk` later does
not void an earlier honest record. Every
self-approval and every taken answer is reported by name. Autopilot approves one
ticket at a time: a group approval and its `/crew:approve --confirm` stay the
owner's, and `crew_ticket.approve` refuses an `autopilot` approval carrying a
group's hashes.

**The one writer.** `crew_autopilot.py` is read-only except `approve`, and
only when `autopilot.approval` allows it (a ticket `assign` mints is written by
`crew_ticket.py assign` and `mint`, not by this script). `approve` writes exactly what
`crew_ticket.approve` writes for every approval route, all under
`<git-common-dir>/crew/`: `approval.json`; the scope ramp's
`scope-tickets.json` on a ticket's first approval; and, when the review ledger
is NEEDS_REPLAN and the plan is a distinct successor, the ledger itself, moved
NEEDS_REPLAN -> IN_REVIEW (the successor continuation, a fresh review budget).
`next`, `resume`, `settings`, `stops`, `route`, `status`, `questions-check` and
T-0072's `deploy-allowed` write nothing, and T-0018's `route` and `status` read no policy of their own:
`status`'s lines, the approve and open-questions reasons included, read the
same under every setting, and at the approve phase it names
`/crew:approve <id>`; `next` is what names the policy's route. The one policy
effect `status` shows is `crew_ticket.accepted`'s: an `autopilot` receipt
stands only while the policy still allows it.

**What arming it does not change.** Review acceptance and brainstorm always
stop for a person, at every setting — accepting review FINDINGS with any
BLOCK (`review_ledger.py --accept`) is never automatic; the one exception is
not a setting either: a final 0-BLOCK round from a Codex or Kimi reviewer (never a
same-family Claude-fallback round, never a verdict recovered from stray lines) is accepted by the ledger-guarded
`review_ledger.py --auto-accept` (L-0510), and no config key changes that; every
`AUTONOMOUS_STOPS` id (§5) binds it; no hook, review budget or completion
audit is relaxed. `pm.authority: autonomous` from 0.20 arms nothing —
`/crew:migrate` keeps it under `retired.pm` and its note points here.

**Production without asking (T-0072).** `autopilot.deploy` says where a deploy
may run with no person asked: `none` (the default) nowhere, `nonprod` in a
`nonProd` environment only, `all` in production too. Production needs **two
opt-ins**: `autopilot.deploy: all` in the repo's `.crew/config.json`, **and**
`environments.prodUnattended: true` in **both** config layers (§16, the
ratchet: a repo cannot grant it alone, and neither can the machine file). It
also needs `guards.cloudGuard` to resolve to a plain `block`, so T-0009's guard
is armed to enforce the dispatch. `crew_autopilot.deploy_allowed(root, env,
class)` answers, first match wins:

| Condition | Verdict |
|---|---|
| the checkout cannot be found (the lookup raised), `.crew/incident.json` exists in any form, or its path cannot be checked for any reason | `refuse` — an emergency may be active |
| the environment name is blank, not a string, or not printable | `ask` — could not tell which environment |
| the class is not exactly `nonProd` or `prod` (T-0005's classes; `unknown` included) | `ask` — crew could not classify it |
| either config layer could not be checked (its path cannot be stat'ed for any reason but a missing file), or is present and not ok (unreadable, not JSON, a bad `guards` or `environments` block) | `ask` — could not read that layer |
| `autopilot.mode` is not `plan`, or `autopilot.deploy` is `none` | `ask` |
| `nonProd`, with `nonprod` or `all` | `allow` |
| `prod`, with `nonprod` | `ask` |
| `prod`, with `all`, and `prodUnattended` not `true` in both layers | `ask`, naming the layer |
| `prod`, with `all`, and `guards.cloudGuard` not a plain `block` (a fail-closed `block` with a note included) | `ask` |
| `prod`, with `all`, otherwise | `allow` |

The checkout root is resolved **once** per answer, and that one root is what
the incident check, both layers and every row judge; the result names it
(`root`). Every path is probed for present, absent or could-not-tell, and
could-not-tell never reads as absent: it refuses for the incident file and
asks for a config layer. A crash inside the decision asks, and so does one
building its report or printing a value it was handed; the CLI prints
`verdict=ask` even for a crash it cannot describe. The incident check runs
before anything that can fail to import, so a crash never turns an
emergency's `refuse` into `ask`. Every production decision — `allow`, `ask`
or `refuse` — carries a report line naming the environment
(`unattended production: <env> <verdict> - <reason>`). The CLI is
`crew_autopilot.py deploy-allowed --root . --env <name> --class <class>
[--json]`: the verdict line (or one line of JSON) on stdout, the report on
stderr, exit 0. Each is one line, the verdict first: a value that is not plain
printable text (a class or environment holding whitespace included) prints as
its repr, so no input can add a line a consumer would read as a second verdict.

**Inert until T-0045.** Nothing in this crew version dispatches a deploy, so
`settings` warns whenever `autopilot.deploy` is not `none`. The consumer
(T-0045) calls `deploy_allowed` immediately before each dispatch, passes the
class from T-0005's classifier, proceeds only on the exact verdict `allow`
(anything else — `ask`, `refuse`, no answer, a non-zero exit — stops), and
persists every report. `allow` is necessary, not sufficient: T-0009's hook,
promote-gate (`requireHuman`, the post-deploy proof) and every other gate
still decide.

---

## 21. `route` — plain-text lifecycle routing, off until `true`

`route.enabled` (T-0023, since 1.0.46) lets a short plain-text prompt reach a
lifecycle command. When it is on, crew's UserPromptSubmit context hook
(`crew_context.route_item`) calls `crew_route.decide` on the prompt and, unless
the answer is `none`, puts one line FIRST in the turn's context: the
`/crew:<command> <ticket>` whose procedure Claude should run through the Skill
tool, or a request to ask the user which ticket. The hook runs nothing and
blocks nothing; the command's own checks still decide. The table of phrases,
the three outcomes and what never routes are in the plugin README's
"Plain-text lifecycle" section; `crew_route.PHRASES` is the single definition.

| Key | Default | Read by | What an unexpected value does |
|---|---|---|---|
| `route.enabled` | `false` | `crew_route.settings`, through `crew_config.resolve_config` | Only the JSON value `true` arms it. `"true"`, `1`, `"yes"`, `"on"` — anything else — reads as off, and `settings` names the value it saw. A `route` that is not an object, in either file, is ignored by the merge and reported. |

**Which file.** `.crew/config.json` over the machine-global
`~/.claude/crew/config.json` over the default — `resolve_config`'s ordinary
precedence. The context hook's own `memory.inject` switch is read from
`.crew/crew.json` first (`crew_context.load_crew_config`), but this key is not:
a `route` block found only in `.crew/crew.json` is reported by
`python3 crew_route.py settings --root .` ("move it to .crew/config.json")
rather than read as off with no word.

**A machine-wide `true` reaches only repos whose file leaves the key out.**
`/crew:init` writes the whole template, which carries `"route": {"enabled":
false}`, and the repo layer wins. In a repo set up that way, delete the key
from `.crew/config.json` or set it `true` there.

**What arming it does not change.** Routing never approves: no phrase routes
to `/crew:approve`, a `continue` whose next step is approval asks instead, and
`commands/approve.md` sets `disable-model-invocation: true` besides. Under
`--harness codex` no line is emitted, because the Skill tool it names does not
exist there. With `memory.inject: false` the hook emits nothing, route line
included.
