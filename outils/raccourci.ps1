# Cree le raccourci "Got-it" sur le Bureau : il ouvre la fenetre de Got-it, sans fenetre noire.
# Appele par raccourci.bat, depuis le dossier de l'application. (Sans accents : Windows PowerShell 5.1.)
$racine = Split-Path -Parent $PSScriptRoot
$python = Join-Path $racine '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $python)) {
    Write-Host "Got-it n'est pas installe : lancez d'abord installer.bat"
    exit 1
}
$bureau = [Environment]::GetFolderPath('Desktop')
$raccourci = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $bureau 'Got-it.lnk'))
$raccourci.TargetPath = $python
$raccourci.Arguments = 'lancer.py'
$raccourci.WorkingDirectory = $racine
$raccourci.IconLocation = Join-Path $racine 'transcripteur\static\icone.ico'
$raccourci.Description = 'Enregistrer, transcrire et resumer un rendez-vous, sur ce PC'
$raccourci.Save()
Write-Host 'Raccourci "Got-it" cree sur le Bureau.'
