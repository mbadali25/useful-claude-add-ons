# Apps: Win32/LOB deployment and troubleshooting

Base: `deviceAppManagement/mobileApps` (note: **not** `deviceManagement`).

## Listing apps

Everything under `mobileApps` is polymorphic — `@odata.type` determines the shape:
`win32LobApp`, `windowsMobileMSI`, `officeSuiteApp`, `iosStoreApp`, `androidManagedStoreApp`,
`macOSPkgApp`, `winGetApp`.

```bash
python scripts/graph.py GET "deviceAppManagement/mobileApps" \
  --select "id,displayName,publisher,createdDateTime" --top 50

# Win32 only — cast filter
python scripts/graph.py GET "deviceAppManagement/mobileApps" \
  --filter "isof('microsoft.graph.win32LobApp')" \
  --select "id,displayName,displayVersion"

python scripts/graph.py GET "deviceAppManagement/mobileApps" \
  --filter "startswith(displayName,'Adobe')"
```

## Troubleshooting install failures

Start with the aggregate, then drill down — don't loop devices first:

```bash
# Rollup: installed / failed / pending counts
python scripts/graph.py GET "deviceAppManagement/mobileApps/{id}/installSummary"

# Per-device detail
python scripts/graph.py GET "deviceAppManagement/mobileApps/{id}/deviceStatuses" --beta

# Assignments — often the actual problem
python scripts/graph.py GET "deviceAppManagement/mobileApps/{id}/assignments"
```

`deviceStatuses` carries `installState`, `errorCode`, and `displayName`. Error codes are
raw Windows/MSI codes, not Intune ones — `0x87D00324` is the famous one and means the app
installed but **detection failed**. That distinction matters: the install worked, the
detection rule is wrong. Chasing the installer instead of the detection rule wastes hours.

Other frequent codes: `0x87D00325` (detection found it already present), `1603` (generic
MSI failure — check the app's own log on the device), `0x87D13B60` (content download failed).

Fleet-wide app install reporting: use `AppInstallStatusAggregate` or
`DeviceInstallStatusByApp` exports (see reporting.md).

## Assignments

```bash
python scripts/graph.py POST "deviceAppManagement/mobileApps/{id}/assign" --body '{
  "mobileAppAssignments": [{
    "@odata.type": "#microsoft.graph.mobileAppAssignment",
    "intent": "required",
    "target": {"@odata.type": "#microsoft.graph.groupAssignmentTarget", "groupId": "GROUP-GUID"},
    "settings": {
      "@odata.type": "#microsoft.graph.win32LobAppAssignmentSettings",
      "notifications": "showAll",
      "deliveryOptimizationPriority": "notConfigured"
    }
  }]
}'
```

`assign` **replaces the entire assignment list**. It is not additive. To add one group,
GET the existing assignments first, append, and POST the full set back — otherwise you
silently unassign the app from everyone else, and nobody notices until the helpdesk does.

`intent`: `required` (auto-install), `available` (Company Portal opt-in),
`uninstall` (actively removes), `availableWithoutEnrollment`.

Targets: `groupAssignmentTarget`, `exclusionGroupAssignmentTarget`, `allDevicesAssignmentTarget`,
`allLicensedUsersAssignmentTarget`. Exclusions win over inclusions — check for them before
concluding an assignment is broken.

## Uploading a Win32 app (.intunewin)

Six stages, and it fails at the chunked upload for most people. All Win32 content endpoints
are **beta-only** — there's no v1.0 equivalent, so `--beta` isn't optional here.

The `.intunewin` produced by the Microsoft Win32 Content Prep Tool is a zip containing
`IntunePackage.intunewin` (the already-encrypted payload) and `Detection.xml` (metadata +
the encryption keys). **You don't encrypt anything** — the prep tool did it. Your job is to
pass its keys through to the commit call unchanged.

1. **Create the app shell**
   ```
   POST deviceAppManagement/mobileApps
   {"@odata.type": "#microsoft.graph.win32LobApp", "displayName": "...", "publisher": "...",
    "fileName": "IntunePackage.intunewin", "installCommandLine": "...", "uninstallCommandLine": "...",
    "setupFilePath": "...", "minimumSupportedWindowsRelease": "21H1",
    "installExperience": {"runAsAccount": "system", "deviceRestartBehavior": "allow"},
    "detectionRules": [...], "returnCodes": [...]}
   ```
2. **Create a content version**
   `POST deviceAppManagement/mobileApps/{appId}/microsoft.graph.win32LobApp/contentVersions` with body `{}`
3. **Create the file placeholder** — sizes come from `Detection.xml`:
   ```
   POST .../contentVersions/{versionId}/files
   {"@odata.type": "#microsoft.graph.mobileAppContentFile", "name": "IntunePackage.intunewin",
    "size": <UnencryptedContentSize from Detection.xml>,
    "sizeEncrypted": <actual byte size of IntunePackage.intunewin>,
    "manifest": null, "isDependency": false}
   ```
4. **Poll for `azureStorageUri`** — `GET .../files/{fileId}` until it's populated
   (`uploadState` becomes `azureStorageUriRequestSuccess`). It is empty on creation. The
   SAS URI **expires**, so don't fetch it and then go do something else.
5. **Upload in chunks** to Azure Blob (not Graph). Use the Block Blob API: PUT each block
   with `?comp=block&blockid={base64}`, then PUT the block list with `?comp=blocklist`.
   Chunk at 4–6 MB. Every block ID must be base64 of the same byte length or Azure rejects
   the list. Header `x-ms-blob-type: BlockBlob`. For files over ~100 MB, renew the SAS
   mid-upload via `.../files/{fileId}/renewUpload`.
6. **Commit**, passing the encryption info from `Detection.xml` verbatim:
   ```
   POST .../contentVersions/{versionId}/files/{fileId}/commit
   {"fileEncryptionInfo": {"encryptionKey": "...", "macKey": "...", "initializationVector": "...",
    "mac": "...", "profileIdentifier": "ProfileVersion1", "fileDigest": "...",
    "fileDigestAlgorithm": "SHA256"}}
   ```
   Then poll `uploadState` until `commitFileSuccess`, and finally:
   ```
   PATCH deviceAppManagement/mobileApps/{appId}
   {"@odata.type": "#microsoft.graph.win32LobApp", "committedContentVersion": "1"}
   ```

Skipping that final PATCH is the most common silent failure: content uploads fine, app
shows up in the console, and installs nothing, because no version is committed.

**Before writing this from scratch**, check whether the user can use `IntuneWin32App`
(PowerShell, `Install-Module IntuneWin32App`) — it wraps all six stages and is well
maintained. Reimplementing chunked blob upload to save a module dependency is rarely the
right call. Microsoft's reference implementation is at
`github.com/microsoftgraph/powershell-intune-samples/tree/master/LOB_Application`.

## Detection rules

The most common cause of "installed but reports failed". Types:

```json
{"@odata.type": "#microsoft.graph.win32LobAppFileSystemRule", "ruleType": "detection",
 "path": "%ProgramFiles%\\App", "fileOrFolderName": "app.exe",
 "operationType": "exists", "check32BitOn64System": false}

{"@odata.type": "#microsoft.graph.win32LobAppRegistryRule", "ruleType": "detection",
 "keyPath": "HKEY_LOCAL_MACHINE\\SOFTWARE\\...", "valueName": "Version",
 "operationType": "version", "operator": "greaterThanOrEqual", "comparisonValue": "1.2.0"}

{"@odata.type": "#microsoft.graph.win32LobAppProductCodeRule", "ruleType": "detection",
 "productCode": "{GUID}", "productVersionOperator": "greaterThanOrEqual", "productVersion": "1.0"}
```

`%ProgramFiles%` on x64 resolves differently under a 32-bit installer — `check32BitOn64System`
exists precisely for this and is the reason a rule that looks right still fails.
