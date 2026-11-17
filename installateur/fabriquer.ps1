# Fabrique l'installateur de Got-it : Got-it-Setup-<version>.exe, dans le dossier "distribution".
# Usage (depuis le dossier du projet) : powershell -ExecutionPolicy Bypass -File installateur\fabriquer.ps1
# Il faut : l'environnement .venv (installer.bat), PyInstaller (pip install pyinstaller) et Inno Setup 6.
# (Sans accents : Windows PowerShell 5.1.)
$ErrorActionPreference = 'Stop'
$racine = Split-Path -Parent $PSScriptRoot
$python = Join-Path $racine '.venv\Scripts\python.exe'
$travail = Join-Path $env:TEMP 'got-it-fabrication'      # hors du projet : plusieurs centaines de Mo
$sortie = Join-Path $racine 'distribution'

$version = (& $python -c "import sys; sys.path.insert(0, r'$racine'); import transcripteur; print(transcripteur.VERSION)").Trim()
Write-Host "=== Got-it $version : empaquetage de Python et des bibliotheques ==="
if (Test-Path $travail) { Remove-Item -Recurse -Force $travail }
& $python -m PyInstaller --noconfirm --clean --log-level WARN --windowed --name Got-it `
    --icon (Join-Path $racine 'transcripteur\static\icone.ico') `
    --distpath (Join-Path $travail 'dist') --workpath (Join-Path $travail 'build') --specpath $travail `
    --paths $racine `
    --add-data ((Join-Path $racine 'transcripteur\templates') + ';transcripteur\templates') `
    --add-data ((Join-Path $racine 'transcripteur\static') + ';transcripteur\static') `
    --collect-all faster_whisper --collect-all ctranslate2 --collect-all onnxruntime --collect-all av `
    --collect-all soundcard --collect-all tokenizers --collect-all huggingface_hub --collect-all docx `
    --collect-submodules uvicorn --hidden-import python_multipart --hidden-import multipart `
    --exclude-module PyInstaller --exclude-module pip --exclude-module setuptools --exclude-module tkinter `
    (Join-Path $racine 'lancer.py')
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller a echoue.' }
Copy-Item (Join-Path $racine 'LICENSE') (Join-Path $travail 'dist\Got-it\LICENSE.txt')

Write-Host '=== Construction de l''installateur ==='
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw 'Inno Setup 6 est introuvable (winget install JRSoftware.InnoSetup).' }
New-Item -ItemType Directory -Force $sortie | Out-Null
& $iscc /Qp "/DVersion=$version" "/DSource=$(Join-Path $travail 'dist\Got-it')" "/DSortie=$sortie" `
    "/DIcone=$(Join-Path $racine 'transcripteur\static\icone.ico')" (Join-Path $PSScriptRoot 'got-it.iss')
if ($LASTEXITCODE -ne 0) { throw 'Inno Setup a echoue.' }
Get-ChildItem $sortie -Filter "Got-it-Setup-$version.exe" | ForEach-Object { Write-Host ("Installateur : {0} ({1:N0} Mo)" -f $_.FullName, ($_.Length / 1MB)) }
