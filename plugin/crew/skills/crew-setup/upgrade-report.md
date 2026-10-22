# Relaying a pre-0.20 upgrade (read by /crew:migrate)

`/crew:migrate` brings a `.crew/config.json` below the current schema (no
`schema` key, or an integer 1-7) up to the current schema with `crew_upgrade.upgrade_config`, the
code `/crew:upgrade` ran before T-0038 folded that command into migrate. The
preview and apply print what that stage did as `upgrade` lines. This file says
how to relay them. It is a migration, not a rebuild: it must not lose or
silently skip anything a human wrote, and it must not change where any role
dispatches.

## Lead with an absent machine-global config

**Absent is the headline, not a list item.** When `~/.claude/crew/config.json`
does not exist, the first `upgrade` line starts `NO MACHINE-GLOBAL CONFIG`,
naming the effective `pm.authority` and pointing at `/crew:config`. Lead with
THAT line, verbatim, before any other. Every repo on this machine falls back to
built-in defaults until that file exists, and that fact is the one thing here
nobody should have to go looking for. The other machine-global findings
(`unreadable`, `missing-keys`, `repo-keys`, `inert-schema`, `authority`) come
from `crew_config.py --root . --check-global`, which `/crew:config` runs. Point
at `/crew:config`; do not fix the global file here. Migrate never writes it.

## Read each line out

- **Config** — the `upgrade  ## Config` lines name the guards profile the
  migration chose and every key it removed (held its default, retired, or
  accepted). Read them out, and state the guard line even when no override
  was needed.
- **May be pinned by an earlier `/crew:upgrade`** — a globally-settable leaf
  (`pm.authority`, `qa.order`, `install.policy`, any `guards.*`, ...) this
  repo's file still carries at exactly the built-in default. This run never
  writes one of those unless the repo asked for it, but an OLDER release did,
  and this line is how a repo upgraded before that fix finds out. Never
  removed automatically — say the operator can delete the line from
  `.crew/config.json` by hand to let the global layer answer again, and that
  doing so needs their yes, not migrate's guess.
- **Schema 2 → 3** — when the report names `qa.roles`, `dev.roles`,
  `qa.fallback` or `dev.fallback`, read the whole line out. Those keys arrive
  **neutral**: the role tables are empty, so every role still runs on its
  block's own `provider`, and `fallback` only fires when a pinned model has
  been retired, which used to be a plain error. **This repo dispatches exactly
  as it did before the upgrade.** Say that explicitly — a mandatory migration
  that quietly re-routed someone's development work to a different model would
  be indefensible, and the only way a user can be sure it did not is to be
  told.
- **Schema 3 → 4** — when the report says `docs.theme` was rewritten, read the
  whole line out, including WHY it was allowed. This is the one value an
  upgrade changes rather than preserving, so a user who notices their config
  differs from what they wrote is owed the reason unprompted: the key has
  never had a consumer, so no value in it can be a preference anyone formed by
  watching it work. Leaving `"neutral"` would mean that, once the pass-through
  lands, every upgraded repo passes an explicit `--brand neutral` that
  OVERRIDES an installed brand pack. **If they did mean neutral, say they can
  set it again and it will stick** — the rewrite is one-shot, gated on the
  schema it landed in, so no later `--force` will take it away again.
- **Schema 4 → 5** — when the report says `install.policy` was added, read the
  whole line out, and lead with what did NOT happen: it arrives as `manual`,
  which is what crew already did — name a missing skill and its install command,
  and run nothing. **Nobody's machine started installing anything because they
  upgraded.** Then say what the other values buy: `ask` lets crew offer and
  install only after an explicit yes, `auto` lets it install without asking. Two
  things are worth saying unprompted because neither is guessable. First, under
  every policy crew can only run a command from its own source — never a string
  from a repo config or a skill file, which matters because crew reads config
  out of cloned repositories. Second, the key resolves to the NARROWER of the
  repo and machine-global layers rather than the repo winning, so `auto` needs
  both layers to say `auto`; a user who sets it in one place and sees nothing
  change is not looking at a bug.
- **Schema 5 → 6** — when the report names the `guards` block, read the whole line out, and this time do **not** lead
  with what did not happen, because two things did. Every guard arrives as
  `block`, and for `guards.terraformApply` and `guards.forcePush` that is
  exactly what the guard already did — but `guards.adminMerge` refuses
  `gh pr merge --admin`, which no crew guard refused before, and
  `guards.terraformApply` now covers `tofu` as well as `terraform`. **A
  command that ran yesterday can be refused today**, and a user who is told
  only "the default is block, so nothing changed" will go looking for a bug in
  their tooling. Both were bypasses rather than features; say that, and say
  what the other values buy: `ask` makes crew print the exact command and
  refuse until the user creates the one marker file it names, which approves
  THAT command and no other, and `allow` lets it run while writing a row to
  `.crew/guard.log` — under `allow` nothing is silent, and the log is where the
  record lives. Say unprompted that these keys take the NARROWER of the repo
  and global layers, exactly as `install.policy` does, so `allow` needs both
  layers to say `allow`; and that `guards.mergeGate` governs `/crew:gate`
  rather than the command guard.

  Then the two the same block adds in a DIFFERENT vocabulary:
  `guards.prodDatabase` and `guards.prodServer` are `none` | `read` | `full`,
  not `block` | `ask` | `allow`, and they arrive at `none`. Say the thing that
  makes `none` safe rather than alarming: they match against
  `production.databases` and `production.hosts`, which arrive EMPTY, and **with
  no patterns declared the guard matches nothing**. So nothing is refused until
  the user declares what production is, and the older unconfigurable
  `prod`-in-an-argument rule is unchanged until they do. Say too that those two
  lists are REPO-ONLY while the levels ratchet across both layers — the level
  is a fact about the machine, what counts as production is a fact about the
  checkout — and that under `read` anything crew cannot positively classify as
  read-only, an interactive `psql` session included, is treated as a write and
  refused. The merge-gate step of `/crew:promote` is no longer
  configured at all: it runs only on `--merge-gate <github|bitbucket>`.
- **Schema 6 → 7** — when the report names the `change` block, read the whole
  line out, and here you **do** lead with what did not happen, because nothing
  did. `change.requireForProduction` arrives `false`, so `/crew:promote
  production` asks for no change request, exactly as before; `/crew:change`
  has to be invoked. **No promotion starts failing because someone
  upgraded.** Then say what the block buys: `/crew:change new` files a change
  request into whichever tracker this repo uses — ServiceDesk Plus against the
  `Change Management Request` template, Jira as a `Change` issue, or
  `.work/changes/<id>.md` in files mode — and refuses to file while any of the
  template's questions 1–9 is unanswered or a placeholder, naming which.
  It asks for the requester, the implementor and the category each time.

  Say the one thing about `change.requireForProduction` that is **not**
  guessable, because it is the opposite of every other ratcheted key: a repo
  may turn it **ON** and never off. `install.policy` and the six `guards` keys
  resolve to the narrower layer, and for them narrower means a smaller
  capability; here the narrower value is `true`, so a machine-global `true`
  cannot be defeated by a `false` in a repo somebody cloned — and a repo's own
  `true` holds on a machine that said nothing. A value that is neither `true`
  nor `false` reads as `true`, so a typo stops a production promotion and names
  the key rather than quietly waving it through. CONFIG.md §17.
- **Schema 7 → 8** — the twelve `guards.<name>` keys become `guards.profile`
  plus `guards.overrides`, the profile being whichever of `off`, `standard`,
  `strict` needs the fewest overrides (a tie goes off, standard, strict). Say
  that **every guard keeps the value it had in this file**; the rewrite changes
  how it is written, not what it decides. Then the dropped keys: 60 settings
  became code constants at their old defaults. A key that held its default is
  removed without comment; `tier` and `roles` (retired) are removed whatever
  they held; the backup keeps all of them. A dropped key holding anything else
  is a `CONFLICT` and migrate writes nothing until the person removes it or
  passes `--accept-dropped <key>` for it — read each named key and its constant
  out, and never print the value. Keys crew does not know are listed as
  `unknown` and carried untouched. The machine file has its own pass,
  `crew_migrate.py --global`, with the same preview, apply and rollback.
- **Blocks left unmigrated** — a `pm`, `graph`, `qa`, `dev` or `guards` value
  that arrived as the wrong type is left exactly as the user wrote it, and
  `schema` is deliberately NOT stamped current. Migrate reports it as a
  `CONFLICT` naming each block and writes nothing - not the config, not
  `crew.json` - so a half-upgraded config never reaches `crew.json`. Name each
  block and say it needs a hand edit, then a fresh preview.

## After apply: re-run the QA audit - report, do not fix

A repo set up before an audit item existed was never judged by it. Run
`python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-qa-standards/scripts/qa_audit.py --root .`
and show the table verbatim, GAP and UNKNOWN first. Fix nothing here; offer
`/crew:init --audit` for the fixes and `--stamp` once the report is read. A G1
GAP means the Stop gate skips those rules today: say so first.

## Say what the upgrade stage did not do

State this explicitly, every run - a migration that silently declines work
reads as one that succeeded:

- It did not touch `.crew/codemap/` or any anchor. Graph facts for the code map
  come from `/crew:onboard --refresh <subsystem>`.
- It did not grant `graph.obsidian.confirmed` - an upgrade never sets that
  flag; only explicit consent in session does. Adding roles is not a
  counter-example: a role is a capability and reversible, and that flag is
  consent to write into the user's own notes outside the repo.
- It did not touch `~/.claude/crew/config.json` (that is `crew_migrate.py --global`).
- It did not write a single per-role model pin. Schema 3's `qa.roles` and
  `dev.roles` arrive empty; `/crew:model` and `/crew:config` own model pins.
- It did not fix a QA audit GAP or stamp the audit (the audit above reports only).
