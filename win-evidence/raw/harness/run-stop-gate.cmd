@echo off
rem Stop-hook equivalent for crew 1.2.68: verify-gate.sh with no flags (stop budget).
rem %1 = worktree path. stdin is taken from NUL (a VALID handle), unlike the
rem Claude Code Stop hook, which hands the child an invalid one.
set "PATH=C:\Program Files\Git\usr\bin;C:\Program Files\Git\bin;%PATH%"
cd /d "%~1"
"C:\Program Files\Git\bin\bash.exe" "C:/Users/d3ade/.claude/plugins/cache/useful-claude-add-ons/crew/1.2.68/hooks/scripts/verify-gate.sh" < NUL 2>&1
echo VERIFY_GATE_EXIT=%ERRORLEVEL%
