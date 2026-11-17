@echo off
chcp 65001 >nul
cd /d "%~dp0"
rem Cree le raccourci "Got-it" sur le Bureau, avec l'icone de l'application.
powershell -NoProfile -ExecutionPolicy Bypass -File "outils\raccourci.ps1"
pause
