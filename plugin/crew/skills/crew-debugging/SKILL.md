---
name: crew-debugging
description: Find the cause of a defect before proposing a fix - read errors, reproduce, check recent changes, gather evidence from this repo's code map and verification map, then form one hypothesis and test it minimally. Use when encountering any bug, test failure, flaky test, performance problem or unexpected behaviour, before writing a fix. Also use when a previous fix did not work, when three fixes have failed, or when time pressure makes guessing tempting.
---

# Systematic debugging

**Adapted from `superpowers:systematic-debugging` by Jesse Vincent, MIT
licensed. The full copyright and permission notice is in
`plugin/crew/NOTICE.md`.** Upstream: <https://github.com/obra/superpowers>.
The method below - the Iron Law, the four phases, the red flags and the
rationalisation table - is upstream's and is reproduced with its wording
intact. What crew changed is **where Phase 1 gets its evidence**: this
repository already wrote down what breaks here, and a debugging method that
re-derives it from the diff is throwing that away.

## Prefer the upstream skill when it is installed

`superpowers:systematic-debugging` is the source of this method and is
maintained. When it is present, use it.

1. Invoke `superpowers:systematic-debugging` with the `Skill` tool.
2. If that invocation returns, you are on the upstream method. Come back here
   for **"Phase 1 in a crew repository"** below, which is the part upstream
   does not have, and follow everything else from upstream.
3. If the invocation errors, the skill is not available - use this file, which
   is a complete copy of the method and needs nothing else.

**Say in your report which path you took.** "Ran `superpowers:systematic-debugging`
plus crew's Phase 1 evidence sources" and "ran crew's inline copy" are
different provenance, and a reader who cannot tell them apart cannot tell
whether they are reading upstream's current wording or crew's snapshot of it.

**The honest limit on that check.** A failed `Skill` invocation proves the
skill is absent **from this session** - not from the machine. A plugin can be
installed and disabled, or enabled in another project, and this session sees
the same error in every case. So report "not available in this session", never
"not installed". Do not go looking in the plugin cache to settle it: that is
crew reimplementing the harness's own resolution, it goes stale the moment the
harness changes, and the answer it produces would not change what you do next.

**This is a preference between two present methods, not a survival path.**
Crew bundles the full copy, so nothing is lost when upstream is missing; the
routing only decides whose wording you read. Do not report an absent
`superpowers` as a degraded run.

## Overview

**Core principle:** ALWAYS find root cause before attempting fixes. Symptom
fixes are failure.

**Violating the letter of this process is violating the spirit of debugging.**

## The Iron Law

```
NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST
```

If you haven't completed Phase 1, you cannot propose fixes.

## When to Use

Use for ANY technical issue:
- Test failures
- Bugs in production
- Unexpected behavior
- Performance problems
- Build failures
- Integration issues

**Use this ESPECIALLY when:**
- Under time pressure (emergencies make guessing tempting)
- "Just one quick fix" seems obvious
- You've already tried multiple fixes
- Previous fix didn't work
- You don't fully understand the issue

**Don't skip when:**
- Issue seems simple (simple bugs have root causes too)
- You're in a hurry (rushing guarantees rework)
- Manager wants it fixed NOW (systematic is faster than thrashing)

## The Four Phases

You MUST complete each phase before proceeding to the next.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

1. **Read Error Messages Carefully**
   - Don't skip past errors or warnings
   - They often contain the exact solution
   - Read stack traces completely
   - Note line numbers, file paths, error codes

2. **Reproduce Consistently**
   - Can you trigger it reliably?
   - What are the exact steps?
   - Does it happen every time?
   - If not reproducible -> gather more data, don't guess

3. **Check Recent Changes**
   - What changed that could cause this?
   - Git diff, recent commits
   - New dependencies, config changes
   - Environmental differences

4. **Gather Evidence in Multi-Component Systems**

   **WHEN system has multiple components (CI -> build -> signing, API ->
   service -> database):**

   **BEFORE proposing fixes, add diagnostic instrumentation:**
   ```
   For EACH component boundary:
     - Log what data enters component
     - Log what data exits component
     - Verify environment/config propagation
     - Check state at each layer

   Run once to gather evidence showing WHERE it breaks
   THEN analyze evidence to identify failing component
   THEN investigate that specific component
   ```

   **This reveals:** which layer fails - secrets reached the workflow, the
   workflow did not reach the build.

5. **Trace Data Flow**

   **WHEN error is deep in call stack:**

   See `root-cause-tracing.md` in this directory for the complete backward
   tracing technique.

   **Quick version:**
   - Where does bad value originate?
   - What called this with bad value?
   - Keep tracing up until you find the source
   - Fix at source, not at symptom

### Phase 1 in a crew repository - read what is already written down

**This is the only part of the method crew changed, and it is an addition
rather than a substitution.** Steps 1-5 above still run. What follows tells you
where this repository has already recorded its own failure modes, so that
Phase 1 starts from evidence instead of from an empty context.

Do this **before** instrumenting anything. Every line in these files cost
somebody real time in this repository, and reading four files is cheaper than
re-deriving one of them.

1. **The code map's landmines.** Read `.crew/codemap/INDEX.md`, then open every
   `.crew/codemap/<subsystem>.md` whose paths intersect the failing code and
   read its **`## Landmines`** section in full. A landmine is a defect that
   already shipped here once. The bug you are chasing is disproportionately
   likely to be one of them, and a landmine naming your symptom collapses
   Phases 1 through 3 into a single read.

   If `.crew/codemap/INDEX.md` does not exist, say so in your report and carry
   on. An absent map is a finding, not a blocker.

2. **An anchor behind HEAD means re-check, not ignore.** Each note's first line
   carries `anchor: <repo>@<sha>`. When it is behind, run
   `git diff --name-only <anchor>..HEAD -- <the paths that note cites>`. Empty
   output means the note is still current despite the lag. Only treat a claim
   as unreliable when the file it cites actually moved - and when it did, that
   diff is itself Phase 1 step 3 ("check recent changes"), already narrowed to
   the code you care about.

3. **The schema note, when the defect touches data.** If the symptom involves a
   migration, DDL, a model, a query or a column, read
   `.crew/codemap/schema-<datasource>.md`. Its `## Written by / Read by` block
   answers "if this column changes, what breaks" - which is the backward trace
   from `root-cause-tracing.md`, already done and written down. Its
   `## Unverified` block matters as much: a fact in there is one nobody has
   confirmed, so a hypothesis resting on it is resting on nothing and must be
   checked against a migration before you build on it.

4. **The code graph.** `graphify-out/graph.json` is the mechanical call and
   import graph. Use it for the "what called this?" step of a backward trace
   when the call chain crosses files, rather than grepping the name and reading
   whatever comes back. Check it is current before trusting it - a graph built
   before the change you are debugging does not contain the edge that broke.

5. **The verification map.** `.crew/verify.json` maps paths to the commands
   that check them. Two uses, and they are different:
   - **Reproduce with the mapped command**, not one you invented. It is the
     command the gate will run, so a fix that satisfies something else is a fix
     that fails the gate later.
   - **A defect in code whose mapped command passes is itself evidence** -
     either the reproduction is wrong or the check does not cover this
     behaviour, and which one it is changes what Phase 4 has to write.

**Report which of these you read and what each one gave you.** A note read and
a note skipped are indistinguishable in a summary that mentions neither, and
the reader cannot then tell whether the landmine was checked or missed. Where a
source was absent, empty or stale, say that too - "could not tell" is its own
finding and has to survive into the report rather than collapsing into silence.

### Phase 2: Pattern Analysis

**Find the pattern before fixing:**

1. **Find Working Examples**
   - Locate similar working code in same codebase
   - What works that's similar to what's broken?

2. **Compare Against References**
   - If implementing pattern, read reference implementation COMPLETELY
   - Don't skim - read every line
   - Understand the pattern fully before applying

3. **Identify Differences**
   - What's different between working and broken?
   - List every difference, however small
   - Don't assume "that can't matter"

4. **Understand Dependencies**
   - What other components does this need?
   - What settings, config, environment?
   - What assumptions does it make?

### Phase 3: Hypothesis and Testing

**Scientific method:**

1. **Form Single Hypothesis**
   - State clearly: "I think X is the root cause because Y"
   - Write it down
   - Be specific, not vague

2. **Test Minimally**
   - Make the SMALLEST possible change to test hypothesis
   - One variable at a time
   - Don't fix multiple things at once

3. **Verify Before Continuing**
   - Did it work? Yes -> Phase 4
   - Didn't work? Form NEW hypothesis
   - DON'T add more fixes on top

4. **When You Don't Know**
   - Say "I don't understand X"
   - Don't pretend to know
   - Ask for help
   - Research more

### Phase 4: Implementation

**Fix the root cause, not the symptom:**

1. **Create Failing Test Case**
   - Simplest possible reproduction
   - Automated test if possible
   - One-off test script if no framework
   - MUST have before fixing
   - `superpowers:test-driven-development` covers writing the failing test. If
     the repository has no harness to hang the test on, that is
     `crew:smoke-author`'s job - say so rather than improvising one.

2. **Implement Single Fix**
   - Address the root cause identified
   - ONE change at a time
   - No "while I'm here" improvements
   - No bundled refactoring

3. **Verify Fix**
   - Test passes now?
   - No other tests broken?
   - Issue actually resolved?
   - Run the `.crew/verify.json` commands the changed paths map to, and quote
     what they printed with the exit code.
     `superpowers:verification-before-completion` covers the general
     discipline.

4. **If Fix Doesn't Work**
   - STOP
   - Count: How many fixes have you tried?
   - If < 3: Return to Phase 1, re-analyze with new information
   - **If >= 3: STOP and question the architecture (step 5 below)**
   - DON'T attempt Fix #4 without architectural discussion

5. **If 3+ Fixes Failed: Question Architecture**

   **Pattern indicating architectural problem:**
   - Each fix reveals new shared state/coupling/problem in different place
   - Fixes require "massive refactoring" to implement
   - Each fix creates new symptoms elsewhere

   **STOP and question fundamentals:**
   - Is this pattern fundamentally sound?
   - Are we "sticking with it through sheer inertia"?
   - Should we refactor architecture vs. continue fixing symptoms?

   **Discuss with your human partner before attempting more fixes**

   This is NOT a failed hypothesis - this is a wrong architecture.

## Red Flags - STOP and Follow Process

If you catch yourself thinking:
- "Quick fix for now, investigate later"
- "Just try changing X and see if it works"
- "Add multiple changes, run tests"
- "Skip the test, I'll manually verify"
- "It's probably X, let me fix that"
- "I don't fully understand but this might work"
- "Pattern says X but I'll adapt it differently"
- "Here are the main problems: [lists fixes without investigation]"
- Proposing solutions before tracing data flow
- **"One more fix attempt" (when already tried 2+)**
- **Each fix reveals new problem in different place**

**ALL of these mean: STOP. Return to Phase 1.**

**If 3+ fixes failed:** Question the architecture (see Phase 4.5)

## Your human partner's signals you're doing it wrong

**Watch for these redirections:**
- "Is that not happening?" - You assumed without verifying
- "Will it show us...?" - You should have added evidence gathering
- "Stop guessing" - You're proposing fixes without understanding
- "Ultra-think this" - Question fundamentals, not just symptoms
- "We're stuck?" (frustrated) - Your approach isn't working

**When you see these:** STOP. Return to Phase 1.

## Common Rationalizations

| Excuse | Reality |
|--------|---------|
| "Issue is simple, don't need process" | Simple issues have root causes too. Process is fast for simple bugs. |
| "Emergency, no time for process" | Systematic debugging is FASTER than guess-and-check thrashing. |
| "Just try this first, then investigate" | First fix sets the pattern. Do it right from the start. |
| "I'll write test after confirming fix works" | Untested fixes don't stick. Test first proves it. |
| "Multiple fixes at once saves time" | Can't isolate what worked. Causes new bugs. |
| "Reference too long, I'll adapt the pattern" | Partial understanding guarantees bugs. Read it completely. |
| "I see the problem, let me fix it" | Seeing symptoms is not understanding root cause. |
| "One more fix attempt" (after 2+ failures) | 3+ failures = architectural problem. Question pattern, don't fix again. |
| "The code map is probably stale" | Behind is not wrong. Run the path diff - it is one command and it answers the question. |

## Quick Reference

| Phase | Key Activities | Success Criteria |
|-------|---------------|------------------|
| **1. Root Cause** | Read errors, reproduce, check changes, read the codemap landmines, gather evidence | Understand WHAT and WHY |
| **2. Pattern** | Find working examples, compare | Identify differences |
| **3. Hypothesis** | Form theory, test minimally | Confirmed or new hypothesis |
| **4. Implementation** | Create test, fix, verify | Bug resolved, tests pass |

## When Process Reveals "No Root Cause"

If systematic investigation reveals issue is truly environmental,
timing-dependent, or external:

1. You've completed the process
2. Document what you investigated
3. Implement appropriate handling (retry, timeout, error message)
4. Add monitoring/logging for future investigation

**But:** 95% of "no root cause" cases are incomplete investigation.

**And record it where the next session will find it.** A cause established here
is a landmine for the codemap note covering those paths - that is how the
evidence source in Phase 1 stays worth reading. A defect diagnosed and never
written down is one the next session pays for again.

## Supporting Techniques

These techniques are part of systematic debugging and available in this
directory:

- **`root-cause-tracing.md`** - Trace bugs backward through call stack to find
  original trigger
- **`defense-in-depth.md`** - Add validation at multiple layers after finding
  root cause
- **`condition-based-waiting.md`** - Replace arbitrary timeouts with condition
  polling
- **`find-polluter.sh`** - Bisect a test suite to find which test creates
  unwanted files or state

## Pressure tests

`test-pressure-1.md`, `test-pressure-2.md`, `test-pressure-3.md` and
`test-academic.md` in this directory are upstream's adversarial scenarios.
They are not documentation and they are not examples - they are the check on
whether the Iron Law survives the three situations that actually break it:
money burning per minute, four hours of sunk cost at 8pm, and a senior engineer
on a call saying they have seen this a hundred times. `test-academic.md` is the
control: it asks what the skill says, under no pressure at all, so a model that
answers it correctly and then folds under `test-pressure-1.md` has demonstrated
that it knows the method and abandons it - which is the failure mode worth
catching.

**These ship with crew deliberately.** The method without them is a document
everyone agrees with and nobody follows at the moment it matters. Run them
against any change to this skill's wording, and against a model newly assigned
to a crew role that debugs.
