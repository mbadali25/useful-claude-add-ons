# Reconciling the codemap against the graph

The one procedure `/crew:upgrade` and `/crew:onboard --refresh` both run,
so the rules live here instead of twice. It's implemented by
`scripts/graph_reconcile.py` (pure text in, text out) and
`scripts/crew_upgrade.py` (the file I/O and reporting around it).

## KEEP versus DERIVE

Every `.crew/codemap/<subsystem>.md` has `## `-headed sections. Each one is
one of two kinds:

| Kind | Sections | Rule |
|---|---|---|
| `KEEP` | `Does`, `Landmines`, `Unverified` | Human judgment a graph can't produce. Passed through byte-identical, always. Never rewritten by this procedure. |
| `DERIVE` | `Entry points`, `Owns data`, `Calls out to` | Mechanical structure the graph knows better. Graph facts are **added**, never used to delete or silently overwrite an existing line. |

A heading outside both sets is left alone. A `DERIVE` heading the codemap
doesn't have yet is created — dropping the graph's facts for it in silence
would be a worse failure than adding a heading, and a codemap written before
anyone thought to record owned tables is exactly the one most likely to be
missing it.

## Comparison is by path, never by `path:line`

An anchor token in a codemap line looks like `` `src/foo.py:42` ``. Line
numbers drift on every refactor that doesn't change meaning; comparing on
the full token would turn that drift into a false "contradiction" on every
run. So:

- A new graph line whose file path is already claimed in the existing
  section is treated as an update to that entry (typically the line number
  moved) and is **not** added again.
- A path the codemap claims but the graph's derived facts don't mention for
  that heading is a **conflict** — a whole file the map claims and the graph
  doesn't corroborate, not a line that moved.

## Conflicts are reported, never applied

A conflict does not change the file it was found in. `graph_reconcile.py`
returns it in `conflicts`; `crew_upgrade.py` writes every run's conflicts
into `.crew/codemap/UPGRADE.md` under "Contradictions — kept in the map,
verify by hand" and leaves the codemap's existing line untouched.

The graph is not assumed to be right when it disagrees with a human-written
line — it misses generated call sites, reflection, and dynamic dispatch, and
either side can be the one that's wrong. Silently overwriting a `DERIVE`
section from a conflict would resolve that ambiguity by fiat instead of
surfacing it.

## Anchors are bumped only on sections actually re-verified

`crew_upgrade.py` bumps a codemap's `anchor:` line to HEAD only when this
run's reconcile touched at least one of its `DERIVE` sections (added a line
or created a missing heading). A codemap none of whose sections changed
keeps its old anchor and is listed in the report under "Anchors left stale
on purpose."

A false freshness claim is worse than an honest stale one — `crew-pm`'s
freshness check and `crew_state.knowledge.behind` both trust the anchor, and
that trust only holds if nothing bumps it without having actually looked.

## Invoking it

`crew_upgrade.py` takes the graph-derived facts as a JSON file, not inline
arguments:

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/crew-graph/scripts/crew_upgrade.py \
  --root <repo> --derived <path-to-derived.json>
```

The JSON shape it expects — one entry per subsystem, keyed by the same name
as its `.crew/codemap/<name>.md` file:

```json
{
  "<subsystem-name>": {
    "Entry points": ["- `src/foo.py:12` — handles the POST route"],
    "Owns data": ["- `users` table"],
    "Calls out to": ["- `src/bar.py` — via the shared queue client"]
  }
}
```

Only `DERIVE` headings belong in this file — `graph_reconcile.reconcile`
ignores any key that's in `KEEP` or unrecognized, so putting `Does` or
`Landmines` facts here has no effect either way. Producing this JSON from a
graph query is the calling command's job (`/crew:upgrade`, `/crew:onboard
--refresh`), not this skill's — it's the contract those commands write to,
not a script this skill runs on their behalf.

Without `--derived`, or with an unreadable/malformed file, `crew_upgrade.py`
treats it as `{}` and runs everything else (backup, config upgrade) with no
codemap changes.
