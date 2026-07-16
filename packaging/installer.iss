; Inno Setup script for the Parrotype installer.
; Compile: ISCC.exe packaging\installer.iss   (requires Inno Setup 6)
; Input:   dist\Parrotype\  (PyInstaller onedir build)
; Output:  dist\ParrotypeSetup.exe

#define AppName "Parrotype"
#define AppVersion "0.1.0"
#define AppExe "Parrotype.exe"

[Setup]
AppId={{7E1B4A83-9C93-4A5E-A0B7-PARROTYPE01}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=ParrotypeSetup
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "autostart"; Description: "{cm:AutoStartProgram,{#AppName}}"; \
    GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\Parrotype\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autostartup}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: autostart

[Run]
; The app itself shows the first-run wizard on first start.
Filename: "{app}\{#AppExe}"; Description: "{cm:LaunchProgram,{#AppName}}"; \
    Flags: nowait postinstall skipifsilent
