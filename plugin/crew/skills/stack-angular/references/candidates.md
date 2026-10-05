# Angular 2+ candidate standards (not gated)

No gated Angular standards set ships yet (L-0538). Nothing in this file is loaded by
`crew_standards.py` or asked in the pre-review self-check. It is guidance, kept with its
evidence. A rule is promoted once three distinct reviewed change sets earn it, into
`crew-standards/references/angular.md`, set `NG` (the loader takes 2-6 capitals, so not
`ANGULAR`), with `applies-to: ["**/src/app/**/*.ts", "**/src/app/**/*.html"]`. The research
numbering is kept, so ANGULAR-07 is `NG-07`. AngularJS 1.x gets no standards.

**Why nothing ships.** The bar and the counting rule are `python.md`'s: a change set is a
crew review, or a fix commit whose own message or CHANGELOG entry records that a review
found the defect. There is no file-type condition. The spec's provisional private count
admits only NG-07, at three, and one of those three rests on a finding id alone. NG-07's
Why, Earned by and Change sets text has to come from the coordinator's private research,
which this build did not have. ANGULAR-05 and -06 have two each, and every other rule has
zero or one. The owner decided on 2026-10-05 that public third-party change sets do not
count. The public change sets below are leads, each counted 0.

**How the public pass read its evidence.** Commit messages came from GitHub commit
search. Diffs were not read. Every Source sentence was string-matched against the raw
angular.dev page on 2026-10-05. `NG-Pn` are labels from the public pass, not research
ids. NG-P1 may be the owner's ANGULAR-05 or -06, but that could not be determined.

## Candidate standards (not gated)

### NG-07 A failed read renders as "could not verify" and disables every write it feeds

0 counted. 3 in the spec's private count. Publicly, 3 change sets show the read half and
1 shows the write half.

Rule (the spec's publishable text). Refines GEN-01. When a read that a view's write
controls depend on fails, the view does not fall back to empty or default values that
look like data. It records the failure as its own state and shows "could not verify"
where the value would be. It gates every control that can lead to a write on that state,
both in the template and again in the handler. A destructive control is not rendered at
all, not merely disabled. A cached advisory value never becomes a hard client-side block
on an action the server decides live.

Applies when: a component joins two or more reads to build rows that carry write
controls; a control is enabled or disabled from cached data; or a parser maps free-text
input to a list where empty means "all".

Self-check:
1. For each read that feeds a write control, what does the view show and allow if the
   read fails? Pass: a distinct failure state, and no write is reachable.
2. Do the write handlers re-check that state, not only the template? Pass: yes.
3. Is any control hard-disabled from cached or advisory data that the server re-checks
   anyway? Pass: no, it is a hint.
4. Where empty input means "all", is non-empty raw input that parses to empty refused?
   Pass: yes.

Public change sets (message text only). All three are in one public Angular repository,
linuxfoundation/lfx-self-serve:
- `lfx-2355` (@8ee46339, #2355): a pre-push review pass found that both error arms set an
  empty list with no flag, so the view asserted a verified absence during an outage. In
  the same PR, "Two HIGH findings from the review rounds" let a write run before the
  suppression read was known. This is the only public change set for the write half.
- `lfx-1597` (@aaf3fa4a, #1597): "suppress the whole drawer body on a failed request.
  Three independent reviewers found the same defect". Read half only.
- `lfx-1193` (@77105da9, #1193): in review round 5, a failed child load renders
  "Couldn't load" instead of the "No sub-items" text that a confirmed-empty leaf shows.
  Read half only.

Source: https://angular.dev/guide/routing/route-guards: "CRITICAL: Never rely on
client-side guards as the sole source of access control." "Always enforce user
authorization server-side, in addition to any client-side guards." That supports only the
"server decides live" half. No Angular doc states the first half.

### NG-P1 No `bypassSecurityTrust*` on content a user, contact or model can author

0 counted. 5 public change sets, not counted.

Never pass user-authored, contact-authored, model-generated or stored text through
`DomSanitizer.bypassSecurityTrustHtml`, or through `...Url`, `...ResourceUrl`,
`...Script` or `...Style`. Bind plain strings to `[innerHTML]` and let Angular sanitize
them. If rich HTML is required, sanitize it first (for example with DOMPurify) and
bypass only on that output, in one audited helper. Check a resource URL's scheme before
trusting it. This extends the `bypassSecurityTrust*` pitfall in `SKILL.md`.

Public change sets (message text only). In each, a security or code review found
authored or stored content rendered through `bypassSecurityTrustHtml`:
- `mj-committees-0880ab86` (MemberJunction/bizapps-committees@0880ab86, an adversarial
  security review)
- `mj-messaging-f1257ca7` (MemberJunction/bizapps-secure-messaging@f1257ca7, the same
  kind of review, on the same day, in a different repository and product; it may count
  as one with the previous entry)
- `sgc-618cd989` (techcsd/SGC@618cd989, a security review that found stored XSS)
- `yammer-f8143330` (Pezu/yammer@f8143330, review round 2, across 7 components)
- `awesomecmp-407fcce9` (cbruyndoncx/awesome-comparisons@407fcce9, a code review)

Source: https://angular.dev/best-practices/security: "To systematically block XSS bugs,
Angular treats all values as untrusted by default." "If you trust a value that might be
malicious, you are introducing a security vulnerability into your application."

Public verdict: admitted on public stand-ins (5), or 4 if the two MemberJunction reviews
count as one. That does not count under the owner's decision.

### NG-P2 HTTP interceptors attach credentials only to allow-listed origins

0 counted. 1 public change set, not counted.

An interceptor adds a bearer token or other credential only to requests whose origin is
on an explicit allow-list. A request to any other host goes out without it.

Public change set: `sdcore-97ba679e` (sdcorejs/sdcorejs-angular@97ba679e). A full-scan
review found that a Keycloak interceptor sent the bearer token to any host.

## Research rules not built here

ANGULAR-01 to -06 and -08 to -18 (NG-01..NG-18 except NG-07) are the owner's research
ids. Their titles, text and per-rule counts are in the coordinator's private research,
which this build did not have, so they are not listed one by one. ANGULAR-18 (naive
timestamps) stays in this slice and is not moved to Node.js.
