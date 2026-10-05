# .NET candidate standards (not gated)

No gated .NET standards set ships yet (L-0535). Nothing in this file is loaded by
`crew_standards.py` or asked in the pre-review self-check. It is guidance, kept with its
evidence, so that a rule can be promoted into `crew-standards/references/dotnet.md` (set
`DOTNET`, `applies-to: ["**/*.cs", "**/*.cshtml", "**/*.razor"]`) once three distinct
reviewed change sets earn it.

**Why nothing ships.** The bar and the counting rule are `python.md`'s: a change set is a
crew review, or a fix commit whose own message or CHANGELOG entry records that a review
found the defect. There is no file-type condition.
The owner decided on 2026-10-05 that public third-party change sets do not count toward
that bar. The spec's provisional re-count found three rules at the bar in the owner's
private repositories: DOTNET-08 (3), DOTNET-13 (4) and DOTNET-15 (3). Their rule text and
citations are in the owner's research, which this build did not have, so they could not
be written. The two rules below come from a public pass on 2026-10-05. Its change sets
are recorded as leads, each counted 0 toward the bar.

**How the public pass read its evidence.** Commit messages came from GitHub commit
search. Diffs and changed paths were not read. Every Source sentence was string-matched
against the raw Microsoft Learn page on 2026-10-05. `DOTNET-Pn` are labels from the
public pass, not loader ids. Whether either rule is the same as a research rule could
not be determined.

## Candidate standards (not gated)

### DOTNET-P1 Never block on async code (`.Result`, `.Wait()`, `GetAwaiter().GetResult()`)

Counted toward the bar: unknown (whether it is one of the owner's research rules
could not be determined). 3 public change sets, which do not count.

In request, handler, UI and library code, await asynchronous work all the way up. Do not
call `.Result`, `.Wait()`, `Task.WaitAll` or `.GetAwaiter().GetResult()` on a task that
has not completed. Where a synchronous API cannot be avoided, give it a real synchronous
path, not a wrapper over the async one (a `Task.Run` wrapper still blocks). This extends
the `async void` / `.Result` pitfall in `SKILL.md`.

Public change sets (message text only):
- `ppds-576581ea` (joshsmithxrm/power-platform-developer-suite@576581ea, #81): "address
  remaining issue 71 code review findings (8, 12) Issue 8: Wrap sync-over-async in
  Task.Run to avoid deadlock". The finding supports this rule. The fix chosen there does
  not follow it.
- `headless-dcdb573b` (xshaheen/headless-framework@dcdb573b, #354): "address code-review
  findings ... true sync WriteSync on raw audit stores (no more GetAwaiter()...".
- `fhir-caaa4c08` (GinoCanessa/fhir-augury@caaa4c08): "replace blocking
  .GetAwaiter().GetResult() with async/await ... Addresses critical finding #2 from code
  review".

Source: https://learn.microsoft.com/en-us/aspnet/core/fundamentals/best-practices?view=aspnetcore-9.0:
"Many synchronous blocking calls lead to Thread Pool starvation and degraded response
times." "Do not block asynchronous execution by calling Task.Wait or
Task<TResult>.Result."

Public verdict: admitted on public stand-ins (3). That does not count under the owner's
decision.

### DOTNET-P2 Do not create an `HttpClient` per call: use `IHttpClientFactory` or one long-lived client

Counted toward the bar: unknown (whether it is one of the owner's research rules
could not be determined). 7 public change sets, which do not count, plus 1 weak one.

Get `HttpClient` from `IHttpClientFactory` (named or typed clients). On .NET Core and
.NET 5+, one long-lived instance whose `SocketsHttpHandler` sets `PooledConnectionLifetime`
is the alternative. `SocketsHttpHandler` does not exist on .NET Framework 4.8, which uses the
factory. Never
write `new HttpClient()` in a method that runs per request or per call. One exception: a
client that needs cookies avoids the factory, because pooled handlers share their
`CookieContainer`. It uses its own long-lived client and handler, one per cookie scope.
This extends the `HttpClient` pitfall in `SKILL.md`.

Public change sets (message text only). Each message records a review finding that
replaced a per-call `new HttpClient()` with `IHttpClientFactory`:
- `iep-a49bb565` (brad-gardner/iep-advisor@a49bb565)
- `decloud-0b6bcec5` (bekirmfr/DeCloud.Orchestrator@0b6bcec5)
- `uksf-13f48b3b` (uksf/api@13f48b3b)
- `hazina-f2c7336d` (martiendejong/Hazina@f2c7336d, review of PR #286)
- `meshweaver-6333ae5f` (Systemorph/MeshWeaver@6333ae5f, a Copilot review)
- `einv-5c4cc98a` (madhanrao19/EINVWORLD@5c4cc98a, a production-readiness review)
- `dorc-8e847982` (sefe/dorc@8e847982, a cross-model review)
- Weak: `kioku-7a8f4310` (sandovaldavid/kioku@7a8f4310). It fixes a bug listed in a
  review document. It is counted only if a review document counts as a review round.

Source: https://learn.microsoft.com/en-us/dotnet/fundamentals/networking/http/httpclient-guidelines:
"If you don't use the factory and instead create a new client instance for each request
yourself, you can exhaust available ports." "If your app requires cookies, it's recommended
to avoid using IHttpClientFactory." "Unanticipated CookieContainer sharing might leak
cookies between unrelated parts of the application." "In .NET Framework, use
IHttpClientFactory to manage your HttpClient instances."

Public verdict: admitted on public stand-ins (7). That does not count under the owner's
decision.

## Research rules not built here

DOTNET-01 to DOTNET-20 are the owner's research ids. The spec's provisional re-count
over the owner's private repositories gives these counts: -01 2, -02 1, -03 0-1, -04 1,
-05 1, -06 1, -07 2, -08 3, -09 1, -10 2, -11 2, -12 1, -13 4, -14 2, -15 3, -16 1, -17 1,
-18 1, -19 2, -20 1. Their rule text was not available to this build, so none is
written here. DOTNET-08, -13 and -15 are the rules the spec expected to ship.

## Conventions (no id, no self-check row)

No review finding earned these, so they are conventions, not standards. Always use `var`
(the owner's rule). Prefer file-scoped namespaces, primary constructors, records for
data, no `#region`, and `IReadOnlyList<T>` for returned collections.
