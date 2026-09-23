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
GAC, COM interop, and anything that only runs on Windows. **`LangVersion` defaults to 7.3 on
net48, not a hard cap** - it is a compiler setting, not a runtime one; an explicit newer
`LangVersion` with a current Roslyn compiler accepts newer syntax, but only where nothing it
needs is missing from the older BCL (records need `init` accessors, which need
`System.Runtime.CompilerServices.IsExternalInit` - absent from net48 and has to be hand-added
as a shim; a feature needing a newer runtime type, not just newer syntax, still cannot work no
matter what `LangVersion` says). Entity Framework here is **EF6**, not EF Core - Code
First/Database First/Model First and a different migrations story. EF6 does have
`AsNoTracking()` and a change tracker of its own; the difference from EF Core is in the
details (proxy-based lazy loading via dynamic subclasses, `DbSet.Find()` behaviour), not in
tracking being absent. A `.csproj` with `TargetFramework` (singular) rather than
`TargetFrameworks`, or a `<TargetFrameworkVersion>` in the old non-SDK project format, is the
tell. WCF service contracts and Web Forms page lifecycle/ViewState are the two places most
maintenance time goes; treat both as stable surfaces to patch, not to modernise inline with a
feature change.

## Verification

Run `dotnet build` and `dotnet test`, report exit codes (never the summary line), and check
`TreatWarningsAsErrors` before assuming a build that printed warnings passed. Say which test
actually exercised an async/DI/EF change - a test that constructs the service directly proves
nothing about how the container builds it.

## verify.json rule to propose

```json
{
  "paths": [
    "**/*.cs", "**/*.csproj", "**/*.sln", "**/*.targets",
    "**/.editorconfig", "**/Directory.Build.props"
  ],
  "run": [
    "sh -c 'command -v dotnet >/dev/null 2>&1 || { echo \"TOOL MISSING: dotnet SDK is not on PATH, so dotnet format DID NOT RUN. This is a missing tool, not a passing or failing check. Install the .NET SDK to check locally.\" >&2; exit 77; }; dotnet format --help >/dev/null 2>&1 || { echo \"TOOL MISSING: this dotnet SDK has no format subcommand (SDK too old - dotnet format needs the 6.0+ SDK), so dotnet format DID NOT RUN.\" >&2; exit 77; }; dotnet format --verify-no-changes'"
  ],
  "reach": "local",
  "why": "dotnet format --verify-no-changes catches style drift without mutating the tree; the config-file paths are included because they change format's output without touching a .cs file, so a rule keyed on source alone would miss them"
}
```

`command -v dotnet` only proves the host, not the subcommand - a pre-6.0 SDK has `dotnet` but no
built-in `format`, and would otherwise fail as an ordinary error rather than this repo's UNVERIFIED
77. `dotnet format --help` probes the subcommand itself (every dotnet CLI verb supports `-h`/
`--help`; `--version` is not guaranteed on a subcommand the way it is on `dotnet` itself) before
relying on it.

Nothing in this repo writes rules into `verify.json` on a skill's behalf (see the
`crew-verification` skill) - add this by hand, and prefer `dotnet build`/`dotnet test` rules
already present in the repo over duplicating them here.

## LSP

Use the official C# LSP plugin (decided for crew 1.0) rather than Serena, which was evaluated
and skipped for this stack.
