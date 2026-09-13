# rule-of-two

Two adversarial reviewers from **different model families** read the same
artifact against the same rubric, without seeing each other's findings, and
tell you whether it is viable, where it is weak, what defects it carries, and
what to change.

The name is the claim, and the plugin's main job is to avoid making that
claim falsely. **"Only one reviewer ran" is its own reported outcome.** If
Codex is missing, unauthenticated, or its model has been retired, the report
says plainly that this is one review and not two. It never presents a
single-family opinion under the Rule of Two name.

## What it reviews

Claude Code **agents, skills and plugins** - the artifacts themselves, not the
code they operate on. Not architecture, not implementation plans, not product
ideas.

**Do NOT use it for** architecture, implementation plans, product ideas or
code diffs. `crew` ships `architect-reviewer`, `planner` and `code-reviewer`
for those, and they are better at it.

What is actually new here is the **cross-family comparison**, not artifact
review as such. `plugin/crew/agents/skill-author.md:3` already says it "writes
and reviews Claude Code skills", so this plugin is not the first thing in the
repo to read a skill critically - it is the first to have two model families
read one against the same rubric and report honestly when only one of them
managed it. That distinction is worth stating precisely, because an earlier
draft of this file claimed the broader gap and a reviewer caught it against
`skill-author.md` on the first run.

`VoltAgent/awesome-claude-code-subagents` has adversarial reviewers for
architecture, code and security, and crew ships near-duplicates of those. Its
`project-idea-validator` is the genuinely adversarial entry, and the viability
verdict shape is mined from it. The artifact rubric comes from this repo's own
`Skill-Authoring-Standard.md` and `plugin/crew/agents/skill-author.md`.

An earlier draft of this section claimed nothing upstream reviews prompts, and
that `prompt-engineer` "writes prompts rather than critiquing them". A
reviewer checked that against the live file and it is wrong - its description
covers evaluating prompts, and its procedure asks for review of existing ones.
The narrower claim is the one that survives contact with the evidence: what is
new here is two model families reviewing one artifact against one rubric, with
coverage reported rather than assumed. The overclaim is left visible instead of
quietly deleted, because it is the same shape as every other defect in this
file's history - a claim that outran what anyone had checked.

## Commands

| Command | What it does |
|---|---|
| `/rule-of-two:review <path>` | Runs both reviewers on an agent, skill or plugin and renders one report |
| `/rule-of-two:config` | Shows the two models, their families, where the config came from, and whether a `codex` executable was found |

No hooks. A review tool is invoked deliberately; registering a hook would
have bought the sabotage-tested must-block/must-allow regression requirement
for nothing.

## How coverage is decided

`scripts/rule_of_two.py` owns this, because it is exactly the kind of
judgement that should not be left to a model mid-report. Coverage is an
explicit enum with five values:

| Coverage | Meaning | Headline |
|---|---|---|
| `TWO_CROSS_FAMILY` | Both ran, families resolved, families differ | two independent reviews; the Rule of Two held |
| `TWO_SAME_FAMILY` | Both ran, same family | one perspective wearing two names; did NOT hold |
| `TWO_FAMILY_UNKNOWN` | Both ran, a family would not resolve | **could not tell** - an unanswered question, not a passed check |
| `ONE_REVIEW` | One ran | **THIS IS ONE REVIEW, NOT TWO**, and why the other did not run |
| `NO_REVIEW` | Neither ran | nothing here has been checked |

`UNKNOWN` is a real family value, not a missing one, and it survives into
every line derived from it. This repo's recurring bug is an unknown
collapsing into the safe-looking value - a *missing* answer wearing the label
of a check that happened - and `crew_config.py --models` shipped exactly that
once, barring the only independent reviewer while clearing the author's own
family.

The word "independent" appears in a rendered report **only** under
`TWO_CROSS_FAMILY`. Not even in the negative: a reader skimming for the word
finds it either way, so the other four outcomes phrase it as "cross-family"
and never use the word at all. The suite asserts this.

**The title is governed too, not just the banner.** The first draft rendered
`# Rule of Two review` unconditionally and put the corrective banner
underneath it. A correct banner under a wrong title still leaves the wrong
four words in the line most likely to be pasted, screenshotted or skimmed
alone, so `render_title` derives from coverage exactly as the banner does.
Codex caught that on the first self-review; the Claude reviewer did not.

## What is allowed to count as a review

Two separate gates, both added after the first self-review found the guard
trusting its own inputs:

- **`ran` must be the literal boolean `True`.** It decides the headline, and
  it was previously coerced with `bool()`, so the string `"false"` read as a
  successful review. The string `"true"`, `1`, and `"yes"` are rejected too:
  a truthy string must never buy a review.
- **Success is stated by the caller, never inferred.** `record-claude` takes
  a required, mutually exclusive `--ran` / `--failed`. The first fix to the
  point above hardened `normalize_result` and then re-opened the same hole
  one rung upstream, where `record-claude` computed `ran` from the review
  file being non-empty - and a file containing "dispatch failed: model
  unavailable" is non-empty, so a failed dispatch rendered a full "the Rule
  of Two held" report. Non-empty text is now a necessary condition, not the
  whole test.
- **A successful run must carry review text.** "Ran and returned nothing" is
  not a review. Codex's review is taken from `--output-last-message`, not
  from stdout, because stdout carries a startup banner naming the model and
  the sandbox and an earlier version accepted that banner as findings. The
  diagnostics are kept separately as `log` and shown under the failure line,
  where they are worth most.

A review that ran but carries none of the rubric's three verdicts is *not*
downgraded to "did not run" - that would be brittle - but the report flags it
as having failed to answer the question it was asked. The verdict is matched
as a **whole line near the top**, not as a substring: a substring search was
worse than no check at all, because "This is unviable." contains VIABLE, and
so does "I cannot determine whether this is viable." Both satisfied the flag
whose entire job was to catch exactly that.

**What is NOT established**, stated here rather than left for a reader to
discover:

- **Which model actually served the request.** The recorded model is what the
  orchestrator asked for, so the report says "alias `fable`, requested as
  `claude-fable-5-1`" rather than implying the provider was observed. The
  cross-family check is over *configured* identities. No amount of
  prefix-table care fixes this; only a provider-attested model id would.
- **Whether Codex will actually work.** `/rule-of-two:config` reports
  `codex_found`, which is `shutil.which` and nothing else. Authentication,
  whether the configured model still exists, and account entitlement all fail
  at dispatch, not at discovery - so the command publishes
  `codex_auth_verified: false` alongside it and says so in words. An earlier
  version called the field `codex_available` and invited exactly the reading
  that an installed binary is a working reviewer.
- **The fallback retry.** `/rule-of-two:review` step 3 is prose instruction to
  a model, with no code path and therefore no test. A Fable dispatch could not
  be made to fail on demand to observe it.

## The test, and the sabotage check

```bash
python3 plugin/rule-of-two/scripts/_test/test_rule_of_two.py
python3 plugin/rule-of-two/scripts/_test/test_rule_of_two.py --sabotage
```

Every coverage assertion is made against the **rendered report text**, not
against `compute_coverage`. That is the load-bearing choice: a coverage value
computed correctly can still be dropped on the way to the page, and the
report is what a human acts on. Testing the function alone would pass while
the renderer lied - which is precisely what the unconditional title did.

The `codex` subprocess layer is **stubbed**, so the suite tests this code
rather than the local machine. The first version launched a real `codex exec`
on every run and discarded the result, which meant the suite's behaviour
depended on whether the machine had Codex installed and authenticated - and
left the success, non-zero-exit and empty-output paths untested on every
machine.

`--sabotage` breaks each guard in turn and asserts **the suite goes red for
every one**, then restores them all and asserts it goes green again:

1. the renderer always claims two independent reviews,
2. the title always carries the Rule of Two name,
3. the evidence gate accepts any truthy `ran`,
4. aliases match as loose prefixes,
5. the verdict is a substring search again.

None of these is hypothetical. Every one is a way this plugin has actually
been observed to fail, on its own self-reviews - the list grew from three to
five after the second round, which is the point of running it twice.

Each sabotage varies exactly one thing. A sabotage that also drops a
dictionary key would fail the suite for the wrong reason and prove nothing
about the guard it is aimed at, which happened once while writing this and is
worth avoiding on purpose.

Do not trust a check count written here - state the invariant, re-measure the
number. Run the suite and read its tail: it exits 0 with every check passing,
and the sabotage run names each sabotage it caught before returning
green. The counts move every time a case is added.

## Model spellings - verified, with controls

Two naming conventions are in play and **they are not interchangeable**.
Agent frontmatter takes a bare alias; a CLI `--model` flag takes a full id.
Both were tested here on 2026-09-12, each against a deliberate control with
an invented model name, because a tool that echoes any name you hand it into
its own banner proves nothing by printing it back.

**Claude, full id (`--model` form).** `claude-fable-5-1` exited **0** with no
model error. The control, `definitely-not-a-real-model-xyz`, exited **1**:

```
[claude-code:unrecognized_model] {"model":"definitely-not-a-real-model-xyz","query_source":"sdk"}
There's an issue with the selected model (definitely-not-a-real-model-xyz).
```

One caveat, recorded rather than smoothed over: the positive run returned
unrelated text instead of the requested `OK`, because the child session
loaded this machine's hooks and plugins. So what is actually established is
*exit 0 with no `unrecognized_model` error*, against *exit 1 with one* - not
a clean round trip. That is enough to settle the spelling and not enough to
call it an end-to-end dispatch test.

**Claude, alias (frontmatter form).** `fable`. Attested twice: this harness's
Agent tool accepts it as a model alias, and the control's own error text names
the valid set - "Switch to a public model alias (opus, sonnet, fable)".
`agents/reviewer-claude.md` therefore carries `model: fable`, not the full id.

**Codex.** `codex-cli 0.153.4`. `gpt-6-astra` exited **0** and replied exactly
`OK`. The control exited **1**:

```
ERROR: {"type":"error","status":400,"error":{"type":"invalid_request_error",
"message":"The 'definitely-not-a-real-model-xyz' model is not supported when
using Codex with a ChatGPT account."}}
```

Note that the control's banner still printed `model:
definitely-not-a-real-model-xyz` on its way to failing. That is the trap the
control exists to catch, and why a banner reading `model: gpt-6-astra` is not
evidence on its own.

Pin-then-fallback is configurable rather than hardcoded, for crew's own
stated reason: model names churn, and a hardcoded fallback is the next name
to churn. The default pairing is Fable falling back to Opus 5, against
`gpt-6-astra`.

The fallback is driven by `/rule-of-two:review` step 3, which dispatches the
subagent on `dispatch_order_claude[0]` and retries once on
`dispatch_order_claude[1]` **only** if the model was unavailable - never
because a review came back thin, which would quietly swap the model the
report names. In the first draft the config keys existed and nothing read
them: the agent's frontmatter alias was the only thing that decided the
model, so editing `.rule-of-two.json` changed the printout and not the
reviewer. Both reviewers flagged that independently, and it was the one
defect they agreed was blocking.

## Invoking Codex

`run_codex` in `scripts/rule_of_two.py` redirects **stdin from devnull** and
applies an explicit **timeout**, and maps a `TimeoutExpired` to *did not run*
rather than *ran and found nothing*.

Both are deliberate departures from crew, which is the anti-pattern here and
not the pattern. crew's real invocation is a shell snippet inside a command
prompt at `plugin/crew/commands/review.md:297`, with no stdin redirect and no
timeout at all. Nothing under `plugin/crew/hooks/scripts/` shells out to
`codex`; the `DEVNULL` and timeout constants there belong to its git calls.
An inherited stdin is a ten-minute stall that looks intermittent - `codex
exec` prints `Reading additional input from stdin...` even when it is
redirected, which is how you know it reads it.

## Configuration

Standalone by design. It **never** reads crew's config - not `qa.order`, not
`author_families`, not the provider list.

Resolution order, nearest first: `.rule-of-two.json` at the repo root, then
`~/.claude/rule-of-two/config.json`, then built-in defaults. Only the keys
present are overridden.

```json
{
  "claude": {
    "pin": "fable",
    "fallback": "opus",
    "pin_model_id": "claude-fable-5-1",
    "fallback_model_id": "claude-opus-5"
  },
  "codex": { "pin": "gpt-6-astra", "timeout_seconds": 900 }
}
```

`pin` and `fallback` are **dispatch aliases** - the namespace the Agent tool
and agent frontmatter accept. `pin_model_id` and `fallback_model_id` are the
full ids a CLI `--model` flag takes. They are not interchangeable, and
changing one without the other gives you a config that says one thing and
dispatches another.

Valid JSON that is not an object - a bare list, a string - falls back to the
defaults and says so in `config_source`, rather than raising an
`AttributeError` three frames down.

The risk this accepts is a second implementation of cross-family
independence, whose failure mode is quietly clearing a same-family reviewer.
What keeps it tolerable: **this is not a solver.** It has exactly two
reviewers, fixed to different families by construction, and the only question
it asks is "are these two actually different, and did both run" - never
"search a list for an independent candidate". `FAMILY_PREFIXES` is a short
table over exactly two families and is meant to stay that small; read the
table rather than a count written here. If it ever needs a provider list,
revisit the standalone decision rather than growing the table.

It is **two** tables, and the split is load-bearing. Dispatch aliases
(`fable`, `opus`, `sonnet`, `haiku`, `gpt`, `codex`) are whole words matched
**exactly**; model ids match on a prefix that carries its own separator
(`o3-`, never `o3`). Anything else is `UNKNOWN`. For a guard whose thesis is
that "could not tell" must be its own outcome, erring toward `UNKNOWN` is the
only defensible direction - a wrong family reads as a passed check, an
unknown one reads as the open question it is.

That split exists because the first draft got it half right, and the half it
got wrong is instructive. One edit tightened the OpenAI prefixes from `o3` to
`o3-` and left the Anthropic aliases as loose prefixes, so `sonnetting`,
`fable-fiction` and `opus-not-a-real-model` all resolved confidently to
`anthropic` and rendered "the Rule of Two held". The fix was right about its
own case and one rung short of its neighbour - which is exactly where this
repo says to look after any guard fix, and exactly where the second reviewer
found it.

## Relationship to crew

Referenced, never depended on. The review runs, and the report renders,
whether or not crew is installed. If a `.crew/` directory is present,
`/rule-of-two:review` will *offer* to turn blocking defects into crew
tickets; if it is not, the findings are yours to act on and the command does
not suggest installing anything.

## Registration

**Registered at 0.1.0.** The entry is in `.claude-plugin/marketplace.json`,
the catalog rows are in the root `README.md` and `plugin/README.md`, the
section is in `plugin/PLUGINS.md`, and both install scripts carry
`rule-of-two` last in their plugin catalogs, in the same order with the same
text. `python3 scripts/check-marketplace.py` passes.

This plugin registers **no hooks**, so nothing here runs unless it is asked
to. It still ships off by default in the installer, because the whole
`repo-plugins` menu row does - a plugin can register a hook, so the row is
opted into explicitly rather than ticked for you.

Any later content change needs a version bump in **both**
`.claude-plugin/marketplace.json` and
`plugin/rule-of-two/.claude-plugin/plugin.json`: `check_versions` is
git-history based and fails when the directory has moved since the version was
last set, and `claude plugin update` compares declared versions, so an
unbumped edit never reaches a machine that already installed the old copy.

## The self-review

The first artifact this plugin reviewed was itself, three times, before it
shipped. All three rounds are worth recording because the result argues for the
design better than the design section does.

**Round one**, on the first draft: the two reviewers **disagreed on the
verdict** - Claude returned VIABLE WITH CHANGES, Codex returned NOT VIABLE AS
WRITTEN. They agreed on one blocking defect (configured `pin`/`fallback` that
nothing read) and each found blockers the other missed. Codex found that the
report title said "Rule of Two review" unconditionally while the banner
withdrew the claim, and that its own startup banner was being captured as
review text. Claude found that the renderer raised `KeyError` on a result
missing a key - the degraded input the report exists to describe.

**Round two**, on the fixed draft, is the one that justifies re-reviewing a
fix as hard as the guard. Codex found that the loose-prefix fix had been
applied to the OpenAI side and not the Anthropic side. Claude found that
hardening `ran` in `normalize_result` had been undone one rung upstream in
`record-claude`. Both fixes were right about their own case and one rung short
of the neighbour.

**Round three** did it again, and the most useful finding was that a fix had
made things *worse*. The round-two verdict fix stopped matching the token as a
substring and started matching a whole line - but allowed a leading `-` and
`>`, so a bulleted echo of the three options matched, and `re.search` returns
the earliest, meaning the most favourable verdict won. A reviewer explicitly
declining to answer was rendered as having passed the artifact. The flag whose
entire purpose was catching "did not answer the question" had started
supplying an answer instead. Claude found the list form, Codex found the
quoted form, and neither found both. Round three also found that the
degraded-input fix had been installed in `build_state` and not in `cmd_render`,
which never called it - the same crash, still shipping, one caller over.

By round three both reviewers returned **VIABLE WITH CHANGES** on the same
artifact, which is the closest thing to convergence this has produced. Every
round's reviewers found blockers the other family missed, in both directions.
That is the entire argument for the plugin, and the reason a single-family
report may not wear its name.

One finding no reviewer made, found by running the real pipeline: `assemble`
wrote the finished report and *then* exited 1, because printing it raised
`UnicodeEncodeError` on a cp1252 Windows console - the Codex half is full of
en-dashes. A caller checking the exit code would have concluded the review
failed while holding the completed report. Reading only the reviews would have
missed it; this is what running the thing buys that reviewing it does not.

## Layout

```
plugin/rule-of-two/
  .claude-plugin/plugin.json
  agents/reviewer-claude.md        model: fable - the Claude half
  commands/review.md               /rule-of-two:review <path>
  commands/config.md               /rule-of-two:config
  scripts/rule_of_two.py           config, families, codex, coverage, rendering
  scripts/_test/test_rule_of_two.py  the invariant suite + sabotage check
  templates/rubric.md              the one contract both reviewers work from
```

`templates/rubric.md` holds the **whole** method - how to read the artifact,
what to run, which failure shapes to hunt, the verdict shape, the section
order, the numbered checks. `agents/reviewer-claude.md` defers to it rather
than restating it, and `build-prompt` hands Codex the same file. An earlier
draft kept the local failure shapes in the agent file only, so Claude was
told to hunt them and Codex was not - which would have made every difference
between the two reports ambiguous between procedure and judgement, while each
report still read as careful work. The suite asserts the agent does not grow
its own copy back.

There is no `agents/reviewer-codex.md`, deliberately. An agent file can only
carry `model: sonnet|opus|fable` - a Claude wrapper wearing an independence
label, which is precisely the failure this plugin exists to prevent. The
Codex review text comes from the `codex` CLI, invoked by `rule_of_two.py`.
