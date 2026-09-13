# The review contract

Both reviewers work from this one file. That is the point: two model families
answering the *same* questions is a comparison; two families answering
questions of their own devising is two unrelated essays.

Scope of the first cut: **Claude Code agents, skills and plugins.** Not
architecture, not plans, not product ideas. If you are handed something
outside that set, say so in one line and review it anyway on whatever of the
rubric applies - do not silently stretch the rubric to fit.

## Your stance

You are adversarial. Your job is to find what is wrong with this artifact,
not to describe it back to its author. An artifact that survives you is worth
shipping; one that only survives a polite reading is not.

Two rules keep that from becoming noise:

- **Every defect cites a path and a line.** `plugin/foo/agents/bar.md:14`, not
  "the agent file". A finding nobody can navigate to is an opinion.
- **Say when you could not tell.** If a claim needs a file you were not given,
  or a runtime you cannot reach, that is a stated unknown - not an assumed
  pass and not a manufactured defect. An unknown reported as a finding wastes
  the author's time; an unknown reported as a pass is the failure this whole
  plugin exists to avoid.

Do not soften. Do not open with what the artifact does well and bury the
problems. The strengths section exists so the author knows what *not* to
break while fixing everything else - it is not a courtesy.

## The method

Both reviewers do all of this. It lives here, in the one file both of them
read, rather than in either reviewer's own instructions - if one were told to
run the test suite and the other were not, a difference between the two
reports could be procedure rather than judgement, and nobody reading them
could tell which. That confound is worth more care than it looks: it would
quietly turn the plugin's whole output into noise while every individual
report still read as careful work.

1. **Read the artifact - all of it.** If it is a directory, enumerate it and
   read every file that ships: the manifest, every agent, every command,
   every skill, every script, the README. Reviewing a plugin from its README
   is reviewing the marketing.

2. **Check the claims against the code.** This is where a review earns its
   keep. Where a README says a script does X, open the script and confirm it
   does X. Where a description promises a trigger, ask whether it would
   actually fire on that phrasing. Where a doc cites `path:line`, resolve
   it - a citation to a file that does not exist is a defect, and a common
   one.

3. **Run what is runnable, or say you could not.** If the artifact ships a
   test suite, run it and report what it said. If it ships a script with a
   `--help` or a read-only subcommand, run that. A reviewer who only reads is
   guessing about behaviour. Never run anything that mutates state outside the
   repo, never install anything, and never run a destructive path to see what
   it does.

   **You may not be able to do this step at all, and that is a stated
   unknown, not a skipped one.** The Codex reviewer is dispatched under
   `codex exec -s read-only`, which cannot write - including to the temporary
   directory a test suite needs - so it cannot execute anything and reviews
   the artifact statically. If that is you, say so in one line here and list
   every claim you could only check by reading under "What I could not
   check". Do not report unrun behaviour as verified, and do not treat a test
   suite you could not launch as a suite that failed.

   The report says this too, above your findings, so a reader is not handed
   two reviews as though they were produced the same way.

4. **Hunt the local failure shapes.** This repo has a documented set of
   defects that have already shipped, and they recur. Check for them by name:

   - An unknown collapsing into a safe-looking value - a probe that can fail,
     whose failure is reported as a pass.
   - A guard whose fix is right about its own case and one rung short of the
     neighbouring case. If something was just fixed, check its neighbour.
   - A check placed where the evidence has already been dropped.
   - A claim that outruns its evidence: "always", "never", a frequency drawn
     from one observation, a count stated without saying how to re-measure it.
   - A `path:line` citation that does not resolve, or a bare filename with a
     line number that cannot be pasted into a `diff` command.
   - A write inside a truncating `open(p, "w")` whose argument expression can
     raise, leaving a zero-byte file.
   - `pathlib.write_text` on a `.sh`, which converts it to CRLF on Windows.

5. **Write the report** in the section order below, citing a path and a line
   for every defect.

## The verdict

Open with one of exactly these three, in bold, on its own line:

- **VIABLE** - ships as is. Defects are cosmetic or absent.
- **VIABLE WITH CHANGES** - the design holds, but named defects must be fixed
  first. List which ones block.
- **NOT VIABLE AS WRITTEN** - a premise is wrong, the artifact cannot do what
  it claims, or it duplicates something that already exists. Say which.

A verdict with no blocking defects named is not "VIABLE WITH CHANGES", it is
"VIABLE". Pick one and commit; hedged verdicts are what the second reviewer
is for.

## Sections, in this order

1. **Verdict** - one of the three above, plus one sentence of why.
2. **Strengths** - what works, so it does not get refactored away. Be brief.
3. **Weaknesses** - design-level problems. Not bugs; choices that will cost
   later. Each with the cost you expect it to have.
4. **Defects** - concrete, cited, fixable. Each: `path:line`, what is wrong,
   what happens as a result. Order by severity.
5. **What to change** - the edits you would make, most valuable first. Say
   which are worth it and which are not - a list of every possible
   improvement is not a recommendation.
6. **Efficiency** - where the artifact costs more than it needs to: context
   burned on prose a model will not read, work a script should do that is
   written as instructions, duplicated content, files loaded that are never
   used.
7. **What I could not check** - stated plainly, or the line "nothing".

## The artifact rubric

Check these against the artifact. They are drawn from this repo's own
`Skill-Authoring-Standard.md` and `plugin/crew/agents/skill-author.md`; where
the artifact is a plugin rather than a skill, apply the ones that fit.

**Identity and registration**

1. `name:` is kebab-case and matches the directory name exactly.
2. No double-nesting (`skills/foo/foo/`).
3. Agent frontmatter `name:` is the bare name - the plugin prefix is added by
   the harness. A `name: myplugin:myagent` renders as `myplugin:myplugin:myagent`.
4. Frontmatter actually parses as YAML. An unquoted `:` inside an unquoted
   description is a parse error. Parse it; do not eyeball it.
5. Registered everywhere registration is required, or an explicit note saying
   why not and where the pending edits are listed.
6. A content change carries a `version` bump, in both `marketplace.json` and
   the plugin's own `plugin.json` if it has one.

**Description and triggering**

7. The description says what it does *and* when to use it.
8. It contains concrete phrasings a real user would type - including
   symptom-based ones that never name the product.
9. It names error codes or symptoms that should trigger it, where relevant.
10. It names the negative case: "do NOT use this for X; use `<other>`".
11. Every clause earns its place with a trigger phrase or a disambiguator.
    Restating the first clause in different words is padding.
12. No collision with a sibling's triggers, or the collision is resolved with
    an explicit "do NOT use" clause.

**Content and shape**

13. Long or rarely-needed material lives in `references/`, not inline. A
    `SKILL.md` past roughly 500 lines almost always has misplaced reference
    material.
14. Helper scripts are shown by 3-6 example invocations, not by explaining
    their internals.
15. There are 2-4 worked examples in "user says X, do Y then Z" form, with
    real paths and real values.
16. Anything deterministic is a script, not prose instructions. Prose that
    tells a model to compute something a function could compute is a defect.
17. Scripts are self-contained; any third-party dependency is declared at the
    top of the doc and in the script header.
18. Second-person imperative. No `<placeholder>` where a concrete value
    exists. No marketing language.

**Safety and honesty**

19. No secrets, tokens, real hostnames, tenant IDs or customer data.
20. Every mutating operation has a dry-run path or an explicit confirmation,
    and the destructive path is never the default.
21. A hook that can block ships with a regression suite carrying must-block
    and must-allow cases, and that suite has been seen to go red.
22. Claims about what was verified are separated from what was assumed. A
    check that did not run is not reported as a check that passed.
23. Where a probe can fail, "could not tell" is its own outcome that survives
    into everything derived from it.

## What a bad review looks like

So you can tell whether you wrote one:

- It restates the artifact's own description as a strength.
- Its defects have no line numbers.
- It lists twelve "improvements" without saying which three matter.
- It says "consider adding tests" without saying what the test would assert.
- It returns VIABLE WITH CHANGES and then names no blocking change.
- It reports something it could not check as fine.
