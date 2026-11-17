; Installateur de Got it! (Inno Setup 6). Appele par fabriquer.ps1, qui fournit Version, Source, Sortie et Icone.
; Installation pour l'utilisateur courant, sans droits d'administrateur. Les donnees (C:\Users\<vous>\Got-it)
; et le modele de transcription ne sont ni installes ni supprimes par cet installateur.

[Setup]
AppId={{6F1C2B7E-3D0A-4C59-9E41-7A2B5D8C1F36}
AppName=Got it!
AppVersion={#Version}
AppVerName=Got it! {#Version}
AppPublisherURL=https://github.com/fanny-ctrl/got-it
DefaultDirName={localappdata}\Programs\Got-it
DefaultGroupName=Got it!
DisableProgramGroupPage=yes
DisableDirPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#Sortie}
OutputBaseFilename=Got-it-Setup-{#Version}
SetupIconFile={#Icone}
UninstallDisplayIcon={app}\Got-it.exe
UninstallDisplayName=Got it!
LicenseFile={#Source}\LICENSE.txt
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "french"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "bureau"; Description: "Créer une icône sur le Bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "{#Source}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[InstallDelete]
; Raccourcis des versions precedentes, qui portaient l'ancien nom.
Type: files; Name: "{autodesktop}\Got-it.lnk"
Type: files; Name: "{autoprograms}\Got-it.lnk"

[Icons]
Name: "{autoprograms}\Got it!"; Filename: "{app}\Got-it.exe"; Comment: "Enregistrer, transcrire et résumer un rendez-vous, sur ce PC"
Name: "{autodesktop}\Got it!"; Filename: "{app}\Got-it.exe"; Tasks: bureau; Comment: "Enregistrer, transcrire et résumer un rendez-vous, sur ce PC"

[Run]
Filename: "{app}\Got-it.exe"; Description: "Ouvrir Got it!"; Flags: nowait postinstall skipifsilent

[Messages]
french.FinishedLabel=Got it! est installé. Au premier enregistrement, il vous proposera de télécharger le modèle de transcription (1,6 Go, une seule fois).

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
