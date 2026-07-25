@echo off
rem Pentaho Migration Copilot uninstaller (cmd). Delegates to uninstall.ps1.
rem Pass-through flags: -Force -All -DryRun
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall.ps1" %*
