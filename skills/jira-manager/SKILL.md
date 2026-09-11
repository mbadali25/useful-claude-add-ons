---
name: jira-manager
description: Full read/write access to Jira Cloud via direct REST API calls, authenticated with an email + API token (no MCP connector needed). Look up projects, search/read tickets with JQL, create issues, update fields, assign, close/transition status, comment, and log work. Use this whenever the user wants to look up, create, update, close, comment on, reassign, retitle, reprioritize, or reorganize Jira issues, or asks about their tickets, backlog, sprint, projects, or board. Requires JIRA_EMAIL, JIRA_API_TOKEN, and JIRA_WORKSPACE (or JIRA_BASE_URL) to be set as environment variables — check for these before running any command and prompt the user to set them if missing. True issue deletion is technically possible via this API but is gated behind explicit confirmation — see "Deleting an issue" below; default to closing/transitioning instead.
---

# Jira Manager (direct API, env-var auth)

Full CRUD-style workflow for Jira Cloud using the Jira REST API v3 directly over `curl` — no MCP connector, no OAuth flow. Works anywhere with `curl` **7.76+** (March 2021) and `jq` available (Claude Code, Cowork, a terminal, this sandbox). The version floor is `--fail-with-body`, which is what makes a 4xx return non-zero **and** still hand you Jira's `errorMessages` — the only thing that says whether it was a bad field, a stale transition id or a missing token scope. On an older curl (RHEL 8 ships 7.61, Ubuntu 20.04 7.68, Debian 11 7.74) every call aborts with `curl: option --fail-with-body: is unknown` before making a request: loud and precisely named, so it diagnoses itself.

## Required environment variables

Works with either kind of Atlassian API token — classic (unscoped) or the newer scoped tokens — but they need different variables:

| Variable | Needed for | What it is |
|---|---|---|
| `JIRA_EMAIL` | both | The Atlassian account email tied to the API token |
| `JIRA_API_TOKEN` | both | From https://id.atlassian.com/manage-profile/security/api-tokens — "Create API token" (classic) or "Create API token with scopes" (scoped) |
| `JIRA_WORKSPACE` | classic only | Site subdomain only, e.g. `acme` for `acme.atlassian.net` |
| `JIRA_BASE_URL` | classic only | Alternative to `JIRA_WORKSPACE`, full base URL, for sites not on the standard `*.atlassian.net` pattern |
| `JIRA_CLOUD_ID` | scoped only | The site's Cloud ID (a UUID, not the site name). If unset but `JIRA_WORKSPACE` is set, get it with `jira_get_cloud_id acme` (no auth required). Setting this switches the script to route through `api.atlassian.com` as scoped tokens require. |

If using a scoped token, it must have been granted these scopes: `read:jira-work`, `write:jira-work`, `read:jira-user`, `read:me` — otherwise calls will fail even with a correct Cloud ID.

Before doing anything, check whether the right combination is set:

```bash
[[ -n "${JIRA_EMAIL:-}" && -n "${JIRA_API_TOKEN:-}" && ( -n "${JIRA_CLOUD_ID:-}" || -n "${JIRA_WORKSPACE:-}" || -n "${JIRA_BASE_URL:-}" ) ]] && echo "configured" || echo "missing"
```

If missing, tell the user which specific variable(s) are unset and how to get them (API token link above) rather than guessing or proceeding without auth.

## Setup: source the helper library once per session

```bash
source scripts/jira-api.sh
```

This defines all the functions below. **Sourcing succeeds even with no credentials set** -- deliberately, so `jira_get_cloud_id` (which needs none) is usable during setup, and so sourcing never changes the shell it is sourced into. Each function that needs credentials checks at CALL time and fails loudly then. A clean `source` is therefore not evidence that `JIRA_EMAIL` and `JIRA_API_TOKEN` are set; call `jira_whoami` if you want that confirmed.

## Looking up projects

- `jira_list_projects` — list all projects you can see. Use when the user asks "what projects do we have" or you need to confirm a project key.
- `jira_project_issue_types PROJECTKEY` — valid issue types and fields for a project. Check this before creating an issue in an unfamiliar project.

## Reading issues

- `jira_get_issue ISSUEKEY [fields_csv]` — get one issue. Defaults to summary/status/assignee/reporter/priority/labels/description/updated; pass a custom comma-separated field list for more.
- `jira_search 'JQL STRING' [maxResults]` — search. Common JQL patterns:
  - My open issues: `assignee = currentUser() AND resolution = Unresolved ORDER BY updated DESC`
  - Project backlog: `project = PROJ AND status = "To Do" ORDER BY priority DESC`
  - Recently updated: `updated >= -7d ORDER BY updated DESC`

## Creating issues

`jira_create_issue PROJECTKEY ISSUETYPE "Summary" ["Description"]`

For anything beyond summary/description at creation time (priority, labels, assignee, custom fields), create first, then follow with `jira_edit_issue` to set the rest.

## Editing issues

`jira_edit_issue ISSUEKEY '<json fields object>'`

Examples:
- Retitle: `jira_edit_issue PROJ-123 '{"summary": "New title"}'`
- Priority + labels: `jira_edit_issue PROJ-123 '{"priority": {"name": "High"}, "labels": ["urgent"]}'`
- Clear a field: pass an explicit `null`, e.g. `{"resolution": null}`.

## Assigning

Assignee needs an **account ID**, not a name or email:

1. `jira_find_account_id "name or email"` to resolve it (or `jira_whoami` to get the token owner's own account ID for "assign to me").
2. `jira_assign ISSUEKEY ACCOUNT_ID`
3. Unassign: `jira_assign ISSUEKEY null`

## Status changes (transitions) — this is how you close an issue

Status is not a plain field — Jira workflows gate it through transitions:

1. `jira_get_transitions ISSUEKEY` to see legal transitions from the current status (workflows differ per project — "Done"/"Closed"/"Resolved"/"Won't Do" aren't universal).
2. `jira_transition ISSUEKEY TRANSITION_ID`
3. If closing a reopened issue fails, it may still carry a stale resolution — run `jira_clear_resolution ISSUEKEY` first, then retransition.

## Comments & work log

- `jira_add_comment ISSUEKEY "text"`
- `jira_add_worklog ISSUEKEY "2h 30m" ["optional comment"]`

## Linking issues

- `jira_link_types` — valid link type names (Blocks, Relates, Duplicate, Clones, ...)
- `jira_link_issues INWARD_KEY OUTWARD_KEY "Link Type Name"` — for directional types, "A is blocked by B" means `INWARD_KEY=B OUTWARD_KEY=A`.

## Bulk operations

No native bulk endpoint. For "update all issues matching X": `jira_search` to get the matching keys, then loop `jira_edit_issue`/`jira_transition` per issue. Confirm scope with the user first if the JQL could match more than a handful — easy to get wrong at scale, and now genuinely hard to undo (see below).

## Deleting an issue

`jira_delete_issue ISSUEKEY` exists and **works** — unlike an MCP-connector-based setup, direct API access can call Jira's real `DELETE /issue/{key}` endpoint if the token's account has delete permission. This is **permanent and irreversible**: no trash, no undo.

Default behavior when the user asks to "delete" an issue:

1. Don't call `jira_delete_issue` automatically. Ask first: do they want it truly gone, or moved to a terminal status (Done/Cancelled/Won't Do)? Default to the latter unless they say otherwise.
2. For a real delete request, restate the issue key and confirm they understand it's unrecoverable before calling `jira_delete_issue`.
3. For the safer path: `jira_get_transitions` → `jira_transition` to a terminal status, optionally `jira_add_comment` explaining why.

## Safety notes

- Confirm the issue key/summary with the user before writing to or transitioning any issue they didn't explicitly name — keys are easy to mix up across projects.
- For broad JQL filters that could match many issues, state the match count and get explicit go-ahead before writing to more than a few.
- Never print `JIRA_API_TOKEN` back to the user or into logs/output.
