@echo off
rem Run hello_touch.exe with hd.dll findable.
setlocal
cd /d "%~dp0"

if "%OH_SDK_BASE%"=="" set "OH_SDK_BASE=%~dp0..\..\OpenHaptics"
rem hd.dll lives with the DRIVER, which is a separate install from the SDK.
set "DRIVER_ROOT=D:\Tool_Software\Phantom Device Drivers"

set "PATH=%DRIVER_ROOT%;%PATH%"

if not exist "%~dp0hello_touch.exe" (
    echo hello_touch.exe not built yet. Running build.bat first...
    call "%~dp0build.bat" || exit /b 1
)

rem Call it by full path: some environments set
rem NoDefaultCurrentDirectoryInExePath=1, and then cmd will not run an
rem executable found only in the current directory.
"%~dp0hello_touch.exe"
