@echo off
rem ai-connect: the console entry point on Windows (cmd and PowerShell). See ai_connect_cli.py.
rem Put this directory on PATH to type `ai-connect` anywhere.
rem The Python: the plugin's own venv first (install.cmd makes it), else py -3, else
rem python. When none works this says so on stderr and exits 127.
rem The CLI runs outside any ( ) block: cmd expands %ERRORLEVEL% in a block when it
rem reads the block, before the CLI has run, so `exit /b %ERRORLEVEL%` there exits 0.
setlocal
set "PLUGIN=%~dp0.."
set "CLI=%PLUGIN%\ai_connect_cli.py"
set "CHECK=import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)"

if exist "%PLUGIN%\venv\Scripts\python.exe" (
    "%PLUGIN%\venv\Scripts\python.exe" -c "%CHECK%" >nul 2>&1 && goto run_venv
)
where py >nul 2>&1 && (
    py -3 -c "%CHECK%" >nul 2>&1 && goto run_py
)
where python >nul 2>&1 && (
    python -c "%CHECK%" >nul 2>&1 && goto run_python
)
echo ai-connect: no Python 3.10 or newer found (tried %PLUGIN%\venv, py -3, python). 1>&2
echo ai-connect: install Python 3.10+, or run the plugin's install.cmd to make its venv. 1>&2
exit /b 127

:run_venv
"%PLUGIN%\venv\Scripts\python.exe" "%CLI%" %*
exit /b %ERRORLEVEL%

:run_py
py -3 "%CLI%" %*
exit /b %ERRORLEVEL%

:run_python
python "%CLI%" %*
exit /b %ERRORLEVEL%
