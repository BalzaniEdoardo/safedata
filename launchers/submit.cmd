@echo off
rem Check and save your edits. Double-click to run.
cd /d "%~dp0.."
uv run safedata submit
echo.
pause
