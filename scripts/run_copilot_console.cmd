@echo off
title Migration Copilot - API calls (port 8321)
cd /d C:\Projects\Pentaho-Migration
.venv\Scripts\python.exe -m uvicorn pentaho_migration.api.main:app --port 8321 --access-log
pause
