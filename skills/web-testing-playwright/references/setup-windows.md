# Installing Playwright on Windows

Always run `scripts/check_env.py` first and show the user what's missing before installing
anything. Installs need consent — some of these need an administrator shell and pull down
several hundred megabytes.

## Contents
- [Which package manager](#which-package-manager)
- [Using winget](#using-winget)
- [Using Chocolatey](#using-chocolatey)
- [Installing Playwright itself](#installing-playwright-itself)
- [PATH refresh](#path-refresh-the-most-common-it-didnt-work)
- [Elevation](#elevation)
- [Corporate proxies and blocked downloads](#corporate-proxies-and-blocked-downloads)
- [Environment variables in PowerShell](#environment-variables-in-powershell)
- [WSL](#wsl)

## Which package manager

```
Does `winget --version` work?
├─ yes → use winget. It ships with Windows (App Installer) on Win10 1809+ and Win11,
│        needs no bootstrap, and doesn't require admin for most user-scope installs.
└─ no  → Does `choco --version` work?
         ├─ yes → use Chocolatey (common on managed corporate machines).
         └─ no  → Older Windows, App Installer removed, or a locked-down image.
                  Options, in order of preference:
                  1. Install App Installer from the Microsoft Store → gets winget.
                  2. Bootstrap Chocolatey (needs admin — see below).
                  3. Skip package managers: download the Node.js or Python MSI
                     directly from nodejs.org / python.org.
```

If the machine already has one in use, use that one. Mixing winget and Chocolatey for the
same package produces two installations and a confusing PATH.

## Using winget

```powershell
winget install --id OpenJS.NodeJS.LTS -e --source winget   # Node (for @playwright/test)
winget install --id Python.Python.3.12 -e --source winget  # Python (for the bundled scripts)
```

`-e` means exact-ID match, which avoids installing something with a similar name. Add
`--scope machine` to install for all users — that one does need admin.

Accept the source agreements non-interactively when scripting:
`--accept-package-agreements --accept-source-agreements`.

If winget itself is broken (`0x8a15000f` or similar), `winget source reset --force` fixes
most of it.

## Using Chocolatey

Bootstrap, in an **administrator** PowerShell:

```powershell
Set-ExecutionPolicy Bypass -Scope Process -Force
[System.Net.ServicePointManager]::SecurityProtocol = `
    [System.Net.ServicePointManager]::SecurityProtocol -bor 3072
iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
```

Explain to the user what that does before running it: it sets the execution policy for
that one process only, forces TLS 1.2, and runs Chocolatey's official install script. If
they're uncomfortable running a piped remote script — a reasonable instinct — point them
at the MSI installers instead.

Then:

```powershell
choco install nodejs-lts -y
choco install python312 -y
```

Chocolatey installs are machine-wide and essentially always need an elevated shell.

## Installing Playwright itself

Package managers only get you Node/Python. Playwright comes from npm or pip.

**Python** (what the bundled scripts use):
```powershell
python -m pip install --upgrade pip
python -m pip install playwright
python -m playwright install chromium      # or: install  (all three engines)
```

**Node**:
```powershell
npm init playwright@latest                 # scaffolds a full test project
# or, into an existing project:
npm install -D @playwright/test
npx playwright install chromium
```

Notes specific to Windows:

- There is **no `install-deps` step on Windows**. That's Linux-only. If you see advice to
  run `playwright install-deps`, it doesn't apply here.
- Browsers land in `%LOCALAPPDATA%\ms-playwright`. Roughly 150 MB for Chromium alone,
  ~400 MB for Chromium + Firefox + WebKit. Say so before starting the download.
- Prefer `python -m pip` over bare `pip`, and `py -3.12 -m pip` when several Pythons are
  installed — it guarantees the package lands in the interpreter you'll actually run.
- Installing only `chromium` is usually right. Add Firefox/WebKit only when the user
  specifically cares about cross-browser behavior; WebKit is the closest available proxy
  for Safari.

## PATH refresh (the most common "it didn't work")

A freshly installed `node` or `python` will not be on PATH in the shell that ran the
install. This looks like the install failing when it actually succeeded.

- Simplest: open a new terminal.
- In the current PowerShell:
  ```powershell
  $env:Path = [System.Environment]::GetEnvironmentVariable("Path","Machine") + ";" + `
              [System.Environment]::GetEnvironmentVariable("Path","User")
  ```
- With Chocolatey: `refreshenv`.

Re-run `check_env.py` afterwards to confirm rather than assuming.

## Elevation

Ask the user to run an elevated shell rather than trying to self-elevate — a UAC prompt
triggered from an automated session is confusing and often just fails silently.

> "This step needs an administrator PowerShell. Right-click the Start button → *Terminal
> (Admin)* or *Windows PowerShell (Admin)*, then run: ..."

Needs admin: Chocolatey bootstrap, all `choco install`, `winget --scope machine`, MSI
installers. Does not need admin: user-scope winget, `pip install --user`, `npm install`
into a project, and `playwright install` (browsers go under the user profile).

## Corporate proxies and blocked downloads

Very common on managed Windows machines, and the symptom is a Playwright browser download
that hangs or fails with a TLS error.

```powershell
$env:HTTPS_PROXY = "http://proxy.corp.example:8080"
$env:HTTP_PROXY  = "http://proxy.corp.example:8080"
npm config set proxy http://proxy.corp.example:8080
npm config set https-proxy http://proxy.corp.example:8080
```

If the corporate CDN mirrors browser builds internally:
```powershell
$env:PLAYWRIGHT_DOWNLOAD_HOST = "https://internal-mirror.corp.example/playwright"
```

If the user's org can't allow the download at all, fall back to
`channel="msedge"` or `channel="chrome"` in the launch call, which drives the
already-installed Edge or Chrome rather than a downloaded build:

```python
browser = p.chromium.launch(channel="msedge")
```

Edge is present on every modern Windows install, so this is a dependable escape hatch.
It's slightly less hermetic than a pinned Playwright build — the browser version follows
whatever the machine has — so mention that tradeoff.

Antivirus (particularly on locked-down corporate images) sometimes quarantines the
freshly extracted browser. If `playwright install` reports success but launching fails
with a missing-executable error, that's the likely cause; the user will need their IT
team to allow `%LOCALAPPDATA%\ms-playwright`.

## Environment variables in PowerShell

For credentials, current session only — this is what you want for a test run, since it
disappears when the terminal closes:

```powershell
$env:APP_USER = "someone@example.com"
$env:APP_PASSWORD = "..."
```

Persisting with `setx` writes the value to the registry, where it survives reboots and is
readable by anything running as that user. Don't suggest `setx` for passwords.

cmd.exe uses `set VAR=value` (no quotes around the value, and no spaces around `=`).

## WSL

If the user is in WSL, they're on Linux — use `references/setup-linux.md`. Two things
regularly trip people up:

- A dev server started in Windows on `localhost:3000` is not automatically the same
  `localhost` inside WSL2. From WSL, reach the Windows host via the IP in
  `/etc/resolv.conf`, or run the server inside WSL too.
- Headed mode works on Windows 11 through WSLg with no extra setup. On Windows 10 it
  needs a separate X server, so prefer headless there.
