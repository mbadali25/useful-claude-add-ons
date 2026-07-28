# Runbooks — playbooks and automated active response

"Runbook" covers two different deliverables. Build both when asked for a runbook on a given alert/rule — they complement each other rather than compete:

1. **A static playbook** — what a human does when the alert fires. Always write this first; it's the source of truth for what "correct response" even means.
2. **Automated active response** — what Wazuh does automatically, tied to specific rule IDs. Only automate steps that are safe to run without a human in the loop.

## 1. Static playbook

Keep these as markdown, one per alert/rule-group, versioned alongside the ossec.conf backups so they evolve together. A minimal template:

```markdown
# Runbook: <Alert name, e.g. "Multiple failed SSH logins">

**Triggers on:** rule ID(s) ____, rule group ____, level ≥ ____
**Typical false positives:** ____

## Triage (first 5 minutes)
1. Confirm scope — which agent(s)/IP(s), is it ongoing or historical
2. Check for related alerts in the same window (`search` / `raw-search` against the Indexer)
3. Classify: contained noise, real but low-risk, active incident

## Response
- If [condition]: do X
- If [condition]: escalate to Y, page via [integration — see integrations.md]

## Automated actions already in place for this rule
(list any active-response wired to this rule ID — see section 2 below, so the human
knows what already happened before they arrive)

## Post-incident
- [ ] Rule tuning needed? (adjust level/group/suppression)
- [ ] Update this runbook if the response didn't fit reality
```

Generate this from context you already have: the rule's description/level/group (pull via Server API `get /rules?rule_ids=...` — see `server-api.md`), and recent real examples from the Indexer to ground the triage steps in what this alert actually looks like on this deployment, not a generic template.

## 2. Automated active response

Only for actions safe to run unattended — reversible, well-scoped, low blast-radius. Two ways to trigger, and they answer different questions:

| Trigger | Question it answers | Where it's configured |
|---|---|---|
| **Persistent, rule-bound** | "Every time rule X fires, always do Y" | `ossec.conf` `<active-response>` block (this section) |
| **Ad hoc, on demand** | "Run this action right now, on these agents" | Server API `PUT /active-response` (already in `server-api.md`) |

### Persistent active response — ossec.conf block

```xml
<active-response>
  <disabled>no</disabled>
  <command>firewall-drop</command>       <!-- one of the built-in commands, or a <command> you defined -->
  <location>local</location>              <!-- local = on the endpoint where the alert triggered -->
  <rules_id>100010,100011</rules_id>      <!-- comma-separated rule IDs this responds to -->
  <timeout>600</timeout>                  <!-- optional: auto-reverse after N seconds, where the command supports it -->
</active-response>
```

Deploy with `manager_config.py apply --block block.xml --anchor active-response` per `manager-config.md`. Built-in commands include `firewall-drop`, `restart-wazuh`, `disable-account`, `host-deny` — check what's already registered under `<command>` blocks in the existing config before assuming one is available.

### Custom command (your own script)

```xml
<command>
  <name>my-response</name>
  <executable>my-response.sh</executable>   <!-- must live in /var/ossec/active-response/bin/ on the agent -->
  <timeout_allowed>yes</timeout_allowed>
</command>

<active-response>
  <disabled>no</disabled>
  <command>my-response</command>
  <location>local</location>
  <rules_id>100012</rules_id>
</active-response>
```

The script itself has to exist on the agent(s) at that path with correct permissions — the `<command>` block just registers it, it doesn't deploy the script.

### Ad hoc trigger (no persistent binding — run once, right now)

Use the existing Server API path for this instead of touching ossec.conf:

```bash
python scripts/wazuh_client.py put /active-response --json '{"command":"restart-wazuh0","agents_list":["001","002"]}'
```

## Safety — this is the highest-blast-radius part of the whole skill

- **Never wire a new persistent active-response without the user confirming the exact rule IDs and the exact command.** A wrong `rules_id` list means the action fires on the wrong alerts at scale.
- **Prefer `timeout`-bound / reversible actions** (temporary block, temporary disable) over permanent ones unless the user explicitly wants permanent.
- **Test with the ad hoc Server API trigger on one known agent first**, confirm the actual effect, before binding it persistently to a rule.
- **Fleet-wide persistent active-response is exactly the case `SKILL.md`'s top-level safety rails already call out** — don't push it live without an explicit, scoped instruction naming the rule IDs and the command.
