# PowerShell candidate standards (not gated)

The gated PowerShell set is `crew-standards/references/powershell.md`, set `PWSH`. It holds
PWSH-16, the command-resolution half of that research rule. Nothing in this file is loaded by
`crew_standards.py` or asked in the self-check. There are three ways forward. An ordinary
candidate is promoted into the set once three distinct reviewed change sets earn it. PWSH-04
keeps its id. PWSH-P1, -P2 and -P3 are public-pass labels that the loader cannot read
(`[A-Z]{2,6}-\d{2}`), so on promotion each takes its research id once the owner's file maps
it, or else the next unused `PWSH-NN`. The StrictMode half joins the shipped PWSH-16 as an
amendment if three change sets earn that half. PWSH-20 never enters the plugin set: it is
overlay material and needs the owner's approval of a proposal. `PWSH-NN` is the owner's research
`POWERSHELL-NN`. The set name is `PWSH` because the loader takes 2-6 capitals.

**Counting.** The rule is `python.md`'s: a crew review, or a fix commit whose own message or
CHANGELOG entry records that a review found the defect. Commits of one review series or one
PR count once. One change set may count toward several rules. The owner decided on 2026-10-05
that public third-party change sets do not count, so only this repository's reviews are
counted below. Public change sets from a cloud research pass on 2026-10-05 (commit-search
message text only, diffs not read) are recorded as leads. This repository's CHANGELOG was
sampled by keyword (`LASTEXITCODE`, `Get-Command`, `-like`, `ConvertFrom-Json`, encoding),
not read in full, and the owner's private repositories were not available. A count here is
therefore a floor. `PWSH-Pn` are labels from the public pass, not research ids. Sources were
string-matched against the raw learn.microsoft.com page (`view=powershell-7.5`) on
2026-10-05.

## Candidate standards (not gated)

### PWSH-P1 Check a native command's exit status explicitly, and treat `$null` as failure

Counted: 1 (crew-0.19.92). 6 public change sets, which do not count.

After every native command whose outcome matters, read `$LASTEXITCODE` immediately: not
after a cmdlet, `Invoke-Expression`, or a pipeline that may have closed early. Reset it before
a sequence that relies on it. Treat `$null` as failure, because it means the program never
ran, and `exit $LASTEXITCODE` on `$null` exits 0. `try`/`catch` does not observe a native
non-zero exit, so check it as well.

- crew-0.19.92 (PR #200), BLOCK: "a launch failure ... left `$LASTEXITCODE` `$null`, and
  `exit $LASTEXITCODE` on a `$null` value silently evaluates to 0".
- Public leads: Reddimus/kettle@b5ca4b4c, applicate2628/Orchestrarium@72df1140,
  kobolingfeng/deepseek-desktop@1e004603, AKCodez/seo-god@154b4ed1,
  bolin8017/env-setup@e82554ce and NekoBend/den@ff19332e. Each message records a review that
  found an unchecked or `$null` exit status.

Source: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_automatic_variables?view=powershell-7.5:
"$LASTEXITCODE Contains the exit code of the last native program or PowerShell script that
ran." "For native commands (executables), $? is set to True when $LASTEXITCODE is 0, and set
to False when $LASTEXITCODE is any other value."

### PWSH-P2 Match data literally: no `-like` or `-match` with a data value as the pattern

Counted: 1. L-1503 and #407 round 4 come from one review of #407, and whether they are one
review series or two could not be determined, so they count once together. 1 public change
set, which does not count.

When the "pattern" is data (a command line, a filter entry, a path), compare literally with
`.Contains()`, `.StartsWith()`, `-eq` or `-LiteralPath`, or escape it with
`[WildcardPattern]::Escape()` or `[regex]::Escape()`. A comparison that can throw (an invalid
wildcard range) fails closed and never skips.

- L-1503 (crew 1.0.342), found reviewing #407: `promote-gate.ps1` picked the environment with
  `$cmd -like "*$dep*"`, and `-like` reads `*`, `?` and `[set]`.
- #407 round 4 FIX (crew 1.0.348): a `[!-[]` deploy string, a range that `-like` threw on, is
  now literal text.
- Public lead: bolin8017/env-setup@e82554ce.

Source: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_comparison_operators?view=powershell-7.5:
"-like and -notlike behave similarly to -eq and -ne, but the right-hand side could be a string
containing wildcards."

### PWSH-P3 Force a collection where a collection is meant (`@()`, or `-NoEnumerate` on 7)

Counted: unknown. crew 1.0.153's review round 1 includes a 5.1 `ConvertFrom-Json`
array-unrolling fix, but whether the review itself found that defect could not be determined.
1 public change set, which does not count.

Wrap any value whose `.Count`, indexing or emptiness matters in `@(...)`, after assignment on
5.1. Expect 5.1's `ConvertFrom-Json` to emit an array as one object, and an empty JSON array
to unroll to `$null`. Windows PowerShell 5.1's `ConvertFrom-Json` has no `-NoEnumerate`
(it is a PowerShell 7 parameter), so on 5.1 assign the result first and then wrap it in `@()`.

Source: https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_pipelines?view=powershell-7.5:
"When executing a pipeline, PowerShell automatically enumerates any type that implements the
IEnumerable interface or its generic counterpart." The `ConvertFrom-Json` page, on
`-NoEnumerate`: "Setting this parameter causes arrays to be sent as a single object instead of
sending every element separately."

### PWSH-04 Decode and encode bytes explicitly at every native-process boundary (research id inferred)

Counted: 1 (crew-0.19.92, BLOCK: stdin read with `[Console]::In.ReadToEnd()` decoded through
the OEM codepage).

Read raw bytes, strip a BOM, and decode as UTF-8 explicitly. Set
`[Console]::OutputEncoding` and `$OutputEncoding` before piping to a native program. This
standard does not assert 5.1's redirection default, because the documentation pages
contradict each other and no 5.1 host was measured. A file is written with a BOM only when it
holds a non-ASCII byte (direction: BOM-when-non-ASCII). This repository's `.ps1` files are all
ASCII-only and pass that as they are.

Source: about_Preference_Variables: "$OutputEncoding Determines the character encoding method
that PowerShell uses when piping data into native applications." about_Character_Encoding:
"PowerShell (v6 and higher) defaults to utf8NoBOM for all text output."

### PWSH-16, `Set-StrictMode` half (documentation only)

Counted: 0. The research's PWSH-16 also asks for `Set-StrictMode`, but no change set earned
that half, so no gated rule requires it. The command-resolution half is in the set.

### PWSH-20 Code that reads PowerShell uses PowerShell's parser (overlay material)

Not a plugin candidate. Its code is `.py`, which a `.ps1` glob never applies to, and the
overlay takes a standard only after the owner approves a proposal. This repository's CHANGELOG
records several guard review rounds of this kind (for example "Second review of #347").

## Not assessed

PWSH-01 to -03, -05 to -15 and -17 to -19 are the owner's research ids. Their text was not
available to this build. The spec names PWSH-07, -10, -11 and -19 as the best supported,
reaching two change sets, or three if commits of one series count separately. Whether PWSH-P1,
-P2 or -P3 is one of them could not be determined.
