@echo off
rem === Incubation launcher ===
rem Play (HD / Vanilla), HD texture pipeline, vanilla texture modding, debug tools.
rem
rem Any 32-bit Python 3.8 or newer works. 32-bit is the real requirement: the HD
rem pipeline loads the game's Eng3d.dll to decode textures, and that is a 32-bit
rem DLL a 64-bit interpreter cannot load. 3.8 is the floor because the tools use
rem os.add_dll_directory, which arrived in 3.8.
rem
rem Candidates are probed rather than assumed, so no Python version is hard-coded
rem anywhere and a future 3.15 is found just like 3.8 is.
rem
rem The preflight below runs with the CONSOLE python on purpose: pythonw has no
rem console, so without it any startup failure would show as "nothing happens".
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PY="
rem 1. the py launcher knows every installed version and picks the newest 32-bit
call :try "py -3-32"
rem 2. per-user installs, any version
if not defined PY for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python*-32") do call :try "%%~fD\python.exe"
rem 3. all-users installs, any version
if not defined PY for /d %%D in ("%ProgramFiles(x86)%\Python*") do call :try "%%~fD\python.exe"
rem 4. whatever is on PATH, accepted only if it passes the same test
if not defined PY call :try "python"

if not defined PY (
  echo.
  echo   No suitable Python found.
  echo.
  echo   Needed: Python 3.8 or newer, 32-bit ^("Windows installer ^(32-bit^)"^).
  echo   Get it from https://www.python.org/downloads/windows/
  echo   and tick "Add python.exe to PATH" on the first screen.
  echo.
  echo   A 64-bit Python will not do: the HD pipeline loads the game's 32-bit
  echo   Eng3d.dll, which a 64-bit process cannot load.
  echo.
  pause
  exit /b 1
)

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

%PY% -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   This Python has no tkinter, so no window can be created.
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

rem preflight passed - hand over to the windowed interpreter
set "PYW=%PY%"
if "%PYW%"=="py -3-32" (set "PYW=pyw -3-32") else if "%PYW%"=="python" (set "PYW=pythonw") else set "PYW=!PY:python.exe=pythonw.exe!"
start "" %PYW% "%~dp0tools\launcher.py"
endlocal
exit /b 0

:try
rem accept a candidate only if it is really 32-bit and really >= 3.8
if defined PY goto :eof
%~1 -c "import sys,struct; sys.exit(0 if struct.calcsize('P')==4 and sys.version_info>=(3,8) else 1)" >nul 2>&1
if not errorlevel 1 set "PY=%~1"
goto :eof
