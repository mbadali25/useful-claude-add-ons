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

## Branch restrictions (why a push got 403)
- `GET repositories/{ws}/{repo}/branch-restrictions` — lists rules like
  `push`, `force`, `delete`, `require_approvals_to_merge` per branch pattern.

## Gotchas
- PR `id` is an integer; pipeline `uuid` is a braces-wrapped UUID — URL-encode the
  braces (`%7B...%7D`) or pass them literally in quotes; curl handles literal braces.
- `?q=` query filters use BBQL, e.g. `q=state="OPEN" AND source.branch.name="feature/x"`
  — remember to URL-encode.
- User identifiers are UUIDs (`{...}`), not usernames, in most write payloads.
- Rate limits: 1,000 req/hr for most authenticated endpoints; back off on 429.
