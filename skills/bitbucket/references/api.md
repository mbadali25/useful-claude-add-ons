# Bitbucket Cloud REST API 2.0 — endpoint reference

Base URL: `https://api.bitbucket.org/2.0`
All paths below are relative to the base. `{ws}` = workspace slug, `{repo}` = repo slug.
Pagination: responses with lists have `values[]`, `next`, `pagelen` (max 100 via `?pagelen=100`).
Official docs: https://developer.atlassian.com/cloud/bitbucket/rest/

## Identity / sanity check
- `GET user` — current authenticated user (good auth smoke test)
- `GET workspaces` — workspaces visible to the token
- `GET repositories/{ws}` — list repos in a workspace (`?q=name~"foo"` to filter)

## Repositories
- `GET  repositories/{ws}/{repo}` — repo details
- `GET  repositories/{ws}/{repo}/refs/branches` — list branches
- `POST repositories/{ws}/{repo}/refs/branches` — create branch:
  ```json
  {"name": "feature/x", "target": {"hash": "<commit-or-branch-head-hash>"}}
  ```
- `DELETE repositories/{ws}/{repo}/refs/branches/{name}` — delete branch (confirm with user first)
- `GET repositories/{ws}/{repo}/commits/{branch}` — commit history
- `GET repositories/{ws}/{repo}/src/{commit}/{path}` — file contents at a ref

## Pull requests
- `GET  repositories/{ws}/{repo}/pullrequests?state=OPEN` — states: OPEN, MERGED, DECLINED, SUPERSEDED
- `GET  repositories/{ws}/{repo}/pullrequests/{id}` — PR details (URL in `links.html.href`)
- `POST repositories/{ws}/{repo}/pullrequests` — create:
  ```json
  {
    "title": "Title",
    "description": "Markdown body",
    "source": {"branch": {"name": "feature/x"}},
    "destination": {"branch": {"name": "main"}},
    "close_source_branch": true,
    "reviewers": [{"uuid": "{user-uuid}"}]
  }
  ```
- `PUT  repositories/{ws}/{repo}/pullrequests/{id}` — update title/description/reviewers
- `GET  repositories/{ws}/{repo}/pullrequests/{id}/diff` — raw diff (not JSON)
- `POST repositories/{ws}/{repo}/pullrequests/{id}/approve` — approve
- `DELETE repositories/{ws}/{repo}/pullrequests/{id}/approve` — revoke approval
- `POST repositories/{ws}/{repo}/pullrequests/{id}/merge` — merge (**confirm with user first**):
  ```json
  {"merge_strategy": "merge_commit", "close_source_branch": true}
  ```
  Strategies: `merge_commit`, `squash`, `fast_forward`
- `POST repositories/{ws}/{repo}/pullrequests/{id}/decline` — decline (**confirm first**)

## PR comments
- `GET  repositories/{ws}/{repo}/pullrequests/{id}/comments`
- `POST repositories/{ws}/{repo}/pullrequests/{id}/comments` — general comment:
  ```json
  {"content": {"raw": "Markdown text"}}
  ```
  Inline comment (attach to a file/line in the diff):
  ```json
  {"content": {"raw": "text"}, "inline": {"path": "src/app.py", "to": 42}}
  ```
- Reply: add `"parent": {"id": <comment-id>}` to the POST body.

## Pipelines
- `GET repositories/{ws}/{repo}/pipelines?sort=-created_on&pagelen=10` — recent runs.
  Status lives in `state.name` (PENDING/IN_PROGRESS/COMPLETED) and, when completed,
  `state.result.name` (SUCCESSFUL/FAILED/STOPPED).
- `GET repositories/{ws}/{repo}/pipelines/{uuid}` — single run
- `GET repositories/{ws}/{repo}/pipelines/{uuid}/steps` — steps in a run
- `GET repositories/{ws}/{repo}/pipelines/{pipeline-uuid}/steps/{step-uuid}/log` — step log (plain text)
- `POST repositories/{ws}/{repo}/pipelines` — trigger a run on a branch:
  ```json
  {"target": {"type": "pipeline_ref_target", "ref_type": "branch", "ref_name": "main"}}
  ```

## Commit statuses (build badges on commits)
- `GET  repositories/{ws}/{repo}/commit/{hash}/statuses`
- `POST repositories/{ws}/{repo}/commit/{hash}/statuses/build`:
  ```json
  {"state": "SUCCESSFUL", "key": "my-check", "url": "https://ci.example.com/run/1"}
  ```
  States: SUCCESSFUL, FAILED, INPROGRESS, STOPPED

## Branch restrictions (the merge gate, and why a push got 403)

One resource holds every branch protection *and* every merge check the repo
settings UI shows:

- `GET  repositories/{ws}/{repo}/branch-restrictions` — all of them. Accepts
  `?kind=` to filter and `?pagelen=100`; the response is
  `{pagelen, values, page, size}` where `size` is the total across **all** pages.
- `POST repositories/{ws}/{repo}/branch-restrictions` — create one
- `GET|PUT|DELETE repositories/{ws}/{repo}/branch-restrictions/{id}` — one object

**Scope requirement:** `repository:admin`, for reads as well as writes. There is
no read-only scope for this resource, so a token that can list PRs will still
403 here.

### ON means the object exists; OFF means it does not

There is no falsey PUT. A check is enabled because a restriction object of that
`kind` exists, and disabled by `DELETE`ing it. `PUT` only changes `value` on the
four kinds that carry an integer. One `kind` per POST, so N checks is N POSTs.
Two glob restrictions cannot share the same `kind` + `pattern`.

### The `kind` values

From the POST endpoint's own description. Atlassian words it as "include", so
treat the list as non-exhaustive — code that switches on `kind` needs a branch
for one it does not recognise.

`push`, `force`, `delete`, `restrict_merges`, `require_tasks_to_be_completed`,
`require_approvals_to_merge`, `require_default_reviewer_approvals_to_merge`,
`require_no_changes_requested`, `require_passing_builds_to_merge`,
`require_commits_behind`, `reset_pullrequest_approvals_on_change`,
`smart_reset_pullrequest_approvals`,
`reset_pullrequest_changes_requested_on_change`,
`require_all_dependencies_merged`, `enforce_merge_checks`,
`allow_auto_merge_when_builds_pass`.

Four take an integer `value`: `require_approvals_to_merge`,
`require_default_reviewer_approvals_to_merge`,
`require_passing_builds_to_merge`, `require_commits_behind`. Every other kind is
presence-only — sending a `value` is meaningless.

**Premium-only:** `reset_pullrequest_approvals_on_change`,
`smart_reset_pullrequest_approvals`, `enforce_merge_checks`. Below Premium the
API refuses the write; it does not block the rest of the run. Treat "could not
apply because of the plan" as its own outcome — reporting it as applied or as a
generic failure both lose the distinction the operator needs.

**"No unresolved pull request comments" has no `kind`.** It is enumeratively
absent from the list above: there is no API representation for it, so it can be
neither read nor set from here. BCLOUD-22614 tracks that and is open. Anything
claiming to have turned every merge check off has not touched this one.

### Two scoping schemes — both must be read

A restriction is scoped one of two ways, and a tool that only understands the
first will report a gate as down while half of it is still up:

```json
{"kind": "require_approvals_to_merge", "value": 1,
 "branch_match_kind": "glob", "pattern": "main"}
```
```json
{"kind": "enforce_merge_checks",
 "branch_match_kind": "branching_model", "branch_type": "production"}
```

`branch_type` is one of `production`, `development`, `bugfix`, `release`,
`feature`, `hotfix`. Which concrete branches a type covers depends on the repo's
branching model, not on the branch's name — so a `production`-scoped object can
govern `main` with no glob pattern matching it anywhere in the response. **Never
filter the export.** Resolve the main branch with
`GET repositories/{ws}/{repo}` → `.mainbranch.name`.

### scripts/merge_gate.sh

Wraps the above for the common operations. Calls `bb.sh` for transport.

```bash
scripts/merge_gate.sh export  <ws> <repo> <outfile>
scripts/merge_gate.sh disable <ws> <repo> [--branch NAME] [--export-to FILE]
                                          [--branch-type LIST|none] [--dry-run]
scripts/merge_gate.sh enable  <ws> <repo> [--branch NAME] [--from-export FILE]
```

- `export` is unfiltered: every kind, both scope schemes, pagination followed.
- `disable` exports first, re-reads the file and checks its restriction count
  against the API's `size` before issuing a single DELETE. It removes branch
  restrictions of the merge-gate kinds it manages that cover the target branch —
  not "every merge check", which it cannot do (see the missing kind above). It
  leaves `push`/`force`/`delete` alone: those are write protection, not merge
  checks.
- `disable` **refuses to run** when a `branching_model`-scoped object's coverage
  cannot be determined, rather than guessing. Resolve it with `--branch-type
  production,development` (the types that cover your target branch) or
  `--branch-type none`.
- `enable` applies a preset by default: `require_approvals_to_merge` 1,
  `require_tasks_to_be_completed`, `require_passing_builds_to_merge` 1,
  `enforce_merge_checks`. Everything else is left absent.
- `enable --from-export FILE` restores by POSTing **fresh** objects built from
  `kind` + `value` + scope. Ids are not stable across delete/recreate, so the
  recorded ones are never reused.
- Each setting reports `applied`, `already-present`,
  `not-available-on-this-plan`, or `failed`, and all four survive into the
  summary line.

**Merge settings are per restriction pattern, not per repo.** A repo whose gate
lives on `release/*` is untouched by a run that defaults to the main branch —
pass `--branch`.

## Gotchas
- PR `id` is an integer; pipeline `uuid` is a braces-wrapped UUID — URL-encode the
  braces (`%7B...%7D`) or pass them literally in quotes; curl handles literal braces.
- `?q=` query filters use BBQL, e.g. `q=state="OPEN" AND source.branch.name="feature/x"`
  — remember to URL-encode.
- User identifiers are UUIDs (`{...}`), not usernames, in most write payloads.
- Rate limits: 1,000 req/hr for most authenticated endpoints; back off on 429.
