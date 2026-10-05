# T-0086 research - Angular (2+) development standards (target skill: extend `stack-angular`)

Status: RESEARCH DRAFT for owner spot-check. Written 2026-09-28 by a Fable 5.1 (claude-fable-5-1) research
lane. Read-only: no code changed, no commits, no suites run. The only file written is this one.
Scope is modern Angular only (owner's answer: "Angular 2+ only"); nothing here applies to AngularJS 1.x.

## What this is

Eighteen build-time standards (`ANGULAR-01` to `ANGULAR-18`) in T-0085's format
(`.work/tickets/T-0085/standards-draft.md:137`, "Format every set uses"): **Rule**, **Why**, **Applies
when**, **Self-check** (numbered, each with the answer that passes), **Earned by** (owner history) and
**Source** (official doc this lane fetched), plus an **Evidence** tag:

- `BOTH` - a fetched official doc and at least one real defect in the owner's history (15 of 18). In three
  of them (ANGULAR-11, -14, -15) the doc supports only part of the rule; each rule's Source says which part.
- `OWNER-HISTORY` - real defects only; no fetched doc states the rule in the form given (3 of 18: ANGULAR-03, -06, -07).
- `DOC` - official doc only (0 of 18; two DOC-only candidates were considered and left out, see
  "Considered and not admitted").

Each rule names the T-0085 GEN rule it refines, so the self-audit does not ask the same question twice.
They target the defects that actually recurred in the owner's Angular 21 apps: responses landing on a
page that moved or died, guards that did I/O too early or redirected into a loop, a failed read rendered
as a fact that enabled a write, templates no test ever executed, build config that differed between
`ng serve` and production, and CDN caching of unhashed bundles.

## Where the owner's Angular actually lives

No Angular app is checked out under `/repos/anew` or `/repos/personal` (searched for `angular.json` and
`"@angular/core"` outside `node_modules`). TheHomeDepot's HD Pro Angular app (`thd-prod/frontend`) is
referenced by vault notes but is **not cloned on this host**, so its evidence here is vault-only. The
owner's Angular code is under `/repos/solomon`:

| Repo (HEAD read) | Angular apps (`*/frontend/angular.json`) |
|---|---|
| `solomon/aws-managed-services` @ `7848e99d` | drata-insights, fileshare-audit, infra-management-tool, security-ops-dashboard, terraform-workspace-management, trusted-advisor-report |
| `solomon/aws-shared-infrastructure` @ `17e4db3` | ec2-management-iam |
| `solomon/solomon-fuels-participant` | frontend (22 commits, no fix history found) |

All are Angular 21 (`@angular/core` `^21.0.0` to `^21.2.23`), rxjs `~7.8.0`, standalone components with
signals and `@if`/`@for` control flow. The T-0085 corpus (`.work/tickets/T-0085/findings-224.txt`) has
**zero** Angular/`.ts`/`.html` findings - this marketplace has no Angular code - so no `F`-numbered
findings are cited here. The owner-history evidence is:

- **Review-round fix commits** in the two solomon repos, found with `git log -i -E --grep` over
  `innerHTML|sanitiz|takeUntilDestroyed|unsubscribe|ngOnDestroy|guard|interceptor|[value]|outputHashing|CSP|...`
  restricted to `*frontend*`. Those repos run Codex review rounds and record the round and finding in the
  commit message (e.g. "Round four", "Fix round 2, F3", "Codex review, tasks 14-20, Important #3"). Cited
  as `<repo>@<sha>` with the message quoted.
- **`solomon/aws-shared-infrastructure/CLAUDE.md`** at `17e4db3`, cited by line.
- **Vault concept notes** under `/repos/claude-memories/wiki/concepts/`, cited by path. These are
  second-hand gardener summaries of sessions. Where this lane cross-checked one against a commit it says
  so (the `[value]`/`@for` note against `18e179db`; the unhashed-bundle note against `975a3ac0`).

## How this extends `stack-angular` (and does not repeat it)

`plugin/crew/skills/stack-angular/SKILL.md` (85 lines at `c5f4aa62`) is a pitfalls list with no
self-checks. These standards do **not** restate it:

| stack-angular says (line) | Handled here as |
|---|---|
| Subscription without an end is a leak (:21-23) | ANGULAR-01 adds the self-check and the two gaps the owner hit: route subscriptions in the constructor, and `takeUntilDestroyed` outside an injection context. ANGULAR-02/03 cover what the pitfall does not: the response that lands after the page moved or died. |
| Change detection, `OnPush`, mutated object (:24-26) | Not repeated. No owner finding in this history. |
| RxJS operator choice (:27-30) | Not repeated; ANGULAR-02 uses `switchMap` only as one of two fixes. |
| Injector hierarchy (:31-33) | Not repeated. No owner finding. |
| Forms validation timing (:34-35) | Not repeated; ANGULAR-11 is a different forms defect (initial selection). |
| `bypassSecurityTrust*` / `[innerHTML]` are XSS sinks (:36-37) | ANGULAR-08 turns it into a checked rule and adds direct DOM access and URL-scheme allowlisting. |
| Guard observable that never emits hangs navigation (:38-40) | ANGULAR-05/06 cover the guard defects the owner actually shipped: concurrent guard side effects and redirect loops. |
| Verification: `ng build --configuration production`, a test that never destroys proves nothing (:50-56) | ANGULAR-12 makes it a build-time rule with a revert-the-template control. |

The skill's `AngularJS (1.x) additions` section is out of scope for this set.

## Official sources and method

Every page below was fetched on 2026-09-28. The first pass used WebFetch (a small model's summary);
because the Python lane found WebFetch misquoting a doc, **every quoted sentence in this file was then
re-extracted from the raw HTML by `curl` and string search** (angular.dev pages are prerendered, so the
text is in the HTML). One WebFetch summary was wrong in a way that mattered: it rendered the effects
guidance as a paraphrase of the `linkedSignal` section; the real sentence is on a different page
(`/guide/signals/effect`) and is quoted from there. The rxjs.dev API page is a client-rendered shell with
no text, so `switchMap`/`shareReplay` are cited from the rxjs 7.x source's JSDoc on GitHub (rxjs 7.x is
what the owner's apps pin). The Angular router source is cited for one behaviour the docs describe
misleadingly (ANGULAR-05).

---

## ANGULAR-01 Every subscription a component starts has a stated end

**Evidence.** BOTH. Refines GEN-11 (named requirements hold on every path).

**Rule.** Every `subscribe()` in a component, directive or component-scoped service ends with the view:
through the `async` pipe, `toSignal`, or `takeUntilDestroyed`. `takeUntilDestroyed()` without an argument
is legal only in an injection context (constructor or field initialiser); anywhere else it takes an
injected `DestroyRef`. Router streams (`paramMap`, `queryParamMap`, `events`) subscribed in the
constructor are subscriptions too and need the same end. A `Subscription` field that is replaced on some
other event (a policy switch, a filter change) is not the lifetime owner - tear the lifetime
subscriptions down separately.

**Why.** drata-insights shipped a page whose route subscriptions "were never unsubscribed either - a
query-string change arriving after destruction ran `loadDetail` on a component with no view", and the
fix had to keep them off the per-policy `Subscription` because "`abandonPolicy` unsubscribes and replaces
[it] on every policy switch; parking them there would make the page stop responding to its own URL after
the first switch". Angular's own guidance: clean up "as the subscription callback may otherwise run and
encounter errors when it attempts to interact with the destroyed component".

**Applies when.** A diff adds `.subscribe(`, a `Subscription` field, `setInterval`/`setTimeout`/`timer`,
or subscribes to `ActivatedRoute`/`Router` observables.

**Self-check.**
1. For each new `subscribe(`: which of `async`, `toSignal`, `takeUntilDestroyed(...)`, or an explicit
   `unsubscribe` in `ngOnDestroy` ends it? Pass: one is named for every site.
2. For each `takeUntilDestroyed()` with no argument: is it in a constructor or field initialiser? Pass:
   yes, or it is passed an injected `DestroyRef`.
3. Is any lifetime subscription stored on a `Subscription` that some non-destroy event replaces? Pass: no.
4. Does a spec destroy the component (`fixture.destroy()`) and then drive the source, asserting the
   handler did not run? Pass: yes for every router or timer subscription added.

**Earned by.**
- `solomon/aws-managed-services@e18a5332` (drata-insights, review round four): "NGONDESTROY, which this
  component never had ... tears down the two route subscriptions, which were never unsubscribed either".
- Vault `concepts/solomon/aws-managed-services/An Angular view for a destructive multi-select action
  needs a per-item exact-match confirmation, and its auto-refresh poll needs to stop itself.md:25`
  (terraform-workspace-management polls use `takeUntilDestroyed(destroyRef)`).

**Source.**
- https://angular.dev/ecosystem/rxjs-interop/take-until-destroyed - "provides a concise and reliable way
  to automatically unsubscribe from an Observable when a component or directive is destroyed"; "provide a
  DestroyRef if your code may call takeUntilDestroyed outside of an injection context".
- https://angular.dev/guide/http/making-requests - "we strongly recommend that you clean up subscriptions
  when the component using them is destroyed, as the subscription callback may otherwise run and encounter
  errors when it attempts to interact with the destroyed component."

---

## ANGULAR-02 A response is judged against what it was for, when it arrives

**Evidence.** BOTH. Refines GEN-03 (the irreversible action carries what was checked).

**Rule.** When the page can move (route param, query param, selected item, pinned revision) while a
request is in flight, capture the request's identity when it is sent and compare it with the page's
current identity when the answer lands; a mismatch is refused and said out loud, never applied. Where the
newest request should simply win, `switchMap` from the identity stream does this structurally. Every
caller that loads the same data (the poll, the refresh after an action, the initial load) goes through one
loader that carries the identity - not a second direct API call. When the identity changes, clear the
previous item from the view, so nothing on screen is actionable under the wrong identity while the next
one loads.

**Why.** Three consecutive drata-insights review rounds on one page were this defect: a download URL for
revision A opened while the page showed revision B; the poll called the API directly and "was never
covered by the pin that `loadDetail` reads", writing the newest revision over the pinned one four seconds
later; and while the next revision loaded, "revision B was on screen and downloadable under a URL that
said A". The request-time check "cannot see this - at request time nothing was wrong."

**Applies when.** A component issues HTTP from a handler or subscription whose inputs can change before
the answer (route/query params, a selection, a pinned id), or runs a poll alongside a normal load.

**Self-check.**
1. For each request whose answer is applied to the view or acted on (open, download, save): is the
   identity it was for captured at send time and compared on arrival? Pass: yes, one shared predicate for
   every site that checks it.
2. List every caller that fetches this resource (initial load, poll, post-action refresh). Pass: all go
   through the same identity-carrying loader.
3. When the identity changes, is the previous item cleared before the next arrives? Pass: yes, and only
   when the identity changes (a failed refresh of the same item does not blank it).
4. Is there a spec that parks the response, moves the page, then releases it? Pass: it fails with the
   check removed.

**Earned by.**
- `solomon/aws-managed-services@82c84eef` (round three): "THE DOWNLOAD URL OUTLIVED THE PAGE THAT ASKED
  FOR IT ... Click Download on pinned revision A, navigate to pinned revision B and let it load, and A's
  URL arrived and was opened unconditionally". Predicate at
  `drata-insights/frontend/src/app/features/policy-changes/policy-changes.ts:2322@7848e99d`
  (`mismatchedRevision`).
- `solomon/aws-managed-services@8956cdb4`: "THE POLL DID NOT CARRY THE PIN. `schedulePoll` calls the API
  directly rather than through `loadDetail`"; "CHANGING THE PIN LEFT THE OLD REVISION DOWNLOADABLE".
- `solomon/aws-managed-services@fb12529b` (round five): "a download of revision A of policy P, answered
  after a switch to Q, was reported as revision A OF Q ... What the request was FOR - revision AND policy
  - is captured when it is made".

**Source.**
- https://raw.githubusercontent.com/ReactiveX/rxjs/7.x/src/internal/operators/switchMap.ts (JSDoc) -
  "When a new inner Observable is emitted, `switchMap` stops emitting items from the earlier-emitted inner
  Observable and begins emitting items from the new one."
- https://angular.dev/guide/http/making-requests - "unsubscribing will abort the in-progress request."

---

## ANGULAR-03 Destruction stops the page acting; it does not undo what the user authorised

**Evidence.** OWNER-HISTORY. Refines GEN-01 (unknown stays unknown) and GEN-11.

**Rule.** On destroy: cancel reads, clear timers, and guard every response handler with a `destroyed`
check as a second line behind cancellation. Do **not** cancel writes the user already authorised (a chain
of approvals, a save) - let them finish. A destroyed component keeps its signals, so a check that reads
the component's own state proves nothing about the page the user is now on. Any outcome that must reach
the user after the page is gone (a partial batch, a failed or withheld download) goes to a root-provided
notice store the shell renders, not to a signal on the dying component.

**Why.** Four rounds on one drata-insights page. Round four added `ngOnDestroy` and found "a destroyed
component KEEPS its signals, so the pin check inside it reads the revision that page was pinned to, agrees
with itself, and opens the document". Round five found round four's teardown was "a REGRESSION":
cancelling on destroy meant "leaving the page mid-chain sent one change of three, left two unsent, and
told nobody". Round six found the result sentence "assigned ... to a view nobody can ever see", and "a
poll answer already on the wire ran its whole handler ... and booked another timer" because clearing the
timer "does nothing for an answer in flight". A mutation test then showed the two defences hid each other:
deleting the `unsubscribe()` "left all eleven tests green".

**Applies when.** A diff adds or edits `ngOnDestroy`/`DestroyRef.onDestroy`, cancels subscriptions on
navigation, or reports the result of async work in the component that started it.

**Self-check.**
1. Classify each in-flight operation the page can own: read, or user-authorised write. Pass: reads are
   cancelled on destroy, writes are not.
2. Does every response handler that schedules more work (a timer, a request, a navigation) check
   `destroyed` first? Pass: yes.
3. For each message about async work: can it be produced after destroy? If yes, where does it render?
   Pass: a root-level store the shell shows, not the component's own signal.
4. Are cancellation and the `destroyed` flag each covered by a spec that fails with only that one
   removed? Pass: yes - the spec distinguishes "aborted" from "ignored".

**Earned by.**
- `solomon/aws-managed-services@e18a5332` (round four), `@fb12529b` (round five: "Navigating away is not
  'undo what I just approved'"), `@2bfee978` (round six: "A DESTROYED PAGE NOW REALLY DOES STOP"),
  `@861e98e4` ("Ignoring an answer leaves the request running against the API on behalf of a page that no
  longer exists; cancelling is the mechanism, the flag is the second line").
- Code as fixed: `drata-insights/frontend/src/app/features/policy-changes/policy-changes.ts:547-561` and
  `:1582@7848e99d`.

**Source.** No fetched Angular doc states the read/write split or the surviving-signals point. The
making-requests page supports only the cancellation half ("unsubscribing will abort the in-progress
request"), which is why this is tagged OWNER-HISTORY.

---

## ANGULAR-04 A poll has two stop conditions and goes through the normal loader

**Evidence.** BOTH. Refines GEN-11.

**Rule.** A polling stream (`timer`/`interval` + `switchMap`) ends on **both** "the thing polled for is
finished" (`takeWhile(pred, true)` or equivalent) **and** "the view is gone" (`takeUntilDestroyed`).
The polled request is the same identity-carrying loader as the initial load (ANGULAR-02), and the handler
of an answer already in flight checks `destroyed` before scheduling the next tick (ANGULAR-03).

**Why.** "A polling timer with no stop condition is a timer leak by default; it has to be told explicitly
when to stop, and 'the component was destroyed' is not the same condition as 'the thing being polled for
is finished'" (vault). drata-insights' poll bypassed the pinned loader and overwrote the pinned revision
(`8956cdb4`), and an in-flight poll answer re-armed the timer after destroy (`2bfee978`). A
`ngAfterViewChecked` wait loop with one condition for two states polled forever (`9e4294eb`: "an empty
documentTokens() (nothing painted yet - keep waiting) and a non-empty list that simply omits the target
change's token (painted ... never going to appear). Both fell through the same 'try next pass' branch").

**Applies when.** A diff adds `timer(`, `interval(`, `setInterval`, a re-scheduling `setTimeout`, or a
retry/wait loop in a lifecycle hook (`ngAfterViewChecked`, `ngDoCheck`).

**Self-check.**
1. Name the completion stop and the lifetime stop. Pass: both exist.
2. Does the polled call go through the same loader as the initial load? Pass: yes.
3. For a wait-until-rendered loop: is "not yet" distinguished from "never"? Pass: the never case exits.
4. Is there a spec where the work finishes and the timer is shown to stop (fake timers, no further
   request)? Pass: yes.

**Earned by.** Vault `concepts/solomon/aws-managed-services/An Angular view for a destructive
multi-select action needs a per-item exact-match confirmation, and its auto-refresh poll needs to stop
itself.md:25-33`; `solomon/aws-managed-services@8956cdb4`, `@2bfee978`, `@9e4294eb`.

**Source.** https://angular.dev/ecosystem/rxjs-interop/take-until-destroyed (lifetime half, quoted in
ANGULAR-01). The completion half has no Angular doc; it is owner history.

---

## ANGULAR-05 A guard is UX; the API decides, and guards in one array run at once

**Evidence.** BOTH. Refines GEN-10 (external behaviour is measured, not assumed).

**Rule.** Every route guard's decision is also enforced by the API; the guard only saves a round trip and
a flash of forbidden UI. Guards listed in one `canActivate` array are **all subscribed in the same tick** -
array order ranks their *results*, it does not sequence their side effects. So a guard that does I/O
(`/me`, a permission read) checks its own precondition (already authenticated) before issuing it, instead
of relying on an earlier guard in the array to have stopped navigation. A route-table test asserts the
exact guard identities, not "a guard exists".

**Why.** ec2-management-iam's `/admin` had only an authentication guard; "roles:manage was decided
entirely inside the Admin component. The route table's own 'guards every page' structural test could not
see that gap". The fix then assumed "Angular evaluates canActivate arrays in order and short-circuits on
the first denial", and a Codex re-review found the `/me` call "fired concurrently with, not after, the
authentication decision". The official guide says guards "are executed in the order they appear in the
array"; the router source shows that is true of result priority only (`combineLatest` over every guard,
each wrapped in `defer`).

**Applies when.** A diff adds or edits a `CanActivateFn`/`CanMatchFn`/`CanActivateChildFn`, a route's
guard array, or a component-level permission check.

**Self-check.**
1. For each guarded capability: which API route enforces the same rule server-side? Pass: named.
2. For each guard that makes an HTTP call or other side effect: does it check its own precondition before
   the call, without assuming another guard in the array ran first? Pass: yes.
3. Does a spec assert that an unauthenticated activation issues zero calls from this guard? Pass: yes.
4. Does the route-table spec assert exact guard identities per route? Pass: yes.

**Earned by.**
- `solomon/aws-shared-infrastructure@6b97739` ("Codex review, tasks 14-20, Important #3").
- `solomon/aws-shared-infrastructure@b5b012a`: "canActivate: [autoLoginPartialRoutesGuard,
  hasRolesManageGuard] assumed array order sequences EXECUTION. It does not"; explanation kept in
  `ec2-management-iam/frontend/src/app/core/guards/roles-manage.guard.ts:20-40@17e4db3`.

**Source.**
- https://angular.dev/guide/routing/route-guards - "CRITICAL: Never rely on client-side guards as the sole
  source of access control. All JavaScript that runs in a web browser can be modified by the user running
  the browser. Always enforce user authorization server-side, in addition to any client-side guards." Also
  "They are executed in the order they appear in the array." - **misleading for side effects**, see next.
- https://raw.githubusercontent.com/angular/angular/main/packages/router/src/operators/prioritized_guard_value.ts
  (`combineLatest(obs.map((o) => o.pipe(take(1), startWith(INITIAL_VALUE))))`) and
  https://raw.githubusercontent.com/angular/angular/main/packages/router/src/operators/check_guards.ts
  (`runCanActivate` wraps each guard in `defer(() => ...)` and pipes the array through
  `prioritizedGuardValue()`). Read on `main`, not at the owner's 21.2 tag - see "Not verified".

---

## ANGULAR-06 Every denial and fallback redirect lands on an unguarded route

**Evidence.** OWNER-HISTORY. Refines GEN-11.

**Rule.** A guard's denial `UrlTree`/`RedirectCommand`, the `**` wildcard, and an auth library's
`unauthorizedRoute`/`forbiddenRoute` all point at a route that carries no guard. A redirect that is only
loop-free under an assumption the guard cannot verify ("the caller is authenticated") is the wrong
target. A guard that decides it cannot tell (the `/me` read failed) fails closed.

**Why.** aws-operations' SSO change shipped "an infinite authorize loop ... unauthorizedRoute/forbiddenRoute
were unset, defaulting to routes that do not exist, so a failed token exchange fell through the wildcard
onto a guarded route, which re-triggered authorize(), which failed again - forever". The next guard denied
to `/instances`, itself guarded; the re-review "rejected the reasoning, not just the outcome ... this
guard's /me-error branch cannot actually distinguish an authenticated caller from an unauthenticated one".

**Applies when.** A diff adds a guard, changes a guard's denial target, the wildcard route, or OIDC/auth
library route settings.

**Self-check.**
1. List every redirect target a guard, the wildcard and the auth config can produce. Pass: each is a route
   with no `canActivate`/`canMatch`.
2. For each guard error branch: does it deny? Pass: yes (fail closed).
3. Is each target asserted by a spec against the route table itself? Pass: yes.

**Earned by.**
- `solomon/aws-shared-infrastructure@84693f3` ("C2 BLOCKER -- fixed an infinite authorize loop").
- `solomon/aws-shared-infrastructure@ee5ad15` ("Fix round 2, F3 ... Denies to /login instead ... the one
  address proven to carry no canActivate at all").
- `solomon/aws-shared-infrastructure/CLAUDE.md:212-215@17e4db3`: "**Never point the `**` wildcard at a
  guarded route**: that recreates an infinite authorize loop."

**Source.** https://angular.dev/guide/routing/route-guards - return type table: "UrlTree or
RedirectCommand Redirects to another route instead of blocking". The doc does not discuss loops; the
unguarded-target rule is owner history on top of it.

---

## ANGULAR-07 A failed read renders as "could not verify" and disables every write it feeds

**Evidence.** OWNER-HISTORY. Refines GEN-01.

**Rule.** When a read that a view's write controls depend on fails, the view does not fall back to empty
or default values that look like data. It records the failure as its own state, shows "could not verify"
where the value would be, and gates every control that can lead to a write on that state - both in the
template (not rendered, not merely disabled, for destructive controls) and again in the handler. The
reverse also holds: a cached *advisory* value never becomes a hard client-side block on an action the
server decides live.

**Why.** ec2-management-iam: "When /principals failed but /users still loaded, every directory row
defaulted to roles=[] ... an admin saving from it would PUT an empty role list for a real person,
overwriting whatever they actually held". The first fix disabled Remove; the re-review rejected it:
"'disabled and present' is not 'not offered.'" In the other direction, a stale `power_cycle_manager` cache
"disabled the control AND runAction() refused the click, so the request never reached the server's live
EC2 tag check ... The advisory field had become the authority." And a delimiter-only input "parsed to []
- indistinguishable from a genuinely blank box, which is the one shape that legitimately means
fleet-wide".

**Applies when.** A component joins two or more reads to build rows that carry write controls; a control
is enabled/disabled from cached data; a parser maps free-text input to a list that has an "empty means
all" meaning.

**Self-check.**
1. For each read feeding a write control: what does the view show and allow if it fails? Pass: a distinct
   failure state, and no write reachable.
2. Do the write handlers re-check that state, not only the template? Pass: yes.
3. Is any control hard-disabled from cached/advisory data the server re-checks anyway? Pass: no - it is a
   hint.
4. Where empty input has a special meaning ("all"), is non-empty raw input that parses to empty refused?
   Pass: yes.

**Earned by.** `solomon/aws-shared-infrastructure@d1c39e6` ("Codex review, tasks 14-20, Critical +
Important #2"), `@a65df55` ("Fix round 2, F2"), `@36ffb7c` ("Fix round 3 on task 8. Critical"),
`@f774865` ("I2"); `solomon/aws-managed-services@14d24e8d` ("a whitespace-only owner no longer blanks the
select").

**Source.** No fetched Angular doc states it; the route-guards "enforce ... server-side" sentence
(ANGULAR-05) supports only the second half.

---

## ANGULAR-08 Untrusted text reaches the DOM only through interpolation or the sanitizer

**Evidence.** BOTH. Refines GEN-06 (hostile text and paths are neutralised at the sink).

**Rule.** Render untrusted data with interpolation or property bindings. `[innerHTML]` is allowed only with
Angular's sanitizer left on; `bypassSecurityTrust*` is never applied to a value that crossed a trust
boundary (API response, vendor HTML, user input, markdown rendered from either). No direct DOM writes of
untrusted content (`ElementRef.nativeElement.innerHTML`, `document.write`, `insertAdjacentHTML`); where DOM
access is unavoidable, pass the value through `DomSanitizer.sanitize(SecurityContext.X, value)`. Links
built from data accept an allowlist of schemes (`https:`, and `mailto:` if needed) and refuse
`javascript:`, `data:`, `vbscript:`, scheme-relative `//host` and scheme-less targets.

**Why.** trusted-advisor-report's QA/security round had to make the link pattern refuse
"javascript:/data:/vbscript:/`//evil`/ scheme-less targets", and to stop plain prose "spelling" a link
token. drata-insights shows the pattern that holds: vendor HTML "goes through `[innerHTML]`, so Angular's
sanitizer runs on it - never bypass that".

**Applies when.** A diff adds `[innerHTML]`, `[outerHTML]`, `DomSanitizer`, `ElementRef`/`viewChild`
DOM writes, `Renderer2.setProperty(..., 'innerHTML', ...)`, a markdown/HTML renderer, or builds an
`href`/`src` from data.

**Self-check.**
1. `git grep -n "bypassSecurityTrust"` over the diff's files: for each hit, is the value a compile-time
   constant or produced by code in this repo from constants? Pass: yes, or no hits.
2. For each `[innerHTML]`: where does the value come from, and is the sanitizer on? Pass: named, and no
   bypass upstream.
3. For each DOM write via `nativeElement`/`Renderer2`: is the value sanitized for its context first?
   Pass: yes.
4. For each data-built URL: is there a scheme allowlist and a spec feeding `javascript:` and `//host`?
   Pass: yes.

**Earned by.** `solomon/aws-managed-services@20bf35cd` ("PR #506 QA/security fix round", item 11:
"LINK_TOKEN accepts any scheme | 7: refuses the link target javascript:alert1 / JavaScript:alert1 /
data:... / vbscript:msgbox / //evil.example/x / evil.example/x / https:evil.example");
`drata-insights/frontend/src/app/shared/policy-preview/policy-preview.ts:279-283@7848e99d`.

**Source.** https://angular.dev/best-practices/security -
"Angular treats all values as untrusted by default."; for `bypassSecurityTrust*`, "tell Angular that you
inspected a value, checked how it was created, and made sure it is secure. Do be careful. If you trust a
value that might be malicious, you are introducing a security vulnerability into your application.";
"the built-in browser DOM APIs don't automatically protect you from security vulnerabilities. For
example, document, the node available through ElementRef, and many third-party APIs contain unsafe
methods."; "Avoid directly interacting with the DOM and instead use Angular templates where possible. For
cases where this is unavoidable, use the built-in Angular sanitization functions. Sanitize untrusted
values with the DomSanitizer.sanitize method and the appropriate SecurityContext."

---

## ANGULAR-09 Component styles do not reach injected DOM; style it on purpose

**Evidence.** BOTH. Refines GEN-10.

**Rule.** Styles in a component's `styles`/`styleUrl` under the default emulated encapsulation apply only
to elements compiled from that component's template. Content inserted with `[innerHTML]`, a third-party
library, or direct DOM calls is never matched by them. Style such content from the global stylesheet
under a scoping class, or from a dedicated wrapper component with `ViewEncapsulation.None`; do not add new
`::ng-deep`. Verify against the built bundle or a rendered spec that injects exactly as production does,
not by loading the component CSS as a global sheet.

**Why.** exec-insights' chat rendered answers with `[innerHTML]`; "every rule in `chat.css` compiled to a
selector that matched nothing" while a global `overflow-wrap: anywhere` did reach the table - "the
symptom applies and the remedy is inert". The verification harness loaded the CSS globally, so "the check
passed while production was broken".

**Applies when.** A diff adds component CSS for content that arrives via `[innerHTML]`, a library, or DOM
APIs; or adds `::ng-deep`/`ViewEncapsulation`.

**Self-check.**
1. For each new rule: is its target element written in this component's template? Pass: yes, or the rule
   lives in the global sheet/an unencapsulated wrapper.
2. Any new `::ng-deep`? Pass: no.
3. Was the styling checked in a harness that injects the content as production does? Pass: yes.

**Earned by.** Vault `concepts/anew/exec-insights/Component-scoped Angular CSS never reaches
innerHTML-injected DOM.md:29-58`.

**Source.** https://angular.dev/guide/components/styling - "Angular uses emulated encapsulation so that a
component's styles only apply to elements defined in that component's template."; "The Angular team
strongly discourages new use of ::ng-deep. These APIs remain exclusively for backwards compatibility."

---

## ANGULAR-10 What a binding produces is what the CSS, ARIA and tests select

**Evidence.** BOTH. Refines GEN-07 (one validated contract between producer and consumer).

**Rule.** `[class.x]` adds a CSS class; `[attr.x]` sets an attribute (and removes it on `null`); a
property binding sets a DOM property, which is not an attribute. Write the stylesheet selector and the
test locator for what the binding produces. Every ARIA reference (`aria-controls`, `aria-labelledby`,
`for`) names an id an element in the rendered DOM carries; dynamic ARIA uses `[attr.aria-*]`.

**Why.** exec-insights' timesheet bound `[class.ts-cell-future]` while the CSS targeted
`.ts-cell[data-future='true']` "in two places ... the class binding never creates a data-future
attribute, so neither CSS rule ever matched". trusted-advisor-report's first mounting spec found
"`aria-controls="side-nav"` on the drawer toggle pointed at an id no element carried."

**Applies when.** A diff adds `[class.`, `[attr.`, `[style.`, `aria-*` references, or CSS/test selectors
targeting classes or attributes set by bindings.

**Self-check.**
1. For each new CSS or test selector on a bound class/attribute: does the binding produce exactly that
   (class vs attribute vs property)? Pass: yes.
2. For each `aria-controls`/`aria-labelledby`/`for`: does a rendered element carry that id? Pass: yes,
   asserted in a rendered spec.

**Earned by.** Vault `concepts/_general/javascript/An Angular class binding creates a CSS class, not a
data-attribute, so a data-attribute selector never matches.md:23`; `solomon/aws-managed-services@69da7611`.

**Source.** https://angular.dev/guide/templates/binding - "When you need to set HTML attributes that do
not have corresponding DOM properties, such as SVG attributes, you can bind attributes to elements in your
template with the attr. prefix."; "If the value of an attribute binding is null, Angular removes the
attribute by calling removeAttribute." https://angular.dev/best-practices/a11y (attribute binding
`[attr.aria-valuenow]` for dynamic ARIA).

---

## ANGULAR-11 A `<select>` over `@for` options selects per option, and a spec starts it non-default

**Evidence.** BOTH. Refines GEN-04 (every behaviour has a control that fails).

**Rule.** Do not bind `[value]` on a `<select>` whose `<option>`s come from `@for`: the value is assigned
before the options exist and the browser shows the first option (or nothing). Use a forms control
(`formControl`/`ngModel` with `[ngValue]` and `compareWith` for object values), or `[selected]="opt ===
value()"` on each option. A spec renders the component with a **non-default** value already set and
asserts the displayed selection, not only the value emitted on change.

**Why.** It shipped three times across two projects. terraform-workspace-management's admin role select
"silently fell back to the first option in the list (Administrator)" - the most privileged role; the same
race recurred in aws-shared-infrastructure's filter bar and again in TableControls ("caught in review that
time by citing the filter-bar precedent"). A test that only checks the emitted value "won't catch this
class of bug".

**Applies when.** A diff adds or edits a `<select>` whose options are produced by `@for`/`*ngFor`, or a
custom select.

**Self-check.**
1. `[value]` on a `<select>` with `@for` options? Pass: no.
2. Object option values without `compareWith`? Pass: no.
3. Is there a spec that initialises a non-default value and asserts the selected option? Pass: yes, and it
   fails with `[value]` put back.

**Earned by.** `solomon/aws-managed-services@18e179db` ("The <select [value]> binding runs before the @for
options render, so the value assignment silently fails and the browser displays the first option
(Administrator)") - cross-checked against the vault note
`concepts/solomon/aws-managed-services/An Angular select bound with [value] before its @for options render
silently falls back to the first option.md:25-45`, which also records the two aws-shared-infrastructure
recurrences.

**Source.** https://angular.dev/api/forms/SelectControlValueAccessor - "Angular uses object identity to
select option. It's possible for the identities of items to change while the data does not."; "To
customize the default option comparison algorithm, `<select>` supports `compareWith` input." (The doc does
not describe the `[value]`-before-`@for` race itself; that is owner history.)

---

## ANGULAR-12 A template change is proven by a rendered spec and the production build

**Evidence.** BOTH. Refines GEN-04 and GEN-12 (verification evidence matches the final HEAD).

**Rule.** A change to a template (`.html` or inline `template`) is covered by a spec that mounts the
component with `TestBed` and asserts rendered DOM, and the change is proven with the production build
(`ng build` / `npm run build` with the production configuration), not only `ng test`. The control: revert
the template change alone - a spec must go red. Where the build output is committed (a `frontend_dist`
the deploy uploads), the rebuilt artifact is committed with the source change or the gate that compares
them is green.

**Why.** trusted-advisor-report: "The UI v2 suite tested only pure functions under vitest's node
environment, so no template in the branch had ever been executed"; later "QA blocked #480 by
reverse-applying the diff: revert work-queue.html and all 221 frontend tests still pass". In
security-ops-dashboard "170 tests passed while the build was broken, because the three spec files do not
import `queue.ts`" - a backtick in a template comment ended the template literal (`NG1002`), twice. And in
aws-managed-services an entire UI redesign "deployed as a no-op" because the deploy uploads the committed
bundle and "`frontend/src` is deployed by nothing".

**Applies when.** Any diff touching a component template, inline `template:`/`styles:` literal, or
component class code that the template reads.

**Self-check.**
1. Which spec mounts this component and asserts the changed markup? Pass: named.
2. With the template hunk reverted and the rest kept, does that spec fail? Pass: yes (report the run).
3. Did the production build run on the final HEAD, and what was its exit code? Pass: 0, stated.
4. If the repo commits build output: is it rebuilt from this HEAD, or does the artifact gate pass? Pass:
   yes.

**Earned by.** `solomon/aws-managed-services@69da7611`, `@14d24e8d`, `@975a3ac0`; vault
`concepts/unknown/security-ops-dashboard/A backtick in a template comment terminates the TypeScript
template literal and fails the Angular build.md:30-50`;
`solomon/aws-shared-infrastructure/CLAUDE.md:157-161@17e4db3` ("otherwise an apply deploys stale JS").

**Source.** https://angular.dev/guide/testing/components-basics - "A component is more than just its
class. A component interacts with the DOM and with other components. Classes alone cannot tell you if the
component is going to render properly, respond to user input and gestures, or integrate with its parent
and child components."

---

## ANGULAR-13 Build configurations override, `public/` ships everything, environment files are public

**Evidence.** BOTH. Refines GEN-09 (what the change says is true at this commit) and GEN-10.

**Rule.** (a) A setting in `angular.json` `build.options` is overridden, not merged, by the same key in a
named configuration - an array such as `assets` set in both places must be edited in both, and checked
under the production configuration. (b) Everything in `public/` (or a configured asset glob) is copied
into the bundle whether referenced or not - keep source art and working files outside it. (c) Anything in
`src/environments/` or a bundled config file is readable by every visitor - no secrets there. (d) A
runtime config file the deploy generates (e.g. `environment.json` from Terraform) is excluded from the
build's assets, from the upload, and from the committed artifact, so a dev copy cannot overwrite it.

**Why.** aws-shared-infrastructure: "An asset mapping added to only the first works under `ng serve` and
404s in production"; "four original PNG brand images totaling 6,290 KB sat directly in `public/` ... even
though the app only ever rendered WebP-converted versions" (fixed to 103 KB). terraform-workspace-management
broke Cognito sign-in in production because "a development `environment.json` (checked into git with
empty credentials) got included in the Angular production build ... and overwrote the Terraform-generated
`environment.json`".

**Applies when.** A diff edits `angular.json`, adds files under `public/`/`assets`, edits
`src/environments/*`, or touches a runtime config file.

**Self-check.**
1. For each `angular.json` key changed under `options`: is the same key set under any configuration? Pass:
   no, or edited there too.
2. For each file added under `public/`: is it referenced by the app and already optimised? Pass: yes.
3. Does any environment or bundled config file gain a key, token, or password? Pass: no.
4. If a deploy-generated config exists: is it excluded at build, upload and commit? Pass: all three.

**Earned by.** `solomon/aws-shared-infrastructure/CLAUDE.md:163-175@17e4db3`; vault
`concepts/solomon/aws-shared-infrastructure/Angular's public asset folder copies everything verbatim and
unfiltered by reference, so unreferenced source art ships to every visitor unless moved out of it.md:25-29`;
vault `concepts/solomon/aws-managed-services/A committed development config file can silently overwrite a
Terraform-generated production config unless every layer that touches it excludes it.md:23-25`.

**Source.** https://angular.dev/reference/configs/workspace-config - "Each configuration sets the default
options for that intended environment, overriding the associated value under options."; "By default, the
contents of the public/ directory are copied over." https://angular.dev/tools/cli/environments - "Files in
src/environments/ are bundled into your client-side application and visible to anyone who loads the page.
Never store secrets such as API keys here. Use a server-side proxy or a secrets manager instead."
(The workspace-config page does not state that arrays are replaced wholesale; that detail is the
aws-shared-infrastructure CLAUDE.md's measured claim.)

---

## ANGULAR-14 Production bundles are content-hashed, or the cache headers say what to do

**Evidence.** BOTH. Refines GEN-10.

**Rule.** The production configuration sets `"outputHashing": "all"`. If it cannot, the upload sets
`Cache-Control` explicitly per object (`no-cache` for `index.html`, long `max-age` + `immutable` only for
hashed files). A CDN invalidation is evidence about the edge, not about returning browsers - prove a
client-side fix from a profile that visited before, without a hard refresh.

**Why.** HD Pro deploys invalidated CloudFront "and returning visitors still saw the previous UI" because
`outputHashing` was `none` and the upload set no `cache_control`. terraform-workspace-management's deploy
analysis found the sharper edge: with `outputHashing` `none`, "a returning browser with the old `main.js`
cached has no cue to refetch and that script references two chunks this same apply deletes ... the dynamic
import fails hard". The commit named "`outputHashing: "all"`" as the fix and left it for later; **five of
the owner's seven Angular apps still set `"none"`** at the HEADs read (listed under Earned by).

**Applies when.** A diff edits `angular.json` build configurations, the S3/CDN upload of the bundle, or
deploys a frontend change meant to reach existing users.

**Self-check.**
1. Production `outputHashing`? Pass: `"all"`, or explicit per-object `Cache-Control` in the upload.
2. Does `index.html` get `no-cache` (or equivalent)? Pass: yes.
3. Was the fix verified in a browser that had the previous version cached? Pass: yes, stated.

**Earned by.** Vault `concepts/anew/TheHomeDepot/Unhashed bundle filenames plus no Cache-Control means a
CloudFront invalidation fixes nothing for returning visitors.md:29-64` (THD's `thd-prod` repo is not on
this host; second-hand); `solomon/aws-managed-services@975a3ac0` (cross-checks the mechanism first-hand).
Still `"none"` at read time: `aws-managed-services/fileshare-audit/frontend/angular.json:73`,
`infra-management-tool/frontend/angular.json:70`, `terraform-workspace-management/frontend/angular.json:71`,
`trusted-advisor-report/frontend/angular.json:70` (all `@7848e99d`);
`aws-shared-infrastructure/ec2-management-iam/frontend/angular.json:71@17e4db3`;
`solomon-fuels-participant/frontend/angular.json:52`.

**Source.** https://angular.dev/cli/build - "output-hashing Define the output filename cache-busting
hashing mode. none: No hashing. all: Hash for all output bundles. media: Hash for all output media ...
bundles: Hash for output of lazy and main bundles." (The CLI flag's listed default is `none`; the
recommendation to use `all` is owner history, not a doc sentence.)

---

## ANGULAR-15 The production CSP and the build's inline output agree

**Evidence.** BOTH. Refines GEN-10.

**Rule.** When the app is served with a `Content-Security-Policy`, the build must not emit inline script
the policy blocks. `optimization.styles.inlineCritical` (default `true`) rewrites the stylesheet link with
an inline `onload` handler; under `script-src 'self'` that handler never runs and the full stylesheet
stays `media="print"`. Either set `inlineCritical: false`, or use a per-request nonce (`autoCsp`,
`ngCspNonce`, or `CSP_NONCE`). Verify rendering through the real response headers, and check the browser
console for CSP violations - a dev server or a bare file harness has no CSP.

**Why.** HD Pro rendered as unstyled chrome in production only: "An inline event-handler attribute is
inline script, so the browser refuses to run it. `media` never flips." It "survived several rounds of
review" because reading the CSS, the dev server, the screenshot harness and the build were "structurally
blind to it". The two owner apps that do ship a `script-src` CSP now also set `inlineCritical: false`.

**Applies when.** A diff adds or edits a CSP (response-headers policy, meta tag, server config), or edits
`angular.json` `optimization`, `security.autoCsp`, or `index.html` inline script/handlers.

**Self-check.**
1. Does the emitted `index.html` contain an inline `on*=` handler or inline `<script>`? If so, does the
   CSP allow it by nonce? Pass: none, or nonce-allowed.
2. Was the page loaded through the production headers with zero CSP console errors? Pass: yes.
3. If nonces are used: are they unique per request? Pass: yes.

**Earned by.** Vault `concepts/anew/TheHomeDepot/A CSP without unsafe-inline kills Angular's critical-CSS
media flip and the whole stylesheet stays inert.md:35-91` (THD, second-hand); first-hand configuration:
`aws-managed-services/security-ops-dashboard/frontend/angular.json:48` and
`trusted-advisor-report/frontend/angular.json:77` (`"inlineCritical": false`) alongside `script-src` in
each module's `terraform/response_headers_policy.tf` (`@7848e99d`).

**Source.** https://angular.dev/best-practices/security - "The minimal policy required for a brand-new
Angular application is: default-src 'self'; style-src 'self' 'nonce-randomNonceGoesHere'; script-src
'self' 'nonce-randomNonceGoesHere';"; "Set the autoCsp option to true in the workspace configuration.";
"Always ensure that the nonces you provide are unique per request and that they are not predictable or
guessable." https://angular.dev/reference/configs/workspace-config - "inlineCritical Extract and inline
critical CSS definitions to improve First Contentful Paint. boolean true". (No fetched doc states the
`inlineCritical` / `onload` / CSP interaction; that link is owner history.)

---

## ANGULAR-16 Angular stays on a supported major and moves as one set

**Evidence.** BOTH. Refines GEN-09.

**Rule.** The app runs a major in Angular's active or LTS window. A security patch moves every
`@angular/*` runtime package to the same patch together (they pin each other exactly), within the current
major - a major bump is its own change. Regenerate the lockfile from `package.json` rather than patching
it, then prove the production build and suite on the result.

**Why.** A security sweep found "the same four Angular CVEs in drata-insights, infra-management-tool and
terraform-workspace-management, all locked at 21.2.18", including an i18n hole "letting a lower-trust
translation file replace a static handler with executable JavaScript" and a compiler that "could omit or
pick the wrong sanitizer for security-sensitive host bindings". "Upgrading core and common alone is
refused by npm, correctly", and "`npm update` moved only the CLI and left every runtime package at
21.2.18".

**Applies when.** A diff changes `package.json`/`package-lock.json` Angular entries, or a scan reports an
Angular advisory.

**Self-check.**
1. Is the major in the active or LTS table on the releases page? Pass: yes.
2. Are all `@angular/*` runtime packages at one version in the lockfile? Pass: yes.
3. Did the production build and the suite run on the regenerated lock? Pass: yes, exit codes stated.

**Earned by.** `solomon/aws-managed-services@e57ebd7d` ("upgrade Angular to 21.2.23 across three modules,
closing four CVEs").

**Source.** https://angular.dev/best-practices/security - "Keep current with the latest Angular library
releases - The Angular libraries get regular updates, and these updates might fix security defects
discovered in previous versions. Check the Angular change log for security-related updates."; "Don't alter
your copy of Angular". https://angular.dev/reference/releases - "Long-term (LTS) 12 months Only critical
fixes and security patches are released"; "Angular versions v2 to v19 are no longer supported."

---

## ANGULAR-17 An identity or permission cached on the client is dropped on any 401/403

**Evidence.** BOTH. Refines GEN-01.

**Rule.** A client-side cache of who the user is or what they may do (`/me`, roles, a group check)
caches success only, is cleared on sign-out, and is cleared by the HTTP interceptor on any 401 or 403 from
any API call, so a revoked user loses access at the next call. Interceptors modify requests only by
`clone()`. Do not attach the XSRF header or bearer token to cross-origin URLs by hand - Angular's XSRF
interceptor deliberately sends only to relative and same-origin URLs.

**Why.** trusted-advisor-report's guard called `GET /api/me` on every navigation; caching it was only safe
as "`shareReplay`, success only, cleared on sign-out and on any 401 or 403 seen anywhere in the API, so a
revoked member loses access at the next call rather than at a timer".

**Applies when.** A diff caches an HTTP result behind a guard or permission check (`shareReplay`, a
signal, a service field), or adds/edits an `HttpInterceptorFn`.

**Self-check.**
1. For each cached identity/permission read: where is it invalidated? Pass: sign-out and any 401/403.
2. Does the cache hold failures? Pass: no.
3. Does any interceptor mutate a request in place, or add credentials for absolute third-party URLs?
   Pass: no.

**Earned by.** `solomon/aws-managed-services@8cd162ed`; implementation
`trusted-advisor-report/frontend/src/app/core/services/api.service.ts:50-78@7848e99d`.

**Source.** https://angular.dev/guide/http/interceptors - "Most aspects of HttpRequest and HttpResponse
instances are immutable, and interceptors cannot directly modify them. Instead, interceptors apply
mutations by cloning these objects using the .clone() operation". https://angular.dev/best-practices/security
- "an interceptor sends this header on all mutating requests (such as POST) to relative and same origin
URLs, but not on GET or HEAD requests."

---

## ANGULAR-18 A timestamp without a zone is refused, not parsed as the browser's local time

**Evidence.** BOTH. Refines GEN-07.

**Rule.** A component or pipe that turns an API timestamp into a `Date` requires a trailing `Z` or a
numeric offset. A date-time string without one is treated as invalid and rendered as "unknown", never
passed to `new Date()`/`Date.parse`. Specs that assert rendered times run under a non-UTC `TZ`.

**Why.** "`data-as-of.ts:39` passed any string straight to `new Date()`. A value with no zone marker
(`2026-06-15T12:30:00`) is read as the BROWSER'S LOCAL time, not UTC -- this repo has shipped that exact
defect shape once already, for the legacy status-history ingest." The mutation rendered "12:30:00 PM"
against a true "07:30:00 AM".

**Applies when.** A diff parses a date/time string from an API or storage in frontend code, or adds a
date pipe/formatter over such a value.

**Self-check.**
1. For each `new Date(str)`/`Date.parse(str)` on external data: is a zone marker required first? Pass: yes.
2. Do the specs run under a non-UTC timezone and assert exact output? Pass: yes.

**Earned by.** `solomon/aws-shared-infrastructure@d1f0d44` ("Review findings (round 1): Important").

**Source.** https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Date/parse -
"The following call, which does not specify a time zone will be set to 2019-01-01 at 00:00:00 in the
local timezone of the system, because it has both date and time." (MDN, not an Angular doc; this rule
overlaps the Node lane and should live in one place - see "Proposed shape".)

---

## Considered and not admitted

- **`@for` track by a stable unique id** (DOC only). angular.dev/guide/templates/control-flow: "Select a
  property that uniquely identifies each item in the track expression"; tracking by the item itself
  "Avoid this option whenever possible as it can lead to significantly slower rendering updates". No owner
  defect found; `@for` requires `track`, so the compiler already forces a choice. Candidate for the
  skill's pitfalls list, not a self-checked standard.
- **Derive state with `computed`, not `effect`; never deep-mutate a signal's value** (DOC only).
  angular.dev/guide/signals/effect: "Avoid using effects for propagation of state changes. This can result
  in ExpressionChangedAfterItHasBeenChecked errors, infinite circular updates, or unnecessary change
  detection cycles."; angular.dev/guide/signals: "The readonly signals do not have any built-in mechanism
  that would prevent deep-mutation of their value." No owner defect of this shape found. Same
  recommendation.
- **Destructive multi-select needs a per-item typed confirmation** (vault, terraform-workspace-management).
  A UX pattern the owner adopted, not a defect that recurred; left out.
- **Design-token role misuse fails in one theme** (vault, THD). Real, but CSS/design-system, not Angular.

## Anti-patterns seen in the owner's repos

1. **Route subscriptions in a constructor with no teardown**, and lifetime subscriptions parked on a
   `Subscription` that another event replaces (`aws-managed-services@e18a5332`).
2. **Checking a request only when it is sent** - the answer lands after the page moved and is applied
   anyway (`@82c84eef`, `@8956cdb4`, `@fb12529b`).
3. **A second code path that calls the API directly** (the poll) and so skips the invariant the main
   loader enforces (`@8956cdb4`). Its comment claimed it was covered: "the poll tick and each post-action
   refresh included" - "how an unpinned caller survived an audit of every `loadDetail` caller".
4. **Cancelling user-authorised writes on destroy**, and reporting results to the dying component's own
   signal (`@fb12529b`, `@2bfee978`).
5. **Two redundant defences, neither tested alone**, so deleting one left every test green (`@861e98e4`).
6. **Assuming guard array order sequences execution** (`aws-shared-infrastructure@b5b012a`).
7. **Guard denials, wildcard and auth fallbacks pointing at a guarded route** - infinite authorize loop
   (`@84693f3`, `@ee5ad15`).
8. **Authorization decided only inside a component**, with a route-table test that asserts "a guard
   exists" (`@6b97739`).
9. **A failed read joined as empty data**, rendering "No roles" and enabling a PUT that would erase real
   roles (`@d1c39e6`); then **disabled-but-present** as the fix (`@a65df55`).
10. **A stale advisory cache as a hard client gate** in front of a server that checks live (`@36ffb7c`).
11. **`<select [value]>` over `@for` options** - three recurrences, one defaulting new users to
    Administrator (`aws-managed-services@18e179db`, vault note).
12. **Component CSS for `[innerHTML]` content**, verified with the CSS loaded globally (vault, exec-insights).
13. **`[class.x]` binding with a `[data-x]` selector**, and `aria-controls` naming a missing id (vault;
    `@69da7611`).
14. **Specs that never mount a template**, so reverting the template left 221 tests green (`@14d24e8d`);
    tests that do not import the component, green while `ng build` failed (vault, security-ops-dashboard).
15. **Committed build output that the deploy uploads, not rebuilt** - "an entire UI redesign deployed as a
    no-op" (`@975a3ac0`).
16. **`outputHashing: "none"` with no `Cache-Control`** - still in five of seven apps (ANGULAR-14).
17. **`inlineCritical` left on under `script-src 'self'`** (vault, THD).
18. **Asset mapping added only to `build.options`**; source art in `public/`; a dev `environment.json`
    shipped over the deployed one (CLAUDE.md, vault).
19. **Patching one or two `@angular/*` packages for a CVE**, or `npm update` believed to have moved them
    (`@e57ebd7d`).
20. **`new Date(naiveString)`** - shipped twice in one repo (`aws-shared-infrastructure@d1f0d44`).

## Proposed shape for the extended `stack-angular`

- Keep the existing pitfalls section; add a short "Standards" section pointing at
  `references/standards.md` holding ANGULAR-01..18 in T-0085's format, loaded by `/crew:plan` and
  `/crew:implement` when the diff touches `angular.json`, `*.component.ts`/`*.ts` under a directory with
  `angular.json`, or `*.html` templates.
- Repo-specific paths (the `frontend_dist` gate, the `response_headers_policy.tf` files, a repo's
  `app.config.spec.ts`) belong in that repo's `.crew/standards.md` overlay under `Supplements
  ANGULAR-<n>`, never in the plugin copy. The Earned-by paths above are evidence, not self-check text.
- ANGULAR-18 (naive timestamps) is JavaScript, not Angular: move it to the Node lane's set if that lane
  has the same rule, and reference it from here, rather than shipping it twice.
- Rules 03, 06, 07 overlap GEN-01/GEN-11 in intent; they are kept because each self-check asks an
  Angular-specific question (surviving signals, unguarded redirect targets, template-and-handler gating)
  that the GEN self-check would not prompt.

## Official sources (fetched by this lane, 2026-09-28)

Quotes re-extracted from raw HTML/source with `curl` + string search, not from WebFetch summaries.

- https://angular.dev/best-practices/security
- https://angular.dev/guide/routing/route-guards
- https://angular.dev/guide/components/styling
- https://angular.dev/guide/http/making-requests
- https://angular.dev/guide/http/interceptors
- https://angular.dev/ecosystem/rxjs-interop/take-until-destroyed
- https://angular.dev/guide/templates/control-flow
- https://angular.dev/guide/templates/binding
- https://angular.dev/guide/signals and https://angular.dev/guide/signals/effect
- https://angular.dev/best-practices/skipping-subtrees (read; not cited - OnPush is already in the skill)
- https://angular.dev/best-practices/a11y
- https://angular.dev/api/forms/SelectControlValueAccessor
- https://angular.dev/guide/testing/components-basics
- https://angular.dev/tools/cli/environments
- https://angular.dev/reference/configs/workspace-config
- https://angular.dev/cli/build
- https://angular.dev/reference/releases
- https://raw.githubusercontent.com/ReactiveX/rxjs/7.x/src/internal/operators/switchMap.ts
- https://raw.githubusercontent.com/ReactiveX/rxjs/7.x/src/internal/operators/shareReplay.ts
- https://raw.githubusercontent.com/angular/angular/main/packages/router/src/operators/prioritized_guard_value.ts
- https://raw.githubusercontent.com/angular/angular/main/packages/router/src/operators/check_guards.ts
- https://developer.mozilla.org/en-US/docs/Web/JavaScript/Reference/Global_Objects/Date/parse
- Fetched and empty (client-rendered shell): https://rxjs.dev/api/operators/switchMap. Fetched and
  containing nothing on caching/hashing: https://angular.dev/tools/cli/deployment,
  https://angular.dev/tools/cli/build.

## Not verified

- **No test, build or mutation was run.** Every "fails with X removed" claim in Earned by is the owner's
  commit message, not re-run by this lane.
- **Router source was read on `main`, not at the owner's 21.2.x tag.** The `combineLatest` behaviour in
  ANGULAR-05 matches what the owner's 2026-08-05 commit describes for their installed version, but this
  lane did not check out the 21.2 tag. No `node_modules` exists in the solomon frontends on this host.
- **A code comment in the owner's repo disagrees with rxjs 7.x source.**
  `trusted-advisor-report/frontend/src/app/core/services/api.service.ts:57-61@7848e99d` says a naive
  `shareReplay` would lock a user out "since a ReplaySubject that has errored replays that error to every
  future subscriber". rxjs 7.x `shareReplay` is `share({ connector: () => new ReplaySubject(...),
  resetOnError: true, ... })`, i.e. it resets on error rather than replaying it. The explicit reset in that
  code is harmless; the stated reason looks wrong for rxjs 7. ANGULAR-17 does not rely on it. Not verified
  against the exact installed rxjs patch.
- **Vault notes are second-hand.** THD's `thd-prod` Angular app is not on this host, so ANGULAR-14's and
  ANGULAR-15's THD evidence is vault-only (ANGULAR-14 is cross-checked first-hand by `975a3ac0`; ANGULAR-15
  only by the configuration pairing in two solomon apps, not by a reproduced failure).
- **The "five of seven apps still `outputHashing: none`" count** is a grep of `angular.json` at the HEADs
  named; it does not check whether those modules set `Cache-Control` at upload, which would satisfy
  ANGULAR-14 by its second branch. `solomon-fuels-participant`'s HEAD sha was not recorded.
- **Subscription hygiene was not audited.** A grep found 75 frontend `.ts` files containing `subscribe(`
  and 14 containing `takeUntilDestroyed`; that ratio is not a defect count (one-shot HTTP calls complete on
  their own) and is not used as evidence.
- **The `[value]`/`@for` race** is documented from owner history only; no Angular doc describing it was
  found. The two aws-shared-infrastructure recurrences are cited from the vault note, not from commits
  this lane located.
- **`drata-insights/frontend/src/app/features/chat/chat.html:54`** binds `[innerHTML]="renderMarkdown(...)"`
  (a function call re-evaluated each change-detection pass, with `marked` output going through the
  sanitizer). Noted, not assessed as a defect.
- Only `/repos/solomon`, `/repos/anew`, `/repos/personal` and the vault were searched. Jira/SDP tickets and
  Bitbucket PR comments were not.
