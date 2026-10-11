@echo off
rem AI-Connect installation for Windows: double-click for the interactive
rem installation, or pass the options of install.ps1 (e.g. install.cmd -Client).
rem Runs install.ps1 without changing the PowerShell execution policy.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1" %*
set RESULT=%ERRORLEVEL%
rem Keep the window open only when started by double-click (no options)
if "%~1"=="" pause
exit /b %RESULT%
