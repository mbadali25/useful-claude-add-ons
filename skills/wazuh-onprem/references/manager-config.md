# Editing the manager's ossec.conf over SSH

Notification integrations, new log feeds (O365, Cloudflare, etc.), and automated runbook actions all live in the same place: XML blocks inside `/var/ossec/etc/ossec.conf` on the **manager** host. There's no HTTP API for most of this on-prem, so this skill edits it over SSH using `scripts/manager_config.py`.

## Reachability — read this first

`manager_config.py` shells out to the local `ssh`/`scp` binaries. It only works if the machine running it can route to the manager host and has an authorized key. In a sandboxed agent environment with no path to the on-prem network, connection attempts will simply fail — that's expected, not a bug. Two ways to actually use this:

1. Run the script yourself on a box that has network access to the manager (copy `manager_config.py` there — no dependency beyond `ssh`/`scp`/`xmllint` on the target).
2. Give the current session real network reachability + a key, if the environment supports it.

Either way, confirm reachability first (`ssh $WAZUH_SSH_USER@$WAZUH_SSH_HOST true`) before trusting any of the workflow below.

## Setup

```bash
export WAZUH_SSH_HOST="wazuh-manager.example.local"
export WAZUH_SSH_USER="ops"                      # needs sudo rights over /var/ossec/etc and the service
export WAZUH_SSH_KEY_PATH="/path/to/id_ed25519"   # key-based auth strongly preferred over password
export WAZUH_SSH_PORT="22"                        # optional, default 22
export WAZUH_CONF_PATH="/var/ossec/etc/ossec.conf"  # optional, this is the default
```

## The safe-edit flow (`apply`)

Every `apply` call — no matter what block it's inserting — does the same six steps, and stops at the first failure:

1. **Backup** the live `ossec.conf` remotely to `ossec.conf.bak.<timestamp>` (never overwritten, never deleted automatically).
2. **Fetch** the current config.
3. **Build the candidate** by inserting your XML fragment — by default just before `</ossec_config>`, or after a named tag's last occurrence via `--anchor` (e.g. `--anchor integration` to group with existing integration blocks).
4. **Validate well-formedness** with `xmllint --noout` on the candidate *before* it touches the live file. Malformed XML aborts here — nothing is installed.
5. **Install and config-test**: copies the candidate over the live path, then runs `wazuh-analysisd -t` (falls back to `ossec-analysisd -t` on older installs). **Any failure triggers an automatic rollback** to the pre-edit backup.
6. **Restart — only if you pass `--restart`.** A passing config test does not restart the manager on its own. Until restarted, the new config is written but not the running one.

```bash
# Always preview first — shows a unified diff, touches nothing remote
python scripts/manager_config.py diff --block new_block.xml

# Apply: validates and installs, but does NOT restart the manager
python scripts/manager_config.py apply --block new_block.xml

# Apply AND restart in one step, once you're ready to go live
python scripts/manager_config.py apply --block new_block.xml --restart

# Something went wrong later? Roll back to a specific backup
python scripts/manager_config.py list-backups
python scripts/manager_config.py rollback --backup /var/ossec/etc/ossec.conf.bak.20260727-120000
```

## Safety rules this skill follows

- **Never restart the manager without the user's explicit go-ahead.** Config test passing is not the same as "ship it" — a live restart briefly interrupts alert processing, which matters on a production SIEM. Default to `apply` without `--restart`, tell the user the config is staged, and let them choose when to flip it live.
- **Always run `diff` and show the user what will change before `apply`.** Don't construct and install an XML block the user hasn't seen.
- **One logical change per `apply` call.** Don't bundle an integration + a feed + a runbook into one XML fragment — if something fails, a smaller blast radius is easier to reason about and roll back.
- **Never touch decoders/rules files and ossec.conf in the same operation** without saying so explicitly — they have separate reload semantics.
- **Reference `integrations.md`, `log-sources.md`, or `runbooks.md`** for the actual XML content to insert — this file only covers the delivery mechanism.

## Related, but separate, validation surfaces

- `xmllint --noout` — is it well-formed XML? (this skill checks it before every install)
- `wazuh-analysisd -t` — does Wazuh accept the *values* (valid module names, required fields)? (checked after install, auto-rollback on failure)
- `wazuh-logtest` — once live, does a specific log line actually decode and match the rules you expect? Use this to confirm new feeds/rules are working, not just syntactically valid.
