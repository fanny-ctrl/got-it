@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
  echo Got-it n'est pas installe : lancez d'abord installer.bat
  pause
  exit /b 1
)
rem Ouvre la fenetre de Got-it, sans fenetre noire.
start "" ".venv\Scripts\pythonw.exe" lancer.py
