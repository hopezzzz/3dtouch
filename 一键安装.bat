@echo off
rem One-click setup: download the 3D Systems driver and SDK, then install them.
rem Contents kept ASCII-only so cmd.exe renders it on any code page.
setlocal
cd /d "%~dp0code\setup"

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found on PATH. Install 64-bit Python 3.8+ first.
    pause
    exit /b 1
)

python fetch_vendor.py %*
echo.
pause
