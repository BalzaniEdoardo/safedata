@echo off
rem Get the latest records. Double-click to run.
cd /d "%~dp0.."
uv run safedata update
echo.
pause
