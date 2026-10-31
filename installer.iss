; Inno Setup script (free: https://jrsoftware.org/isinfo.php). Build the exe first with build_exe.bat.
[Setup]
AppName=Business Manager
AppVersion=0.1.0
DefaultDirName={autopf}\BusinessManager
DefaultGroupName=Business Manager
OutputBaseFilename=BusinessManagerSetup
Compression=lzma
SolidCompression=yes
OutputDir=installer_output

[Files]
Source: "dist\BusinessManager.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Business Manager"; Filename: "{app}\BusinessManager.exe"
Name: "{autodesktop}\Business Manager"; Filename: "{app}\BusinessManager.exe"

[Run]
Filename: "{app}\BusinessManager.exe"; Description: "Start Business Manager"; Flags: nowait postinstall skipifsilent
; Note: user data lives in D:\BusinessManagerData and is NOT touched by installing, updating or uninstalling.
