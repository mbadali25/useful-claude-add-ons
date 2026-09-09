# Changing data in KnowBe4

The Reporting API cannot write. Every mutation goes through one of three routes.

Contents: [Choosing a route](#choosing-a-route) · [SCIM](#scim-20) · [ADI](#active-directory-integration-adi) ·
[Console-only](#console-only-operations) · [Drift](#the-drift-problem)

## Choosing a route

| Route | Good for | Requires |
|---|---|---|
| **SCIM 2.0** | Ongoing joiner/mover/leaver from Okta or Entra ID | SAML SSO configured first, SCIM token |
| **ADI (AD Integration)** | On-prem AD as source of truth, no cloud IdP | ADI agent + AD |
| **Graph API (GraphQL)** | Scripted bulk operations, one-off remediation, iPaaS workflows | Diamond tier, Product API token with Read/Write scope |
| **Console / CSV upload** | One-off bulk import, hard deletes, anything else can't model | Admin login |

The Reporting API is the only one of KnowBe4's APIs that cannot write. Do not generalise
"the KnowBe4 API is read-only" — that is true of the Reporting API specifically.

Pick the route that matches where identity actually lives. If the org already provisions
everything else from Entra or Okta, adding KnowBe4 to that flow is less work over a year than
any script, and it removes the drift problem instead of managing it.

## SCIM 2.0

| Item | Value |
|---|---|
| Endpoint | `https://training.knowbe4.com/scim/v2` |
| Token | Account Settings → User Management → SCIM. **Separate from the Reporting API token** |
| Hard prerequisite | SAML SSO must be configured first, or provisioning silently fails |
| Direction | One-way, IdP → KnowBe4. Console changes never sync back |
| Documented IdPs | Okta, Microsoft Entra ID (Azure AD). Others may work, undocumented |

Supported operations:

| Operation | Call |
|---|---|
| Create user | `POST /Users` |
| Update user | `PUT /Users/{id}` |
| Deactivate (archive) | `PATCH /Users/{id}` with `{"active": false}` |
| List / get users | `GET /Users`, `GET /Users/{id}` |
| Create group | `POST /Groups` |
| Change group members | `PATCH /Groups/{id}` |
| List groups | `GET /Groups` |

Limits worth stating up front:

- SCIM delete **archives**, it does not hard-delete. Archived users still appear in historical
  reporting and may still count for some reporting purposes.
- SCIM creates **console groups only**. Smart Groups are attribute-driven and console-only.
- Computed fields (`phish_prone_percentage`, `current_risk_score`) cannot be set or overridden
  by any route.

Offboarding via SCIM in practice: unassign the KnowBe4 app in the IdP → IdP sends
`PATCH /Users/{id}` with `active: false` → KnowBe4 archives the user, revokes console access,
and drops them from active campaigns while retaining history.

## Graph API (GraphQL)

KnowBe4's Graph API supports queries **and mutations**, and covers most functions of the
supported products — including creating and updating users, groups, phishing and training
objects. This is a genuine write surface, distinct from SCIM.

| Item | Value |
|---|---|
| Protocol | GraphQL |
| Base URL | Same regional hosts as the Reporting API (`us.` / `ca.` / `eu.` / `uk.` / `de.api.knowbe4.com`) |
| Token | Account Settings → Account Integrations → **Product API** → Create New API Token |
| Scope | Choose **Read/Write** at token creation; Read Only is also available |
| Tier gate | **Diamond only** |
| Also used by | iPaaS connectors (Make, Workato, Tray) and the SecurityCoach / PasswordIQ / PhishER integrations |

Partner and multi-account organisations must create the token from the management admin account.

### When it is the right tool, and when it is a trap

Good uses: bulk remediation the console makes painful (merging or archiving hundreds of records),
reporting that the REST API cannot express, and event-driven workflows via an iPaaS.

The trap: **if SCIM or ADI is provisioning users, the Graph API is a second writer to the same
records.** Anything it sets on a SCIM-mapped field is overwritten at the next sync, silently and
on a 40-minute cycle. Before recommending it for user data, establish which system owns each
field. Using it for a one-off cleanup while provisioning is paused is sound; using it as an
ongoing provisioning path alongside SCIM is how drift gets built in deliberately.

Prefer Read Only tokens unless a write is actually needed, and set an expiry.

### Find out what exists before planning around it

"Most functions of the supported products" is marketing copy, not a specification. Introspect
the schema rather than assuming a mutation exists:

```bash
export KB4_PRODUCT_TOKEN='...'          # Product API token, NOT the Reporting token
export KB4_REGION=us
python scripts/kb4.py schema --show mutations
python scripts/kb4.py schema --grep archive
python scripts/kb4.py schema --grep merge
```

Read Only scope is enough for introspection. If the operation the plan depends on is absent,
say so and budget the manual console effort instead of designing around an endpoint that does
not exist.

The GraphQL path defaults to `/graphql` on the regional base URL. If that 404s, override it
with `KB4_GRAPHQL_PATH` and confirm the correct path at `developer.knowbe4.com`.

## Active Directory Integration (ADI)

ADI syncs from on-prem AD on a schedule. Users it manages carry `adi_manageable: true` in the
Reporting API.

The consequence that generates tickets: **any console edit to an ADI-managed field is reverted
at the next sync.** When someone reports that a department, manager, or group keeps reverting,
check `adi_manageable` first and fix the value in AD, not in KnowBe4. Do not build a script that
re-applies the change after each sync — that is a loop, not a fix.

## Console-only operations

No API path exists for these. Budget manual time; do not promise automation.

| Operation | Why it matters |
|---|---|
| Hard delete a user | Required for GDPR/DSAR erasure. Archiving is not deletion |
| Create/edit Smart Groups | Attribute-driven, evaluated by KnowBe4 |
| Create phishing or training campaigns | Including templates and landing pages |
| Change admin roles and permissions | |
| Configure SSO / SCIM / ADI | The bootstrap step for everything above |

## The drift problem

Four routes can write to the same user record — SCIM, ADI, the Graph API, and the console. If
more than one is live, whichever runs last wins and the discrepancy surfaces days later as a
support ticket.

Before adding any automation, establish which system is authoritative for each field and say it
out loud. A one-line "AD owns department and manager; KnowBe4 console owns nothing" is worth
more than the script.
