# Drata API — Common Tasks

Recipes use the helper (`scripts/drata_client.py`). Set `DRATA_API_KEY` (or the
`DRATA_OAUTH_*` vars) and `DRATA_REGION` first. Prefer importing `DrataClient` for
anything multi-step.

## Connectivity / auth check

```bash
python scripts/drata_client.py whoami
```

## Export all personnel (with compliance status)

```bash
python scripts/drata_client.py get-all /public/personnel > personnel.json
```

Python (filter to non-compliant active staff):

```python
from drata_client import DrataClient
c = DrataClient()
flagged = [
    p for p in c.get_all("/public/personnel")
    if p.get("isActive") and p.get("complianceStatus") == "NON_COMPLIANT"
]
for p in flagged:
    print(p["email"], p["complianceStatus"])
```

`complianceStatus`/`trainingStatus` are computed server-side and can't be written back.
Poll on a schedule (e.g. hourly) — Drata does not offer outbound webhooks for personnel
events.

## Find failing monitoring tests (a compliance gap sweep)

```python
from drata_client import DrataClient
c = DrataClient()
failing = [
    t for t in c.get_all("/public/v2/monitoring-tests", params={"workspaceId": "1"})
    if t.get("checkResultStatus") == "FAILED"
]
for t in failing:
    print("FAIL:", t.get("name"))
```

## Check framework readiness

```python
from drata_client import DrataClient
c = DrataClient()
for fw in c.get_all("/public/v2/frameworks", params={"workspaceId": "1"}):
    ready, total = fw.get("numReadyInScopeRequirements", 0), fw.get("numInScopeRequirements", 0)
    pct = (ready / total * 100) if total else 0
    flag = "" if fw.get("isReady") else "  <-- NOT READY"
    print(f"{fw['name']}: {ready}/{total} ({pct:.0f}%){flag}")
```

## Export all controls

```bash
python scripts/drata_client.py get-all /public/v2/controls --params 'workspaceId=1' > controls.json
```

## Update personnel employment status (write — confirm first)

```bash
# preview
python scripts/drata_client.py --dry-run put /public/personnel/{id}/employment-status \
  --json '{"isActive": false}'
# then, after confirming the target, drop --dry-run to execute
```

## Upload training / other evidence for a user

Drata supports uploading evidence (security / HIPAA / NIST AI training, MFA, disk
encryption, anti-virus, auto-updates, screensaver lock, password manager, etc.) for a
specific user. The exact path and multipart/body shape differ per evidence type — pull
the matching "Add … Evidence" recipe from `https://developers.drata.com/` and confirm
the `workspaceId` and target user id, then POST. Preview with `--dry-run` first.

## Download a published policy PDF

```bash
# 1) get the signed URL
python scripts/drata_client.py get '/public/v2/policies/{id}/download-url'
# 2) fetch the returned signedUrl separately (no Drata auth header) to save the PDF
```

## CI compliance gate (fail the build on failing tests)

```bash
#!/usr/bin/env bash
set -euo pipefail
# env: DRATA_API_KEY, DRATA_REGION, DRATA_READ_ONLY=1  (this gate only reads)
FAILS=$(python scripts/drata_client.py get-all /public/v2/monitoring-tests \
          --params 'workspaceId=1' \
        | jq '[.[] | select(.checkResultStatus=="FAILED")] | length')
echo "Failing monitoring tests: $FAILS"
if [ "$FAILS" -gt 0 ]; then
  python scripts/drata_client.py get-all /public/v2/monitoring-tests --params 'workspaceId=1' \
    | jq -r '.[] | select(.checkResultStatus=="FAILED") | "FAIL: \(.name)"'
  exit 1
fi
```

Store `DRATA_API_KEY` as a CI secret and scope it read-only. Set `DRATA_READ_ONLY=1`
in read-only jobs so a stray mutation can't slip through.
