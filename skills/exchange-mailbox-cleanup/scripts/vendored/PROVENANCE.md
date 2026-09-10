# Vendored driver scripts - provenance

The six `.ps1` files in this directory are **byte-for-byte copies** of upstream code. They are
bundled so the two Exchange operator skills work with no clone of `infrastructure-scripts` on the
operator's machine. They are not forked: nothing here is reformatted, "improved", or patched. The
skill works *around* their behaviour (for example, every one of the first three calls
`Disconnect-ExchangeOnline` in a `finally` block and tears down the operator's session - the
walkthrough prints a reconnect after each rather than editing the script).

`Export-Terminated-Mailbox-to-PST.ps1` is deliberately **not** vendored. Upstream marks it
deprecated and it throws on execution; the skills refuse to reference it as a working option.

## Copied at

| Field | Value |
|---|---|
| Source repository | `infrastructure-scripts` (Bitbucket Cloud, `solomonassociatessdlc/infrastructure-scripts`) |
| Source directory | `Powershell/Exchange/` |
| Upstream commit | `5c0cee15c56493020ff16a08300bbbfc1d256b96` |
| Working tree at copy | clean for `Powershell/Exchange/` (`git status --short` empty) |
| Copy date | 2026-09-10 |
| Verified | `cmp` byte-identical for all six at copy time |

## Manifest

`exo_preflight.ps1 -Check` reads this table, hashes each file with `Get-FileHash -Algorithm SHA256`,
and reports `NOTICE DriverScriptModified` for any mismatch. Keep the table shape: the script matches
a row by the `.ps1` name in the first cell and the 64-hex SHA-256 in the last cell.

| Script | Source path | Bytes | SHA-256 |
|---|---|---|---|
| `Invoke-M365OffboardingHold.ps1` | `Powershell/Exchange/Invoke-M365OffboardingHold.ps1` | 96383 | `18b2cd7be9a3fb5ce921bf59e6717cb73893e6615a8c4e7d0d937d50bfe63bab` |
| `Get-M365OffboardingStatus.ps1` | `Powershell/Exchange/Get-M365OffboardingStatus.ps1` | 45323 | `58e9674568d3a0f6cac47f7a5875f8685892d73d34a0b1890a9c56646c60d54c` |
| `Test-MailboxPreservation.ps1` | `Powershell/Exchange/Test-MailboxPreservation.ps1` | 48570 | `e987966c999413dee24ac2bdf003aee51d432965c2507a81ff16a99a0653d611` |
| `New-EDiscoveryAccessGroup.ps1` | `Powershell/Exchange/New-EDiscoveryAccessGroup.ps1` | 53827 | `6dd8c08f0c331f950819fb73d63daf6e8e330d6580a4ac9c77b5d6d19e5958ae` |
| `Get-SharedMailboxInventory.ps1` | `Powershell/Exchange/Get-SharedMailboxInventory.ps1` | 67381 | `2a9aa8fc6069fefeb20514f1787edaf12135f5582cbf717617e489782418125a` |
| `Split-MailboxCleanupReports.ps1` | `Powershell/Exchange/Split-MailboxCleanupReports.ps1` | 36135 | `e8b74bbbd1e4c536a56398e677a2bef6fdf292f0327f7eb69f30ddce2c4a344d` |

Byte counts and hashes are of the files as checked out on Windows with `core.autocrlf=true`
(CRLF line endings). A checkout with LF endings produces different hashes for identical content;
if `-Check` reports every script modified at once, compare line endings before suspecting tampering.

## Upstream may have moved on

This copy is a snapshot. Upstream fixes - and there are known defects the skills work around (see
"Six runbook defects" in `SKILL.md`) - do **not** arrive here on their own.

To check for drift:

```powershell
git -C <clone of infrastructure-scripts> log --oneline 5c0cee15c56493020ff16a08300bbbfc1d256b96..HEAD -- Powershell/Exchange
```

To re-sync, from a clean clone at the commit you want:

1. Copy the six files byte-for-byte over the ones here (`Copy-Item`, no editor in between).
2. Re-run `Get-FileHash -Algorithm SHA256 *.ps1` and `(Get-Item *.ps1).Length` and update the
   manifest table above, plus the upstream commit and copy date.
3. Re-read `SKILL.md`'s "Six runbook defects" and the reconnect steps in
   `references/runbook-steps.md` against the new copies - a fixed upstream defect means a
   workaround here can be retired, and a new parameter or renamed column means a printed command
   is now wrong.
4. Run `exo_preflight.ps1 -Check` and confirm every driver script row reports `PASS`.

Never edit a vendored file in place. If one needs a change, make it upstream and re-sync.
