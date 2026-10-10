@echo off
rem Open the records for editing. Double-click to run.
cd /d "%~dp0.."
uv run safedata edit
echo.
pause
