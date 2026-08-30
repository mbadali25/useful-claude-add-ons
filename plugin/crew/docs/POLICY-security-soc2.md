# Policy: vulnerability management for deployed web applications

**Status:** DRAFT - not approved, not in force.
**Owner:** _unassigned_
**Approver:** _unassigned_
**Effective date:** _not set_
**Review cadence:** annually, or on material change to the deployment process
**Version:** 0.1

> **Read this before using it as audit evidence.** This is a drafted policy, not
> an approved one. A policy carries weight because a named person approved it on
> a date and the organisation demonstrably follows it. Until it has an owner, an
> approver and an effective date, it is a template. The Trust Services Criteria
> mapping in section 9 is a starting point offered in good faith and must be
> confirmed with your auditor - do not present it as agreed scope.

The operating procedure that implements this policy is
[`SOP-web-deployment-security-review.md`](SOP-web-deployment-security-review.md).
This document states *what must be true and why*; the SOP states *how*.

---

## 1. Purpose

To ensure that internet-reachable web applications are assessed for known
exploitable vulnerabilities before they are deployed and on a recurring basis
afterwards, and that the assessment, its findings, and their disposition are
recorded in a form that can be reviewed later.

## 2. Scope

**In scope:** every web application, website, or HTTP-reachable service operated
by the organisation and reachable from the public internet, including staging
and pre-production hosts that are publicly resolvable.

**In scope regardless of who wrote it:** vendor-supplied, low-code, and
inherited legacy applications. A system does not leave scope because nobody
currently maintains it. In practice these carry the most risk, because nobody is
watching them.

**Out of scope:** systems reachable only from internal networks or via VPN.
These are governed separately. A publicly resolvable hostname is in scope even
if the application behind it requires authentication.

## 3. Policy statements

### 3.1 Two independent controls, both required

No in-scope application may be deployed to production without **both**:

- **P1 - Peer security review** of the change by someone other than its author.
- **P2 - External vulnerability scan** of the deployed hostname, performed from
  outside the organisation's network, checking for publicly known exploitable
  conditions.

These are not interchangeable. P1 examines the change; P2 examines the running
system. A reviewed change can be deployed onto an unpatched host, and an
unreviewed change can pass a scan that has no template for the flaw introduced.

### 3.2 Scanning is performed against the public entry point

The scan must target the hostname a user resolves, from outside the network.

Where a CDN, load balancer, or WAF terminates TLS, the origin server's
configuration is not what the public receives. A scan run on the origin will
report protocol versions, headers and server banners that no visitor ever sees,
and can produce a clean result for a control that is in fact absent at the edge.

Where an assessment covers only the origin, that limitation is recorded with the
result.

### 3.3 Authorisation is a precondition

Scanning is performed only against assets the organisation owns or has explicit
written permission to test. Where ownership is uncertain, the scan does not
proceed until it is established.

### 3.4 Findings are triaged by severity

| Severity | Requirement |
|---|---|
| Critical | Remediate before deployment. Deploying with an open Critical requires documented risk acceptance by the policy owner. |
| High | Remediate before deployment, or accept in writing with an owner and target date. |
| Medium | Ticketed and scheduled. Does not block deployment unless directly exposed. |
| Low / Informational | Recorded as counts. Not individually tracked. |

Low and informational output from a signature scanner is inventory - version
banners, DNS records, the presence of a form. Tracking it individually creates a
queue nobody works, which devalues the queue that matters. The counts are
retained so the omission is visible and deliberate rather than silent.

### 3.5 Evidence is retained in version control

For each assessment, the rendered report is committed to the repository:

| Repository shape | Location |
|---|---|
| Monolith / multi-project | `<project>/docs/security/` |
| Single-project repository | `docs/security/` at the repository root |

Reports are date-stamped so that a later assessment cannot overwrite an earlier
one. Retention follows the organisation's general record retention schedule; a
minimum of one full audit period is required.

### 3.6 Raw scanner output is not committed

**Raw scanner output must not be stored in a shared repository.**

Raw output embeds the full HTTP response for every match and therefore carries
whatever the target returned, including live session material. This is a
demonstrated failure mode, not a theoretical one: two scans conducted on a
single day in August 2026 each captured live credentials - one recorded two
156-character anti-CSRF tokens from a login form, another a live session cookie
and user token.

Automated secret scanning did not detect either, because the values were carried
inside escaped HTML attributes rather than in a recognisable `key=value` form.
Detection therefore cannot be relied upon as the control. Exclusion is the
control: repositories holding scan output carry a `.gitignore` rule excluding
raw scanner formats.

Rendered reports contain template identifiers, severities and matched URLs, and
no response bodies. They are the artefact of record.

### 3.7 Recurring assessment

In-scope applications are re-assessed at least **quarterly**, and on any change
to the web server, TLS configuration, reverse proxy, or application runtime.

Each recurring assessment is compared against the previous one. The comparison -
what is newly present and what has resolved - is the evidence that remediation
occurred. A subsequent clean result on its own does not demonstrate a fix.

### 3.8 Remediation is closed on verification, not on intent

A finding is closed when a re-scan demonstrates it is no longer present, and the
evidence is attached to the record. Code-complete, merged, or deployed are
progress states. Verified is the closing state.

## 4. Roles

| Role | Responsibility |
|---|---|
| Policy owner | Maintains this policy, approves risk acceptances, reviews annually |
| Change author | Requests review; remediates findings |
| Reviewer | Performs P1; must not be the author |
| Deployer | Confirms P1 and P2 are complete before release |
| Ticket owner | Tracks each Critical/High to closure with verification |

Independence requirement: the reviewer must not be the author of the change. An
automated reviewer satisfies this only when it evaluates the change in a context
separate from the one that produced it.

## 5. Exceptions

An exception requires:

1. A documented business justification.
2. Named acceptance by the policy owner.
3. A compensating control, or an explicit statement that none exists.
4. An expiry date. Exceptions do not roll over silently.

Open exceptions are reviewed at each policy review. An expired exception is a
finding.

## 6. Non-compliance

A deployment that proceeded without P1 or P2 is recorded as a control exception,
assessed after the fact, and remediated. The record is retained rather than
removed - a corrected exception is stronger evidence of a working control
environment than an unblemished log nobody believes.

## 7. Limitations of the control

Stated deliberately. A control described as stronger than it is will fail an
auditor's testing and mislead the organisation in the meantime.

- **Signature-based detection.** Scanning identifies conditions a published
  detection exists for. Business logic flaws, broken authorisation, and
  application-specific defects are not detected and require separate assessment.
- **Unauthenticated coverage.** Default scanning assesses the unauthenticated
  surface. Functionality behind a login is not covered, and a clean result makes
  no statement about it.
- **Edge filtering.** A WAF may absorb probes, suppressing a finding without the
  underlying weakness being addressed.
- **Point in time.** An assessment reflects the target at the moment it ran.

This policy therefore reduces the likelihood of deploying a *known* exploitable
condition. It does not establish that an application is free of vulnerabilities,
and must not be represented as doing so.

## 8. Tooling

The control is tool-independent. It is currently implemented with the
`gizmoduck` plugin, which runs Nuclei and renders triaged reports, and the
`crew` plugin's review roles and verification gates.

Replacing the tooling does not require a policy change, provided the replacement
performs an external, authenticated-where-applicable assessment against known
exploitable conditions and produces a retainable report.

## 9. Trust Services Criteria mapping

**Provisional. Confirm with your auditor before relying on it.**

| Criterion | How this policy relates |
|---|---|
| CC7.1 | Detection of vulnerabilities through recurring external assessment |
| CC7.2 | Monitoring for anomalies; recurring re-assessment and diffing |
| CC8.1 | Change management - review and assessment as pre-deployment gates |
| CC6.1 / CC6.6 | Logical access and boundary protection, where findings concern authentication, TLS, or exposed configuration |
| CC4.1 | Evaluation of control effectiveness through retained, comparable evidence |

Mapping alone does not satisfy a criterion. What satisfies it is the evidence in
section 3.5 existing consistently across the audit period, with exceptions
documented rather than absent.

## 10. Review

This policy is reviewed annually by the owner, and on any material change to the
deployment process or scanning toolchain. Each review records the date, the
reviewer, and whether the policy changed.

| Date | Reviewer | Outcome |
|---|---|---|
| _pending_ | _pending_ | Initial draft, not yet approved |
