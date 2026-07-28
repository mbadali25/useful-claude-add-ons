# Alert notifications (Slack, PagerDuty, custom webhook)

This is the `wazuh-integratord` daemon: it watches the alert stream on the manager and pushes matching alerts to an external service. Configured via `<integration>` blocks in `ossec.conf` — deploy with `manager_config.py` per `manager-config.md`.

## Block anatomy

```xml
<integration>
  <name>slack</name>                 <!-- slack | pagerduty | virustotal | shuffle | maltiverse | custom-<name> -->
  <hook_url><URL></hook_url>          <!-- required: slack, shuffle, maltiverse -->
  <api_key><KEY></api_key>            <!-- required: pagerduty, virustotal, maltiverse -->
  <alert_format>json</alert_format>   <!-- required for all of the above -->
  <!-- optional filters — omit any of these to widen scope -->
  <rule_id>100010,100011</rule_id>    <!-- comma-separated rule IDs -->
  <level>12</level>                  <!-- this level and above only -->
  <group>attack,exploit</group>       <!-- comma-separated rule groups -->
  <event_location></event_location>
  <options>{"pretext": "Custom Title"}</options>  <!-- JSON passthrough, service-specific -->
</integration>
```

Put this inside `<ossec_config>` on the **manager**. Use `--anchor integration` on `manager_config.py apply` so new integration blocks group with existing ones.

## Slack

```xml
<integration>
  <name>slack</name>
  <hook_url>https://hooks.slack.com/services/T000/B000/XXXXXXXX</hook_url>
  <level>10</level>
  <alert_format>json</alert_format>
</integration>
```

- Get the webhook URL from Slack's "Incoming Webhooks" app for the target channel.
- Message includes level, rule description, agent ID, timestamp, source; color-coded by severity.
- Narrow noisy channels with `<level>` and/or `<group>` — e.g. `<level>12</level><group>attack,exploit</group>` for criticals only.

## PagerDuty

```xml
<integration>
  <name>pagerduty</name>
  <api_key>YOUR_PAGERDUTY_INTEGRATION_KEY</api_key>
  <level>12</level>
  <alert_format>json</alert_format>
</integration>
```

- Create a PagerDuty service with an **Events API v2** integration; the integration key is what goes in `<api_key>`.
- Wazuh maps alert level to PagerDuty severity automatically (12+ → Critical, on-call paged). Fine-tune the mapping only by editing the integration script at `/var/ossec/integrations/pagerduty` on the manager — that's a script edit, not a config block; treat it like any other manager file change (back it up first).

## Generic webhook / custom integration

For anything without native support (Teams, a custom internal endpoint, etc.), use `custom-<name>` — Wazuh looks for a script named `custom-<name>` in `/var/ossec/integrations/` on the manager:

```xml
<integration>
  <name>custom-teams</name>
  <hook_url><WEBHOOK_URL></hook_url>
  <level>10</level>
  <alert_format>json</alert_format>
</integration>
```

The script receives the alert JSON as an argument and posts it however you write it — this is a small script-authoring task, not just a config block. Base it on the existing `slack`/`pagerduty` scripts in that directory for the calling convention.

## Known gotcha — don't run Slack + PagerDuty carelessly together

Multiple `<integration>` blocks of *different* names can coexist, but there's a documented bug where the integrator daemon can pick up the wrong alert file when two integrations are both configured, breaking one of them intermittently (order-dependent). If you add a second integration on a box that already has one:

1. Add it, apply, restart.
2. Trigger a test alert for **each** integration separately and confirm both actually fire, not just that the config test passed.
3. If one silently stops working, it's this known conflict, not a bad config — check for it before re-debugging the XML.

## Verifying it's actually live

Config test passing only means the XML is well-formed and the fields are valid — it doesn't confirm the webhook/key actually delivers. After `apply --restart`:

```bash
# On the manager, watch the integrator log while you trigger a matching alert
tail -f /var/ossec/logs/integrations.log
```
