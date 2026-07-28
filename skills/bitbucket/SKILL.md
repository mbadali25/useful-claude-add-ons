---
name: bitbucket
description: >
  Work with Atlassian Bitbucket Cloud from Claude Code: authenticate git over HTTPS
  with Atlassian API tokens, commit and push changes, and interact with the Bitbucket
  REST API 2.0 (pull requests, pipelines, comments, branches, repos). Use this skill
  whenever the user mentions Bitbucket, bitbucket.org, a Bitbucket workspace/repo,
  pull requests on Bitbucket, Bitbucket Pipelines, or hits authentication errors
  (401/403/410) pushing or cloning from bitbucket.org — even if they only say
  "push my code" and the git remote points at bitbucket.org.
---

# Bitbucket Cloud

Interact with Bitbucket Cloud: git operations (clone/commit/push) and the REST API
(pull requests, pipelines, comments). **Always check the remote first** — if
`git remote -v` shows `bitbucket.org`, this skill applies.

## Critical: authentication (2026 rules)

App passwords are **dead** (removed July 28, 2026; brownouts before that cause
intermittent HTTP 410 errors). Use **Atlassian API tokens with scopes** instead.

The confusing part — the same token uses a **different username** depending on context:

| Context | Username | Password |
|---|---|---|
| Git over HTTPS | `x-bitbucket-api-token-auth` | API token |
| REST API (Basic auth) | Atlassian account **email** | API token |

### Required environment variables

Expect these to be set (suggest adding to `~/.bashrc`, `~/.zshrc`, or the project's
`.env` — never commit them):

```bash
export BITBUCKET_EMAIL="user@example.com"      # Atlassian account email
export BITBUCKET_API_TOKEN="ATATT..."          # API token with scopes
export BITBUCKET_WORKSPACE="my-workspace"      # default workspace slug (optional)
```

If missing, tell the user how to create a token:
Bitbucket → Settings → Atlassian account settings → Security →
**Create and manage API tokens** → **Create API token with scopes** → select app
**Bitbucket**. Minimum scopes for this skill: `read:account`,
`read:repository:bitbucket` + `write:repository:bitbucket` (git push),
`read:pullrequest:bitbucket` + `write:pullrequest:bitbucket` (PRs),
`read:pipeline:bitbucket` (+ `write:pipeline:bitbucket` to trigger runs).
The token is shown once — copy it immediately.

### Git credential setup (do once per machine)

Preferred: a scoped credential helper entry so the token never lands in the remote
URL or shell history:

```bash
git config --global credential."https://bitbucket.org".username x-bitbucket-api-token-auth
git config --global credential.helper store   # or the OS keychain helper
# Prime it non-interactively:
printf "protocol=https\nhost=bitbucket.org\nusername=x-bitbucket-api-token-auth\npassword=%s\n" "$BITBUCKET_API_TOKEN" | git credential approve
```

Quick-and-dirty alternative (leaks token into `.git/config` — warn the user):

```bash
git remote set-url origin "https://x-bitbucket-api-token-auth:${BITBUCKET_API_TOKEN}@bitbucket.org/<workspace>/<repo>.git"
```

SSH keys also still work and sidestep token expiry entirely — offer as an option.

## Commit and push workflow

Standard git; only the auth is Bitbucket-specific.

1. `git status` and `git diff` — review what changed before staging.
2. Stage deliberately (`git add <paths>`), never blind `git add -A` on dirty trees.
3. Commit with a concise message describing the why.
4. `git push origin <branch>`. First push of a new branch: `git push -u origin <branch>`.

### Push failure triage

- **HTTP 410 + "CHANGE-3222 / app passwords deprecated"** → stored credential is an
  app password. Replace it with an API token (setup above), then retry. Clear the
  stale credential first: `git credential reject` with the host, or the OS keychain.
- **401** → wrong username for the context (see table above) or expired token.
- **403** → token lacks the `write:repository:bitbucket` scope, or branch
  restrictions on the target branch — check with the API (see references/api.md,
  branch-restrictions section).

## REST API operations

Use `scripts/bb.sh` — a thin curl wrapper that handles auth and JSON:

```bash
scripts/bb.sh GET  "repositories/$BITBUCKET_WORKSPACE/my-repo/pullrequests?state=OPEN"
scripts/bb.sh POST "repositories/$BITBUCKET_WORKSPACE/my-repo/pullrequests" '{
  "title": "Fix NPS timeout",
  "source": {"branch": {"name": "feature/nps-fix"}},
  "destination": {"branch": {"name": "main"}},
  "close_source_branch": true
}'
```

For the endpoint catalogue (PRs, approve/merge, comments, pipelines, branches,
commit statuses), read `references/api.md` before constructing any non-trivial
API call — don't guess payload shapes.

## Common tasks, end to end

**"Push my changes and open a PR"**
1. Verify remote is bitbucket.org; confirm auth works (`scripts/bb.sh GET user`).
2. Commit + push the branch.
3. `POST .../pullrequests` with source/destination branches; return the PR URL
   from the response's `links.html.href`.

**"Did the pipeline pass?"**
`GET repositories/{ws}/{repo}/pipelines?sort=-created_on&pagelen=5` — report
`state.result.name` per run.

**"Review comments on PR #12"**
`GET repositories/{ws}/{repo}/pullrequests/12/comments` — summarize unresolved ones.

## Safety rails

- Never echo `$BITBUCKET_API_TOKEN` in output, logs, or committed files.
- Never force-push (`--force`) or delete branches without explicit user confirmation.
- Merging or declining PRs via the API is destructive — confirm with the user first.
