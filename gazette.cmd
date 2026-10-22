@echo off
rem Gazette launcher for Windows terminals (cmd, PowerShell). Inside Claude Code use ./gazette instead.
setlocal
set "PY=python"
where py >nul 2>nul && set "PY=py -3"
%PY% -I "%~dp0scripts\cli.py" %*
exit /b %errorlevel%
