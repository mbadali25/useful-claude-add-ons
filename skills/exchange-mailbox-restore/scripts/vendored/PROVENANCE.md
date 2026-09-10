# Vendored driver script - provenance (exchange-mailbox-restore copy)

This directory holds a **byte-for-byte copy** of the one upstream script the restore walkthrough
runs, so the skill works with no clone of `infrastructure-scripts` and no other skill installed. It
is not forked: nothing is reformatted, "improved" or patched. The walkthrough works *around* its
behaviour (it calls `Disconnect-ExchangeOnline` in a `finally` block and tears down the operator's
session; Step 0 prints a reconnect rather than editing the script).

**Two copies of this script now exist**, here and in `exchange-mailbox-cleanup/scripts/vendored/`.
Both trace to the same upstream commit below and carry the same SHA-256. They are independent
installs by design (the marketplace gives every plugin its own cache), so drift between them is
possible; the hash in each manifest is what makes it detectable. When re-syncing, re-sync both.

## Copied at

| Field | Value |
|---|---|
| Source repository | `infrastructure-scripts` (Bitbucket Cloud, `solomonassociatessdlc/infrastructure-scripts`) |
| Source directory | `Powershell/Exchange/` |
| Upstream commit | `5c0cee15c56493020ff16a08300bbbfc1d256b96` |
| Working tree at copy | clean for `Powershell/Exchange/` (`git status --short` empty) |
| Copy date | 2026-09-10 |
| Verified | `cmp` byte-identical to upstream and to the `exchange-mailbox-cleanup` copy at copy time |

## Manifest

`exo_preflight.ps1 -Check` reads this table - it is the list of bundled scripts as well as their
hashes - runs `Get-FileHash -Algorithm SHA256` on each, and reports `NOTICE DriverScriptModified` on
a mismatch or `FAIL DriverScriptMissing` if the file is absent. Keep the table shape: the script
matches a row by the `.ps1` name in the first cell and the 64-hex SHA-256 in the last cell.

| Script | Source path | Bytes | SHA-256 |
|---|---|---|---|
| `Test-MailboxPreservation.ps1` | `Powershell/Exchange/Test-MailboxPreservation.ps1` | 48570 | `e987966c999413dee24ac2bdf003aee51d432965c2507a81ff16a99a0653d611` |

Byte counts and hashes are of the file as checked out on Windows with `core.autocrlf=true` (CRLF
line endings). A checkout with LF endings produces a different hash for identical content; if
`-Check` reports the script modified on a fresh clone, compare line endings before suspecting
tampering.

Only this script is vendored here because it is the only driver `references/runbook-paths.md` ever
invokes (Step 0 triage). The cleanup skill's five other drivers are not needed for any restore path
and are deliberately not duplicated.

## Upstream may have moved on

This copy is a snapshot. Upstream fixes do **not** arrive here on their own. To check for drift:

```powershell
git -C <clone of infrastructure-scripts> log --oneline 5c0cee15c56493020ff16a08300bbbfc1d256b96..HEAD -- Powershell/Exchange/Test-MailboxPreservation.ps1
```

To re-sync, from a clean clone at the commit you want:

1. Copy the file byte-for-byte over the one here **and** over the copy in
   `exchange-mailbox-cleanup/scripts/vendored/` (`Copy-Item`, no editor in between).
2. Re-run `Get-FileHash -Algorithm SHA256` and `(Get-Item).Length`; update this table and the
   cleanup copy's table, plus the upstream commit and copy date in both.
3. Re-read `references/hold-and-mailbox-states.md` ("verdicts") against the new copy - a renamed
   column or verdict means a printed command or a "good looks like" is now wrong.
4. Run `exo_preflight.ps1 -Check` in both skills and confirm the driver script row reports `PASS`.

Never edit a vendored file in place. If it needs a change, make it upstream and re-sync.
