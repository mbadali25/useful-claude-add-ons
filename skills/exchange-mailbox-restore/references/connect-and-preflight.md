# Connecting, modules and preflight

Identical copies of this file ship in `exchange-mailbox-cleanup` and `exchange-mailbox-restore`
(each skill is standalone; change both). Cleanup step numbers are "Step n", restore's are "Sn"
and "Path n". Everything here is printed
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
Import-Module Microsoft.Graph.Authentication -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Users -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Users.Actions -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Identity.DirectoryManagement -RequiredVersion 2.39.0
Import-Module ExchangeOnlineManagement
```

`-RequiredVersion 2.39.0` on the four Graph lines is not optional. The driver scripts run **inside the
operator's window** and import Graph with `-RequiredVersion 2.39.0`
(`Invoke-M365OffboardingHold.ps1`: `$GraphModuleVersion = '2.39.0'`). If the operator's own imports
loaded a different version first, the driver hits a strong-name binding conflict that reads like a
corrupt install, and by design stops with *"Close this PowerShell session, open a new one, and re-run
exactly the same command"* - losing all three interactive logins. Pin the operator's imports to the
same version and the conflict cannot arise.

## Modules and versions

| Module | Version | Why |
|---|---|---|
| `ExchangeOnlineManagement` | **3.9.0 or later** | `Connect-IPPSSession -EnableSearchOnlySession` did not exist earlier and `New-ComplianceSearch` fails at initialisation without it. `Test-MailboxPreservation.ps1 -RunComplianceSearch` requires it |
| `Microsoft.Graph.Authentication` | **exactly 2.39.0** | `Connect-MgGraph`, `Get-MgContext` |
| `Microsoft.Graph.Users` | **exactly 2.39.0** | `Get-MgUser`, `Remove-MgUser`, `Get-MgUserLicenseDetail`, `Get-MgUserMemberOf` |
| `Microsoft.Graph.Users.Actions` | **exactly 2.39.0** | `Revoke-MgUserSignInSession` - `Invoke-M365OffboardingHold.ps1` revokes the leaver's sessions. Missing from both printed runbooks; the driver installs it mid-run and then demands a restart |
| `Microsoft.Graph.Identity.DirectoryManagement` | **exactly 2.39.0** | `Get-MgSubscribedSku`, `Get-MgDirectoryDeletedItemAsUser`, `Restore-MgDirectoryDeletedItem` |
| `ADSync` | in-box on `AWSPRDINFAAD01` | **Windows PowerShell 5.1 only.** No PowerShell 7 build exists. Never installed; only present on the Entra Connect server |

**Why the exact pin, and why it must happen before any login.** The drivers import
`-RequiredVersion 2.39.0` and refuse to proceed with another Graph version loaded. Without the
preflight, the sequence is: three interactive logins at Steps 7-9, then Step 16 installs 2.39.0
in-session and throws by design, and every login is lost. `exo_preflight.ps1 -Check` reports each of
the four at exactly 2.39.0 (a newer-only install is a `FAIL`, not a pass) and `-Install` adds 2.39.0
side by side with `-RequiredVersion`. Both print, before it happens: *"If a PowerShell window is
already open on this PC with a Microsoft Graph module loaded, close it and open a fresh blue Windows
PowerShell window before signing in. Nothing is lost - you have not signed in to anything yet."*
**Never widen the pin in the vendored script** - that breaks the byte-identical provenance contract.

`scripts/exo_preflight.ps1 -Check` reports all of these. `-Install` installs the missing ones after
one confirmation - it does not hand the operator a shopping list.

### Installing: under the user profile, TLS 1.2 first, verify after

The install path inside `exo_preflight.ps1 -Install`, in this order:

```powershell
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force
Install-Module ExchangeOnlineManagement -MinimumVersion 3.9.0 -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Authentication -RequiredVersion 2.39.0 -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Users -RequiredVersion 2.39.0 -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Users.Actions -RequiredVersion 2.39.0 -Scope CurrentUser -Force -AllowClobber
Install-Module Microsoft.Graph.Identity.DirectoryManagement -RequiredVersion 2.39.0 -Scope CurrentUser -Force -AllowClobber
Get-Module -ListAvailable ExchangeOnlineManagement, Microsoft.Graph.* | Select-Object Name, Version, ModuleBase
```

| Rule | Why |
|---|---|
| **TLS 1.2 first, always** | 5.1 negotiates TLS 1.0/1.1 and the Gallery has required 1.2 for years. Without it `Install-Module` dies with `Unable to resolve package source 'https://www.powershellgallery.com/api/v2'`, which reads like a network outage and is not |
| **NuGet provider bootstrapped** | This workstation's 5.1 ships `PowerShellGet` 1.0.0.1, the version that cannot reliably update itself; a fresh NuGet provider is what lets `Install-Module` proceed |
| **`-Scope CurrentUser`, never machine-wide** | A managed corporate workstation's operator very likely has no local admin. Machine-wide triggers a UAC prompt they cannot answer; per-user needs none and affects nobody else |
| **Sub-modules, not `Microsoft.Graph`** | The meta-module is huge and takes many minutes; the skill needs exactly four sub-modules, each pinned `-RequiredVersion 2.39.0`. The operator is told each takes a few minutes so the pause does not read as a hang |
| **Install before any login** | A Graph version change may need a fresh window. Done at Step 5, before Steps 7-9, that restart costs nothing; done by the driver at Step 16 it costs three logins |
| **`-Force` per install, PSGallery policy untouched** | `Set-PSRepository -InstallationPolicy Trusted` is a persistent, profile-wide change. `-Force` on each call is the smaller footprint |
| **`-AllowClobber`** | The in-box `PowerShellGet` refuses to overwrite commands it thinks it owns |
| **Verify after** | `Install-Module` returning is not success. The script re-reads `Get-Module -ListAvailable` and shows `Name, Version, ModuleBase` |
| **Stop on first failure** | Verbatim error, no retry loop, no machine-wide fallback |
| **OneDrive check** | `-Scope CurrentUser` resolves under `Documents\WindowsPowerShell\Modules`; Known Folder Move often redirects `Documents` and a redirected module path makes imports slow or flaky in ways that look nothing like an install problem. Reported as `NOTICE`, never changed |

## The connect block

```powershell
Import-Module Microsoft.Graph.Authentication -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Users -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Users.Actions -RequiredVersion 2.39.0
Import-Module Microsoft.Graph.Identity.DirectoryManagement -RequiredVersion 2.39.0
Import-Module ExchangeOnlineManagement

Connect-ExchangeOnline -UserPrincipalName '{Admin}' -ShowBanner:$false
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
Connect-IPPSSession -UserPrincipalName '{Admin}'
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
| Interactive (default) | Operator at a keyboard | `-UserPrincipalName '{Admin}'`; a browser window opens |
| Device code | Browser window never appears, or opens behind everything | `Connect-MgGraph -UseDeviceCode`; the scripts take `-UseDeviceCode` |
| `-DisableWAM` | `Connect-ExchangeOnline` fails with `0x80070002` or a `NoNetwork` WAM error | `Connect-ExchangeOnline -UserPrincipalName '{Admin}' -DisableWAM`; `New-EDiscoveryAccessGroup.ps1` takes `-DisableWAM` |
| Certificate / Managed Identity | Unattended runs only | Not for this walkthrough. `Connect-IPPSSession` has no managed-identity option at all |

## Reconnect after every script (defect 2)

`Invoke-M365OffboardingHold.ps1`, `Get-M365OffboardingStatus.ps1` and `Test-MailboxPreservation.ps1`
all end with `Disconnect-ExchangeOnline -Confirm:$false` in a `finally` block, and the first two
also call `Disconnect-MgGraph` there (`Invoke-M365OffboardingHold.ps1:1887`,
`Get-M365OffboardingStatus.ps1:941`). They open their own sessions with `-AdminUpn` and tear down
**the operator's** sessions - all three - on the way out. Print this block immediately after any of
them finishes, before the next step. Omitting the Graph line is how Step 27's
`Get-MgUser -Property OnPremisesSyncEnabled` - the check that decides on-prem versus cloud deletion -
fails with an auth error in the middle of Phase C:

```powershell
Connect-ExchangeOnline -UserPrincipalName '{Admin}' -ShowBanner:$false
Connect-IPPSSession -UserPrincipalName '{Admin}'
Connect-MgGraph -Scopes 'Organization.Read.All','User.ReadWrite.All','Directory.AccessAsUser.All','User.RevokeSessions.All' -NoWelcome
Get-Mailbox -ResultSize 1 | Select-Object DisplayName
Get-MgContext | Select-Object Account
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
users only, assigned with `Add-eDiscoveryCaseAdmin -User '{Admin}'`.

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
| `*.csv` from the five scripts | `Export-Csv -Encoding UTF8` | UTF-8 **with BOM** | Read tool or `Read-ScriptLog.ps1` |
| `*.log` from the five scripts | `Add-Content -Path $logFile -Value $logEntry` - **no `-Encoding`** | ANSI code page (cp1252) | `scripts/Read-ScriptLog.ps1` - reads bytes, tries UTF-16 BOM, strict UTF-8, BOM-less UTF-16, then `cp1252`; reports which won |
| Anything the operator made with `>` or `Out-File` | - | UTF-16LE | `Read-ScriptLog.ps1` detects the `FF FE` BOM; but never print `>` or `Out-File` in the first place |

No parameter the skill prints can change how the scripts write their logs; the fix lives in the
reader. Without it an accented display name, a smart quote pasted from a ticket, or an em dash comes
back as mojibake in the report - silently, with no error.

```powershell
powershell.exe -NoProfile -File "{SkillDir}\scripts\Read-ScriptLog.ps1" -Path C:\scripts\logs\Invoke-M365OffboardingHold-20260910.log -Tail 40
powershell.exe -NoProfile -File "{SkillDir}\scripts\Read-ScriptLog.ps1" -Path C:\scripts\logs\Test-MailboxPreservation-20260910.log -Grep unproven -AsJson
```

Windows PowerShell 5.1 only - nothing else is guaranteed on a corporate workstation. `read_log.py`
and `parse_user_input.py` remain in `scripts/` as the reference implementations but no step depends
on them.

Every ad hoc export the skill prints is the explicit form:
`... | Export-Csv -Path 'C:\scripts\reports\{Name}.csv' -NoTypeInformation -Encoding UTF8`.

## Exit codes of `scripts/exo_preflight.ps1`

| Code | Meaning |
|---|---|
| 0 | Every check passed |
| 1 | At least one FAIL - read the report, fix that item, re-run |
| 2 | `ProvenanceMissing` - `scripts\vendored\PROVENANCE.md` is absent or empty, so the bundled scripts cannot be listed or verified. Reinstall the skill |
| 3 | `-Roles` was asked but no live session was found - connect first, then re-run in the same window |

The report is also written to `C:\scripts\reports\exo-preflight-{yyyyMMddHHmm}.txt` (UTF-8) when
that directory exists, so it can be attached to the ticket.
