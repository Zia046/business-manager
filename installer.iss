; Inno Setup script - builds BusinessManager-Setup.exe (a normal Windows installer wizard).
; GitHub Actions compiles it automatically. To build by hand: install Inno Setup, run build_exe.bat, then compile.
#ifndef AppVersion
  #define AppVersion "0.3.0"
#endif

[Setup]
AppId={{6F0B7C12-3D1A-4E8B-9C55-B07A1E2D4F61}
AppName=Business Manager
AppVersion={#AppVersion}
AppVerName=Business Manager {#AppVersion}
AppPublisher=Burhan Nexus
AppContact=03475093446
AppSupportPhone=03475093446
DefaultDirName={autopf}\Business Manager
DefaultGroupName=Business Manager
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=BusinessManager-Setup
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\BusinessManager.exe
UninstallDisplayName=Business Manager
InfoBeforeFile=installer_info.txt
WizardStyle=modern
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=admin
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &Desktop shortcut"; GroupDescription: "Shortcuts:"
Name: "startmenu"; Description: "Create a &Start Menu shortcut"; GroupDescription: "Shortcuts:"

[Files]
Source: "dist\BusinessManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autodesktop}\Business Manager"; Filename: "{app}\BusinessManager.exe"; IconFilename: "{app}\BusinessManager.exe"; Tasks: desktopicon
Name: "{autoprograms}\Business Manager\Business Manager"; Filename: "{app}\BusinessManager.exe"; Tasks: startmenu
Name: "{autoprograms}\Business Manager\Uninstall Business Manager"; Filename: "{uninstallexe}"; Tasks: startmenu

[Run]
Filename: "{app}\BusinessManager.exe"; Description: "Start Business Manager now"; Flags: nowait postinstall skipifsilent

; Your data (D:\BusinessManagerData) is deliberately NOT listed here, so uninstalling never deletes it.
