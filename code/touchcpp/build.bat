@echo off
rem Build hello_touch.cpp against the OpenHaptics HD API.
rem Contents kept ASCII-only so cmd.exe renders it on any code page.

setlocal
cd /d "%~dp0"

rem --- where the SDK is -------------------------------------------------
if "%OH_SDK_BASE%"=="" set "OH_SDK_BASE=%~dp0..\..\OpenHaptics"
if not exist "%OH_SDK_BASE%\include\HD\hd.h" (
    echo ERROR: OpenHaptics headers not found under:
    echo   %OH_SDK_BASE%
    echo Set OH_SDK_BASE to your OpenHaptics install directory.
    exit /b 1
)

rem --- MSVC environment -------------------------------------------------
rem cl.exe needs vcvars64 for its own headers, libs and PATH.
if "%VSCMD_ARG_TGT_ARCH%"=="x64" goto :have_msvc

rem Nested parentheses around a multi-line FOR confuse cmd's parser, so
rem branch with GOTO instead of an IF block.
set "VCVARS=D:\Tool_Software\Visual Studio\VS_IDE\VC\Auxiliary\Build\vcvars64.bat"
if exist "%VCVARS%" goto :run_vcvars

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto :no_msvc
for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -property installationPath`) do set "VCVARS=%%i\VC\Auxiliary\Build\vcvars64.bat"
if exist "%VCVARS%" goto :run_vcvars

:no_msvc
echo ERROR: vcvars64.bat not found. Edit VCVARS at the top of this script.
exit /b 1

:run_vcvars
call "%VCVARS%" >nul
:have_msvc

rem --- compile ----------------------------------------------------------
rem /D WIN32 is required, not optional. hdExport.h guards the whole
rem Windows branch with "#if defined(WIN32)", and that is where HDAPI
rem (__declspec(dllimport)) and HDAPIENTRY (__stdcall) get defined.
rem Modern MSVC defines _WIN32 but NOT WIN32 -- WIN32 comes from the
rem Visual Studio project templates. Without it every HD prototype
rem collapses into "missing type specifier" errors.
echo Building hello_touch.exe ...
cl /nologo /EHsc /W3 /O2 /std:c++17 ^
   /D WIN32 ^
   /I "%OH_SDK_BASE%\include" ^
   hello_touch.cpp ^
   /Fe:hello_touch.exe /Fo:hello_touch.obj ^
   /link /LIBPATH:"%OH_SDK_BASE%\lib\x64\Release" hd.lib

if errorlevel 1 (
    echo.
    echo BUILD FAILED
    exit /b 1
)

echo.
echo Built hello_touch.exe
echo.
echo hd.dll is not next to the exe, so add the driver directory to PATH
echo before running, or just use run.bat:
echo   run.bat
