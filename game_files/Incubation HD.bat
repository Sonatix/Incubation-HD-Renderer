@echo off
rem === Incubation HD launcher ===
rem GUI for resolution, HD textures, 2D sharpen, bump, and the hd_tool pipeline.
cd /d "%~dp0"
set PYW=%LOCALAPPDATA%\Programs\Python\Python312-32\pythonw.exe
if not exist "%PYW%" set PYW=%LOCALAPPDATA%\Programs\Python\Python312-32\python.exe
start "" "%PYW%" "%~dp0tools\launcher.py"
