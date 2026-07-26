@echo off
REM One command, no arguments. Same as: python bootstrap.py
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3.11+ is required. & exit /b 1)
python bootstrap.py
pause
