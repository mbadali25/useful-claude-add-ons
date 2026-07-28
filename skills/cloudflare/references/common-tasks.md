# Common tasks

Recipes assume `CLOUDFLARE_API_TOKEN` is exported and the client is on `scripts/`.
Every mutating example shows the safe pattern: preview, then confirm.

## 1. Bulk DNS export

Export every record in a zone to a file (auto-paginates, DNS allows big pages):

```bash
zid=$(python scripts/cloudflare_client.py zone-id example.com)
python scripts/cloudflare_client.py get-all /zones/$zid/dns_records > dns_export.json
```

## 2. Bulk DNS import

Loop the export and POST each record. **Dry-run first**, inspect, then drop `--dry-run`:

```bash
zid=$(python scripts/cloudflare_client.py zone-id example.com)
jq -c '.[] | {type,name,content,ttl,proxied}' dns_export.json | while read -r rec; do
  python scripts/cloudflare_client.py post /zones/$zid/dns_records --json "$rec" --dry-run
done
```

Cloudflare also has a bulk import endpoint that accepts a BIND zone file:
`POST /zones/{zid}/dns_records/import` (multipart). Prefer it for large migrations.

## 3. DNS upsert (create or update by name+type)

```bash
zid=$(python scripts/cloudflare_client.py zone-id example.com)
rid=$(python scripts/cloudflare_client.py get /zones/$zid/dns_records \
        --params type=A name=www.example.com | jq -r '.result[0].id // empty')

body='{"type":"A","name":"www","content":"5.6.7.8","ttl":300,"proxied":true}'
if [ -n "$rid" ]; then
  python scripts/cloudflare_client.py put /zones/$zid/dns_records/$rid --json "$body" --dry-run
else
  python scripts/cloudflare_client.py post /zones/$zid/dns_records --json "$body" --dry-run
fi
```

Before editing/deleting, check `MX`/`TXT`/`SPF` records - a careless change can break
mail delivery or SPF/DKIM alignment.

## 4. Cache purge: targeted vs full

Prefer targeted purge. A full purge can spike origin load.

```bash
zid=$(python scripts/cloudflare_client.py zone-id example.com)

# Targeted - specific URLs (safe):
python scripts/cloudflare_client.py post /zones/$zid/purge_cache \
  --json '{"files":["https://example.com/app.js","https://example.com/style.css"]}'

# By hostname or cache-tag (Enterprise):
python scripts/cloudflare_client.py post /zones/$zid/purge_cache --json '{"hosts":["img.example.com"]}'

# Full purge - last resort, confirm explicitly:
python scripts/cloudflare_client.py post /zones/$zid/purge_cache \
  --json '{"purge_everything":true}' --dry-run
```

## 5. Mint a least-privilege token (read-only DNS auditor)

First find the permission group id for `Zone / DNS / Read`, then create the token:

```bash
python scripts/cloudflare_client.py get /user/tokens/permission_groups --params per_page=100 \
  | jq '.result[] | select(.name=="DNS Read") | {id,name}'

zid=$(python scripts/cloudflare_client.py zone-id example.com)
python scripts/cloudflare_client.py post /user/tokens --json '{
  "name": "dns-auditor-example.com",
  "policies": [{
    "effect": "allow",
    "resources": {"com.cloudflare.api.account.zone.'"$zid"'": "*"},
    "permission_groups": [{"id": "<DNS_READ_PERMISSION_GROUP_ID>"}]
  }]
}' --dry-run
```

## 6. List all zones in an account

```bash
aid=$(python scripts/cloudflare_client.py account-id "My Org")
python scripts/cloudflare_client.py get-all /zones --params account.id=$aid \
  | jq -r '.[] | "\(.name)\t\(.id)\t\(.status)"'
```

## 7. Find a proxied record's real origin

When a record is proxied (orange cloud), public DNS returns Cloudflare anycast IPs,
not the origin. The origin is the `content` field in the API record itself:

```bash
zid=$(python scripts/cloudflare_client.py zone-id example.com)
python scripts/cloudflare_client.py get /zones/$zid/dns_records --params name=www.example.com \
  | jq -r '.result[] | "\(.name)\t\(.content)\tproxied=\(.proxied)"'
```

Flipping `proxied` from `true` to `false` exposes that origin IP publicly and drops
WAF/DDoS coverage - treat it as a production-affecting change, not a toggle.
