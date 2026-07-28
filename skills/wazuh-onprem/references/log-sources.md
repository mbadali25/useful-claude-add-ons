# Onboarding new log feeds

Both of these are `ossec.conf` module blocks deployed via `manager_config.py` (see `manager-config.md`). They're fundamentally different maturity levels — know which one you're dealing with before promising a timeline.

| Source | Wazuh support | Effort |
|---|---|---|
| **Office 365 / Microsoft 365** | Native built-in module (`office365`, or `ms-graph` for the newer/broader Graph API surface) | Config block + Azure app registration |
| **Cloudflare** | **No native module.** Community pattern only | Config block + a custom Python collector script + custom decoder/rules |

## Office 365 — native `office365` module

### Prerequisites (Azure side, not Wazuh)

1. Register an app in **Azure AD > App registrations**.
2. Under **API permissions**, add (Application permissions): `Office 365 Management APIs > ActivityFeed.Read`, and `ActivityFeed.ReadDlp` if you want DLP events too.
3. **Grant admin consent** for those permissions.
4. Under **Certificates & secrets**, create a client secret — copy the value immediately, it's shown once.
5. Note the tenant ID, application (client) ID, and the secret.

### ossec.conf block (on the agent monitoring O365, or the manager if that's where it's configured)

```xml
<office365>
  <enabled>yes</enabled>
  <only_future_events>yes</only_future_events>
  <interval>1m</interval>
  <curl_max_size>1M</curl_max_size>
  <api_auth>
    <tenant_id>YOUR_TENANT_ID</tenant_id>
    <client_id>YOUR_CLIENT_ID</client_id>
    <client_secret>YOUR_CLIENT_SECRET</client_secret>
    <api_type>commercial</api_type>   <!-- use gov_community / gov_dod / gov_gcc_high for US Gov clouds -->
  </api_auth>
  <subscriptions>
    <subscription>Audit.AzureActiveDirectory</subscription>
    <subscription>Audit.General</subscription>
    <!-- also available: Audit.Exchange, Audit.SharePoint, DLP.All -->
  </subscriptions>
</office365>
```

- Multiple `<api_auth>` blocks under one `<office365>` = multi-tenant monitoring from a single collector.
- `only_future_events: yes` avoids replaying historical events on first enable — flip to `no` deliberately if you want backfill, and expect a large initial burst.

### If you need broader signal (Intune, sign-ins, risk detections, security alerts): use `ms-graph` instead/also

```xml
<ms-graph>
  <enabled>yes</enabled>
  <only_future_events>yes</only_future_events>
  <curl_max_size>10M</curl_max_size>
  <run_on_start>yes</run_on_start>
  <interval>5m</interval>
  <version>v1.0</version>
  <api_auth>
    <client_id>YOUR_APPLICATION_ID</client_id>
    <tenant_id>YOUR_TENANT_ID</tenant_id>
    <secret_value>YOUR_SECRET_VALUE</secret_value>
    <api_type>global</api_type>
  </api_auth>
  <resource>
    <name>security</name>
    <relationship>alerts_v2</relationship>
    <relationship>incidents</relationship>
  </resource>
  <resource>
    <name>deviceManagement</name>
    <relationship>auditEvents</relationship>
  </resource>
</ms-graph>
```

`office365` and `ms-graph` are separate modules with separate API surfaces (Management Activity API vs. Microsoft Graph) — decide based on what data you actually want, don't assume one supersedes the other.

### After deploying

Restart the manager (or the specific agent, if that's where the module runs), then confirm ingestion:

```bash
tail -f /var/ossec/logs/ossec.log | grep -i office365   # or ms-graph
```
New events land as standard Wazuh alerts — no custom decoders needed, the built-in ruleset covers these fields. Extend `local_rules.xml` if you want custom alerting on specific O365 event types.

## Cloudflare — no native module, build the bridge yourself

Cloudflare cannot push directly to Wazuh, and Wazuh has no built-in Cloudflare collector. The community-standard pattern is: a small Python script that pulls from Cloudflare's API, writes JSON lines to a log file, and a `localfile` block reads that file. Which Cloudflare API depends on plan tier:

| Cloudflare plan | Mechanism |
|---|---|
| Free/Pro (no Logpush) | Pull via Cloudflare's Audit Logs API (or GraphQL Analytics API for firewall events) on a schedule |
| Enterprise (Logpush available) | Cloudflare pushes logs to S3 → Wazuh's built-in `aws-s3` wodle reads them (this direction *is* natively supported) |

### Path A — Enterprise / Logpush to S3 (prefer this if available — no custom script)

1. In Cloudflare, configure Logpush to an S3 bucket: `https://developers.cloudflare.com/logs/get-started/enable-destinations/`
2. On the manager, add an `aws-s3` wodle bucket block:

```xml
<wodle name="aws-s3">
  <disabled>no</disabled>
  <interval>10m</interval>
  <run_on_start>yes</run_on_start>
  <skip_on_error>yes</skip_on_error>
  <bucket type="custom">
    <only_logs_after>2026-JAN-01</only_logs_after>
    <name>your-cloudflare-logpush-bucket</name>
    <path>example.com/logs</path>
    <aws_profile>cloudflare-s3</aws_profile>
  </bucket>
</wodle>
```

This reuses Wazuh's existing AWS integration — no custom script to maintain.

### Path B — any plan, API-pull script (the common case if not Enterprise)

1. Write (or adapt) a Python script that calls Cloudflare's API (Audit Logs, or GraphQL for firewall/security events) with a Cloudflare API token, and appends each event as one JSON line to a log file, e.g. `/var/ossec/logs/cloudflare.log`.
2. Place it at `/var/ossec/integrations/cloudflare-logs.py`, `chmod 750`, `chown root:wazuh`.
3. Schedule it as a `wodle command` and point a `localfile` at its output:

```xml
<wodle name="command">
  <disabled>no</disabled>
  <tag>cloudflare</tag>
  <command>/bin/bash -c "/usr/bin/python3 /var/ossec/integrations/cloudflare-logs.py"</command>
  <interval>1h</interval>
</wodle>

<localfile>
  <location>/var/ossec/logs/cloudflare.log</location>
  <log_format>json</log_format>
</localfile>
```

4. **Custom rules** (JSON needs no decoder — Wazuh's JSON decoder handles it; you still need rules to classify/alert on it):

```xml
<group name="cloudflare,">
  <rule id="101000" level="0">
    <decoded_as>json</decoded_as>
    <field name="integration">cloudflare</field>
    <description>Cloudflare default grouping rule.</description>
  </rule>
  <!-- Add child rules with <if_sid>101000</if_sid> for specific fields,
       e.g. action == "block" at a meaningful level. -->
</group>
```

Reserve a rule-ID range (e.g. 101000–101999) for this so it doesn't collide with other custom rules — check `references/version-notes.md` / existing `local_rules.xml` for what's already taken.

5. Validate before going live: `wazuh-logtest` with a sample Cloudflare JSON line to confirm the rule actually fires, *before* relying on the live pipeline.

### Honest framing for the user

Path B is a maintained integration, not a one-time config block — the Cloudflare API, auth token, and JSON shape can all change upstream, and it's your script to keep working. Say this explicitly rather than presenting it as equivalent in durability to the native `office365` module.
