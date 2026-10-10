@echo off
rem Opens the records editor in the browser. Keep this window open while editing.
cd /d "%~dp0.."
uv run safedata edit
pause
