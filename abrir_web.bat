@echo off
REM Doble clic: abre la interfaz web en el navegador
cd /d "%~dp0"
where uv >nul 2>nul || (echo Falta instalar uv. Mira la seccion "Instalacion" del README.md & pause & exit /b 1)
uv run app_web.py
pause
