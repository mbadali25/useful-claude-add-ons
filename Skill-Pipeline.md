# Skill Pipeline

How a skill moves from an idea to something the whole team can `claude plugin install`. This is the CI/CD model for this repo — there's no build step (skills are just markdown + scripts), so the "pipeline" is the sequence of checks and gates below, run by a human or a lightweight CI job.

```
Author -> Validate -> Review -> Merge -> Release -> Distribute
```

## Stage 1 — Author

- Follow [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) for structure, frontmatter, and style.
- Work on a branch: `git checkout -b skill/<skill-name>` for a new skill, `skill/<skill-name>-<change>` for an update.
- Keep the branch scoped to one skill. Cross-cutting changes (this doc, the authoring standard, install scripts) get their own branch.

## Stage 2 — Validate

Run before opening a PR:

```bash
# Structural/manifest validation
claude plugin validate .

# Frontmatter sanity check — every SKILL.md must have non-empty name/description
# and name must match its directory
for f in skills/*/SKILL.md; do
  dir=$(basename "$(dirname "$f")")
  name=$(grep -m1 '^name:' "$f" | sed 's/name: *//')
  [ "$dir" = "$name" ] || { echo "MISMATCH: $f (dir=$dir, name=$name)"; exit 1; }
done

# No accidental secrets committed
git diff --cached --name-only | xargs -I{} grep -lE "AKIA[0-9A-Z]{16}|-----BEGIN [A-Z]+ PRIVATE KEY-----|ghp_[A-Za-z0-9]{36}" {} 2>/dev/null && echo "POSSIBLE SECRET COMMITTED" && exit 1
```

Checklist (mirrors [`Skill-Authoring-Standard.md`](Skill-Authoring-Standard.md) section 6):

- [ ] `skills/<kebab-case-name>/SKILL.md`, no double-nesting.
- [ ] `name:` matches directory name.
- [ ] `description` has both what-it-does and when-to-trigger, with concrete phrases.
- [ ] No secrets, tokens, real hostnames/tenant IDs, or customer data.
- [ ] Destructive/mutating operations have a dry-run path or explicit confirm rule.
- [ ] `skills/README.md` table updated.
- [ ] `.claude-plugin/marketplace.json` has a matching plugin entry (new skill) or bumped `version` (changed skill).
- [ ] `CHANGELOG.md` has an `Unreleased` entry.

## Stage 3 — Review

Open a PR against `main`. At least one other person reviews for:

- **Correctness** — do the documented endpoints/commands/flags actually exist and do what's claimed? Spot-check against the vendor's current docs; APIs drift.
- **Safety** — is every mutating/destructive action gated (dry-run, explicit confirmation, scoped credentials)? This is the single most important review criterion for skills that touch production systems (Cloudflare, AWS, Sophos, Wazuh, etc.).
- **Trigger quality** — does the `description` avoid false positives (firing on unrelated conversations) and false negatives (missing obvious phrasings a user would actually type)?
- **No secrets** — re-check even though Stage 2's grep ran; the automated check is a floor, not a guarantee.

Use [`superpowers:requesting-code-review`](https://github.com/obra/superpowers) / [`superpowers:receiving-code-review`](https://github.com/obra/superpowers) conventions if the reviewer or author wants a structured review pass — see [`MARKETPLACE.md`](MARKETPLACE.md) section 3 for installing the Superpowers plugin.

## Stage 4 — Merge

- Squash or rebase-merge to `main` once approved and Stage 2 checks are green.
- Delete the branch after merge.

## Stage 5 — Release

- Confirm [`.claude-plugin/marketplace.json`](.claude-plugin/marketplace.json) reflects the merged state (new plugin entry, or bumped `version` on the changed one).
- Move the `CHANGELOG.md` entry from `Unreleased` into a dated release section if you're cutting one (see [`CHANGELOG.md`](CHANGELOG.md) for the format). Tag the repo if you want a pinned reference point for rollback: `git tag -a v<version> -m "<summary>" && git push --tags`.

## Stage 6 — Distribute

Teammates already tracking this marketplace pick up the change with:

```bash
claude plugin marketplace update useful-claude-add-ons
claude plugin install <skill-name>@useful-claude-add-ons     # new skill
claude plugin update <skill-name>@useful-claude-add-ons      # changed skill, if the CLI supports update; otherwise uninstall + reinstall
```

Anyone not yet on the marketplace follows [`MARKETPLACE.md`](MARKETPLACE.md) section 1 first.

## Fixing a bad release

If a merged skill turns out to be broken or unsafe (wrong endpoint, missing dry-run gate, leaked internal hostname):

1. Revert the merge commit on `main` (`git revert -m 1 <merge-sha>`), or push a hotfix through Stages 1-4 on an expedited basis.
2. Bump `version` in `marketplace.json` again so `claude plugin marketplace update` actually picks up the fix (plugin managers commonly cache by version).
3. Note the incident in `CHANGELOG.md` under the fix's entry — what broke, what the fix was. Don't silently rewrite history.
