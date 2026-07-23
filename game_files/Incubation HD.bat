@echo off
rem === Incubation launcher ===
rem Play (HD / Vanilla), HD texture pipeline, vanilla texture modding, debug tools.
rem
rem Needs a 32-bit Python: the HD pipeline calls the game's Eng3d.dll, which is a
rem 32-bit DLL and cannot be loaded by a 64-bit interpreter. Tries the default
rem install location, then the py launcher, then whatever is on PATH.
cd /d "%~dp0"

set "PYW=%LOCALAPPDATA%\Programs\Python\Python312-32\pythonw.exe"
if exist "%PYW%" goto run
set "PYW=%LOCALAPPDATA%\Programs\Python\Python312-32\python.exe"
if exist "%PYW%" goto run

rem py launcher: -3-32 selects any installed 32-bit Python 3
py -3-32 -c "import sys" >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3-32 "%~dp0tools\launcher.py"
  goto :eof
)

rem last resort: whatever "python" is on PATH (warn if it turns out to be 64-bit)
python -c "import struct,sys; sys.exit(0 if struct.calcsize('P')==4 else 1)" >nul 2>&1
if errorlevel 1 (
  echo.
  echo   No 32-bit Python 3 found.
  echo   Install the "Windows installer (32-bit)" build from
  echo   https://www.python.org/downloads/windows/ and tick "Add python.exe to PATH",
  echo   then run:  py -3-32 -m pip install Pillow numpy
  echo.
  pause
  goto :eof
)
set "PYW=pythonw"

:run
start "" "%PYW%" "%~dp0tools\launcher.py"
