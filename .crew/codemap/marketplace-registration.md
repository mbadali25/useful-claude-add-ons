anchor: useful-claude-add-ons@62b1c7a

# Marketplace and registration

The root `.claude-plugin/marketplace.json` is the **only** marketplace file in
this repo (`CLAUDE.md`'s own rule — a second one anywhere under `plugin/`
would look like a nested marketplace and `check_registration` treats it as an
error).

## The registration web

**DERIVED.** A skill (source path starting `./skills/`) and a plugin (source
path starting `./plugin/`) are registered in different, non-overlapping sets
of places. Confirmed by reading each file, not just by the brief that named
them:

| | Skill | Plugin |
|---|---|---|
| Marketplace entry | `.claude-plugin/marketplace.json` (all 29 entries in one `plugins` array — the file does not distinguish skills from plugins by field, only by `source` prefix) | same file |
| Catalog doc | `skills/README.md` — table starts around line 36 (`\| \[\`aws-opensearch\`\]... \|`) | `plugin/PLUGINS.md` (a section) **and** `plugin/README.md` (a row) |
| Root README | linked via `README.md` under `skills/{name}` | linked via `README.md` under `plugin/{name}` |
| `.sh` install script | `SKILL_KEYS`/`SKILL_NAME`/`SKILL_SPEC` arrays, `scripts/install-prerequisites.sh:803` (`SKILL_KEYS=(`) through `:845` (`unset _i` after `SKILL_STATE`) | `PLUGIN_KEYS`/`PLUGIN_NAME`/`PLUGIN_SPEC`, `scripts/install-prerequisites.sh:852` (`PLUGIN_KEYS=(`) onward |
| `.ps1` install script | `$script:SkillCatalog`, `scripts/install-prerequisites.ps1:805` | `$script:PluginCatalog`, `scripts/install-prerequisites.ps1:842` |
| Own manifest version | none (skills have no `plugin.json`) | `plugin/<name>/.claude-plugin/plugin.json`, bumped in lockstep with the marketplace entry |

**A recent change checked against this table rather than assumed to fit it:**
crew 0.16.7 added three agents (`node-developer`, `power-automate-specialist`,
`sharepoint-developer`) inside `plugin/crew/agents/`. `git diff --stat
2b0972d..HEAD -- .claude-plugin/marketplace.json` shows exactly one entry
touched, 2 lines changed: the existing `crew` row's `description` (agent
count 14 -> 17) and `version` (`0.16.9` -> `0.16.10`) fields. No new
`plugins` array entry was added, `plugin/PLUGINS.md` and `plugin/README.md`
gained prose (a new specialists paragraph and a `### crew 0.16.10` /
`### crew 0.16.7` changelog section) rather than new catalog rows, and both
install scripts are byte-identical to the old anchor
(`git diff --stat 2b0972d..HEAD -- scripts/install-prerequisites.sh
scripts/install-prerequisites.ps1` produces no output). Total marketplace
entries stayed at 29 (25 skills, 4 plugins) throughout.

So the registration web did **not** change shape here — an agent is not a
unit this table's rows describe at all. It ships as a file inside a plugin's
own directory (`plugin/crew/agents/*.md`), the same way a command or a skill
subdirectory does; the plugin's *one* marketplace entry, *one* `PLUGINS.md`
section, *one* `README.md` row and *one* `plugin.json` cover every agent,
command and skill the plugin bundles, at whatever count they currently sum
to. Adding an agent is a content change to an existing plugin (bump its
version, per `CLAUDE.md`'s stop-and-ask rule, and update the prose that
states the count) — not a new registration. Correspondingly, neither
`PLUGIN_KEYS`/`PLUGIN_SPEC` nor `SKILL_KEYS`/`SKILL_SPEC` in either install
script needed a new entry for these three agents, and none was added: those
arrays register installable *plugins* and *skills* (top-level marketplace
units), not the agents/commands/skills bundled inside one.

**The asymmetry stated plainly, because it is a trap:** skills register in
`skills/README.md`; plugins register in `plugin/PLUGINS.md` **and**
`plugin/README.md`. There is no single doc both kinds share except the root
`README.md`. Registering a skill's entry in `plugin/PLUGINS.md`, or a
plugin's entry only in `plugin/PLUGINS.md` without the `plugin/README.md`
row, both pass a naive read of "did I add a doc row" while failing the actual
check.

**A gap enforced by nothing today (DERIVED, verified against source):**
`check_docs` (`scripts/check-marketplace.py:263-278`) reads exactly three
files — `skills/README.md`, `plugin/README.md`, and root `README.md` — for
every entry's `[\`name\`](link)` row. It **never opens `plugin/PLUGINS.md`**.
So a plugin whose `PLUGINS.md` section was never written, or drifted out of
sync with reality, fails no automated check. This matches what the ground
truth going into this task claimed, and it checks out against the current
source.

## Two version-check paths, not one — corrected

The ground truth handed into this task claimed: *"`scripts/check-marketplace.py`
deliberately runs everything EXCEPT `check_versions`."* **This is wrong for
the script itself**, and worth recording precisely because it is exactly the
kind of claim that looks right from an adjacent comment.

**DERIVED, what is actually true:**

- `scripts/check-marketplace.py`'s own `main()` (`scripts/check-marketplace.py:377-403`)
  calls all eight check functions in order, **including** `check_versions` at
  line 394. Running `python3 scripts/check-marketplace.py` — the exact
  command `CLAUDE.md` names as the gate — executes `check_versions`. Verified
  by running it: `all checks passed`, `marketplace: 25 skills, 4 plugins`.
- The exclusion is real, but it lives one layer down, inside
  `_verify/smoke.sh`'s own helper. `run_marketplace_check()`
  (`_verify/smoke.sh:54-79`) re-imports `check-marketplace.py` as a Python
  module and calls six of its eight check functions directly — its own
  comment says why, verbatim: *"Same calls main() makes, in the same order,
  minus check_versions (slow: see header)"* (`_verify/smoke.sh:62`). The
  header explains the cost: `check_versions` walks marketplace.json's full
  git history and diffs each entry's `source` path against the commit where
  its version was last bumped — expensive, and explicitly deferred to
  `run-all.sh` rather than smoke's ~90s budget.
- `_verify/smoke.sh`'s check 10 (`version_agreement_check`,
  `_verify/smoke.sh:261-357`, registered at `:356-357`) is **a different
  check entirely**, not a stand-in for the one it skips. It confirms that
  `pyproject.toml`, `plugin.json`, `marketplace.json`, and every hardcoded
  `VERSION`/`__version__` literal in a plugin's Python source all name the
  *same* version number right now. `check_versions` instead asks whether a
  plugin's files changed *since* its version was last set — a temporal /
  git-history question the point-in-time consistency check cannot answer and
  does not try to.

**JUDGEMENT:** so there genuinely are two version-related gates that do not
substitute for one another, exactly as the brief said — the correction is
narrower than it sounds: it is *`_verify/smoke.sh`'s internal fast-path* that
skips `check_versions`, not `check-marketplace.py` as a program. A change
that only runs `bash _verify/smoke.sh` and treats a clean run as proof
`check_versions` also passed is trusting a check that never ran there. Anyone
citing "check-marketplace.py never checks version drift" should say
"smoke.sh's fast subset doesn't" instead — the full script does, on every
direct invocation.

## What was not re-verified

`check_menu_parity` and `check_group_parity` (called from `main()` at
`scripts/check-marketplace.py:390-391`, exercised by smoke check 5 via the
`"menus"` group at `_verify/smoke.sh:69-70`) were read but not traced line by
line against every array in both install scripts — the registration-web table
above is the load-bearing claim of this section and was checked directly;
menu-parity internals were only skimmed.
