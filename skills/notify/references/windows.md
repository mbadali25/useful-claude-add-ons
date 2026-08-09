# Windows setup

`notify` is pure Python and runs on Windows unchanged — only the shell commands
differ. Examples below are PowerShell unless noted.

## Python
Use `python` (or the launcher `py -3`). Verify: `python --version` (need 3.8+).

## Where config and spool live
The `~/...` defaults expand correctly on Windows — you don't need to edit them:

| | Path on Windows |
|---|---|
| Global config | `C:\Users\<you>\.config\notify\config.json` |
| Project config | `.notify.json` in the folder you run from |
| Spool | `C:\Users\<you>\.local\state\notify\spool` |

Create the global config from the example:
```powershell
New-Item -ItemType Directory -Force "$HOME\.config\notify" | Out-Null
Copy-Item .\assets\config.example.json "$HOME\.config\notify\config.json"
notepad "$HOME\.config\notify\config.json"
```

## Set the token (and SMTP creds if used)
**This session only (PowerShell):**
```powershell
$env:TELEGRAM_BOT_TOKEN = "123456789:AAE..."
```
**Persist for future shells (User scope):**
```powershell
setx TELEGRAM_BOT_TOKEN "123456789:AAE..."   # open a NEW terminal afterward
```
**CMD equivalents:**
```cmd
set TELEGRAM_BOT_TOKEN=123456789:AAE...          :: this session
setx TELEGRAM_BOT_TOKEN "123456789:AAE..."       :: persist (new shells)
```
Use the same pattern for `SMTP_USER` / `SMTP_PASS`. Avoid `setx` for secrets on
shared machines (it stores them in your user environment).

## Send a notification
```powershell
python .\scripts\telegram_get_chat_id.py         # after messaging your bot once
python .\scripts\notify.py -e info -m "hello" --dry-run
python .\scripts\notify.py -e info -m "hello"
```

## Run the dispatcher (needed for topics / concurrent questions)
Pick one:

**A — Keep a terminal open (simplest)**
```powershell
python .\scripts\notifyd.py
```

**B — Background, no console window (pythonw)**
```powershell
Start-Process pythonw -ArgumentList ".\scripts\notifyd.py" -WindowStyle Hidden
```

**C — Start automatically at logon (Task Scheduler)**
```powershell
$py = (Get-Command pythonw).Source
$script = "C:\path\to\notify\scripts\notifyd.py"
schtasks /Create /TN "notifyd" /TR "`"$py`" `"$script`"" /SC ONLOGON /RL LIMITED /F
```
Set the token with `setx` (User scope) first so the task inherits it.

**D — True Windows service (NSSM)**
```powershell
nssm install notifyd "C:\path\to\python.exe" "C:\path\to\notify\scripts\notifyd.py"
nssm set notifyd AppEnvironmentExtra TELEGRAM_BOT_TOKEN=123456789:AAE...
nssm start notifyd
```

## Status / stop
```powershell
python .\scripts\notifyd.py status     # {"running": true, "heartbeat_age_s": 1}
python .\scripts\notifyd.py stop
```
On Windows, `stop` hard-terminates the process, so the daemon's cleanup doesn't run
and the pid file can linger. That's harmless: the client's liveness check keys off
the **heartbeat** file (stale >10s = not running), so a stopped daemon is still
detected correctly and the client won't hang waiting for a reply.

## Notes
- Paths in commands use backslashes; the scripts themselves handle paths portably.
- If `python` opens the Microsoft Store, install Python from python.org or use
  `py -3`, and re-run.
