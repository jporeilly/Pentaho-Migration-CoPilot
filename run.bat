@echo off
rem Pentaho Migration Copilot launcher (cmd). Delegates to run.ps1 so the
rem setup logic lives in one place.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1"
