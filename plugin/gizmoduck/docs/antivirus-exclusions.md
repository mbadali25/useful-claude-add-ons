# Antivirus / EDR exclusions for the gizmoduck toolchain

Five of gizmoduck's nine scanners (nikto, sqlmap, ZAP, Nuclei, and trivy/checkov
when their template or policy libraries embed exploit content) are the same
category of software Microsoft Defender's HackTool family exists to catch. On
a machine running bootstrap.sh/bootstrap.ps1 tonight, Defender caught three of
them within minutes of install and deleted or quarantined the files before the
scanner ever ran:

- `HackTool:Perl/NiktoSanner.A` on `nikto.pl` (ThreatID `2147794255`)
- `HackTool:Python/SqlMap!AMTB` on `sqlmap.py`
- `Program:Java/Multiverze!rfn` on `ZAP_2.17.0_Crossplatform.zip` (ThreatID `453479`),
  caught mid-download at ~286MB
- ThreatID `2147959786` on a Nuclei template,
  `nuclei-templates\http\cves\2017\CVE-2017-12615.yaml`

Each of these looked, at the time, like a failed install - a script that
vanished, a zip that never finished. It wasn't. It was Defender doing exactly
what it's supposed to do. Nothing was actually lost: once the exclusions below
were applied, every file re-downloaded intact and stayed put. Quarantine was
empty by the end - Defender had deleted outright rather than held anything in
its vault, which is worth knowing before you go looking for a "restore" option.

## 1. Why these are correct detections, not false positives

Don't file these as bugs in your antivirus. Read the tools' own contents and
the detections make sense:

- **Nuclei's template library ships exploits, not just checks.** The template
  that tripped ThreatID `2147959786`, `CVE-2017-12615.yaml`, *is* a working
  proof-of-concept for a Tomcat remote-file-upload vulnerability - it's not a
  description of the bug, it's an HTTP request that exploits it. Thousands of
  the templates under `nuclei-templates/http/cves/` are the same shape. An EDR
  that fingerprints exploit payloads will keep flagging this directory as new
  CVE templates get added, forever - that's not noise, that's the product
  working.
- **nikto.pl and sqlmap.py are attack tools by design.** Nikto fingerprints
  and probes web servers for thousands of known-dangerous files, misconfigs,
  and outdated software the same way an attacker's recon phase would. sqlmap
  automates SQL injection exploitation, including extracting a database and, on
  the right target, popping a shell. Signature vendors classify both as
  hacktools because that's what they are when pointed at something you don't
  own.
- **The alternative is worse.** Someone who assumes their AV is "just being
  paranoid" and disables it wholesale, or excludes their entire user profile
  to make the red banners stop, has traded a narrow, understood blind spot for
  an unbounded one. Understand the tradeoff in section 5 before touching a
  single exclusion.

## 2. Per-tool exclusion table

| Tool | What gets flagged | Signature (if known) | Narrowest fix |
|---|---|---|---|
| Nuclei (engine) | Occasionally the binary itself, heuristically | - | Path exclusion on the install dir |
| Nuclei templates | CVE PoC templates, esp. RCE/upload chains | ThreatID `2147959786` (`CVE-2017-12615.yaml`) | Path exclusion on the templates dir |
| nikto | The script itself | `HackTool:Perl/NiktoSanner.A`, ThreatID `2147794255` | Path exclusion on the nikto dir + process exclusion for `nikto.pl`/`perl.exe` |
| sqlmap | The script itself | `HackTool:Python/SqlMap!AMTB` | Path exclusion on the sqlmap dir + process exclusion for `sqlmap.py` |
| OWASP ZAP | The release zip, mid-download | `Program:Java/Multiverze!rfn`, ThreatID `453479` | Path exclusion on the zap dir + process exclusion for `java.exe` |
| nmap | Occasionally, on some engines | - | Process exclusion for `nmap.exe` if it recurs |
| trivy | Rarely - its own binary or a scanned image layer | - | Process exclusion for `trivy.exe` if it recurs |
| testssl.sh | Rarely; a bash script probing TLS is low-signal for hacktool heuristics | - | Path exclusion on the testssl.sh dir as a precaution |
| checkov, dependency-check | Not observed tonight | - | No exclusion added unless it happens |

Only add rows you've actually hit. This table reflects what fired on one
machine, not a blanket "exclude everything gizmoduck touches" list.

## 3. Ready-to-run commands (Windows Defender, elevated PowerShell)

Run these from an elevated PowerShell prompt. They cover the paths and
processes that were actually needed tonight; drop any line for a tool you
haven't hit a detection on.

```powershell
# Path exclusions - one per tool install directory
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Programs\nuclei"
Add-MpPreference -ExclusionPath "$env:USERPROFILE\nuclei-templates"
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Programs\nikto"
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Programs\sqlmap"
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Programs\zap"
Add-MpPreference -ExclusionPath "$env:LOCALAPPDATA\Programs\testssl.sh"

# Process exclusions - the interpreters/binaries that execute the above
Add-MpPreference -ExclusionProcess "nuclei.exe"
Add-MpPreference -ExclusionProcess "nikto.pl"
Add-MpPreference -ExclusionProcess "perl.exe"
Add-MpPreference -ExclusionProcess "nmap.exe"
Add-MpPreference -ExclusionProcess "trivy.exe"
Add-MpPreference -ExclusionProcess "sqlmap.py"
Add-MpPreference -ExclusionProcess "java.exe"
```

Verify what's actually registered afterward:

```powershell
Get-MpPreference | Select-Object -ExpandProperty ExclusionPath
Get-MpPreference | Select-Object -ExpandProperty ExclusionProcess
```

A process exclusion for `perl.exe` and `java.exe` is broader than the others
on this list - both are general-purpose interpreters, not gizmoduck-specific
binaries. If that's too wide for your environment, drop those two rows and
rely on the path exclusions alone; nikto and ZAP still need to actually run
without Defender killing the process mid-scan, so test before assuming the
path exclusion alone is enough.

## 4. Other EDRs (CrowdStrike, SentinelOne, Defender for Endpoint)

None of this was tested against these products tonight - the detections above
are Defender-specific. But the shape of the request is the same everywhere:
a per-directory (and sometimes per-process) allowlist for the same tool paths
and binaries listed in section 2. The mechanism differs per product, and on a
managed endpoint you likely can't set any of this yourself:

- **CrowdStrike Falcon** - exclusions are configured server-side in the Falcon
  console (Prevention Policy → exclusion lists), not on the endpoint. There's
  a distinction between *detection* exclusions (stop Falcon from flagging the
  path) and *sensor visibility* exclusions (stop it from even monitoring the
  path) - ask for the former, not the latter, since you still want telemetry
  on what these tools do, you just don't want them quarantined.
- **SentinelOne** - exclusions live in the management console under
  Exclusions, scoped by path, file hash, certificate, or process, and can be
  attached to a specific policy/group rather than the whole fleet.
- **Microsoft Defender for Endpoint** (the managed, tenant-controlled version
  of Defender, as opposed to the local `Add-MpPreference` above) - exclusions
  are pushed via Intune or an ASR/AV configuration profile, and a local
  `Add-MpPreference` call is typically overridden or blocked entirely on an
  enrolled device by tenant policy.

If you're on a managed endpoint, `Add-MpPreference` above may silently no-op
or get reset on the next policy sync - check with IT before assuming a local
exclusion stuck.

## 5. Scoping warning - read this before adding anything above

An excluded path is a place malware can live unscanned and undetected. That's
the actual cost of every line in section 3, and it's a real cost, not a
formality:

- **Scope to the exact tool directory, never a drive root, never the whole
  user profile.** `%LOCALAPPDATA%\Programs\nuclei` is fine. `%LOCALAPPDATA%`
  is not.
- **Never exclude `%TEMP%`.** It's tempting because installers download
  through it, but `%TEMP%` is exactly where real malware lands and executes -
  excluding it blinds the AV to the most common drop location on the machine.
  If a bootstrap script downloads into `%TEMP%` before moving the tool to its
  final directory, that's a bug in the script's landing spot, not a reason to
  exclude `%TEMP%` - fix the script to download straight into the tool's own
  directory instead. `bootstrap.ps1`/`bootstrap.sh` no longer do this: every
  tool download now lands directly in (or next to) its install directory.
- **Process exclusions are broader than path exclusions** - excluding
  `perl.exe` or `java.exe` stops Defender from inspecting *anything* those
  interpreters run, not just nikto or ZAP. Prefer the path exclusion alone
  where it's sufficient, and only add the process exclusion if the scan still
  gets killed with the path exclusion in place.
- **Revisit periodically.** An exclusion added for one project shouldn't
  outlive the project. If gizmoduck stops being used on a machine, remove the
  exclusions (`Remove-MpPreference -ExclusionPath ...` / `-ExclusionProcess`).

## 6. Getting this approved on a managed device

Most people running this toolchain don't own the AV/EDR policy on their
workstation. The request to IT is straightforward and worth making directly
rather than working around:

- **These are industry-standard security-testing tools**, not custom or
  unknown binaries - Nuclei, nikto, sqlmap, and OWASP ZAP are widely used,
  open-source, and each has a public GitHub repo IT can check.
- **The exclusions are per-directory, not a policy-wide carve-out.** Point IT
  at section 3 - it's a short, specific list, not "turn off the antivirus."
- **Ask for it scoped to one workstation**, not a fleet-wide policy. A
  security-testing workstation has a different risk profile than every laptop
  in the org, and IT is much more likely to approve a narrow, named-device
  request than a change to the default endpoint policy.
- **Bring the detection names.** "Defender flagged nikto.pl as
  HackTool:Perl/NiktoSanner.A, which is correct - it's a hacktool - and I need
  a scoped exclusion to run it for authorized testing" is a request IT can act
  on quickly, versus "my install keeps failing," which reads as a support
  ticket, not a policy change.
