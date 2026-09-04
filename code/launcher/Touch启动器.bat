@echo off
rem Double-click to open the Touch launcher.
rem Contents kept ASCII-only so cmd.exe renders it on any code page.

setlocal
cd /d "%~dp0"

rem pythonw runs the GUI without a console window. Fall back to python if
rem it is missing, so the user at least sees an error message.
where pythonw >nul 2>nul
if %errorlevel%==0 (
    start "" pythonw "touch_launcher.pyw"
    exit /b 0
)

where python >nul 2>nul
if %errorlevel%==0 (
    python "touch_launcher.pyw"
    exit /b 0
)

echo.
echo Python was not found on PATH.
echo Install Python 3.8+ or run: ^<your python^> touch_launcher.pyw
echo.
pause
