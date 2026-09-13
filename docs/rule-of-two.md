# The Rule of Two — scope

**Status: shipped.** `plugin/rule-of-two/` landed as 0.1.0 (#128), 0.1.1 (#130,
the five defects its own first run exposed) and 0.1.2 (#131, a model id that
contradicts its alias withdraws the Rule of Two claim). Its first real review
was of `plugin/crew/`; both families ran and both said VIABLE WITH CHANGES. The
rest of this note is the decision record as made on 2026-09-13, kept because
the decisions still bind — a line below that reads as unfinished is history,
not a task.

A plugin holding two adversarial reviewers from **different model families**,
which tear apart an artifact and report whether it is viable, where it is weak,
what defects it carries, and what would make it better. It can hand the result
to `crew` as work, or leave a report to act on later.

## Verified, and how

- **`gpt-6-astra` is a real Codex model.** `codex exec -m gpt-6-astra` answered
  and exited 0; a deliberate control name (`definitely-not-a-real-model-xyz`)
  exited 1. The control matters: Codex echoes any model name into its startup
  banner, so a banner reading `model: gpt-6-astra` proves nothing on its own,
  and an earlier version of this check was wrong for exactly that reason —
  it also read `$?` after a pipe, which is the pipe's status, not Codex's.
  Codex CLI 0.153.4, `-m/--model` present, `codex exec review` subcommand exists.

- **Two model naming conventions are in play and they are not interchangeable.**
  Agent frontmatter across all 54 shipped agents uses a bare alias — `sonnet`
  ×52, `opus` ×2, never a full ID. Crew config pins use full IDs
  (`crew_state.py:966`, `FALLBACK_DEFAULT = "claude-sonnet-5"`).

- **NOT verified: the Fable spelling.** `claude-fable-5-1` was asserted from a
  model list, never tested. Given the split above, `fable` is the likely
  frontmatter form and `claude-fable-5-1` the likely config form. Test both
  against a live dispatch before writing either. Do not carry this forward as
  settled.

## Decisions

**1. Fully standalone.** Its own model config; it never reads crew's. Chosen
over reusing crew's `qa.order` / `author_families` / `independentReviewerProbed`.

The risk this accepts is a second implementation of cross-family independence,
whose failure mode is quietly clearing a same-family reviewer — crew shipped
that bug once already. What makes it tolerable here: this plugin is **not a
solver**. It has exactly two reviewers, fixed to different families by
construction. The only check it needs is "are these two actually different
families, and did both actually run" — not "search a list for an independent
candidate." Keep it that small. If this ever grows a provider list, revisit
this decision rather than growing the logic.

**2. First cut reviews agents, skills and plugins** — not architecture or plans.
It is the half with no prior art (see below), the rubric already exists locally
(`plugin/crew/agents/skill-author.md`, `Skill-Authoring-Standard.md`,
`Skill-Pipeline.md`), and it is self-testing: the first artifact the two
reviewers tear apart can be this plugin.

**3. Pin-then-fallback is configurable, not hardcoded**, defaulting to the
requested Fable → Opus 5 pairing. This is crew's own decision, already argued at
`crew_state.py:955`: *"model names churn, and a hardcoded fallback is the next
name to churn."*

**4. No hook.** A review tool is invoked deliberately. Registering a hook would
buy the sabotage-tested must-block/must-allow regression suite requirement for
nothing.

## The load-bearing invariant

**"Only one reviewer ran" is its own reported outcome.** If Codex is missing,
unauthenticated, or its model is retired, the result must say plainly that this
is one review and not two — never a single-reviewer report wearing the name
Rule of Two. The whole value of the plugin is the second family; a report that
silently loses it while keeping the title is this repo's signature defect, and
the one most worth a test.

Same rule for the family check itself: if the two configured models cannot be
resolved to families, that is "could not tell", not "independent".

## VoltAgent

`https://github.com/VoltAgent/awesome-claude-code-subagents`, MIT. Use as a
coverage checklist, not a dependency — the repo's standing policy is to mine it
and write in crew's own voice.

- Architecture and general-code reviewers there are near-duplicates of agents
  crew already ships (`architect-reviewer`, `code-reviewer`, `security`,
  `planner`, `penetration-tester`).
- `project-idea-validator` ("brutal go/no-go product idea validator") is the one
  genuinely adversarial entry worth mining, for the viability verdict.
- **Nothing in it reviews prompts, agents, skills or plugins as artifacts.**
  The closest are `prompt-engineer` (writes prompts, does not critique them) and
  `llm-architect` (designs systems, does not evaluate them). That gap is why
  decision 2 starts where it does.

## Before it ships

Registration is all-or-nothing in one commit, per `CLAUDE.md`: marketplace
entry, catalog row, `plugin/PLUGINS.md`, **both** install scripts in the same
order with the same text, and a version. A partial registration fails the
checker and leaves nobody able to tell which half was intended.

Layout to copy: `plugin/obsidian-vault/` — `.claude-plugin/plugin.json`,
`agents/`, `commands/`, `README.md`.

## Open

- Config keys this plugin needs are not yet enumerated. Crew's schema 5 bump was
  being cut around the same time; keys known before that bump cost nothing extra,
  keys found after it cost a second bump that prompts every crew repo on every
  machine.
- `docs/adr/` does not exist, though `CLAUDE.md` names it as where decisions
  live. This note is in `docs/` instead. Unresolved, not important.
