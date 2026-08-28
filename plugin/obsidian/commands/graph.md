---
description: Build or update a graphify code graph for a repo, keeping it outside the vault
argument-hint: [repo-path, default cwd]
allowed-tools: Read, Write, Bash, PowerShell
---

Build or update the graphify code graph for: $1 (default: the current repo).

**The full graph never lives inside the Obsidian vault.** A repo of any size
produces a graph with more notes than the vault's own content - the crew
plugin's own experience is a graph running into the thousands of notes for a
single repo. Putting that inside the configured vault would drown the ~1,000
notes that are actually the user's memory in generated ones. This command
enforces the split; do not put generated output in the vault under any
argument.

1. Check `graphify --version`; if missing, install it (`graphify install
   --platform claude` per its own CLI, or point at its install docs) before
   proceeding - do not silently skip the build.
2. Resolve the source repo path (`$1` or cwd) and its current commit sha.
3. Run the build (`graphify update <path>` for an existing graph, first build
   otherwise) with output directed at a location **outside** the configured
   vault - the vault's own `codegraphs/` convention (if this vault has one)
   names an external sibling directory per repo, e.g.
   `<vault-parent>/<vault-name>-codegraphs/<repo-name>/`. Read the vault's own
   `CLAUDE.md` for its exact convention before inventing a new one.
4. Write or refresh a **stub note** inside the vault's `codegraphs/` folder:
   node/edge/note counts, the commit sha the graph was built at, and the
   absolute path to the real graph and its canvas - never the graph content
   itself.
5. Report node/edge/note counts and where the stub landed.

If the vault has no established convention for this yet, propose one (mirror
the shape above) and confirm before writing the first stub note.
