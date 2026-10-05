; Inno-Setup-Skript für DMNT-Kobold.
; Aufruf über packaging/bauen.ps1:  ISCC.exe /DAppVersion=0.7.0 /DNumVersion=0.7.0 DMNT-Kobold.iss
;
; Installation pro Nutzer ohne Admin-Rechte (kein UAC-Dialog), auch beim Update.
; Nutzerdaten liegen in Dokumente\DMNT-Kobold\ und werden nie angefasst.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef NumVersion
  #define NumVersion "0.0.0"
#endif

[Setup]
; AppId nie ändern – sonst erkennt das Setup alte Installationen nicht mehr.
AppId={{4B04F168-3E25-420C-99CC-41B5E34A58BD}
AppName=DMNT-Kobold
AppVersion={#AppVersion}
AppVerName=DMNT-Kobold {#AppVersion}
AppPublisher=Stefan Rohrbach
AppPublisherURL=https://dmnt-studio.github.io/DMNT-Kobold/
AppSupportURL=https://github.com/DMNT-Studio/DMNT-Kobold/issues
AppUpdatesURL=https://github.com/DMNT-Studio/DMNT-Kobold/releases
VersionInfoVersion={#NumVersion}
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\DMNT-Kobold
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=yes
UsePreviousAppDir=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=DMNT-Kobold-Setup
SetupIconFile=kobold.ico
UninstallDisplayIcon={app}\DMNT-Kobold.exe
UninstallDisplayName=DMNT-Kobold
WizardStyle=modern
Compression=lzma2/max
SolidCompression=yes
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "deutsch"; MessagesFile: "compiler:Languages\German.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[InstallDelete]
; Alte Programmdateien weg, damit nach einem Update nichts Veraltetes liegen bleibt.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\DMNT-Kobold\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\DMNT-Kobold"; Filename: "{app}\DMNT-Kobold.exe"
Name: "{autodesktop}\DMNT-Kobold"; Filename: "{app}\DMNT-Kobold.exe"; Tasks: desktopicon

[Run]
; Normale Installation: Häkchen „DMNT-Kobold starten“ am Ende.
Filename: "{app}\DMNT-Kobold.exe"; Description: "{cm:LaunchProgram,DMNT-Kobold}"; Flags: nowait postinstall skipifsilent
; Update aus dem Programm (/SILENT): den neuen Kobold gleich wieder starten.
Filename: "{app}\DMNT-Kobold.exe"; Flags: nowait skipifnotsilent

[Code]
function InitializeUninstall(): Boolean;
var
  Ergebnis: Integer;
begin
  { Laufenden Kobold beenden, damit alle Dateien entfernt werden können. }
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/IM DMNT-Kobold.exe /F', '', SW_HIDE,
       ewWaitUntilTerminated, Ergebnis);
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { Autostart-Eintrag entfernen. Dokumente\DMNT-Kobold bleibt unangetastet. }
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'DMNT-Kobold');
  end;
end;
