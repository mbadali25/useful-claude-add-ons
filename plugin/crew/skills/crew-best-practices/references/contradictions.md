# The five contradictions the document records about itself

Source: <https://rosmur.github.io/claudecode-best-practices/> §5. These are the
document's own words for where its sources disagree — it does not resolve them,
and neither should a reader who cites it as settled practice.

Quoting these matters. A synthesis of twelve practitioners is often cited as
though it were consensus; §5 exists because five of its central questions are
not.

## 1. Skills versus context bloat

- **A:** create many specialised skills, with progressive disclosure.
- **B:** keep skills minimal, under 100 lines each.

Its own resolution: use progressive disclosure (main file under 500 lines plus
references), rely on auto-activation either way, and let the token budget decide
the count.

**crew:** 19 bundled skills, each main file under 500 lines with references
beside it. Position A, with B's size discipline applied per file.

## 2. Custom subagents versus the clone pattern

- **A:** build specialised subagents with clear roles.
- **B:** avoid them; spawn clones with `Task(…)`.

Its resolution: "Both work in practice … Most users should start with the clone
pattern."

**crew:** position A, deliberately. A clone inherits the context whose blind
spots a review exists to find, and crew's reason for existing is work where one
session cannot hold the whole picture. Recorded with its costs in
`docs/adr/0003-crew-departs-from-three-community-best-practices.md`.

## 3. Auto-formatting hooks

- **A:** auto-format after edits for consistency.
- **B:** never — it cites 160k tokens consumed over three rounds.

Its resolution: run the formatter manually between sessions.

**crew:** position B. No formatting hook, and `verify-gate` runs lint as a
*check* rather than a rewrite — a hook that edits files under the model is a
hook whose output nobody reviewed.

## 4. Planning mode versus manual plans

- **A:** use the built-in planning mode.
- **B:** use manual planning with custom prompts.

Its resolution: both — plan mode for research, then write dev docs from the
result.

**crew:** both, which is what `/crew:plan` plus `.work/` tickets is.

## 5. Documentation volume

- **A:** extensive — it cites a project with 850+ markdown files.
- **B:** minimal and targeted.

Its resolution: volume follows codebase size; skills for reusable patterns
(HOW), docs for project-specific architecture (WHAT), progressive disclosure
throughout, and point at documents rather than embedding them.

**crew:** the split it describes is the one crew already draws — `.crew/codemap/`
is the WHAT (per-subsystem prose, each claim marked DERIVED with a `path:line`
or JUDGEMENT, each carrying an anchor commit), and skills are the HOW.

## Reading the document after this

The five above are the places to be most careful quoting it, because both
positions have practitioners behind them. Everywhere else it is reporting
consensus, and the consensus is generally worth following — particularly on
context management, which it puts first and which crew's hooks implement.
