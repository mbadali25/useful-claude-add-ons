---
name: bitbucket
description: >
  Work with Atlassian Bitbucket Cloud from Claude Code: authenticate git over HTTPS
  with Atlassian API tokens, commit and push changes, and interact with the Bitbucket
  REST API 2.0 (pull requests, default reviewers, pipelines, pipeline and deployment
  variables, comments, branches, repos). Use this skill whenever the user mentions Bitbucket,
  bitbucket.org, a Bitbucket workspace/repo, pull requests on Bitbucket, Bitbucket Pipelines,
  a pipeline or deployment variable that reads as absent, adding reviewers to a Bitbucket PR,
  a repository access token, or hits authentication errors (401/403/410) pushing or cloning from bitbucket.org — even if they only say "push my code" and the git remote points at bitbucket.org.
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

Use `scripts/bb.sh` — a thin curl wrapper that handles auth and JSON. Invoke it
through `bash`, never as a bare path: its executable bit is not something to
rely on across clones or platforms.

```bash
bash scripts/bb.sh GET  "repositories/$BITBUCKET_WORKSPACE/my-repo/pullrequests?state=OPEN"
bash scripts/bb.sh POST "repositories/$BITBUCKET_WORKSPACE/my-repo/pullrequests" '{
  "title": "Fix NPS timeout",
  "source": {"branch": {"name": "feature/nps-fix"}},
  "destination": {"branch": {"name": "main"}},
  "close_source_branch": true
}'
```

For the endpoint catalogue (PRs, approve/merge, comments, pipelines, branches,
commit statuses), read `references/api.md` before constructing any non-trivial
API call — don't guess payload shapes.

## Merge checks / branch restrictions

Use `scripts/merge_gate.sh` rather than hand-rolling calls — the failure modes
below are the reason it exists.

```bash
scripts/merge_gate.sh export  "$BITBUCKET_WORKSPACE" my-repo gate-backup.json
scripts/merge_gate.sh disable "$BITBUCKET_WORKSPACE" my-repo --branch main
scripts/merge_gate.sh enable  "$BITBUCKET_WORKSPACE" my-repo --from-export gate-backup.json
```

`enable` with no `--from-export` applies a preset: one approval, tasks
completed, one passing build, enforce merge checks. Everything else is left
absent, which is how a check is off.

**The preset is a fresh baseline, not an undo.** `disable` removes more kinds
than the preset creates — `restrict_merges` and `require_no_changes_requested`
among them — so `disable` followed by a bare `enable` silently drops whatever
those were. Only `enable --from-export` puts back what was there.

What to tell the user before touching any of it:

- **These settings are per restriction pattern, not per repo.** The default
  target is the repo's main branch. A gate that lives on `release/*` needs
  `--branch release/*` — a run without it changes nothing and still reports
  success for what it did do.
- **Reading requires `repository:admin`**, same as writing. There is no
  read-only scope, so a token that lists PRs fine will 403 here.
- **Restrictions are scoped two different ways** — a glob `pattern`, or a
  `branch_type` from the repo's branching model. An object scoped
  `branching_model: production` can govern `main` with no glob matching it, so
  `disable` stops and asks rather than guessing which branch types cover your
  branch. Answer with `--branch-type production,development` or
  `--branch-type none`.
- **Three kinds are Premium-only**: `reset_pullrequest_approvals_on_change`,
  `smart_reset_pullrequest_approvals`, `enforce_merge_checks`. Below Premium
  they come back as `not-available-on-this-plan` in the summary. That is not
  "applied" and not "failed" — report it to the user as its own outcome.
- **"No unresolved pull request comments" has no API representation at all.**
  It is absent from the `kind` enum (BCLOUD-22614, open), so it cannot be read
  or changed here. Never claim a run turned *every* merge check off; say which
  kinds it removed.

`disable` always exports first and re-validates the file against the API's
reported count before deleting anything — if that check fails, nothing is
deleted. Keep the export: it is the only way back, and `enable --from-export`
POSTs fresh objects from it (restriction ids are not stable across
delete/recreate).

Details, the full `kind` enum and payload shapes: `references/api.md`.
Offline checks for the script: `scripts/_test/merge_gate.sh`.

## Common tasks, end to end

**"Push my changes and open a PR"**
1. Verify remote is bitbucket.org; confirm auth works (`bash scripts/bb.sh GET user`).
2. Commit + push the branch.
3. `POST .../pullrequests` with source/destination branches; return the PR URL
   from the response's `links.html.href`.

**"Did the pipeline pass?"**
`GET repositories/{ws}/{repo}/pipelines?sort=-created_on&pagelen=5` — report
`state.result.name` per run.

**"Review comments on PR #12"**
`GET repositories/{ws}/{repo}/pullrequests/12/comments` — summarize unresolved ones.

**"Add reviewers to PR #12"** / **"who reviews here?"**
1. Bitbucket has no CODEOWNERS file and no `--reviewer` flag, so the GitHub habit
   of reading CODEOWNERS and passing `gh pr create --reviewer` has no twin here.
   Reviewers come from the repo's *default reviewers*, which Bitbucket adds to
   every new PR. List them with
   `bash scripts/bb.sh GET "repositories/$BITBUCKET_WORKSPACE/my-repo/effective-default-reviewers"`
   — the repo's own plus those inherited from its project
   ([Atlassian](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pullrequests/#api-repositories-workspace-repo-slug-effective-default-reviewers-get)).
   An HTTP 200 whose `values` is empty means none are configured: report "this
   repo has no default reviewers", never "the call failed".
2. To add a reviewer to an open PR, read then write. `GET .../pullrequests/12`
   first — Atlassian: "the API only includes this list on a pull request's `self`
   URL", so a PR read from the list endpoint carries no reviewers to extend. Then `PUT .../pullrequests/12`
   with the existing `title` and the existing `reviewers` plus
   `{"uuid": "{new-uuid}"}`. Atlassian's text for that PUT names only branches
   and description ([Atlassian](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pullrequests/#api-repositories-workspace-repo-slug-pullrequests-pull-request-id-put))
   and does not say whether `reviewers` replaces or merges, so always send the
   full list.
3. Reported 2026-09-28, not reproduced here: that PUT returned HTTP 200 with the
   description preserved.
4. Reviewer uuids: `values[].uuid` from `effective-default-reviewers`, or
   `GET workspaces/{ws}/members`. Payload shapes: `references/api.md`.

## Pipeline and deployment variables: read back with the trailing slash

```bash
bash scripts/bb.sh GET "repositories/$BITBUCKET_WORKSPACE/my-repo/pipelines_config/variables/"
bash scripts/bb.sh GET "repositories/$BITBUCKET_WORKSPACE/my-repo/deployments_config/environments/{environment_uuid}/variables/"
```

Environment uuids come from `GET repositories/{ws}/{repo}/environments`.

**An empty `values` from either path written WITHOUT the trailing slash is
"could not tell", not "absent".** Confirm with the trailing-slash call, or the
repository's Pipelines settings page, before reporting a variable missing.

Reported 2026-09-28, not reproduced here: the slash-less GET returned HTTP 200
with `"values": []` while variables existed, and the trailing-slash form listed
them. Atlassian documents both paths without a slash
([repository variables](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pipelines/#api-repositories-workspace-repo-slug-pipelines-config-variables-get),
[environment variables](https://developer.atlassian.com/cloud/bitbucket/rest/api-group-pipelines/#api-repositories-workspace-repo-slug-deployments-config-environments-environment-uuid-variables-get)),
so this is a gap between the documented path and observed behaviour, and the
slash costs nothing either way.

A `secured` variable is a different symptom: it is listed, but its `value`
comes back empty by design — Atlassian's schema: "The value will never be
exposed in the logs or the REST API." Create and update payloads:
`references/api.md`.

## Repository access tokens are UI-only on Cloud

Bitbucket Cloud's REST API has no endpoint to create, list or rotate access
tokens: Atlassian's OpenAPI description of the Cloud API
(`https://developer.atlassian.com/cloud/bitbucket/swagger.v3.json`) has no path
containing "token" (checked 2026-09-29). Create a repository access token in
the UI — Repository settings > Security > Access tokens > Create access token —
and "The token is only displayed once and can't be retrieved later"
([Atlassian](https://support.atlassian.com/bitbucket-cloud/docs/create-a-repository-access-token/)).

The REST create endpoint that turns up in searches — "Create repository HTTP
token", `PUT /rest/access-tokens/latest/projects/{projectKey}/repos/{repositorySlug}`
— is Bitbucket Data Center's, not Cloud's
([Atlassian](https://developer.atlassian.com/server/bitbucket/rest/v1000/api-group-access-tokens/)).
Reported 2026-09-28, not reproduced here: access-token endpoints return 404 on
`api.bitbucket.org`. Do not build a workflow that creates one from a session:
ask the user to create it, and to put the value into an environment variable or
the git credential helper exactly as `BITBUCKET_API_TOKEN` above — never into
the conversation (see Safety rails).

## Safety rails

- Never echo `$BITBUCKET_API_TOKEN` in output, logs, or committed files.
- Never ask a user to paste a token-creation or rotation page, or its HTML,
  into the conversation. The "Access token rotated" dialog was reported
  2026-09-28 (not reproduced here) to carry the value three times in the page
  source; a user did paste it and a live token landed in chat. Ask for the
  value to go into the env var or the credential helper instead.
- A token that has appeared in chat, a log or a commit is leaked: revoke it and
  create a new one. Atlassian: "create a new token and consider revoking the
  old token"
  ([source](https://support.atlassian.com/bitbucket-cloud/docs/create-a-repository-access-token/)).
  Do not keep using it because it still works.
- Never force-push (`--force`) or delete branches without explicit user confirmation.
- Merging or declining PRs via the API is destructive — confirm with the user first.
- `merge_gate.sh disable` deletes branch restrictions. Confirm with the user
  first, show them `--dry-run` output if they are unsure, and tell them where
  the export landed before reporting the run as done.
