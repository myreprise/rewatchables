@echo off
rem Double-click to publish: runs scripts\publish.py from this folder and
rem keeps the window open so the result can be read. See README.md.
cd /d "%~dp0"
python scripts\publish.py %*
echo.
pause
