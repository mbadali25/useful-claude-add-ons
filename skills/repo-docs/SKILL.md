---
name: repo-docs
description: Generate and keep up to date a complete documentation set for a codebase - CLAUDE.md (repo /init), root and per-directory README.md files, application/API reference docs covering endpoints and functions, an architecture design document, TODO.md, SECURITY.md, CHANGELOG.md, and handoff notes for the next person or session. Use this skill whenever the user asks to document a repo or app, write or refresh a README, produce handoff or onboarding notes, draft an architecture doc, build an API or function reference, start or update a changelog, create a TODO or security doc, run or verify /init and CLAUDE.md, or says anything like "the docs are stale", "document this codebase", "I'm handing this project off", "write up what we did", "wrap up this session", or "get this repo ready for someone else". Also use it proactively at the end of a substantial coding session, before a handoff, or after a large refactor, even if the user only asks for one of these documents - offer the rest.
---

# Repo Docs

Produce and maintain a coherent documentation set for a codebase. The value is not in
writing eight files once; it is in writing them so they can be *re-run* against a changed
repo without destroying human edits and without drifting from the code.

## The two rules that matter most

**1. Ground everything in the code.** Never document a function, endpoint, env var, or
data flow you have not read. Auto-generated docs fail almost exclusively by confident
invention — an endpoint that was renamed, a config key that never existed. If you cannot
find it in the source, either leave it out or mark it `<!-- unverified -->` with a note.
Every API entry and architecture claim should be traceable to a real `path/to/file.py:42`.

**2. Never leak secrets.** You will be reading `.env` files, configs, and CI definitions.
Document that a secret *exists* and where it is read from; never write the value. If you
find a live credential committed to the repo, stop, tell the user directly, and add it to
SECURITY.md as an unresolved finding — do not paste the value into any document.

## Artifacts

| Artifact | Default location | Purpose |
|---|---|---|
| CLAUDE.md | repo root | Working instructions for Claude: commands, conventions, gotchas |
| README.md | repo root | What it is, how to run it, where to look next |
| README.md | each significant directory | What lives here, why, and how it connects |
| API / reference | `docs/API.md` | Endpoints, CLI commands, public functions, events |
| Architecture | `docs/ARCHITECTURE.md` | Components, data flow, decisions, diagram |
| TODO | `TODO.md` | Prioritized, sourced backlog |
| Security | `SECURITY.md` | Posture, boundaries, secrets handling, findings |
| Changelog | `CHANGELOG.md` | Keep a Changelog format, derived from git history |
| Handoff notes | `docs/HANDOFF.md` | State of play for whoever picks this up next |

Follow whatever the repo already does over these defaults. If docs live in `documentation/`
or the changelog is `HISTORY.md`, keep it there; adopt the existing house style rather
than imposing this one.

## Workflow

### 1. Scope the job

Determine which of three modes you are in, and say which one you picked:

- **Bootstrap** — few or no docs exist. Generate the full set.
- **Refresh** — docs exist. Update only what the code changed out from under them.
- **Single artifact** — the user asked for one thing (e.g. "write handoff notes").
  Do that well, then offer the rest in one line rather than silently expanding scope.

For bootstrap on a repo of any size, confirm scope before writing: which directories,
whether per-directory READMEs are wanted everywhere or only in top-level packages, and
whether docs go in `docs/` or root. Cheap question, expensive mistake.

### 2. Survey the repo

```bash
python scripts/repo_survey.py /path/to/repo --json > /tmp/survey.json
```

This inventories directories, languages, entry points, dependency manifests, config and
env files, existing docs, git metadata, and — if a previous run left a manifest — which
files changed since. Read the summary, then read the actual code: entry points first,
then routing/CLI definitions, then the modules the entry points import. Tests are the
best available specification of intended behavior; read them when the source is ambiguous.

`references/extraction.md` has per-language and per-framework guidance for locating
routes, exported functions, background jobs, and config surfaces. Read it when you hit a
stack you are not immediately fluent in.

### 3. Write in dependency order

Later documents cite earlier ones, so order matters:

CLAUDE.md → root README → ARCHITECTURE → API reference → per-directory READMEs →
SECURITY → TODO → CHANGELOG → HANDOFF

HANDOFF goes last because it summarizes the state including what you just changed.

Templates and required sections for each artifact are in `references/templates.md`.
Read it before writing the first artifact.

### 4. Verify before reporting

Run these checks; they catch the errors that make generated docs untrustworthy:

- Every `file:line` reference resolves to a real file, and the symbol is on/near that line.
- Every relative link in every document resolves to an existing path.
- Every command in a README or CLAUDE.md exists in `package.json` scripts / `Makefile` /
  `pyproject.toml` / equivalent. Do not invent `npm run dev` because it is conventional.
- No secret values appear in any generated file. `repo_survey.py --secrets-scan` flags
  likely credentials in your output files.
- Managed blocks are intact and balanced (see below).

### 5. Report

Tell the user what you created, what you updated, what you deliberately left alone, and —
importantly — what you could not verify. A short list of open questions is more useful
than a confident document with three guesses buried in it.

## Idempotent updates

This is what makes the skill re-runnable. Content this skill owns goes inside markers:

```markdown
<!-- repo-docs:begin id=api-endpoints hash=a1b2c3 -->
...generated content...
<!-- repo-docs:end id=api-endpoints -->
```

Rules:

- **Only rewrite inside your own markers.** Text outside them is human-authored. Leave it
  exactly as found, even if you disagree with it.
- If a human has clearly edited inside a managed block (the content no longer matches the
  recorded `hash`), do not silently overwrite. Preserve their text, write your update
  below it under a `> Note: generated update, prior text preserved above` line, and flag
  it in your report.
- On a document with no markers (pre-existing hand-written README), do not retrofit
  markers across the whole file. Append your generated sections in markers at the end, or
  ask first.
- Released CHANGELOG sections are immutable. Only `## [Unreleased]` is editable.
- Completed TODO items move to a `## Done` section with a date; they are not deleted,
  because "was this ever done?" is a real question a month later.

State lives in `docs/.repo-docs.json`: last run timestamp, commit SHA, artifacts written,
block hashes. `repo_survey.py` reads it to compute what changed. Update it at the end of
every run.

## Ensuring /init and CLAUDE.md

Check for `CLAUDE.md` at the repo root (also check `.claude/CLAUDE.md`).

- If it exists, refresh it against current reality: are the build/test commands still
  correct, do the referenced paths still exist, are new conventions captured?
- If it does not exist and you are running in Claude Code, run `/init` and then improve
  its output — `/init` gives a decent skeleton but rarely captures the gotchas.
- If `/init` is unavailable (Claude.ai, Cowork, API), write CLAUDE.md directly using the
  template in `references/templates.md`. Note in your report that it was written manually
  rather than via `/init`, so the user knows.

A good CLAUDE.md is short and specific: the commands that actually work, the conventions
that are not obvious from reading one file, and the traps. Not a restatement of the README.

## Changelog generation

```bash
python scripts/git_changelog.py /path/to/repo --since-tag auto
```

Groups commits since the last tag into Keep a Changelog categories, using conventional
commit prefixes where present and falling back to keyword heuristics. Treat the output as
a **draft**: rewrite entries in user-facing language. `fix(parser): handle null in
tokenize()` becomes "Fixed a crash when parsing files with empty lines." Drop pure-noise
commits (merges, formatting, dependency bumps unless security-relevant). Cluster the ten
commits that were one feature into one entry.

If the repo has no tags, treat all history as `[Unreleased]` and say so.

## Security document scope

SECURITY.md here is a *defensive posture* document: how to report a vulnerability, what
the trust boundaries are, how secrets and authn/authz are handled, what dependency and
data-handling risks exist, and what is explicitly out of scope.

Document weaknesses at the level a maintainer needs to act — "the admin endpoints in
`routes/admin.py` have no authorization check" — not as a reproducible exploit. If you
find something that looks seriously exploitable, tell the user in conversation and record
it as a finding with a severity and a suggested fix, rather than writing a walkthrough
into a file that lives in the repo.

Never invent a CVE, a compliance claim, or a security guarantee the code does not provide.
"No rate limiting is implemented" is useful. "Rate limiting protects all endpoints" when
you have not verified it is worse than saying nothing.

## When the repo is large

Do not try to read 4,000 files. Sample deliberately:

- Read all entry points, route definitions, config, and schema/model files in full.
- For everything else, use the survey's per-directory language and size breakdown, read
  the largest and most-imported modules, and describe the rest at directory granularity.
- Write per-directory READMEs top-down and stop at the depth where a directory no longer
  has a distinct responsibility. A `utils/` with four files does not need a README per file.
- Say in the docs which parts were surveyed shallowly. Honest coverage beats fake completeness.

## Reference files

- `references/templates.md` — required structure and templates for all nine artifacts. Read
  before writing.
- `references/extraction.md` — how to find routes, functions, jobs, and config across common
  languages and frameworks. Read when the stack is unfamiliar.

## Scripts

- `scripts/repo_survey.py` — repo inventory, doc status, change detection, secrets scan.
- `scripts/git_changelog.py` — commits since last tag, grouped into changelog categories.

Both are plain Python 3, no third-party dependencies. Run `--help` for options.
