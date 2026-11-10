<!-- Moved verbatim from plugin/crew/README.md (7b. The API, feature and integrations reference) by L-0726; the README keeps an index entry. -->

## 7b. The API, feature and integrations reference

```
/crew:reference                # both, whole repo
/crew:reference --api          # endpoints only
/crew:reference --features     # jobs, consumers, CLI, flags, integrations
/crew:reference --integrations # every outbound call, linted before it is written
/crew:reference --audit        # report drift, change nothing
```

The code map and the reference answer different questions, and the second does not fall out of the first. `.crew/codemap/orders.md` saying *"handles order lifecycle, entry `src/Orders/`"* is a good codemap entry and tells you nothing about the eleven endpoints underneath it.

| Document | Audience | Question |
|---|---|---|
| `.crew/codemap/` | an agent about to change code | where does this live |
| `docs/reference/api.md` | a human calling the thing | what can I call, and what does it do to the system |
| `docs/reference/features.md` | a human operating the thing | what can it do, including the parts with no UI |
| `docs/reference/integrations.md` | a human debugging a call out | what does it call, with which credential source, and how does each call fail |

**`--integrations` (since 1.1.13).** One `##` per external system, one `###` entry per outbound call, each with a `path:line` anchor and an `Auth:` line naming where the credential comes from (an env var, a secret name, a config key, `none` or `undocumented - needs a human`) — never its value. The draft is written outside the repo and copied into `docs/reference/` only once `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/crew_reference.py lint --root . --kind integrations <draft>` exits 0 (1: problems, each `<doc>:<line>`; 2: usage error or an unreadable file). The lint refuses a doc with no `> Generated from <repo>@<sha> on <date>` header, an entry with no anchor or no `Auth:` line, an anchor to a file that is missing, outside the repo (symlinks resolved) or shorter than the cited line, a doc with no entry (a repo that calls nothing writes no file and says so), and any secret-shaped string — AWS access key ids and secret keys, private-key blocks, GitHub, Slack, Stripe, Google, npm and SendGrid keys, `sk-` keys, Slack webhook URLs, JWTs, credentials in a URL, an `Authorization:` value, a quoted or unquoted literal assigned to a password/secret/token/API-key name — naming the pattern and line, never the value. The header must be the first non-blank line, and absolute or `../` anchors are refused. The patterns are known shapes only: a novel token format passes, so `crew:security`'s review stays the second line. Auth lines go to `crew:security` before the write. The format is `skills/crew-docs/integrations.md`. The doc is judged by the refresh check (below) as a `reference` artifact. Named end-to-end flow docs (`--flows`) are a separate ticket, L-0549.

### The two rules

**Every entry is anchored to `file:line`.** Unanchored, it cannot be re-verified, so it rots silently and keeps being trusted. Same reason codemap notes carry anchors.

**Enumerate from the code, never from the existing docs.** The existing docs are what you are checking. A reference regenerated from a stale reference is a stale reference with a newer date.

### What is worth the effort

For an endpoint the signature is the guessable part. The valuable half is underneath it:

```
### POST /api/orders/{id}/ship
`src/Controllers/OrderController.cs:142`

Auth: bearer token, role `fulfilment`  (`Attributes/RequireRole.cs:20`)
Body: `{ carrier: string, tracking: string }`
Returns: 200 `{ shipmentId }` | 404 unknown order | 409 already shipped
Side effects: writes `shipments`, emits `order.shipped`, calls ShipStation
Notes: not idempotent - a retry creates a second shipment
```

Side effects, error responses, and idempotency. That last line is the one that causes incidents.

For features, the headless ones are what nobody documents and everybody needs: scheduled jobs and what happens when one is missed, queue consumers, admin scripts, feature flags and the config keys behind them.

### Keeping it honest

`--audit` reports drift both ways - endpoints in the code with no entry, and entries whose anchor no longer holds - and changes nothing. A reference quietly rewritten is indistinguishable from one that was right all along.

Anything unconfirmed is written as `undocumented - needs a human` and left visible. A reference that admits a gap is useful; one that implies full coverage while missing a third of the endpoints is worse than none, because a missing endpoint reads as proof it does not exist.
