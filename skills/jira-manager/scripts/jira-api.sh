#!/usr/bin/env bash
# Jira Cloud REST API v3 helper functions, authenticated via API token.
# Supports BOTH classic (unscoped) tokens and the newer scoped tokens.
#
# Required environment variables:
#   JIRA_EMAIL       - the Atlassian account email tied to the API token
#   JIRA_API_TOKEN   - API token from https://id.atlassian.com/manage-profile/security/api-tokens
#
# Then EITHER (classic/unscoped token):
#   JIRA_WORKSPACE   - the site subdomain only, e.g. "acme" for acme.atlassian.net
#   JIRA_BASE_URL    - (alternative to JIRA_WORKSPACE) full https://... URL, for sites
#                      not on the standard *.atlassian.net pattern
# OR (scoped token — required if the token was created via "Create API token with scopes"):
#   JIRA_CLOUD_ID    - your site's Cloud ID (a UUID, not the site name).
#                      Find it with `jira_get_cloud_id` below (no auth needed for that call),
#                      or at https://<site>.atlassian.net/_edge/tenant_info,
#                      or via https://developer.atlassian.com/cloud/jira/platform/rest/v3/intro/#version
#                      When JIRA_CLOUD_ID is set, requests route through the
#                      api.atlassian.com gateway instead of the site domain, which is
#                      required for scoped tokens (classic tokens work either way).
#                      Scopes needed on the token: read:jira-work, write:jira-work,
#                      read:jira-user, read:me.
#
# Dependencies: curl, jq
#
# Usage: source this file, then call the functions, e.g.:
#   source jira-api.sh
#   jira_get_issue PROJ-123
#   jira_search 'assignee = currentUser() AND resolution = Unresolved'

set -uo pipefail

: "${JIRA_EMAIL:?Set JIRA_EMAIL to the Atlassian account email}"
: "${JIRA_API_TOKEN:?Set JIRA_API_TOKEN (create one at https://id.atlassian.com/manage-profile/security/api-tokens)}"

# Look up a site's Cloud ID with no auth required — useful when the user only has
# JIRA_WORKSPACE and needs JIRA_CLOUD_ID to use a scoped token.
jira_get_cloud_id() {
  # jira_get_cloud_id WORKSPACE   (e.g. jira_get_cloud_id acme)
  curl -s "https://$1.atlassian.net/_edge/tenant_info" | jq -r '.cloudId'
}

if [[ -n "${JIRA_CLOUD_ID:-}" ]]; then
  # Scoped-token mode: must go through the Atlassian API gateway.
  JIRA_BASE_URL="https://api.atlassian.com/ex/jira/${JIRA_CLOUD_ID}"
elif [[ -z "${JIRA_BASE_URL:-}" ]]; then
  # Classic-token mode: direct site domain.
  : "${JIRA_WORKSPACE:?Set JIRA_WORKSPACE (e.g. 'acme' for acme.atlassian.net), or JIRA_BASE_URL, or JIRA_CLOUD_ID for a scoped token}"
  JIRA_BASE_URL="https://${JIRA_WORKSPACE}.atlassian.net"
fi

_JIRA_API="${JIRA_BASE_URL}/rest/api/3"
_JIRA_AUTH="${JIRA_EMAIL}:${JIRA_API_TOKEN}"

_jira_curl() {
  # _jira_curl METHOD PATH [JSON_BODY]
  local method="$1" path="$2" body="${3:-}"
  if [[ -n "$body" ]]; then
    curl -s -u "$_JIRA_AUTH" -X "$method" \
      -H "Content-Type: application/json" -H "Accept: application/json" \
      -d "$body" "${_JIRA_API}${path}"
  else
    curl -s -u "$_JIRA_AUTH" -X "$method" -H "Accept: application/json" "${_JIRA_API}${path}"
  fi
}

# Wrap plain text into the minimal Atlassian Document Format (ADF) required
# by API v3 for descriptions and comments.
_adf() {
  jq -Rn --arg text "$1" '{type:"doc", version:1, content:[{type:"paragraph", content:[{type:"text", text:$text}]}]}'
}

### Projects ###

jira_list_projects() {
  _jira_curl GET "/project/search?maxResults=100"
}

jira_project_issue_types() {
  # jira_project_issue_types PROJECTKEY
  _jira_curl GET "/issue/createmeta?projectKeys=$1&expand=projects.issuetypes"
}

### Reading issues ###

jira_get_issue() {
  # jira_get_issue ISSUEKEY [fields_csv]
  local fields="${2:-summary,status,assignee,reporter,priority,labels,description,updated}"
  _jira_curl GET "/issue/$1?fields=${fields}"
}

jira_search() {
  # jira_search 'JQL STRING' [maxResults]
  local jql="$1" max="${2:-50}"
  local body
  body=$(jq -n --arg jql "$jql" --argjson max "$max" \
    '{jql: $jql, maxResults: $max, fields: ["summary","status","assignee","priority","updated"]}')
  _jira_curl POST "/search/jql" "$body"
}

### Creating issues ###

jira_create_issue() {
  # jira_create_issue PROJECTKEY ISSUETYPE "Summary text" ["Description text"]
  local project="$1" issuetype="$2" summary="$3" desc="${4:-}"
  local desc_json="null"
  [[ -n "$desc" ]] && desc_json=$(_adf "$desc")
  local body
  body=$(jq -n \
    --arg project "$project" --arg issuetype "$issuetype" --arg summary "$summary" \
    --argjson desc "$desc_json" \
    '{fields: {project: {key: $project}, issuetype: {name: $issuetype}, summary: $summary, description: $desc}}')
  _jira_curl POST "/issue" "$body"
}

### Editing issues ###

jira_edit_issue() {
  # jira_edit_issue ISSUEKEY '{"summary": "New title", "priority": {"name": "High"}}'
  local key="$1" fields_json="$2"
  local body
  body=$(jq -n --argjson fields "$fields_json" '{fields: $fields}')
  _jira_curl PUT "/issue/$key" "$body"
  echo "(no content on success = 204)"
}

### Assigning ###

jira_find_account_id() {
  # jira_find_account_id "name or email"
  _jira_curl GET "/user/search?query=$1"
}

jira_whoami() {
  _jira_curl GET "/myself"
}

jira_assign() {
  # jira_assign ISSUEKEY ACCOUNT_ID   (use "null" to unassign)
  local key="$1" account_id="$2"
  local body
  if [[ "$account_id" == "null" ]]; then
    body='{"fields": {"assignee": null}}'
  else
    body=$(jq -n --arg id "$account_id" '{fields: {assignee: {accountId: $id}}}')
  fi
  _jira_curl PUT "/issue/$key" "$body"
  echo "(no content on success = 204)"
}

### Status / transitions (includes closing) ###

jira_get_transitions() {
  # jira_get_transitions ISSUEKEY
  _jira_curl GET "/issue/$1/transitions"
}

jira_transition() {
  # jira_transition ISSUEKEY TRANSITION_ID
  local key="$1" transition_id="$2"
  local body
  body=$(jq -n --arg id "$transition_id" '{transition: {id: $id}}')
  _jira_curl POST "/issue/$key/transitions" "$body"
  echo "(no content on success = 204)"
}

jira_clear_resolution() {
  # Use when a reopened issue won't close because it still has a stale resolution.
  jira_edit_issue "$1" '{"resolution": null}'
}

### Comments & work log ###

jira_add_comment() {
  # jira_add_comment ISSUEKEY "Comment text"
  local key="$1" text="$2"
  local body
  body=$(jq -n --argjson body "$(_adf "$text")" '{body: $body}')
  _jira_curl POST "/issue/$key/comment" "$body"
}

jira_add_worklog() {
  # jira_add_worklog ISSUEKEY "2h 30m" ["Optional comment"]
  local key="$1" time_spent="$2" comment="${3:-}"
  local body
  if [[ -n "$comment" ]]; then
    body=$(jq -n --arg t "$time_spent" --argjson c "$(_adf "$comment")" \
      '{timeSpent: $t, comment: $c}')
  else
    body=$(jq -n --arg t "$time_spent" '{timeSpent: $t}')
  fi
  _jira_curl POST "/issue/$key/worklog" "$body"
}

### Issue links ###

jira_link_types() {
  _jira_curl GET "/issueLinkType"
}

jira_link_issues() {
  # jira_link_issues INWARD_KEY OUTWARD_KEY "Link Type Name"
  local inward="$1" outward="$2" link_type="$3"
  local body
  body=$(jq -n --arg t "$link_type" --arg in "$inward" --arg out "$outward" \
    '{type: {name: $t}, inwardIssue: {key: $in}, outwardIssue: {key: $out}}')
  _jira_curl POST "/issueLink" "$body"
}

### True deletion — disabled by default, see SKILL.md ###

jira_delete_issue() {
  # DESTRUCTIVE AND IRREVERSIBLE. jira_delete_issue ISSUEKEY
  # Only call this after explicit, unambiguous user confirmation (see SKILL.md).
  local key="$1"
  _jira_curl DELETE "/issue/$key"
  echo "(no content on success = 204 — issue is permanently gone)"
}
