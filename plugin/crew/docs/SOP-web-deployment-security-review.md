# SOP: security review and external scan before a website deploys

**Status:** draft, unapproved. Needs an owner and a sign-off date before it is
cited as evidence for anything.
**Applies to:** every internet-reachable web property this crew deploys or
materially changes.
**Owner:** _unassigned_
**Last reviewed:** _never_

This is the operating procedure. The control it satisfies, and the language an
auditor reads, is in [`POLICY-security-soc2.md`](POLICY-security-soc2.md).

---

## 1. The rule

**No website reaches production without both of the following, in this order:**

1. A **security review** of the change, by someone who did not write it.
2. An **external vulnerability scan** of the deployed URL, checking for known
   exploits, run against the real hostname from outside the network.

Neither substitutes for the other. The review reads what changed; the scan tests
what is actually serving. A change can pass review and still deploy onto a host
running an end-of-life web server.

## 2. When this fires

| Trigger | Review | External scan |
|---|---|---|
| New website or hostname goes live | yes | yes |
| Change to auth, session, input handling, uploads, or IAM | yes | yes |
| Web server, TLS, or reverse-proxy configuration change | yes | yes |
| Runtime or framework upgrade (nginx, PHP, .NET, Node) | yes | yes |
| Content or copy change only | no | no |
| Periodic re-scan of a live property | no | yes, quarterly minimum |

The scan is cheap and the deploy is not. When in doubt, scan.

## 3. Step 1 - the security review

Run the crew reviewer against the diff before merge:

```
/crew:review
```

`qa.provider` in `.crew/config.json` decides who reviews. For any change
touching authentication, authorization, user input, uploads, SQL, secrets, PII,
or infrastructure permissions, the `security` role reviews as well - that
mapping already lives in `.crew/verify.json` and does not need to be remembered.

A review is complete when every **BLOCKING** finding is fixed or explicitly
declined with a reason recorded on the ticket. "No findings" is a valid outcome
and must not be padded.

## 4. Step 2 - the external scan

Scan the **deployed URL**, not localhost, and not a build artifact.

```
/gizmoduck:scan https://<hostname>
```

Or directly:

```
python3 <plugin>/scripts/gizmoduck.py scan https://<hostname> \
    --severity critical,high,medium --out findings.jsonl
python3 <plugin>/scripts/gizmoduck.py report findings.jsonl \
    --format html --out <name>.html --title "<hostname> scan <date>"
```

Reports itemise Critical, High and Medium; Low and Info are counted and not
listed. That is deliberate - see the gizmoduck README.

### Scan from outside the network

A localhost scan proves almost nothing about what visitors get. Where a CDN,
load balancer or WAF terminates TLS, the origin's own configuration is invisible
to the internet and the edge's configuration is what users actually negotiate.
A scan run on the web server itself will happily report a protocol or header the
public never sees.

**Resolve the public hostname and scan that.** If the host has no public IP,
find what is in front of it before drawing any conclusion about TLS, headers, or
the server banner.

### Authorization

Only scan assets the organisation owns or has explicit written permission to
test. If ownership is unclear, stop and confirm. This is not a formality - an
unauthorised scan against a third party is a real problem regardless of intent.

## 5. Step 3 - publish the report into the repository

**Where the report goes:**

| Repository shape | Location |
|---|---|
| Monolith / multi-project | `<project>/docs/security/` |
| Single-project repository | `docs/security/` at the repo root |

**What to commit:**

- the rendered report - `.md`, `.html`, `.pdf`
- a date-stamped filename, so a later scan cannot overwrite the comparison point

**What must never be committed:**

- **the raw scanner JSONL**

Raw nuclei output embeds the full HTTP response for every match, so it carries
whatever the target returned. This is not hypothetical. Two scans on a single
day in August 2026 both leaked live credentials into their JSONL:

- one held two 156-character `__RequestVerificationToken` values from a login
  form, repeated across 16 records
- another held a live `PHPSESSID` and a user session token

Neither was caught by a keyword secret scan, because the values sit inside
escaped HTML (`value=\"...\"`) rather than in any `key=value` shape. A human
review caught the first one. **Do not rely on a regex catching the next.**

The rendered reports are safe: they carry template names, severities and matched
URLs, and no response bodies at all.

Add this to the scan directory's `.gitignore`:

```gitignore
# Raw scanner output embeds full HTTP responses and has twice leaked live
# session tokens. Rendered reports are safe; the JSONL is not.
*.jsonl
```

Keep the JSONL locally if a `gizmoduck diff` baseline is wanted. It does not
belong in a shared repository.

## 6. Step 4 - triage what came back

| Severity | Action |
|---|---|
| Critical, High | Ticket automatically, one per finding. Fix before deploy, or record an accepted risk with an owner and a date. |
| Medium | Ticket and schedule. Does not block deploy unless it is directly exposed. |
| Low, Info | Counted, not ticketed, not itemised. |

`/gizmoduck:tickets` produces ticket-ready records with a stable
`[Nuclei <template-id>]` subject. Before creating one, search for an existing
open ticket carrying the same tag and add a note to it instead - otherwise a
recurring finding opens a new ticket every quarter.

## 7. Step 5 - prove the fix

After remediation, re-scan and diff against the previous run:

```
/gizmoduck:diff <baseline.jsonl> <current.jsonl>
```

The diff is the evidence. It names what resolved and what is new, which is the
only honest way to show a fix landed - a second scan showing "0 critical" proves
nothing on its own if the first one also showed 0.

Record the before/after in the ticket, then close it. **Code-complete is a
comment; deployed and verified is a close.**

## 8. What this procedure does not cover

State these when reporting results. A clean scan that is quietly oversold is
worse than no scan.

- **Signature-based detection only.** Nuclei finds what a template exists for.
  Business logic flaws, broken authorisation, and anything unique to the
  application will not appear. Complement with a crawling scanner such as OWASP
  ZAP, and with manual testing for authorisation.
- **Unauthenticated by default.** A host that returns 401 or 403 to an anonymous
  request has only been tested at its front door. Everything behind the login is
  unassessed, and a clean result says nothing about it.
- **A WAF may absorb probes.** Findings can be suppressed by the edge without
  the underlying weakness being fixed.
- **Absence of a finding is not absence of a vulnerability.** A clean result
  narrows the search. It does not close it.

## 9. Records to keep

For each deployment:

1. The review outcome, on the ticket.
2. The rendered scan report, committed to `docs/security/`, date-stamped.
3. Tickets for every Critical and High, with resolution or accepted-risk
   decision.
4. The re-scan diff proving remediation.

That set is the evidence trail. It is also the minimum an auditor will ask for.
