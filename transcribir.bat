@echo off
REM Doble clic: transcribe todos los links de links.txt (sin interfaz web)
cd /d "%~dp0"
where uv >nul 2>nul || (echo Falta instalar uv. Mira la seccion "Instalacion" del README.md & pause & exit /b 1)
if not exist links.txt copy links.ejemplo.txt links.txt >nul && notepad links.txt && exit /b
uv run transcribir_youtube.py --lista links.txt --unir %*
pause
