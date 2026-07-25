@echo off
rem Pentaho Migration Copilot installer (cmd). Delegates to install.ps1.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
