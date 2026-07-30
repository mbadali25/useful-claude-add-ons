# Writing tickets and notes worth reading

The test for any ticket is: **six weeks from now, during an incident, can someone
who wasn't there reconstruct what happened from this alone?** If not, it's a
placeholder, not a record.

## Titles

Pattern: `<system> - <what happened>`, under about 80 characters, specific enough
to be recognised in a list of two hundred.

| Instead of | Write |
| --- | --- |
| `Server issue` | `SQL01 - RAID array rebuild after disk 2 failure` |
| `Fixed AD` | `DC02 - LDAP binds failing after July patch cycle` |
| `Azure work` | `Azure prod - added NSG rule for new VPN subnet 10.20.0.0/24` |
| `DB maintenance` | `PG-PROD-01 - vacuum full on orders table, 340GB reclaimed` |
| `Network stuff` | `CORE-SW-01 - replaced failing SFP in port 24` |
| `Terraform changes` | `terraform - moved prod state to S3 backend with DynamoDB locking` |

Put the hostname or resource identifier in. It's the single highest-value thing in
a title, and it's what people search for.

If the work is planned rather than reactive, say so - `[Planned]` or `[Change]` as
a prefix reads clearly and helps whoever triages the queue.

## Bodies

The shape that survives contact with a real incident:

```
## What changed
One or two sentences. The single most important part - put it first.

## Why
The trigger: an alert, a ticket, a request, a failure. Include the timestamp
and the exact error if there was one.

## Steps taken
- Chronological, with commands or console paths where they matter
- Include things that didn't work, and why you ruled them out

## Verification
How you know it worked. Specific checks, not "confirmed working".

## Impact / rollback
Downtime taken, who was affected, and how to undo it.
```

Drop sections that don't apply. A five-minute DNS record change doesn't need a
rollback plan section; a database migration absolutely does.

### Always include, when they exist

- Hostnames, IPs, FQDNs, instance IDs, resource groups, ARNs
- Exact error text - paste it, don't paraphrase it
- KB numbers, package versions, image tags, AMI IDs
- Change window start and end times
- Ticket or alert IDs that triggered the work
- Names of anyone who approved or was notified

### Never include

- Passwords, keys, tokens, connection strings with credentials
- Full config dumps containing secrets
- Personal details about employees beyond what the work requires

The tool scrubs the obvious cases automatically and tells you on stderr what it
masked, but describe secrets rather than pasting them: "rotated the svc_backup
password and updated the credential in the scheduled task" says everything needed.

## Notes during the work

Notes are the timeline. Each one should be readable on its own, because people
skim them in reverse order during an outage.

Add a note when:

- A change is actually applied (not when you plan it)
- You find the root cause
- A verification step passes or fails
- You roll something back
- You pause, hand off, or hit a blocker

Skip notes for routine intermediate commands. A note per `kubectl get pods` is
noise that buries the three notes that matter.

Good note:

```
14:32 - Applied the NSG rule via Azure CLI:
az network nsg rule create -g rg-prod-net --nsg-name nsg-vpn \
  -n allow-https-vpn --priority 210 --source-address-prefixes 10.20.0.0/24 \
  --destination-port-ranges 443 --access Allow --protocol Tcp

Verified from a client in 10.20.0.0/24: curl to the internal API returns 200.
Effective rules confirmed with `az network nic list-effective-nsg`.
```

Weak note: `Added the firewall rule, works now.`

The difference isn't length - it's that the first one names the resource, shows
what was actually run, and states how it was checked.

## Worked examples by domain

### Windows Server

```
Title: FS02 - expanded D: volume from 500GB to 1TB

## What changed
Extended the D: data volume on FS02 from 500GB to 1TB.

## Why
Disk space alert at 92% on 2026-07-29 06:40. Growth traced to the
department share, ~8GB/week.

## Steps taken
- Expanded the underlying VMDK in vCenter to 1TB
- Rescanned disks in Disk Management
- Extended the volume: `Resize-Partition -DriveLetter D -Size 1TB`

## Verification
`Get-Volume D` reports 1TB with 512GB free. Share accessible; no
reconnect needed by clients. Alert cleared.

## Impact / rollback
No downtime; online extension. Shrinking is not practical, so rollback
would require a restore from the 07-28 backup.
```

### Active Directory

```
Title: DC01/DC02 - fixed SYSVOL replication backlog after DFSR journal wrap

## What changed
Cleared a DFSR journal wrap on DC02 and forced a non-authoritative sync
of SYSVOL.

## Why
`dcdiag` reported SysvolCheck failure on DC02. Event 4012 in the DFS
Replication log: replication stopped for 60+ days, journal wrapped.

## Steps taken
- Confirmed DC01 held a good SYSVOL copy
- Set DC02 msDFSR-Enabled to FALSE, polled AD, then TRUE (D2 restore)
- Monitored for event 4614 then 4604

## Verification
Event 4604 logged on DC02 at 11:52. `dcdiag /test:sysvolcheck` and
`repadmin /replsummary` both clean. GPO count matches DC01.

## Impact / rollback
No user impact - DC01 served policy throughout. GPO changes were frozen
during the window.
```

### AWS / Azure

```
Title: AWS prod - resized RDS orders-db from db.t3.large to db.r6g.xlarge

## What changed
Scaled the orders-db RDS instance up one class and switched to Graviton.

## Why
CPU credit balance exhausted daily since the 07-20 release; p99 query
latency up 4x. Approved in CHG-1182.

## Steps taken
- Snapshot orders-db-pre-resize-20260729 taken first
- Modified the instance with apply-immediately during the 02:00-04:00 window
- Failover completed in 3m40s

## Verification
CPU steady at 18% (was pegged). p99 latency back to 140ms. Application
error rate zero for 6h post-change. CloudWatch alarms cleared.

## Impact / rollback
3m40s connection interruption during failover; app retried cleanly.
Rollback is a modify back to db.t3.large, or restore from the snapshot.
```

### Databases

```
Title: PG-PROD-01 - vacuum full on orders table, 340GB reclaimed

## What changed
Ran VACUUM FULL on public.orders during the maintenance window.

## Why
Table bloat at 61% per pgstattuple after the 90-day archival delete.
Sequential scans were reading dead tuples.

## Steps taken
- Verified 400GB free on the data volume (VACUUM FULL needs a full rewrite)
- Paused the ETL job to avoid lock contention
- Ran VACUUM FULL VERBOSE ANALYZE public.orders - 47 minutes
- Resumed ETL

## Verification
Table size 552GB -> 212GB. Bloat 61% -> 2%. Nightly report query dropped
from 94s to 11s.

## Impact / rollback
ACCESS EXCLUSIVE lock held for 47 minutes; the table was unavailable and
the ETL was paused. Not reversible, and not harmful.
```

### Linux

```
Title: web03 - patched OpenSSL for CVE-2026-XXXX and restarted nginx

## What changed
Updated openssl 3.0.13-1 -> 3.0.15-1 and restarted nginx.

## Why
CVE-2026-XXXX, flagged critical by the scanner on 2026-07-28.

## Steps taken
- Pulled web03 from the load balancer
- `apt-get update && apt-get install --only-upgrade openssl libssl3`
- `systemctl restart nginx`
- Returned to the LB pool after health checks passed

## Verification
`openssl version` reports 3.0.15. `nginx -t` clean. Rescan shows the
finding resolved. LB health checks green for 30 minutes.

## Impact / rollback
No user impact - one node at a time behind the LB. Rollback would be
`apt-get install openssl=3.0.13-1`.
```

### DevOps / IaC

```
Title: terraform - moved prod state to S3 backend with DynamoDB locking

## What changed
Migrated the prod Terraform state from local to s3://si-tfstate-prod,
with state locking via the tf-locks DynamoDB table.

## Why
Two engineers overwrote each other's state last week. No locking, and
the state file only existed on one laptop.

## Steps taken
- Created the bucket with versioning and SSE-KMS; created tf-locks (LockID hash key)
- Added the backend block and ran `terraform init -migrate-state`
- Confirmed `terraform plan` showed no changes after migration
- Archived the local state file to the ops vault, then removed it

## Verification
Plan is a no-op, so state migrated intact. Concurrent `plan` from a
second machine blocks on the lock as expected. Bucket versioning on.

## Impact / rollback
No infrastructure changed. Rollback is reverting the backend block and
restoring the archived local state.
```

## Platform differences that affect formatting

`--body-file` takes plain text with light markdown. Conversion is automatic:

| You write | ServiceDesk Plus | Jira |
| --- | --- | --- |
| `## Heading` | Bold line | Real heading |
| `- item` | Bullet character | Bullet list |
| ` ```code``` ` | `<pre>` block | Code block, monospace |
| Blank line | Line break | Paragraph break |

Nothing more complex is supported by design - tables, nested lists, and inline
links convert unreliably across both platforms and aren't worth the failure modes.
If you need a table, a fenced code block holds its alignment in both tools.

Two limits to be aware of: ServiceDesk Plus caps the subject at 250 characters,
Jira caps the summary at 255. The tool truncates rather than failing, but a
title that long is a symptom - put the detail in the body.
