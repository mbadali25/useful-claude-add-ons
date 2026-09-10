# Connecting, modules and preflight

Shared by `exchange-mailbox-cleanup` and `exchange-mailbox-restore`. Everything here is printed
for the operator to run in **their own Windows PowerShell 5.1 window**. Nothing here is run from a
tool call.

## The edition: Windows PowerShell 5.1, one blue icon

Decided 2026-09-10 by both PowerShell reviewers independently: **target Windows PowerShell 5.1
(`PSEdition = Desktop`)**, and keep every printed command inside the subset that also runs unchanged
on PowerShell 7.6+.

| Why 5.1 | |
|---|---|
| `ExchangeOnlineManagement` 3.10.1 manifest | *"Starting with this version of the module, the minimum required version of PowerShell 7 is now 7.6. Windows PowerShell 5.1 is not affected."* Pointing an operator at 7 adds a version floor they can silently fail; 5.1 adds none |
| Two machines, one icon | 5.1 is in-box on the operator's PC and on `AWSPRDINFAAD01`, so there is one blue icon to recognise |
| `ADSync` | Framework-only. Loads in 5.1, has no 7 build, regardless of anything else |

`scripts/exo_preflight.ps1` carries `#Requires -PSEdition Desktop`. Under pwsh it refuses with,
verbatim (tested under 7.6.5): `The script 'exo_preflight.ps1' cannot be run because it contained a
"#requires" statement for PowerShell editions 'Desktop'. The edition of PowerShell that is required
by the script does not match the currently running PowerShell Core edition.` That is the loud,
self-explaining failure a non-technical operator needs.

The first command printed in every session:

```powershell
$PSVersionTable.PSEdition
```

Expected `Desktop`. On `Core`, say exactly: *"Close this window. Open the Start menu, type Windows
PowerShell, and open the blue icon whose title bar says Windows PowerShell - not the one that says
PowerShell 7."* Do not check for `pwsh` at all - the skill never needs it and looking for it creates a
decision the operator can get wrong.

**The 5.1 subset, for every printed command:** no ternary, no `??` / `??=`, no `&&` / `||` pipeline
chains, no `ForEach-Object -Parallel`, no `-SkipCertificateCheck`, no `ConvertFrom-Json -AsHashtable`,
no null-conditional. A command that stays inside it runs on 7.6 too, so a paste into the wrong window
behaves instead of parse-failing. Nothing here uses `-UseWindowsPowerShell`; if it seems needed, stop
and raise it.

**The machine boundary** is the one confusing part. Say it at Step 6 and again at the sync step:
*"Every step runs in a blue Windows PowerShell window - on your own PC for everything except the
sync step, which you run in the same kind of window on the server AWSPRDINFAAD01 after connecting
with Remote Desktop, and then you come back."*

## Two Exchange sessions, not one

`ExchangeOnlineManagement` opens two different services, and the cmdlet you need lives in exactly
one of them. Say which session a cmdlet needs every time you print it.

| Connect with | Endpoint | Gets you |
|---|---|---|
| `Connect-ExchangeOnline` | `outlook.office365.com` | `Get-Mailbox`, `Set-Mailbox`, `Get-EXOMailbox`, `Get-MailboxStatistics`, `New-Mailbox`, `New-MailboxRestoreRequest`, `Add-MailboxPermission`, every `Litigation*` property, `-InactiveMailboxOnly`, `-SoftDeletedMailbox` |
| `Connect-IPPSSession` | `*.ps.compliance.protection.outlook.com` | `New-/Start-/Get-ComplianceSearch`, `*-ComplianceSearchAction`, `Get-/New-RetentionCompliancePolicy`, eDiscovery cases, `Add-eDiscoveryCaseAdmin`, the **Purview** `Get-RoleGroup` / `Add-RoleGroupMember` |
| `Connect-MgGraph` | `graph.microsoft.com` | `Get-MgUser`, `Remove-MgUser`, `Get-MgSubscribedSku`, `Get-MgUserLicenseDetail`, `Get-MgDirectoryDeletedItemAsUser`, `Restore-MgDirectoryDeletedItem` |

**`Get-Mailbox` does not exist in the IPPS session. `New-ComplianceSearch` does not exist in the
EXO session.** A "cmdlet not recognized" error after a successful connect almost always means the
wrong session.

**Name collision.** Both Exchange sessions export `Get-RoleGroup`, `Get-RoleGroupMember` and
`Add-RoleGroupMember`. With both connected, whichever connected **last** wins, silently. Connect
IPPS last, and re-run `Connect-IPPSSession` immediately before any role-group work
(`runbook-steps.md` Step 13) so the call lands in Purview and not in Exchange.

Remote PowerShell with `New-PSSession` against `outlook.office365.com` is retired and cannot be
made to work. Module v3 is REST-backed; use `Connect-ExchangeOnline`.

## Module order is load-bearing on PowerShell 5.1

Import Graph **before** ExchangeOnlineManagement. The other order breaks Graph under 5.1 with an
opaque `Connect-MgGraph` failure (both `Invoke-M365OffboardingHold.ps1` and
`Get-M365OffboardingStatus.ps1` document this at their import step). Print it in this order every
time:

```powershell
Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Users
Import-Module Microsoft.Graph.Identity.DirectoryManagement
Import-Module ExchangeOnlineManagement
```

## Modules and minimum versions

| Module | Minimum | Why |
|---|---|---|
| `ExchangeOnlineManagement` | **3.9.0** | `Connect-IPPSSession -EnableSearchOnlySession` did not exist earlier and `New-ComplianceSearch` fails at initialisation without it. `Test-MailboxPreservation.ps1 -RunComplianceSearch` requires it |
| `Microsoft.Graph.Authentication` | 2.x | `Connect-MgGraph`, `Get-MgContext` |
| `Microsoft.Graph.Users` | 2.x | `Get-MgUser`, `Remove-MgUser`, `Get-MgUserLicenseDetail` |
| `Microsoft.Graph.Identity.DirectoryManagement` | 2.x | `Get-MgSubscribedSku`, `Get-MgDirectoryDeletedItemAsUser`, `Restore-MgDirectoryDeletedItem` |
| `ADSync` | in-box on `AWSPRDINFAAD01` | **Windows PowerShell 5.1 only.** No PowerShell 7 build exists. Never installed; only present on the Entra Connect server |

`scripts/exo_preflight.ps1 -Check` reports all of these. `-Install` installs the missing ones after
one confirmation - it does not hand the operator a shopping list.

### Installing: under the user profile, TLS 1.2 first, verify after

The install path inside `exo_preflight.ps1 -Install`, in this order:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force
Install-Module ExchangeOnlineManagement -MinimumVersion 3.9.0 -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Authentication -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Users -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Identity.DirectoryManagement -Scope CurrentUser -Force -AllowClobber
Get-Module -ListAvailable ExchangeOnlineManagement, Microsoft.Graph.* | Select-Object Name, Version, ModuleBase
```

| Rule | Why |
|---|---|
| **TLS 1.2 first, always** | 5.1 negotiates TLS 1.0/1.1 and the Gallery has required 1.2 for years. Without it `Install-Module` dies with `Unable to resolve package source 'https://www.powershellgallery.com/api/v2'`, which reads like a network outage and is not |
| **NuGet provider bootstrapped** | This workstation's 5.1 ships `PowerShellGet` 1.0.0.1, the version that cannot reliably update itself; a fresh NuGet provider is what lets `Install-Module` proceed |
| **`-Scope CurrentUser`, never machine-wide** | A managed corporate workstation's operator very likely has no local admin. Machine-wide triggers a UAC prompt they cannot answer; per-user needs none and affects nobody else |
| **Sub-modules, not `Microsoft.Graph`** | The meta-module is huge and takes many minutes; the skill needs exactly three sub-modules. The operator is told each takes a few minutes so the pause does not read as a hang |
| **`-Force` per install, PSGallery policy untouched** | `Set-PSRepository -InstallationPolicy Trusted` is a persistent, profile-wide change. `-Force` on each call is the smaller footprint |
| **`-AllowClobber`** | The in-box `PowerShellGet` refuses to overwrite commands it thinks it owns |
| **Verify after** | `Install-Module` returning is not success. The script re-reads `Get-Module -ListAvailable` and shows `Name, Version, ModuleBase` |
| **Stop on first failure** | Verbatim error, no retry loop, no machine-wide fallback |
| **OneDrive check** | `-Scope CurrentUser` resolves under `Documents\WindowsPowerShell\Modules`; Known Folder Move often redirects `Documents` and a redirected module path makes imports slow or flaky in ways that look nothing like an install problem. Reported as `NOTICE`, never changed |

## The connect block

```powershell
$Admin = "admin@contoso.com"        # the operator's admin UPN - ask for it, do not guess
$Repo  = "C:\repos\solomon\infrastructure-scripts\Powershell\Exchange"
$Csv   = "C:\scripts\reports\holdlist.csv"
$Sku   = "SPE_E3"                   # the only SKU in this tenant that grants Exchange Online Plan 2
Set-Location $Repo

Import-Module Microsoft.Graph.Authentication
Import-Module Microsoft.Graph.Users
Import-Module Microsoft.Graph.Identity.DirectoryManagement
Import-Module ExchangeOnlineManagement

Connect-ExchangeOnline -UserPrincipalName $Admin -ShowBanner:$false
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
Connect-IPPSSession -UserPrincipalName $Admin
```

Good looks like: three prompts return with no red text, then

```powershell
Get-Mailbox -ResultSize 1 | Select-Object DisplayName        # EXO session alive
Get-MgContext | Select-Object Account, Scopes                 # Graph alive, scopes listed
Get-ConnectionInformation | Select-Object ConnectionUri, State, UserPrincipalName   # both EXO rows
```

### Graph scopes are the union of both runbooks (defect 4)

| Scope | Cleanup needs it for | Restore needs it for |
|---|---|---|
| `Organization.Read.All` | `Get-MgSubscribedSku` seat counts | - |
| `User.ReadWrite.All` | `Remove-MgUser`, `Get-MgUser -Property OnPremisesSyncEnabled` | `Restore-MgDirectoryDeletedItem`, `Get-MgUserLicenseDetail` |
| `Directory.AccessAsUser.All` | - | `Get-MgDirectoryDeletedItemAsUser` (Path 4) |
| `User.RevokeSessions.All` | `Invoke-M365OffboardingHold.ps1` revokes sign-in sessions | - |

Request all four once at Step 8. Re-consenting mid-run means a new `Connect-MgGraph`, which is a
new browser prompt for the operator.

### Auth modes

| Mode | When | How |
|---|---|---|
| Interactive (default) | Operator at a keyboard | `-UserPrincipalName $Admin`; a browser window opens |
| Device code | Browser window never appears, or opens behind everything | `Connect-MgGraph -UseDeviceCode`; the scripts take `-UseDeviceCode` |
| `-DisableWAM` | `Connect-ExchangeOnline` fails with `0x80070002` or a `NoNetwork` WAM error | `Connect-ExchangeOnline -UserPrincipalName $Admin -DisableWAM`; `New-EDiscoveryAccessGroup.ps1` takes `-DisableWAM` |
| Certificate / Managed Identity | Unattended runs only | Not for this walkthrough. `Connect-IPPSSession` has no managed-identity option at all |

## Reconnect after every script (defect 2)

`Invoke-M365OffboardingHold.ps1`, `Get-M365OffboardingStatus.ps1` and `Test-MailboxPreservation.ps1`
all end with `Disconnect-ExchangeOnline -Confirm:$false` in a `finally` block. They open their own
sessions with `-AdminUpn` and tear down **the operator's** session on the way out. Print this block
immediately after any of them finishes, before the next step:

```powershell
Connect-ExchangeOnline -UserPrincipalName $Admin -ShowBanner:$false
Connect-IPPSSession -UserPrincipalName $Admin
Get-Mailbox -ResultSize 1 | Select-Object DisplayName
```

`Connect-IPPSSession` intermittently fails with MSAL `0x80070002` in the seconds after a disconnect.
If it does, wait 20 seconds and run it again before trying `-DisableWAM`.

## Roles the operator must hold

| Role | Where | Needed for | Checked by |
|---|---|---|---|
| Exchange Administrator (or Global Administrator) | Entra directory role | `Set-Mailbox`, `New-Mailbox`, `Get-Mailbox -InactiveMailboxOnly` | `exo_preflight.ps1 -Roles` via `Get-MgUserMemberOf` |
| Compliance Administrator or Organization Management (Purview) | Purview role group | `Add-RoleGroupMember` in the IPPS session, `Add-eDiscoveryCaseAdmin` | `-Roles`, best effort |
| **eDiscovery Manager** | Purview role group `eDiscoveryManager` (DisplayName `eDiscovery Manager`) | `New-ComplianceSearch`, `Test-MailboxPreservation.ps1 -RunComplianceSearch` | `-Roles` resolves the group by lookup on Name **or** DisplayName and lists members |
| User Administrator (or Global Administrator) | Entra directory role | `Remove-MgUser`, `Restore-MgDirectoryDeletedItem` | `-Roles` |

**Global Administrator is not automatically an eDiscovery Manager.** The grant is explicit, and it
takes 30-60 minutes to reach the search back end. Until then every compliance search returns zero
items with no error - indistinguishable from an empty mailbox. There is nothing to debug; the fix is
waiting. Check propagation with the Purview portal diagnostic: **Help > search `Diag:edisRBACdiag` >
enter the UPN > Run Tests**.

**There is no role group named `eDiscovery Administrator`.** `Add-RoleGroupMember -Identity
"eDiscovery Administrator"` fails. Administrators are a *subgroup* of eDiscovery Manager, individual
users only, assigned with `Add-eDiscoveryCaseAdmin -User $Admin`.

## Directories

| Path | Holds | Created by |
|---|---|---|
| `C:\scripts\reports` | Normalised `holdlist.csv`, confirmation exports the skill writes | `exo_preflight.ps1 -Install` |
| `C:\scripts\logs` | Every script's `*.log` and `*.csv`, because every call passes `-LogPath 'C:\scripts\logs'` | `-Install` |
| `C:\scripts\log` | **Historic** output from runs before the skill existed. Never written to again | - |

The scripts default to `C:\scripts\log`. They are not modified. Pass `-LogPath 'C:\scripts\logs'`
on **every** call or the artifact lands where the skill will not look for it.

### Reading artifacts back: CSVs are UTF-8, logs are not

| File | Written with | Encoding under 5.1 | Read with |
|---|---|---|---|
| `*.csv` from the five scripts | `Export-Csv -Encoding UTF8` | UTF-8 **with BOM** | Read tool or `read_log.py`; `utf-8-sig` |
| `*.log` from the five scripts | `Add-Content -Path $logFile -Value $logEntry` - **no `-Encoding`** | ANSI code page (cp1252) | `scripts/read_log.py` - opens as bytes, tries `utf-8-sig`, falls back to `cp1252`, reports which won |
| Anything the operator made with `>` or `Out-File` | - | UTF-16LE | `read_log.py` detects the `FF FE` BOM; but never print `>` or `Out-File` in the first place |

No parameter the skill prints can change how the scripts write their logs; the fix lives in the
reader. Without it an accented display name, a smart quote pasted from a ticket, or an em dash comes
back as mojibake in the report - silently, with no error.

```powershell
python "$SkillDir\scripts\read_log.py" C:\scripts\logs\Invoke-M365OffboardingHold-20260910.log --tail 40
python "$SkillDir\scripts\read_log.py" C:\scripts\logs\Test-MailboxPreservation-20260910.log --grep unproven --json
```

Every ad hoc export the skill prints is the explicit form:
`... | Export-Csv -Path 'C:\scripts\reports\<name>.csv' -NoTypeInformation -Encoding UTF8`.

## Exit codes of `scripts/exo_preflight.ps1`

| Code | Meaning |
|---|---|
| 0 | Every check passed |
| 1 | At least one FAIL - read the report, fix that item, re-run |
| 2 | `SiblingSkillMissing` - `exchange-mailbox-restore` is not installed beside this skill. Install both |
| 3 | `-Roles` was asked but no live session was found - connect first, then re-run in the same window |

The report is also written to `C:\scripts\reports\exo-preflight-{yyyyMMddHHmm}.txt` (UTF-8) when
that directory exists, so it can be attached to the ticket.
