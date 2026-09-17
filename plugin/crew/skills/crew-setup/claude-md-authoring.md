# Claude Md Authoring

_Extracted from `SKILL.md` to keep the main file under the
500-line progressive-disclosure limit. Nothing was changed in the
move._

### Triage first: does this rule belong here at all?

Most rules people want in CLAUDE.md should not be. Run each candidate through
this before writing it:

| The rule | Where it goes | Why |
|---|---|---|
| "Run playwright on CSS changes" | `verify.json` rule | A path glob decides it. A hook enforces it. |
| "Run tflint and terraform-docs" | `verify.json` rule | Same — mechanism, not judgment. |
| "No deprecated Terraform syntax" | tflint rules, mostly | The linter already knows. CLAUDE.md only for what it can't see. |
| "Smoke and regression after deploy" | `verify.json` `environments` block | `/crew:promote` runs them as separate gates. Mechanism, not memory. |
| "Production needs a rollback" | **CLAUDE.md** | A judgment gate no command can evaluate. |
| "Check error logs after deploy" | **CLAUDE.md** + runbook | Post-deploy, so no pre-merge hook can cover it. |
| "Don't fix things you notice nearby" | **CLAUDE.md** | Pure judgment, and the most valuable line in the file. |

The test: **could a command decide this?** If yes, it goes in `verify.json`,
where it is enforced rather than hoped for, and is not re-paid on every
delegation. What stays in CLAUDE.md is judgment, boundaries, and repo facts.

Ask the user for their rules, then triage them out loud rather than pasting them
all in. A 200-line CLAUDE.md is the most expensive file in the repo.

Thin. 30-40 lines. Stack, commands table, where things are, do-not-touch paths,
repo-specific rules, known landmines. Nothing else — it loads into every subagent
on every delegation, so every line is paid for repeatedly.

### When the repo already has a CLAUDE.md

This is the common case, and the one that goes wrong quietly. Run:

```bash
bash ${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/scripts/claude-md-audit.sh
```

It reports which template sections are missing, which sections the repo has that
the template does not, the line count against the ceiling, and how many
placeholders remain. Then **append the missing sections; never regenerate the
file.** A repo's existing CLAUDE.md encodes things nobody wrote down twice, and
regenerating it from a template destroys exactly that.

The same command is how an existing crew repo picks up template changes. The
template is not versioned into repos, so nothing propagates on its own - when a
section is added to the template (promotion discipline was added in 0.2.0), the
only way an existing repo gets it is someone running this audit and appending.
`/crew:docs --audit` runs it too, so the drift surfaces during a normal docs pass
rather than never.

### Files to read before writing

- `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/repo-claude-template.md` — the skeleton
  with the section headings and the line budget. Start from this.
- `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/examples/terraform-CLAUDE.md` — a
  filled-in example. **Read it when the repo has `.tf` files**, and read it
  anyway if the user is unsure what a good rule looks like: the shape transfers
  to any stack, only the specifics change.
- `${CLAUDE_PLUGIN_ROOT}/skills/crew-setup/examples/verify-terraform.json` — the
  matching verify map, showing which of the user's rules were mechanized instead
  of written into CLAUDE.md. Read these two together; the split between them is
  the point.

**Adapt, do not copy.** The example names real tables, real buckets, and a real
"business logic lives in `sql/procedures/`" fact. Those lines are valuable
precisely because they are specific to that repo — copying them into a different
one produces a file that is confidently wrong. Take the structure and the kinds
of rule; write the content from this repo.

Work through it with the user rather than filling the blanks yourself. The
sections you cannot answer from the code — the landmine, the do-not-touch paths,
what "done" means here — are the ones worth the most, and only they know them.

