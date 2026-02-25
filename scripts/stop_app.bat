@echo off
REM Force-stop any process on port 8050. Use when Ctrl+C did not stop the app.
REM Run from project root: scripts\stop_app.bat

powershell -ExecutionPolicy Bypass -File "%~dp0stop_app.ps1"
