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
| repo | `.crew/config.json` in the repository root | `crew_state.load_config` |
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

**And seven exceptions that are not visible above, because they do not go
through this function at all: `install.policy` (§15) and the six `guards.*`
(§16).**
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

**Measured, not argued.** `leaf_paths(default_global_config())` yields **59**
leaves. `leaf_paths(default_config())` yields **102**, so **43** are repo-only.
For all 102, `filter_global` and `plan_global_write` agree on whether the path is
settable. (45 / 86 before schema 6 added the six `guards.*`, the two
`github.mergeGate` keys and the repo-only `production.databases` /
`production.hosts`, and 44 / 85 before schema 5 added `install.policy`.
All six of schema 6's keys are settable in both layers, so they moved the first
two numbers and not the third — the same shape `install.policy` had. Re-measure
rather than trusting these: they are a fact about one commit.)

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

| | |
|---|---|
| Type | string enum |
| Values | `report-only` (default), `act`, `autonomous` |
| Layer | global-settable |
| Consumer | `crew_state.normalise_authority` / `authority_rank`; `pm_brief.py`; `crew_config.py` |

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
`pm_brief.py`, which read `knowledge["graph"]` — the *state* dict
`read_knowledge` builds, not the config block — and `crew_upgrade.py`,
which drops the removed `obsidian` sub-block.

The `bitbucket` block is read by no crew **code** — verified the same way,
grepping for `get("bitbucket")` and `["bitbucket"]` across every tracked file,
whose only hits are the two places in `crew_config.py` writing the defaults in.
Its consumer is prose: `commands/promote.md` (§8), with a committed regression
test in `tests/test_promote_merge_gate.py`. `preset` is on this list because
promote names it only to say it binds to nothing.

`jira.project` is the one on this list that most looks like it should work.
`/crew:jira-sync` gates on `tracker == "jira"` (`commands/jira-sync.md`) and
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
| `obsidian.columns.*` (five keys) | `commands/obsidian-sync.md`, which instructs: "Read the names from `obsidian.columns` rather than hardcoding them" |
| `sdp.portal`, `sdp.noteVisibility`, `sdp.closeOnDone` | `commands/sdp-sync.md` |
| `secondOpinion.provider`, `.sendsCode`, `.keyEnv` | `agents/planner.md`, `commands/plan.md`, `skills/crew-providers/SKILL.md` |
| `docs.reportTheme` | `skills/crew-house-style/SKILL.md`, with a committed regression test in `tests/test_docs_routing.py` that binds it to the findings-report genre |
| `bitbucket.mergeGate.enabled`, `.branch` | `commands/promote.md`, `## The Bitbucket merge gate` — the flags it passes to `skills/bitbucket/scripts/merge_gate.sh`, with a committed regression test in `tests/test_promote_merge_gate.py`. `.preset` is **not** here: see §8 and §9 |
| `pm.maxDispatches` | `agents/pm.md` ("Stop after `pm.maxDispatches` roles in one pass"). Also coerced to `int` at `crew_state.py` |

---

## 10. Global-settable keys — all 59

Settable in **either** layer; repo wins — **except `install.policy`, the six
`guards.*` and `change.requireForProduction`, where the narrower of the two
layers wins instead** (§15, §16, §17). For the first seven "narrower" means a
smaller capability; for `change.requireForProduction` the narrower value is
`true`, so a repo may turn that one **on** and never off — §17.
`production.databases` and `production.hosts` are deliberately **not** here:
they are repo-only, and §16 says why. Defaults are identical in `default_config()` and
`default_global_config()` — verified by comparison.

| Key | Type | Default |
|---|---|---|
| `qa.provider` | `auto` \| `claude` \| `codex` \| `copilot` | `"auto"` |
| `qa.order` | list (a leaf; replaced wholesale) | `["codex", "copilot", "claude"]` |
| `qa.fallback` | string | `"claude-sonnet-5"` |
| `qa.codex.model` | string or `null` | `null` |
| `qa.codex.reasoningEffort` | string or `null` | `null` |
| `qa.copilot.model` | string or `null` | `null` |
| `qa.roles` | open table (empty dict = leaf) | `{}` |
| `dev.provider` | `claude` \| `codex` \| `copilot` | `"claude"` |
| `dev.fallback` | string | `"claude-sonnet-5"` |
| `dev.codex.model` | string or `null` | `null` |
| `dev.codex.reasoningEffort` | string or `null` | `null` |
| `dev.copilot.model` | string or `null` | `null` |
| `dev.roles` | open table | `{}` |
| `worktree.root` | path or `null` | `null` |
| `secondOpinion.provider` | string | `"none"` |
| `secondOpinion.mode` | string | `"cli"` |
| `secondOpinion.model` | string or `null` | `null` |
| `secondOpinion.keyEnv` | string | `"GEMINI_API_KEY"` |
| `secondOpinion.sendsCode` | boolean | `false` |
| `memory.mode` | string | `"repo"` |
| `memory.vaultPath` | path or `null` | `null` |
| `notify.provider` | string | `"none"` |
| `notify.urlEnv` | string or `null` | `null` |
| `notify.tokenEnv` | string or `null` | `null` |
| `notify.chatId` | string or `null` | `null` |
| `notify.events` | list (a leaf) | `["phase", "gate", "waiting"]` |
| `install.policy` | `manual` \| `ask` \| `auto` (narrower layer wins, §15) | `"manual"` |
| `pm.enabled` | boolean | `true` |
| `pm.mode` | string | `"adaptive"` |
| `pm.quietLines` | integer | `8` |
| `pm.maxLines` | integer | `40` |
| `pm.authority` | see §5 | `"report-only"` |
| `pm.ticketGranularity` | see §6 | `"system"` |
| `pm.maxDispatches` | integer | `3` |
| `context.autoClear.enabled` | boolean, see §14 | `true` |
| `context.autoClear.method` | string, see §14 | `"auto"` |
| `context.autoClear.windowTitle` | string or `null`, see §14 | `null` |
| `context.autoClear.command` | string | `"/clear"` |
| `context.autoClear.delaySeconds` | integer | `3` |
| `context.autoClear.minHandoffLines` | integer | `5` |
| `docs.theme` | string or `null`, see §7 | `null` |
| `docs.reportTheme` | string or `null`, see §7 | `null` |
| `bitbucket.mergeGate.enabled` | boolean, see §8 | `false` |
| `bitbucket.mergeGate.branch` | string or `null`, see §8 | `null` |
| `bitbucket.mergeGate.preset` | string, see §8 | `"standard"` |
| `github.mergeGate.enabled` | boolean, see §8 | `false` |
| `github.mergeGate.branch` | string or `null`, see §8 | `null` |
| `guards.terraformApply` | `block` \| `ask` \| `allow` (narrower layer wins, §16) | `"block"` |
| `guards.forcePush` | `block` \| `ask` \| `allow` (narrower layer wins, §16) | `"block"` |
| `guards.adminMerge` | `block` \| `ask` \| `allow` (narrower layer wins, §16) | `"block"` |
| `guards.mergeGate` | `block` \| `ask` \| `allow` (narrower layer wins, §16) | `"block"` |
| `guards.prodDatabase` | `none` \| `read` \| `full` (narrower layer wins, §16) | `"none"` |
| `guards.prodServer` | `none` \| `read` \| `full` (narrower layer wins, §16) | `"none"` |
| `change.requester` | string or `null`, see §17 | `null` |
| `change.implementor` | string or `null`, see §17 | `null` |
| `change.requireForProduction` | boolean (narrower layer wins, and `true` is the narrower one, §17) | `false` |
| `change.sdpTemplate` | string, see §17 | `"Change Management Request"` |
| `change.jiraIssueType` | string, see §17 | `"Change"` |
| `change.category` | string or `null`, see §17 | `null` |

`crew_state.QA_PROVIDERS` and `DEV_PROVIDERS` are both
`["claude", "codex", "copilot"]` (dumped by execution). `qa.provider`
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

## 11. Repo-only keys — all 41

Refused in the global file by `plan_global_write`, and pruned out of it by
`filter_global` if some other tool wrote one. Each is a fact about one
repository or one checkout.

| Key | Type | Default | Consumer |
|---|---|---|---|
| `schema` | integer | `7` | see §4 |
| `tier` | integer | `0` | `crew_state.collect` |
| `roles` | list (a leaf) | `["explorer", "qa-reviewer"]` | `crew_state.collect` |
| `tracker` | string | `"files"` | `crew_state.py`, `pm_brief.py`, `commands/ticket.md` |
| `jira.project` | string or `null` | `null` | **no consumer found**, §9 |
| `jira.cloudId` | string or `null` | `null` | written by `commands/jira-sync.md`; **read by nothing**, §9 |
| `sdp.portal` | string or `null` | `null` | prose, §9 |
| `sdp.noteVisibility` | string | `"private"` | prose, §9 |
| `sdp.closeOnDone` | boolean | `false` | prose, §9 |
| `obsidian.vaultPath` | path or `null` | `null` | `commands/obsidian-sync.md` |
| `obsidian.boardDir` | path or `null` | `null` | `commands/obsidian-sync.md` |
| `obsidian.board` | filename | `"Board.md"` | `commands/obsidian-sync.md` |
| `obsidian.columns.backlog` | string | `"Backlog"` | prose, §9 |
| `obsidian.columns.ready` | string | `"Ready"` | prose, §9 |
| `obsidian.columns.inProgress` | string | `"In Progress"` | prose, §9 |
| `obsidian.columns.review` | string | `"Review"` | prose, §9 |
| `obsidian.columns.done` | string | `"Done"` | prose, §9 |
| `verifyGate` | boolean | `true` | `hooks/scripts/verify-gate.sh` |
| `context.enabled` | boolean | `true` | `hooks/scripts/context-watch.ps1` |
| `context.warnAt` | float | `0.5` | `context-watch.ps1` |
| `context.budgetTokens` | integer or `null` | `null` | `context-watch.ps1` |
| `context.reserveTokens` | integer or `null` | `0` | `context-watch.ps1` |
| `context.handoffPath` | path | `".work/HANDOFF.md"` | `auto-clear.ps1` |
| `context.keepTranscripts` | integer | `5` | `handoff-write.ps1` |
| `context.autoClear.unsafeFocus` | boolean | `false` | `auto-clear.sh`, gating `wtype` — **consent, not capability**, see §14 |
| `context.autoWrapUp` | boolean | `true` | `context-watch.ps1`, `context-watch.sh` |
| `context.autoResume` | boolean | `true` | `handoff-read.ps1`, `handoff-read.sh` |
| `context.staleHandoff.maxAgeHours` | integer | `72` | `crew_state.STALE_HANDOFF_DEFAULTS` |
| `context.staleHandoff.maxCommitsBehind` | integer | `3` | `crew_state.STALE_HANDOFF_DEFAULTS` |
| `emergency.standDown` | boolean | `true` | `hooks/scripts/_common.sh` |
| `emergency.ttlMinutes` | integer | `120` | `crew_incident.py` |
| `emergency.maxTtlMinutes` | integer | `480` | `crew_incident.py` |
| `platform.os` | string or `null` | `null` | `crew_platform.py` |
| `platform.wsl` | boolean or `null` | `null` | `crew_platform.py` |
| `platform.shell` | string or `null` | `null` | `crew_platform.py` |
| `platform.windowsHostIp` | string or `null` | `null` | `crew_platform.py` |
| `graph.enabled` | boolean | `true` | **no consumer found**, §9 |
| `graph.tool` | string | `"graphify"` | **no consumer found**, §9 |
| `graph.out` | path | `"graphify-out"` | `crew_state.py` |
| `graph.mode` | string | `"code-only"` | **no consumer found**, §9 |
| `graph.commitHook` | boolean | `false` | **no consumer found**, §9 |

`context.reserveTokens: null` means *off*, and survives as `null` — this is the
case `null_shadows` is deliberately narrow to protect (§1).

`platform.*` is written by `crew_platform.py`, which stamps the detected
machine facts into the repo config. That is why it is repo-only despite
describing a machine: the value records what *this checkout* resolved, and a
global override would make every repo on the box report the first one's answer.

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

### What the widening costs

`windowTitle` is the guard that stops SendKeys typing into whatever happens to
have focus: `auto-clear.ps1` calls it REQUIRED and the SendKeys call refuses to send
without it. Machine-global is the right home for it — a terminal's title is a
property of the machine — but **a wrong global value now aims keystrokes at the
wrong window in every repo on that machine rather than in one.** That is the
trade, taken deliberately.

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

Six keys, one block, one ratchet, **two vocabularies**. What crew's command
guard does about each dangerous action it recognises, and how much of
production crew may reach.

| Key | Type | Default | Layer | Read by |
|---|---|---|---|---|
| `guards.terraformApply` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/guard.sh`, `guard.ps1` |
| `guards.forcePush` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/guard.sh`, `guard.ps1` |
| `guards.adminMerge` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `hooks/scripts/guard.sh`, `guard.ps1` |
| `guards.mergeGate` | `block` \| `ask` \| `allow` | `"block"` | both, **narrower wins** | `commands/gate.md`, `commands/promote.md` |
| `guards.prodDatabase` | `none` \| `read` \| `full` | `"none"` | both, **narrower wins** | `hooks/scripts/guard.sh`, `guard.ps1` |
| `guards.prodServer` | `none` \| `read` \| `full` | `"none"` | both, **narrower wins** | `hooks/scripts/guard.sh`, `guard.ps1` |
| `production.databases` | list of globs | `[]` | **repo only** | `crew_config.py::production_patterns` |
| `production.hosts` | list of globs | `[]` | **repo only** | `crew_config.py::production_patterns` |

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

This is the **only** ratcheted key in crew where "absent" and "unreadable" do
not resolve to the same value, and both halves are load-bearing:

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
