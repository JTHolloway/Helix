; Inno Setup script — turns dist\Helix into a Windows installer.
;
;   iscc packaging\helix.iss
;
; Inno Setup is free, is the installer most small Windows applications use,
; and produces a single Setup.exe with an uninstaller and Start-menu entry.
; It runs on Windows only, which is why `build_app.py` mentions it rather
; than running it.
;
; NOT INTO Program Files BY DEFAULT. `PrivilegesRequired=lowest` installs
; into the user's own AppData, so no administrator password is needed —
; which matters because the people who want this program are as likely to
; be on a family computer they do not administer as on their own.

#define AppName    "Helix"
#define AppVersion "0.5.0"
#define AppExe     "Helix.exe"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=Helix
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=Helix-{#AppVersion}-Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern
DisableProgramGroupPage=yes
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\Helix\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}";           Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}";     Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Put a shortcut on the desktop"; \
  GroupDescription: "Shortcuts:"

; Double-clicking a .helix file opens it in Helix. Registered under HKCU so
; it works without an administrator.
[Registry]
Root: HKCU; Subkey: "Software\Classes\.helix"; ValueType: string; \
  ValueData: "Helix.Family"; Flags: uninsdeletevalue
Root: HKCU; Subkey: "Software\Classes\Helix.Family"; ValueType: string; \
  ValueData: "Helix family file"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Classes\Helix.Family\DefaultIcon"; \
  ValueType: string; ValueData: "{app}\{#AppExe},0"
Root: HKCU; Subkey: "Software\Classes\Helix.Family\shell\open\command"; \
  ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""

[Run]
Filename: "{app}\{#AppExe}"; Description: "Open Helix now"; \
  Flags: nowait postinstall skipifsilent
