# skills-security-ops
anchor: useful-claude-add-ons@1f97e51c
verified: 2026-09-06

## Does
Two read-and-remediate skills pointed at live infrastructure: `cisco-meraki` drives the Meraki
Dashboard API v1 (inventory, events, live diagnostics, and gated config writes to MX/MS/MR);
`wazuh-onprem` drives a self-hosted Wazuh's three APIs - Server on 55000, Indexer on 9200,
Dashboard on 443 - plus SSH edits to `ossec.conf`. They share the shape (live infra,
credential-driven, destructive writes reachable) and no code. DERIVED: no module in
`skills/wazuh-onprem/scripts/` imports anything from `skills/cisco-meraki/`.

## Entry points
- `skills/cisco-meraki/scripts/meraki_client.py:443` (`build_parser`) - verbs registered at
  `:446-481`: orgs, networks, status, inventory, get, get-all, events, changes, security-events,
  air-marshal, live. Dispatch at `:485-513`. **Not read-only** - see the `live` landmine below.
  (This note previously cited `:446` and said "No write verbs here". `:446` is
  `sub.add_parser("orgs")`, a fine anchor for the verb list but not for the claim, and the claim
  itself was false. Corrected 2026-09-06 by reading `:332`.)
- `skills/cisco-meraki/scripts/meraki_config.py:344` (`build_parser`) - the only Meraki path that
  writes persistent *configuration*: snapshot, diff, apply, rollback, batch-stage, batch-commit,
  registered at `:349-370`, dispatched at `:379-408`. (Previously cited `:374`, which is the
  `help="skip the confirmation prompt"` continuation line of `batch-commit`'s `--yes` - real text
  inside the right block, not the line carrying the claim. Corrected 2026-09-06.)
- `skills/wazuh-onprem/scripts/wazuh_client.py:413` (`main`) - CLI over the Server API (JWT,
  `:135-158`) and Indexer API (HTTP basic, `:252-257`); the generic `post` / `put` / `delete` verbs
  are registered by the loop at `:428-429`, arguments at `:430-432`.
- `skills/wazuh-onprem/scripts/manager_config.py:240` (`main`) - SSH-based `ossec.conf` editing:
  fetch, diff, apply, rollback, list-backups, registered at `:244-259`, dispatched at `:263-269`.
  (Previously cited `:251` - the `apply` subparser alone - and omitted `fetch` from the verb list.
  Corrected 2026-09-06.)

## Owns data
- Meraki config snapshots - pre-write payloads, **secrets intact by design**
  (`skills/cisco-meraki/scripts/meraki_config.py:121-126`) - written at `:133-135` by `snapshot()`
  (`:120`). The directory is anchored to the *script*, not the cwd:
  `skills/cisco-meraki/scripts/.meraki-snapshots/` (`skills/cisco-meraki/scripts/meraki_config.py:36-42`),
  and the comment there says why. Covered by `.gitignore:272` (`.meraki-snapshots/`, no leading
  slash, so it matches at any depth). DERIVED. **JUDGEMENT:** the `MERAKI_SNAPSHOT_DIR` env override
  at `:39` can point the unredacted snapshots anywhere, including outside any repo that gitignores
  them; nothing validates the destination.
- Meraki bootstrap/device cache - `skills/cisco-meraki/scripts/meraki_client.py:32` sets
  `CACHE_DIR = ".meraki-snapshots"` as a **bare relative string**, joined at `:164` and created at
  `:177`, so it lands in whatever cwd the caller happened to be in. This is exactly the hazard
  `meraki_config.py:36-41` was reworked to avoid; the client module was not. DERIVED. Contents are
  org/network/device inventory, not credentials.
- Wazuh manager config backups (`ossec.conf.bak.<timestamp>`) written on the remote host by
  `skills/wazuh-onprem/scripts/manager_config.py:172-176` (`sudo cp`). DERIVED.
- Wazuh local scratch copies of the live `ossec.conf` - `_scratch_path`
  (`skills/wazuh-onprem/scripts/manager_config.py:46-58`) puts them in the system temp dir, written
  by `cmd_diff` at `:154-157` and `cmd_apply` at `:179-190`. Nothing deletes them: DERIVED, grep for
  `unlink` / `remove(` / `cleanup` / `finally` over that file returns zero hits.

## Calls out to
- Meraki Dashboard API v1, base URL at `skills/cisco-meraki/scripts/meraki_http.py:26`. (Previously
  cited `:27`, which is `API_KEY_ENV`. Off by one; corrected 2026-09-06.)
- Wazuh Server API `skills/wazuh-onprem/scripts/wazuh_client.py:106`, Indexer API `:110`, Dashboard
  `:117-118`.
- Dashboard saved-objects API on the Dashboard host: `_export` at
  `skills/wazuh-onprem/scripts/wazuh_client.py:342`, `_import` at `:372`, `_find` at `:389`.
  (Previously cited `:314`, which is a line *inside the error-message string* of `_dashboard_auth`.
  It reads plausibly and resolves forever; it supports nothing. Corrected 2026-09-06.)
- The Wazuh manager over SSH: the actual shellouts are `subprocess.run` at
  `skills/wazuh-onprem/scripts/manager_config.py:97` (`run_remote`), `:108` (`scp_down`) and `:115`
  (`scp_up`), with argv built at `:78-90`. (Previously cited `:176`, which is one `run_remote` call
  site inside `cmd_apply`. Corrected 2026-09-06.)

## Gates that actually exist in code
Recorded separately on purpose: a SKILL.md instructing a model is not an enforced gate, and this
note previously listed only the missing gates, which reads as if there were none.

- **Meraki hard blocks.** `skills/cisco-meraki/scripts/meraki_config.py:56-71` is a refusal table
  (delete network, delete org, remove device, release from inventory, revoke admin, touch API keys);
  `check_hard_block` at `:73-82` raises regardless of confirmation, and is called before every
  network round trip at `:127`, `:141`, `:155` and per-action at `:247`. DERIVED. Enforced.
- **Meraki apply cannot reach a PUT unsnapshotted.** `meraki_config.py:152-187`: snapshot `:157`,
  diff `:161`, refuse-if-identical `:162-166`, `confirm(rendered)` `:169`, PUT only at `:176`. It is
  control flow, not a convention. DERIVED. Enforced.
- **Meraki batch caps are enforced in code**, not merely documented: 100 actions at
  `meraki_config.py:221-224`, 5 pending batches at `:249-255`. This was an open unknown in the prior
  version of this note; resolved 2026-09-06 by reading. `batch_commit` takes the same `confirm`
  callable and names the destructive-action count before asking (`:290-308`).
- **Meraki live tools are allowlisted.** `meraki_client.py:115-123` lists seven tools;
  `check_tool_supported` at `:140-150` rejects an unknown tool and a model mismatch before the POST
  at `:332`. DERIVED. Enforced.
- **Meraki secret redaction on output.** Substring denylist at
  `skills/cisco-meraki/scripts/meraki_diff.py:32-42`, applied to every rendered diff at `:248` and
  to every CLI JSON emission in `meraki_config.py` (`:391`, `:397`, `:401`, `:406`). Enforced **on
  display only** - snapshots on disk are deliberately unredacted (see Owns data).
- **Wazuh `ossec.conf` apply is validated before it is trusted.** `manager_config.py:195-197` runs
  `xmllint --noout` on the uploaded candidate and aborts without touching `ossec.conf`; `:201-209`
  then runs `wazuh-analysisd -t` and, on failure, restores the backup and exits. DERIVED. This step
  was listed as unread in the prior version; resolved 2026-09-06. Enforced.

## Landmines
- **Wazuh's generic `post` / `put` / `delete` have no gate in code.**
  `skills/wazuh-onprem/scripts/wazuh_client.py:428-429` registers all three; `:430-432` gives each
  only `endpoint`, `--params` and `--json` - no confirm, no dry-run, no diff, no refusal table.
  Active response, agent deletion and rule or config writes go straight through `request()`
  (`:160-207`), which has no method-based branching at all. The only restraint is prose at
  `skills/wazuh-onprem/SKILL.md:135-145` telling the calling model to confirm first, and prose does
  not restrain a call - it instructs one. CONFIRMED 2026-09-06; still the sharpest thing in either
  skill.
- **`manager_config.py apply` has no confirmation either, and this note previously missed it.**
  Its subparser (`skills/wazuh-onprem/scripts/manager_config.py:251-254`) takes only `--block`,
  `--anchor` and `--restart` - there is no `--yes` because there is no prompt to skip. `cmd_apply`
  (`:170-223`) backs up, validates, and `sudo cp`s over production `ossec.conf` at `:200` in one
  non-interactive run. The validation gates above are real but they check *well-formedness* and
  *parseability*, not *intent*. The restraint on intent is again prose, at
  `skills/wazuh-onprem/SKILL.md:144` ("Always `diff` and show the user the exact XML before
  applying"). Same class as the generic verbs above. DERIVED.
- **Nothing in `skills/wazuh-onprem/scripts/` redacts anything.** DERIVED: grep for
  `redact` / `mask` / `***` over both scripts returns zero hits. `cmd_diff` writes the full live
  `ossec.conf` diff to stdout at `manager_config.py:167`, and `cmd_fetch` writes the whole file to
  `--out` at `:148`. `ossec.conf` carries `<integration>` webhook URLs and API keys
  (`skills/wazuh-onprem/SKILL.md:131`) and authd keys. Contrast Meraki, which redacts on every
  display path. DERIVED for the mechanism; **JUDGEMENT** that this is the more likely credential
  leak of the two skills, because Meraki's unredacted artifact is gitignored and Wazuh's lands in
  the system temp dir uncovered.
- **`--yes` on the Meraki write path auto-confirms.** The swap happens at
  `skills/cisco-meraki/scripts/meraki_config.py:389` (apply), `:395` (rollback) and `:404`
  (batch-commit); `_auto_confirm` at `:414-416` prints the diff to stderr and returns True. Consent
  becomes shown rather than withheld - the diff is displayed to nobody in particular and the write
  proceeds. Meraki collection PUTs are full-replacement (`skills/cisco-meraki/SKILL.md:28-30`), so
  the blast radius of getting this wrong is the whole collection. (The prior version cited `:374`
  for the swap; that line is a `help=` string. `:414-416` was correct.)
- **`meraki_client.py` is not read-only, despite reading like it.** `run_live_tool` POSTs a job at
  `skills/cisco-meraki/scripts/meraki_client.py:332`. It is the module's only write and it is
  allowlist-gated (`:115-123`, `:140-150`), and none of the seven tools reconfigures or reboots a
  device - but `wakeOnLan` (`:122`) emits a real packet onto a client network and `throughputTest`
  (`:119`) generates load. "No configuration writes" is the true statement; "read-only" is not.
  DERIVED. (The prior version asserted "No write verbs here." Recorded rather than quietly deleted:
  this is the shape where a note says a thing is absent when it is present.)
- **Rate limiting is handled on one side only.** Meraki honours `Retry-After` then backs off with
  jitter (`skills/cisco-meraki/scripts/meraki_http.py:111` the 429 branch, `:129` the header read,
  `:132` the jitter), five attempts by default (`:68`), then raises `RateLimitError` at `:124`.
  Wazuh has no 429, backoff, retry or sleep handling anywhere in `skills/wazuh-onprem/scripts/` -
  DERIVED, grep for `429|backoff|Retry-After|time.sleep|max_retries` over both files returns zero
  hits - despite its own SKILL.md naming 429s as something to expect. The one retry it does have is
  a 401 JWT refresh at `skills/wazuh-onprem/scripts/wazuh_client.py:179-181`, single-shot via
  `retry_auth=False`.
- **An unset `WAZUH_CA_BUNDLE` disables TLS verification for every call.**
  `skills/wazuh-onprem/scripts/wazuh_client.py:72-84`: no bundle means `return False`, which becomes
  `self.verify` at `:125` and is passed to every Server, Indexer and Dashboard request. Three things
  make the warning easier to miss than the prior version of this note said: it goes to **stderr**
  (`:81`), not stdout; it prints **once per process** (`_warned` at `:77` and `:83`); and urllib3's
  own `InsecureRequestWarning` is deliberately silenced at `:64-69`, so the library's independent
  signal is gone too. DERIVED.
- **`cmd_rollback` interpolates an operator-supplied path into a remote shell string.**
  `skills/wazuh-onprem/scripts/manager_config.py:228` builds `sudo cp {args.backup} {conf_path}` and
  hands it to `run_remote`, whose docstring at `:94-95` promises "no untrusted interpolation".
  `--backup` comes from the command line, so the promise holds only as far as the operator is
  trusted. DERIVED. **JUDGEMENT:** low severity given the caller already has SSH and sudo on the
  manager; recorded because the docstring states a stronger guarantee than the code provides.
- Test coverage is asymmetric: `skills/cisco-meraki/tests/` holds eight `test_*.py` modules;
  `skills/wazuh-onprem/` ships no `tests/` directory at all (DERIVED: it contains only `SKILL.md`,
  `references/`, `scripts/`). The skill with the ungated write verbs and the unprompted `apply` is
  the one with no tests.

## Out of scope for this note
- `skills/intune-graph/scripts/export_report.py:90` - the live truncating-`open` bug CLAUDE.md
  records - is in neither skill this note covers. Not checked here; see CLAUDE.md.
- Gizmoduck ticket creation and `skills/infra-work-ticketing/SKILL.md` are likewise outside this
  note's two skills. Neither `cisco-meraki` nor `wazuh-onprem` creates tickets: DERIVED, no
  reference to gizmoduck, SDP or ticketing anywhere in either `scripts/` tree.

## Unverified
- Whether `skills/wazuh-onprem/references/indexer-api.md` documents `search_after`/PIT pagination.
  What is now settled is the code: `indexer_search`
  (`skills/wazuh-onprem/scripts/wazuh_client.py:259-273`) issues one `_search` POST and returns it,
  `recent_alerts` (`:288-301`) builds a fixed-`size` body, and `raw-search` passes a body file
  through unchanged. Grep for `search_after|point_in_time|scroll` over both scripts returns zero
  hits, so **no** pagination is implemented in code. The reference file was still not opened.
- The `references/*.md` files for both skills were not opened - eight under `cisco-meraki`, nine
  under `wazuh-onprem`. Every claim above comes from `scripts/` and the two `SKILL.md` files.
- Whether the Meraki redaction denylist (`skills/cisco-meraki/scripts/meraki_diff.py:32-36`) misses
  a field name Meraki actually ships. It is a substring match over a lowercased,
  punctuation-stripped key (`:41-42`), which is broad, but "broad" is not "complete" and the comment
  at `:26-31` says as much. Cannot be settled without the live API; recorded as an unknown, not as
  coverage.
- Whether `MAX_BATCH_ACTIONS` / `MAX_PENDING_BATCHES` (`meraki_config.py:46-48`) match the live
  API's real caps. The comment at `:45` says "Verify against the live API" and no one has. The caps
  are enforced client-side either way; if they are wrong, this note cannot say in which direction.

## Re-anchor provenance
The per-path diff was empty: `git diff --name-only a02331ee..HEAD -- skills/cisco-meraki
skills/wazuh-onprem` returned nothing. That was a **false clean bill**. Every citation was
re-resolved by reading the cited line rather than grepping for the quoted text, and four landed on
real, plausible text that did not support the sentence built on it - `meraki_http.py:27` (the env
var, not the base URL), `meraki_config.py:374` (a `help=` string, cited twice for two different
claims), `wazuh_client.py:314` (text inside an error message), `manager_config.py:176` (a call site,
not the shellout) - plus two entry-point citations that pointed at one subcommand instead of the
parser and omitted verbs from their own lists. One flat-false claim was corrected
(`meraki_client.py` "No write verbs here"; it POSTs at `:332`). One landmine of the same class as
the note's headline finding was missing entirely (`manager_config.py apply` takes no confirmation).
An enforced-gate section was added because the prior version listed only absent gates, which
misrepresents both skills. Three of five prior unknowns were resolved by reading and are now
DERIVED; two survive, narrowed, and two new ones were opened.

Re-read for this refresh: `skills/cisco-meraki/scripts/meraki_http.py` and
`skills/cisco-meraki/scripts/meraki_config.py` in full;
`skills/cisco-meraki/scripts/meraki_client.py` lines 26-155, 295-345 and 435-520;
`skills/cisco-meraki/scripts/meraki_diff.py` redaction section only;
`skills/wazuh-onprem/scripts/wazuh_client.py` lines 60-235, 252-330 and 409-445;
`skills/wazuh-onprem/scripts/manager_config.py` in full; `skills/cisco-meraki/SKILL.md:24-34` and
`:84-94`; `skills/wazuh-onprem/SKILL.md:125-145`; `.gitignore:265-280`; and directory listings of
`skills/cisco-meraki/tests/`, `skills/wazuh-onprem/` and both `references/`. No live system was
contacted and no scan was run; every claim above is from source in the working tree at 1f97e51c.
