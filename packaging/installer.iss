; Inno Setup script for the Parrotype installer.
; Compile: ISCC.exe packaging\installer.iss   (requires Inno Setup 6)
; Input:   dist\Parrotype\  (PyInstaller onedir build)
; Output:  dist\ParrotypeSetup.exe

#define AppName "Parrotype"
#define AppVersion "1.0.0"
#define AppExe "Parrotype.exe"

[Setup]
; Upgrade identity — do not change between releases.
AppId={{8565C990-68C4-443E-900B-28CA79F5907F}
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
; Brand art (dark panel, parrot mark, mint signature) — rendered by
; scripts\render_installer_art.py from the canonical SVG + theme colors.
; Inno picks the variant closest to the display scale.
WizardImageFile=..\assets\installer\wizard-100.bmp,..\assets\installer\wizard-200.bmp
WizardSmallImageFile=..\assets\installer\wizard-small-100.bmp,..\assets\installer\wizard-small-200.bmp
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
