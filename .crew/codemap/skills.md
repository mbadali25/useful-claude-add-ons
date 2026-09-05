# skills

anchor: useful-claude-add-ons@875c9c6f
verified: 2026-09-05

## Does

Every directory under `skills/` is one installable Claude Code Skill: a
`SKILL.md` carrying `name` + `description` frontmatter for auto-discovery, plus
optional `references/`, `scripts/` and `assets/`. 25 are registered. The largest
area in the repo by node count (2022 nodes, 156 files) but the least connected —
148 graph communities across those 156 files, i.e. they are near-independent
documents rather than a system. Domain and bundled assets vary; the SKILL.md
contract and the registration mechanics are identical across all of them.

## Entry points

- `skills/<name>/SKILL.md` — the unit of installation. There is no other.
- `skills/README.md` — the overview table; one row per skill, five columns.
- `skills/UPDATE.md` — mirrored into `README.md` by `scripts/sync-updates.py`.

## Owns data

- `.claude-plugin/marketplace.json` entries with `source: ./skills/<name>` —
  authored here, validated by `scripts/check-marketplace.py`.

## Calls out to

- `scripts/` — every skill is subject to `check-marketplace.py`'s registration
  and version rules.
- `plugin/UPDATE.md`, `CHANGELOG.md`, `Skill-Pipeline.md` — documentation
  mirrors and the authoring process.

## Landmines

- **Content change without a version bump, in the same commit, is the silent
  one.** `scripts/check-marketplace.py:298` (`check_versions`) walks
  `marketplace.json`'s git history via `:280` (`version_set_at`) to find where
  a skill's declared version was last set, and fails if `skills/<name>/`
  changed since. `claude plugin update` compares only the declared version
  string, so a missed bump leaves every machine that already installed it stale
  forever, while the repo looks correct.
- **A new skill is not finished until it is registered in four places** —
  `marketplace.json`; `skills/README.md`'s table; `README.md` inside the
  `<!-- BEGIN skills/README.md -->` block plus the skill count; and both
  install scripts (`SKILL_KEYS`/`SKILL_NAME` in the `.sh`,
  `$script:SkillCatalog` in the `.ps1`, same order and text). Enforced by
  `check_registration` (`scripts/check-marketplace.py:94`), `check_catalogs`
  (`:166`) and `check_docs` (`:263`).
- **`REQUIRED_FIELDS` is exactly `("name", "source", "description",
  "version")`** — `scripts/check-marketplace.py:33`.
- **Never commit a nested `marketplace.json`** inside a skill directory. The
  repo root's is the only marketplace; a nested one makes the directory look
  like a second marketplace to `claude plugin marketplace add`.
- **Renaming or removing a skill is the same four places, in reverse.** The
  count in `README.md` is a literal number and is easy to leave behind.

## Unverified

- The body of `check_skill_manifests` (`scripts/check-marketplace.py:122`). It
  exists and sits between `check_registration` and `check_plugin_manifests`;
  which SKILL.md frontmatter fields it cross-checks against the marketplace
  entry was not read.
- Whether any skill entry requires frontmatter beyond `REQUIRED_FIELDS` (a
  `license` or `allowed-tools` key, say). Not confirmed across the sampled
  SKILL.md files.
- Whether the picker's line-clip rule (`pick_fit` / `Format-PickerLine`) is
  actually violated by any current skill label length. The rule is stated
  repo-wide in `CLAUDE.md`; it was not measured against real labels.
