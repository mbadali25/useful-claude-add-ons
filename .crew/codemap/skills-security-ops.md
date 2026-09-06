# skills-security-ops
anchor: useful-claude-add-ons@a02331ee
verified: 2026-09-06

## Does
Two read-and-remediate skills pointed at live infrastructure: `cisco-meraki` drives the Meraki
Dashboard API v1 (inventory, events, live diagnostics, and gated config writes to MX/MS/MR);
`wazuh-onprem` drives a self-hosted Wazuh's three APIs - Server on 55000, Indexer on 9200,
Dashboard on 443 - plus SSH edits to `ossec.conf`. They share the shape (live infra,
credential-driven, destructive writes reachable) and no code.

## Entry points
- `skills/cisco-meraki/scripts/meraki_client.py:446` - read-only CLI: orgs, networks, status,
  inventory, events, changes, security-events, air-marshal, live. No write verbs here.
- `skills/cisco-meraki/scripts/meraki_config.py:374` - the only Meraki write path:
  snapshot, diff, apply, rollback, batch-stage, batch-commit.
- `skills/wazuh-onprem/scripts/wazuh_client.py:417` - CLI over the Server API (JWT) and Indexer API
  (basic auth); the generic `post` / `put` / `delete` verbs are registered at `:428-429`.
- `skills/wazuh-onprem/scripts/manager_config.py:251` - SSH-based `ossec.conf` editing: diff, apply,
  rollback, list-backups.

## Owns data
- Meraki config snapshots - pre-write payloads, secrets intact - written by
  `skills/cisco-meraki/scripts/meraki_config.py:120` into `.meraki-snapshots/`, gitignored at
  `.gitignore:272`.
- Wazuh manager config backups (`ossec.conf.bak.<timestamp>`) written on the remote host itself by
  `skills/wazuh-onprem/scripts/manager_config.py:173-176`. Nothing local.

## Calls out to
- Meraki Dashboard API v1 at `skills/cisco-meraki/scripts/meraki_http.py:27`.
- Wazuh Server API and Indexer API at `skills/wazuh-onprem/scripts/wazuh_client.py:103-120`;
  Dashboard saved-objects at `:314`.
- The Wazuh manager over SSH, via `ssh`/`scp` shellouts at
  `skills/wazuh-onprem/scripts/manager_config.py:176`.

## Landmines
- **Wazuh's generic `post` / `put` / `delete` have no gate in code.**
  `skills/wazuh-onprem/scripts/wazuh_client.py:428-429` registers all three taking only `endpoint`,
  `--params` and `--json` - no confirm, no dry-run, no diff. Active response, agent deletion and
  rule or config writes go straight through. The only restraint is prose at
  `skills/wazuh-onprem/SKILL.md:135-146` telling the calling model to confirm first, and prose does
  not restrain a call - it instructs one. This is the sharpest thing in either skill.
- **`--yes` on the Meraki write path auto-confirms.** `skills/cisco-meraki/scripts/meraki_config.py:374`
  and `:414-416`: the flag swaps in `_auto_confirm`, which prints the diff and returns True. Consent
  becomes shown rather than withheld - the diff is displayed to nobody in particular and the write
  proceeds. Meraki collection PUTs are full-replacement (`skills/cisco-meraki/SKILL.md:28-30`), so
  the blast radius of getting this wrong is the whole collection.
- **Rate limiting is handled on one side only.** Meraki honours `Retry-After` then backs off with
  jitter, five retries max (`skills/cisco-meraki/scripts/meraki_http.py:111`, `:124`, `:129`). Wazuh
  has no 429, backoff or retry handling anywhere in `wazuh_client.py` - grepped, zero hits - despite
  its own SKILL.md naming 429s as something to expect. The one retry it does have is a 401 JWT
  refresh at roughly `:179`.
- **An unset `WAZUH_CA_BUNDLE` silently disables TLS verification** with only a printed warning
  (`skills/wazuh-onprem/scripts/wazuh_client.py:74-80`), easily lost in a script's stdout.
- Test coverage is asymmetric: `skills/cisco-meraki/tests/` holds eight `test_*.py` modules;
  `skills/wazuh-onprem/` ships no `tests/` directory at all. The skill with the ungated write verbs
  is the one with no tests.

## Unverified
- Whether the Indexer `_search` / `raw-search` paths
  (`skills/wazuh-onprem/scripts/wazuh_client.py:259-301`) implement `search_after`/PIT pagination in
  code or only describe it in `skills/wazuh-onprem/references/indexer-api.md`, which was not opened.
- Whether `meraki_config.py`'s batch-commit enforces the documented 100-actions / 5-pending-batches
  caps in code, or only documents them (`skills/cisco-meraki/SKILL.md:89`) - only the
  `batch_stage` / `batch_commit` signatures were skimmed.
- The `references/*.md` files for both skills were not opened.
- Whether any credential reaches a snapshot or backup file on disk beyond the documented Meraki
  VPN-PSK and RADIUS-secret case; tracing stopped at `skills/cisco-meraki/scripts/meraki_diff.py`'s redaction list.
- `manager_config.py`'s xmllint validation step is named in comments but was not read line by line.
