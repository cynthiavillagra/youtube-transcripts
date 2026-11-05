@echo off
REM Doble clic: transcribe todos los links de links.txt
cd /d "%~dp0"
if not exist links.txt copy links.ejemplo.txt links.txt >nul && notepad links.txt && exit /b
uv run transcribir_youtube.py --lista links.txt --unir %*
pause
