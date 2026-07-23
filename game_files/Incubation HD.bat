@echo off
rem === Incubation launcher ===
rem Play (HD / Vanilla), HD texture pipeline, vanilla texture modding, debug tools.
rem
rem Needs a 32-bit Python 3: the HD pipeline loads the game's Eng3d.dll, which is
rem a 32-bit DLL a 64-bit interpreter cannot load.
rem
rem This script deliberately runs a PREFLIGHT with the console python before
rem handing over to pythonw. pythonw has no console, so without the preflight any
rem startup failure (missing tkinter, a bad copy, wrong folder) would just look
rem like "nothing happens" with nowhere to look.
setlocal
cd /d "%~dp0"

set "PY="

rem --- 1. the usual per-user install locations, newest first
for %%V in (313 312 311 310) do (
  if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe" (
    set "PY=%LOCALAPPDATA%\Programs\Python\Python%%V-32\python.exe"
  )
)

rem --- 2. the py launcher, which knows about every installed version
if not defined PY (
  py -3-32 -c "import sys" >nul 2>&1
  if not errorlevel 1 set "PY=py -3-32"
)

rem --- 3. whatever "python" is on PATH, but only if it really is 32-bit
if not defined PY (
  python -c "import struct,sys; sys.exit(0 if struct.calcsize('P')==4 else 1)" >nul 2>&1
  if not errorlevel 1 set "PY=python"
)

if not defined PY (
  echo.
  echo   No 32-bit Python 3 found.
  echo.
  echo   Install the "Windows installer ^(32-bit^)" build from
  echo     https://www.python.org/downloads/windows/
  echo   and tick "Add python.exe to PATH" on the first screen.
  echo.
  echo   If you already installed a 64-bit Python, that one will not work for the
  echo   HD pipeline - it cannot load the game's 32-bit Eng3d.dll.
  echo.
  pause
  exit /b 1
)

rem --- are we actually in the game folder?
if not exist "%~dp0Incubation.exe" (
  echo.
  echo   Incubation.exe is not next to this file.
  echo   Copy everything from game_files\ INTO your Incubation folder - the one
  echo   that already contains Incubation.exe - and run it from there.
  echo   Current folder: %~dp0
  echo.
  pause
  exit /b 1
)
if not exist "%~dp0tools\launcher.py" (
  echo.
  echo   tools\launcher.py is missing. Copy the whole tools\ folder from
  echo   game_files\, not just the loose files.
  echo.
  pause
  exit /b 1
)

rem --- preflight: import everything the GUI needs, with a visible console
%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   Your Python has no tkinter, so no window can be created.
  echo   Re-run the Python installer, choose Modify, and tick
  echo   "tcl/tk and IDLE".
  echo.
  pause
  exit /b 1
)

%PY% -c "import sys; sys.path.insert(0,r'%~dp0tools'); import launcher" 2>"%TEMP%\incu_launcher_error.txt"
if errorlevel 1 (
  echo.
  echo   The launcher failed to start. The actual error:
  echo.
  type "%TEMP%\incu_launcher_error.txt"
  echo.
  pause
  exit /b 1
)
del "%TEMP%\incu_launcher_error.txt" >nul 2>&1

rem --- preflight passed: hand over to the windowed interpreter
set "PYW=%PY:python.exe=pythonw.exe%"
if "%PYW%"=="py -3-32" set "PYW=pyw -3-32"
if "%PYW%"=="python"   set "PYW=pythonw"
start "" %PYW% "%~dp0tools\launcher.py"
endlocal
