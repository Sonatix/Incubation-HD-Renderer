@echo off
rem === Incubation texture modding (vanilla path) — standalone window ===
rem Decode, paint, repack the game's own texture.lib. The same tool is also the
rem "Vanilla textures" tab of the main launcher (Incubation HD.bat).
rem
rem The VISN codec is pure Python, so ANY Python 3 with Pillow works here —
rem 32- or 64-bit. Prefers a 64-bit one only because it is faster.
cd /d "%~dp0"

for %%P in (
  "%LOCALAPPDATA%\Programs\Python\Python312\pythonw.exe"
  "%LOCALAPPDATA%\Programs\Python\Python312-32\pythonw.exe"
) do (
  if exist "%%~P" (
    "%%~P" -c "import PIL" >nul 2>&1
    if not errorlevel 1 (
      start "" "%%~P" "%~dp0tools\visn_gui.py"
      goto :eof
    )
  )
)

py -3 -c "import PIL" >nul 2>&1
if not errorlevel 1 (
  start "" pyw -3 "%~dp0tools\visn_gui.py"
  goto :eof
)

echo.
echo   No Python 3 with Pillow found.
echo   Install Python 3 from https://www.python.org/downloads/windows/
echo   ^(tick "Add python.exe to PATH"^), then run:  py -3 -m pip install Pillow
echo.
pause
