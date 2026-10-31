#define MyAppName "Pentagon Island"
#define MyAppVersion "1.0.0"
#define MyAppExeName "PentagonIsland.exe"

[Setup]
AppId={{B86B65B1-3F62-4EA5-99C0-82F9D691B20C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
DefaultDirName={autopf}\Pentagon Island
DefaultGroupName=Pentagon Island
OutputDir=..\release
OutputBaseFilename=PentagonIsland-Setup-v1.0.0
Compression=lzma
SolidCompression=yes
WizardStyle=classic
PrivilegesRequired=lowest
UninstallDisplayIcon={app}\{#MyAppExeName}

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\PentagonIsland\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Pentagon Island"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\Pentagon Island"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Pentagon Island"; Flags: nowait postinstall skipifsilent
