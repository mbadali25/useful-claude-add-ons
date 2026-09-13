# crew configuration reference

Every key crew reads, which of the two layers may set it, what it defaults to,
and where the code that acts on it lives.

**This file is derived from the code, not from the templates' comments.** Every
claim below is either a `path:line` you can open, or a value printed by running
the function named beside it. Where a claim rests only on a comment, it says so.
Where no consumer could be found, it says "no consumer found" and never
"unused" — see [Keys with no consumer found](#keys-with-no-consumer-found),
which is the most load-bearing section here.

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
| machine-global | `~/.claude/crew/config.json` | `crew_config.read_global_config` (`crew_config.py:585`) |

Both are optional. `read_global_config` **never raises**: an absent, malformed,
or non-object global file returns `{}` and is indistinguishable from no file at
all. That contract is load-bearing — `resolve_config` is reached from a
`SessionStart` hook, and a broken file in `~/.claude/` must not wedge every
session on the machine.

Nothing in `crew_config` ever writes the global file except
`write_global_config` (`crew_config.py:1388`), which its own docstring names as
the only function in crew that writes outside the repo.

### How the two are merged

`resolve_config` (`crew_config.py:638`) is the single resolver. Read it as five
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

`null_shadows` (`crew_config.py:448`) and `without_null_shadows`
(`crew_config.py:494`) fix that on the read path. The rule is deliberately
narrow, and the narrowness is the point:

- A repo `null` is dropped **only** where the global layer supplies a real
  value at that path (`_layer_supplies`, `crew_config.py:717`).
- A repo `null` with nothing underneath it is left alone. `context.reserveTokens:
  null` still means *off* and does not silently become `100000`.

It is not fixed inside `merge_defaults` because `crew_upgrade.upgrade_config`
shares that function, and changing null semantics there would rewrite users'
files on migration rather than only resolving them for a read
(`crew_config.py:471-474`, a comment).

---

## 2. The invariant

> **What the global file may WRITE is exactly what the global layer may SUPPLY.**

One definition, `default_global_config()` (`crew_config.py:325`), enforced from
both directions:

| Direction | Function | Mechanism |
|---|---|---|
| READ — what a global file may supply | `filter_global` (`:543`) | `_prune` (`:517`) keeps only keys present in `default_global_config()`, and returns the dropped paths as `ignored` |
| WRITE — what a guided flow may set | `plan_global_write` (`:1301`) | refuses any path for which `is_global_path` (`:566`) is false, by name, with the full allowed list in the message |

`is_global_path` agrees with `filter_global` by construction — both stop
descending at a template **leaf**.

**Measured, not argued.** `leaf_paths(default_global_config())` yields **44**
leaves. `leaf_paths(default_config())` yields **85**, so **41** are repo-only.
For all 85, `filter_global` and `plan_global_write` agree on whether the path is
settable.

### The one asymmetry, and it matters

The two rules agree on **which paths**. The write path additionally rejects
**values** the read path only reports:

- `plan_global_write` runs `validate_providers` (`crew_config.py:171`) on the
  *merged result*, and raises `ProviderError` for a bad `qa.provider`,
  `dev.provider`, a bad name inside `qa.order`, or a bad provider in
  `qa.roles.<r>` / `dev.roles.<r>`.
- `resolve_config` **never raises**. A bad provider already on disk is reported
  by `provider_problems` (`crew_config.py:611`) and nothing more.

A reader who takes "exactly what" to mean "identical behaviour" will be
surprised the first time a write is refused for a value a file on disk is
allowed to hold. That asymmetry is deliberate: refuse at the boundary where the
value enters, report at the boundary that must not crash a session hook
(`crew_config.py:1338-1345`, a comment stating exactly this).

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
  The comment at `crew_config.py:1367-1381` records why: the equality form was
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
  never merged element-wise (`leaf_paths`, `crew_config.py:432`).
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
| Current value | `4` (`crew_state.SCHEMA_CURRENT`, dumped by execution) |
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
| Consumer | `crew_state.normalise_authority` / `authority_rank`; `pm_brief.py`; `crew_config.py:66` |

`crew_state.AUTHORITIES` is `["report-only", "act", "autonomous"]` (dumped by
execution). `authority_rank` returns `report-only` 0, `act` 1, `autonomous` 2 —
and **0 for `None` and for any unrecognised string**. A typo in a permissions
field fails closed, to the least permissive tier.

The tiers are a **floor**, not a set: anything `act` may do, `autonomous` may
do.

What each tier grants, quoted verbatim from `_WIDENING_NOTES`
(`crew_config.py:1281`) — this is the string crew itself prints on a widening:

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
warning that silently describes the wrong thing (`crew_config.py:1275-1280`, a
comment naming that as the failure that produced the table).

---

## 6. `pm.ticketGranularity`

| | |
|---|---|
| Type | string enum |
| Values | `session`, `system` (default), `change` |
| Layer | global-settable |
| Consumer | `crew_state.normalise_granularity`, called at `crew_state.py:1220` |

`crew_state.TICKET_GRANULARITIES` is `["session", "system", "change"]` (dumped
by execution). Normalised once in `crew_state.collect` alongside `pm.authority`,
so every consumer downstream reads a value guaranteed to be one of the three
and none of them re-decides what a typo means (`crew_state.py:2730-2734`, a
comment).

`system` files one ticket per session and opens a second only when the work
reaches another **registered marketplace entry**. A repo with no marketplace
declares no system boundary; the documented behaviour is that it falls back to
`session` and says so rather than inventing a boundary from the directory tree.

---

## 7. `docs.theme` and `docs.reportTheme`

| | Layer | Default | Consumer |
|---|---|---|---|
| `docs.theme` | global-settable | `null` | `crew_state.py:35`; `crew-house-style/SKILL.md:66` |
| `docs.reportTheme` | global-settable | `null` | `crew-house-style/SKILL.md:66` (prose only) |

Both are doc-builder theme-pack names, passed as `--brand <name>`.

### What `null` means

Quoted verbatim from `crew_upgrade.py:98-102`, the comment above `DOCS_BLOCK`:

> Both keys' `None` now mean ONE thing -- "I have no answer, ask the next
> authority". For `reportTheme` that authority is `theme`; for `theme` it is
> doc-builder's own five-step resolution.

So `null` is **not** "no theme". A null `docs.theme` passes no `--brand` flag at
all and lets doc-builder resolve; a null `docs.reportTheme` means "follow
`docs.theme`", which is why a findings report in a branded repo does not come
out unbranded.

### The one-shot rewrite

`crew_upgrade.py` carries two constants (`:131` and `:138`, applied at
`:437-441`):

```python
_DOCS_THEME_REWRITTEN_FROM = "neutral"
_DOCS_THEME_REWRITTEN_UNTIL_SCHEMA = 4
```

A `docs.theme` of `"neutral"` in a config below schema 4 is rewritten to `null`
on upgrade. This is the **single documented exception** to crew's rule of
carrying a user's value forward untouched, and the justification given in
`crew-setup/SKILL.md:218-224` is that `docs.theme` **had never had a consumer**,
so no value in it could be a preference anyone formed by watching it work.
Leaving `"neutral"` would have meant every upgraded repo passing an explicit
`--brand neutral` that overrode an installed brand pack — de-branding documents
that come out correctly branded today, with nothing in the config changed to
explain it.

A user who did mean neutral sets it again and it is honoured.

**Read §9 with this in mind.** It is the precedent for every zero-consumer key
in this file.

---

## 8. `bitbucket.mergeGate`

| Key | Type | Default | Layer |
|---|---|---|---|
| `bitbucket.mergeGate.enabled` | boolean | `false` | global-settable |
| `bitbucket.mergeGate.branch` | string or `null` | `null` | global-settable |
| `bitbucket.mergeGate.preset` | string | `"standard"` | global-settable |

Written by `crew_upgrade.BITBUCKET_BLOCK` (`crew_upgrade.py:150`).

Rationale, from `crew-setup/SKILL.md:226-230` — this is prose, and it is the
only statement of intent in the repo:

> off by default, because a gate that arrived switched on would start failing
> merges nobody asked it to watch. `branch: null` means the repo's main branch
> is resolved from the Bitbucket API rather than assumed to be `main` — a repo
> on `master` or a Gitflow `develop` would otherwise get a gate that looks
> configured and guards nothing.

### A correction to the docstring

`default_global_config()`'s docstring (`crew_config.py:445-447`) says
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
API.** `merge_gate.sh:198-202` resolves `.mainbranch.name`, and `:202` dies
asking for `--branch` when it cannot. Because the alternative — promote
substituting `main` — is wrong, and silently wrong, on a repo still on `master`
or on a Gitflow `develop`: the gate would look configured and watch a branch
nobody merges into. The script dying is the better outcome, because it keeps
"could not tell" a visible failure rather than an unknown wearing the label of
an answer.

**`preset: "standard"` means nothing today, and promote says so rather than
binding it.** `merge_gate.sh` has **no `--preset` flag**. The preset a bare
`enable` applies is one hardcoded JSON literal, `PRESET` at
`merge_gate.sh:65`, and nothing selects it. Two moves were available and both
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
| `bitbucket.mergeGate.preset` | `crew_upgrade.py:151` (writes it), `crew-setup/SKILL.md:157` (sample JSON) and `:226` (rationale), both templates, `tests/test_crew_config.py` + `tests/test_upgrade.py` (assert the default and the layering). `commands/promote.md` **names it in order to say it selects nothing** — there is no `--preset` flag to bind it to (§8) |
| `graph.enabled` | `crew_upgrade.py:48` (writes it), `crew-graph/SKILL.md:165` (a table describing it) |
| `graph.tool` | as above, `crew-graph/SKILL.md:166` — which reads "Always `\"graphify\"` today" |
| `graph.mode` | as above, `crew-graph/SKILL.md:168` — "Always `\"code-only\"` today" |
| `graph.commitHook` | as above, `crew-graph/SKILL.md:169` |
| `jira.project` | `crew-setup/SKILL.md:284` (writes it) and `:145` (sample JSON), `crew_config.py:335`/`:1319`/`:1442` (docstrings and one printed sentence), both templates. `commands/jira-sync.md` never mentions it |

The `graph` block's **only** key any crew code reads is `graph.out`, at
`crew_state.py:674`. Verified by grepping every tracked `.py`, `.sh` and `.ps1`
for `get("graph")` and `["graph"]`: the other hits are `crew_state.py:2646` and
`pm_brief.py:59`, which read `knowledge["graph"]` — the *state* dict
`read_knowledge` builds, not the config block — and `crew_upgrade.py:335-343`,
which drops the removed `obsidian` sub-block.

The `bitbucket` block is read by no crew **code** — verified the same way,
grepping for `get("bitbucket")` and `["bitbucket"]` across every tracked file,
whose only hits are `crew_config.py:374` and `:498` writing the defaults in.
Its consumer is prose: `commands/promote.md` (§8), with a committed regression
test in `tests/test_promote_merge_gate.py`. `preset` is on this list because
promote names it only to say it binds to nothing.

`jira.project` is the one on this list that most looks like it should work.
`/crew:jira-sync` gates on `tracker == "jira"` (`commands/jira-sync.md:11`) and
then caches `jira.cloudId` (`:25`) — a key `default_config()` does not declare
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
| `obsidian.columns.*` (five keys) | `commands/obsidian-sync.md:94`, which instructs: "Read the names from `obsidian.columns` rather than hardcoding them" |
| `sdp.portal`, `sdp.noteVisibility`, `sdp.closeOnDone` | `commands/sdp-sync.md:103`, `:63`, `:85` |
| `secondOpinion.provider`, `.sendsCode`, `.keyEnv` | `agents/planner.md:50` and `:54`, `commands/plan.md:21`, `skills/crew-providers/SKILL.md:96` |
| `docs.reportTheme` | `skills/crew-house-style/SKILL.md:66`, with a committed regression test in `tests/test_docs_routing.py:132-165` that binds it to the findings-report genre |
| `bitbucket.mergeGate.enabled`, `.branch` | `commands/promote.md`, `## The Bitbucket merge gate` — the flags it passes to `skills/bitbucket/scripts/merge_gate.sh`, with a committed regression test in `tests/test_promote_merge_gate.py`. `.preset` is **not** here: see §8 and §9 |
| `pm.maxDispatches` | `agents/pm.md:396` ("Stop after `pm.maxDispatches` roles in one pass"). Also coerced to `int` at `crew_state.py:2727` |

---

## 10. Global-settable keys — all 44

Settable in **either** layer; repo wins. Defaults are identical in
`default_config()` and `default_global_config()` — verified by comparison.

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
| `pm.enabled` | boolean | `true` |
| `pm.mode` | string | `"adaptive"` |
| `pm.quietLines` | integer | `8` |
| `pm.maxLines` | integer | `40` |
| `pm.authority` | see §5 | `"report-only"` |
| `pm.ticketGranularity` | see §6 | `"system"` |
| `pm.maxDispatches` | integer | `3` |
| `context.autoClear.enabled` | boolean, see §14 | `false` |
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

`crew_state.QA_PROVIDERS` and `DEV_PROVIDERS` are both
`["claude", "codex", "copilot"]` (dumped by execution). `qa.provider`
additionally accepts `"auto"`; a `dev.provider` of `"auto"` is **not** valid —
`validate_providers` (`crew_config.py:171`) checks `qa.provider` against
`QA_PROVIDERS + ["auto"]` and `dev.provider` against `DEV_PROVIDERS` alone.

The three numeric `pm.*` keys are coerced with `int_or` once, in
`crew_state.collect` (`crew_state.py:2727`), because they come from a
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
| `schema` | integer | `4` | see §4 |
| `tier` | integer | `0` | `crew_state.collect` |
| `roles` | list (a leaf) | `["explorer", "qa-reviewer"]` | `crew_state.collect` |
| `tracker` | string | `"files"` | `crew_state.py:2771`, `pm_brief.py:33`, `commands/ticket.md:13` |
| `jira.project` | string or `null` | `null` | **no consumer found**, §9 |
| `jira.cloudId` | string or `null` | `null` | written by `commands/jira-sync.md:25`; **read by nothing**, §9 |
| `sdp.portal` | string or `null` | `null` | prose, §9 |
| `sdp.noteVisibility` | string | `"private"` | prose, §9 |
| `sdp.closeOnDone` | boolean | `false` | prose, §9 |
| `obsidian.vaultPath` | path or `null` | `null` | `commands/obsidian-sync.md:12` |
| `obsidian.boardDir` | path or `null` | `null` | `commands/obsidian-sync.md:16` |
| `obsidian.board` | filename | `"Board.md"` | `commands/obsidian-sync.md:16` |
| `obsidian.columns.backlog` | string | `"Backlog"` | prose, §9 |
| `obsidian.columns.ready` | string | `"Ready"` | prose, §9 |
| `obsidian.columns.inProgress` | string | `"In Progress"` | prose, §9 |
| `obsidian.columns.review` | string | `"Review"` | prose, §9 |
| `obsidian.columns.done` | string | `"Done"` | prose, §9 |
| `verifyGate` | boolean | `true` | `hooks/scripts/verify-gate.sh:24` |
| `context.enabled` | boolean | `true` | `hooks/scripts/context-watch.ps1:28` |
| `context.warnAt` | float | `0.8` | `context-watch.ps1:30` |
| `context.budgetTokens` | integer or `null` | `null` | `context-watch.ps1:31` |
| `context.reserveTokens` | integer or `null` | `100000` | `context-watch.ps1:39` |
| `context.handoffPath` | path | `".work/HANDOFF.md"` | `auto-clear.ps1:82` |
| `context.keepTranscripts` | integer | `5` | `handoff-write.ps1:22` |
| `context.autoClear.unsafeFocus` | boolean | `false` | `auto-clear.sh:93`, gating `wtype` at `:187` — **consent, not capability**, see §14 |
| `context.autoWrapUp` | boolean | `false` | `context-watch.ps1:33`, `context-watch.sh:41` |
| `context.autoResume` | boolean | `false` | `handoff-read.ps1:36`, `handoff-read.sh:35` |
| `context.staleHandoff.maxAgeHours` | integer | `72` | `crew_state.STALE_HANDOFF_DEFAULTS` |
| `context.staleHandoff.maxCommitsBehind` | integer | `3` | `crew_state.STALE_HANDOFF_DEFAULTS` |
| `emergency.standDown` | boolean | `true` | `hooks/scripts/_common.sh:54` |
| `emergency.ttlMinutes` | integer | `120` | `crew_incident.py:80` |
| `emergency.maxTtlMinutes` | integer | `480` | `crew_incident.py:198` |
| `platform.os` | string or `null` | `null` | `crew_platform.py:347` |
| `platform.wsl` | boolean or `null` | `null` | `crew_platform.py:347` |
| `platform.shell` | string or `null` | `null` | `crew_platform.py:347` |
| `platform.windowsHostIp` | string or `null` | `null` | `crew_platform.py:347` |
| `graph.enabled` | boolean | `true` | **no consumer found**, §9 |
| `graph.tool` | string | `"graphify"` | **no consumer found**, §9 |
| `graph.out` | path | `"graphify-out"` | `crew_state.py:674` |
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
   genuinely removed in 0.16.13; `crew_upgrade.py:339-343` drops them from an
   existing config and says so, and `crew-graph/SKILL.md:172-174` states the
   removal correctly.

2. **`crew_config.py:445-447`**, on `bitbucket.mergeGate.branch` — see §8. The
   docstring's "stays null in both layers" describes the default value, and
   reads as a statement about settability, which it is not. Still open: it is a
   comment, and correcting it is a change to `crew_config.py` rather than to
   this reference.

3. **RESOLVED 0.19.11 — ten keys were in use and declared by no default.** Kept
   because how it was found is worth more than the fact that it is fixed.

   Nine were read by a hook script — the six `context.autoClear.*` at
   `auto-clear.ps1:67`, `context.autoWrapUp` at `context-watch.ps1:33`,
   `context.autoResume` at `handoff-read.ps1:36`, and
   `context.autoClear.unsafeFocus` at `auto-clear.sh:93`. The tenth,
   `jira.cloudId`, is written by `commands/jira-sync.md:25` and read back by
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
   about the machine — `crew_platform.py:384-393` already validates `method`
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
availability is — `crew_platform.py:384-393` validates `method` against what
*this* platform can actually deliver and reports one it cannot honour.

### What the widening costs

`windowTitle` is the guard that stops SendKeys typing into whatever happens to
have focus: `auto-clear.ps1:21` calls it REQUIRED and `:128` refuses to send
without it. Machine-global is the right home for it — a terminal's title is a
property of the machine — but **a wrong global value now aims keystrokes at the
wrong window in every repo on that machine rather than in one.** That is the
trade, taken deliberately.

Its default is `null` where the scripts fall back to `""`. The two are
behaviourally identical (`if ($a.windowTitle)` is false for either, and
`auto-clear.sh:90` does the same), and `null` wins the tiebreak: `""` can read
to a human as a *deliberate* blank, and on this particular key that misreading
is dangerous.

### `unsafeFocus` is declared, and deliberately not granted

`context.autoClear.unsafeFocus` is the seventh leaf and the only one refused in
the global layer. `is_global_path("context.autoClear.unsafeFocus")` returns
`False`, and `filter_global` reports it by name.

It is **consent, not capability**. Setting it `true` accepts that `wtype` types
into whatever currently has focus, which Wayland offers no way to check
(`auto-clear.sh:187`). The rest of the block describes the machine; this one
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
