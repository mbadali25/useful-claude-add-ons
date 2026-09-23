---
name: stack-dotnet
description: |
  .NET-specific pitfalls, checks and verify.json wiring - DI lifetimes, async model, EF Core
  change tracking, plus a short .NET Framework 4.8 section for Web Forms/WCF legacy hosts. Use
  when the repo has *.csproj/*.sln files, or the user asks to write or review C#, wire up
  dependency injection, fix an EF Core query, or work on a service still targeting net48.
---

# Stack: .NET

## When this applies

Any repo with `*.csproj`/`*.sln`. Read the `.csproj` or `Directory.Build.props` first - the
`TargetFramework`, `LangVersion`, and whether `<Nullable>enable</Nullable>` is set decide what
the compiler will accept. `net48` is a different runtime with different rules (below); every
SDK-style target (`netcoreapp*`, `net5.0`+, `netstandard*`) uses the modern-.NET pitfalls.

## Pitfalls that cost time (modern .NET)

- **DI lifetimes are where the production-only bugs live.** A scoped service resolved from a
  singleton is a captive dependency - it lives as long as the singleton. `DbContext` is scoped
  for a reason; capturing one in a singleton or a hosted service that resolves at construction
  produces cross-request data and concurrency exceptions that never show in a single-request test.
- **`async void` is unobservable** - the exception cannot be caught by the caller and usually
  kills the process. `.Result`/`.Wait()` deadlock wherever a context is captured.
- **A `CancellationToken` accepted and not passed on is worse than none** - it advertises
  cancellation the call chain does not honour. Thread it through every async call, EF Core
  included.
- **EF Core's change tracker decides query cost.** A read materialised without `AsNoTracking()`
  holds every entity for the scope's life; lazy loading inside a loop is N+1 in a different
  costume, and with lazy loading off the same code silently reads `null` instead.
- **`.Where()` after materialisation filters in memory** over everything the database already
  sent - `IEnumerable` vs `IQueryable` decides where the work happens.
- **`HttpClient`**: a new instance per call exhausts sockets; a static one held forever pins
  connections past a DNS change. `IHttpClientFactory`, or a long-lived client with
  `PooledConnectionLifetime` set - pick one and say which the repo already uses.
- **A connection string in a committed `appsettings.json` is a finding**, not a convenience.

## .NET Framework 4.8 (legacy)

A different runtime, not an old version of the one above - Web Forms, WCF, `System.Web`, the
GAC, COM interop, and anything that only runs on Windows. Language is capped at **C# 7.3**: no
records, no nullable reference types, no `async` streams, no target-typed `new`. Entity
Framework here is **EF6**, not EF Core - Code First/Database First/Model First, a different
migrations story, and no `AsNoTracking()`-vs-tracking split the same way. A `.csproj` with
`TargetFramework` (singular) rather than `TargetFrameworks`, or a `<TargetFrameworkVersion>`
in the old non-SDK project format, is the tell. WCF service contracts and Web Forms page
lifecycle/ViewState are the two places most maintenance time goes; treat both as stable
surfaces to patch, not to modernise inline with a feature change.

## Verification

Run `dotnet build` and `dotnet test`, report exit codes (never the summary line), and check
`TreatWarningsAsErrors` before assuming a build that printed warnings passed. Say which test
actually exercised an async/DI/EF change - a test that constructs the service directly proves
nothing about how the container builds it.

## verify.json rule to propose

```json
{
  "paths": ["**/*.cs", "**/*.csproj"],
  "run": [
    "sh -c 'command -v dotnet >/dev/null 2>&1 || { echo \"TOOL MISSING: dotnet SDK is not on PATH, so dotnet format DID NOT RUN. This is a missing tool, not a passing or failing check. Install the .NET SDK to check locally.\" >&2; exit 77; }; dotnet format --verify-no-changes'"
  ],
  "reach": "local",
  "why": "dotnet format --verify-no-changes catches style drift without mutating the tree"
}
```

Nothing in this repo writes rules into `verify.json` on a skill's behalf (see the
`crew-verification` skill) - add this by hand, and prefer `dotnet build`/`dotnet test` rules
already present in the repo over duplicating them here.

## LSP

Use the official C# LSP plugin (decided for crew 1.0) rather than Serena, which was evaluated
and skipped for this stack.
