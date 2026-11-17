@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Installation de Got it! ===
where py >nul 2>nul
if %errorlevel% neq 0 (
  echo Python n'est pas installe. Telechargez-le sur https://www.python.org/downloads/windows/
  echo puis cochez "Add python.exe to PATH" pendant l'installation, et relancez ce fichier.
  pause
  exit /b 1
)
py -3 -m venv .venv
if %errorlevel% neq 0 (
  echo Impossible de creer l'environnement Python.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt --quiet
if %errorlevel% neq 0 (
  echo L'installation des dependances a echoue. Verifiez la connexion internet et relancez.
  pause
  exit /b 1
)
echo.
echo Preparation de la transcription (modele Whisper, environ 1,6 Go, une seule fois)...
python outils\preparer.py
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "outils\raccourci.ps1"
echo.
echo Installation terminee. Ouvrez Got it! avec son raccourci sur le Bureau, ou avec lancer.bat
pause
