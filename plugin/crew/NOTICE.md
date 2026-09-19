# Third-party notices — `crew`

Material in this plugin that was written by somebody else, and the notice its
licence requires be carried with it.

Keeping this file is not a formality. The MIT licence's one substantive
condition is that the copyright and permission notice travel with every copy
and substantial portion of the software. `crew` ships a copy, so `crew` ships
the notice.

---

## `plugin/crew/skills/crew-debugging/`

Adapted from the `systematic-debugging` skill in **superpowers** by Jesse
Vincent.

- **Upstream:** <https://github.com/obra/superpowers>
- **Taken from:** the `superpowers` plugin, version `6.3.0`, at
  `skills/systematic-debugging/`
- **Licence:** MIT

**What was copied:** `SKILL.md`, `root-cause-tracing.md`,
`defense-in-depth.md`, `condition-based-waiting.md`, `find-polluter.sh`,
`test-pressure-1.md`, `test-pressure-2.md`, `test-pressure-3.md` and
`test-academic.md`.

**What crew changed:** `SKILL.md` gained an attribution header, a routing
section preferring the upstream skill where it is installed, and a
"Phase 1 in a crew repository" section naming crew's own evidence sources
(`.crew/codemap/`, `graphify-out/graph.json`, `.crew/verify.json`). The four
test files had their skill path repointed at crew's copy.
`condition-based-waiting.md` lost its pointer to
`condition-based-waiting-example.ts`, which was not copied. The method itself —
the Iron Law, the four phases, the red flags, the rationalisation table — is
upstream's, reproduced with its wording intact. `find-polluter.sh` also
carries behavioural fixes on top of the upstream copy — quoted per-file
invocation, an isolated runner stdin, a runner-failure-vs-test-failure
distinction (only exit 126/127 aborts as "RUNNER FAILED", checked only
after the pollution check itself; pollution is checked first and
unconditionally, regardless of exit code, and an ordinary failure without
pollution is recorded and bisection continues), a non-zero exit when no
test actually ran or when a test failed without producing pollution, a
refusal of any test pattern containing more than one `**`, and a checked
`find` exit status out of the discovery pipeline (`DISCOVERY FAILED` on an
unreadable subtree, instead of silently proceeding with a partial list) —
see its own header comment for the current list and why. Four of these
fixes' upstream reproduction steps are recorded in `TODO.md` at the repo
root (whitespace splitting, the swallowed runner exit, the zero-tests-ran
false clean, and the discovery-pipeline exit status); the stdin-isolation
and exit-classification-ordering fixes address defects crew's own earlier
fixes introduced, not upstream ones, so they are not filed there.

**The multi-`**` refusal fixes a crew-introduced defect, not an upstream
one — corrected 2026-09-19 after first (wrongly) filing it in `TODO.md`'s
upstream list.** Upstream's `find` translation handles a `**/x` pattern one
way, with no fallback. Crew added a second alternative,
`-o -path "./${TEST_PATTERN//\*\*\//}"`, to also match a file directly
under the base directory (upstream's version misses `src/top.test.ts` for
a `src/**/*.test.ts` pattern). That addition is what breaks on a SECOND
`**`: with `src/**/tests/**/*.test.ts`, the collapsed alternative reduces
to `src/tests/*.test.ts` while the uncollapsed one requires at least one
directory at every `**`, so a file like `src/pkg/tests/bad.test.ts`
matches neither and is silently never discovered. Since the bug is in
code this plugin added, refusing the pattern outright (`UNSUPPORTED
PATTERN`) is a crew fix to a crew defect, and belongs here rather than
in the upstream-reproduction list.

**What was deliberately not copied:** `CREATION-LOG.md` and
`condition-based-waiting-example.ts`.

### MIT License

```
MIT License

Copyright (c) 2025 Jesse Vincent

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

---

## A note on this repository's two licences

The repository root `LICENSE` is GPL-2.0; `plugin/crew/.claude-plugin/plugin.json`
declares `"license": "MIT"`. That predates this file and is **not** a problem
for the material above: MIT is compatible with GPL-2.0 in this direction, so
MIT-licensed code may be distributed as part of a GPL-2.0 work, and the
attribution obligation is discharged by this notice either way.

The inconsistency between the two declarations is a separate question about
what `crew` itself is licensed as, recorded in `TODO.md` rather than resolved
here, because guessing at it would change the terms this plugin ships under.
