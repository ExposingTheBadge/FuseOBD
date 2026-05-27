; ═══════════════════════════════════════════════════════════════
; Fuse OBD — Ford Utility for Scanning & Engineering
; Inno Setup 6.3+ Visual Installer
; Build:  iscc.exe setup.iss
; ═══════════════════════════════════════════════════════════════

#define MyAppName        "Fuse OBD"
#define MyAppVersion     "2.0.0.7"
#define MyAppPublisher   "Brent Gordon"
#define MyAppURL         "https://fuseobd.com"
#define MyAppExeName     "FuseOBD.exe"
#define MyAppExeSource   "dist\FuseOBD-v2.0.0.7.exe"
#define MyDriversDir     "drivers"
#define MyOutputDir      "dist"

[Setup]
AppId={{F1BB5D9A-3C8E-4B2F-A7D1-9E6C0B4A8F5D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir={#MyOutputDir}
OutputBaseFilename=FuseOBD_Setup_v{#MyAppVersion}

; ── Compression ──
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes

; ── Visual ──
WizardStyle=modern
WizardSizePercent=120,120
SetupIconFile=fuse.ico
UninstallDisplayIcon={app}\fuse.ico

; ── Wizard images (create 164x314 and 55x58 BMPs, place in assets\) ──
; WizardImageFile=assets\wizard-sidebar.bmp
; WizardSmallImageFile=assets\wizard-small.bmp

; ── Pages (controls the visible page sequence) ──
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
DisableReadyPage=no
DisableFinishedPage=no

; ── Privileges ──
PrivilegesRequired=admin
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
MinVersion=10.0.17763

; ── Uninstall ──
Uninstallable=yes
CreateUninstallRegKey=yes

; ── Show license ──
LicenseFile=LICENSE

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Messages]
; ── Polish the wizard text ──
english.WelcomeLabel2=This will install [name] version [name/ver] on your computer.%n%n%nFuse OBD is a free, open-source Ford diagnostic tool — module scanner, fault reader, AI mechanic chat, key programming, factory settings access, and live PID monitoring. No dealer software required.
english.ClickNext=Click Next to continue, or Cancel to exit Setup.
english.SelectDirLabel3=Setup will install [name] into the following folder.%n%nTo continue, click Next. To choose a different folder, click Browse.
english.ReadyLabel2a=Setup is now ready to begin installing [name] on your computer.%n%nClick Install to continue with the installation.
english.FinishedHeadingLabel=Setup Completed — [name] is ready.
english.FinishedLabel=Setup has finished installing [name] on your computer.%n%nYou can now launch the application, browse the adapter drivers folder, or close this window.
english.BeveledLabel=Fuse OBD — Free & Open Source

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; \
  GroupDescription: "Additional shortcuts:"; Flags: checkedonce
Name: "launchafter"; Description: "&Launch {#MyAppName}"; \
  GroupDescription: "Ready:"; Flags: checkedonce

[Files]
; ── Main application (single 60 MB PyInstaller executable) ──
Source: "{#MyAppExeSource}";        DestDir: "{app}";              \
  DestName: "{#MyAppExeName}";       Flags: ignoreversion

; ── Application icon (for uninstall shortcut / file associations) ──
Source: "fuse.ico";                 DestDir: "{app}";              \
  Flags: ignoreversion skipifsourcedoesntexist

; ── Adapter drivers (FTDI, CH340, CP210x, J2534) ──
Source: "{#MyDriversDir}\*";        DestDir: "{app}\drivers";      \
  Flags: recursesubdirs createallsubdirs skipifsourcedoesntexist

; ── License ──
Source: "LICENSE";                  DestDir: "{app}";              \
  Flags: ignoreversion skipifsourcedoesntexist

; ── README ──
Source: "README.md";                DestDir: "{app}";              \
  Flags: ignoreversion skipifsourcedoesntexist isreadme

[Icons]
; ── Start Menu ──
Name: "{group}\{#MyAppName}";          Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\fuse.ico";       Comment: "Launch {#MyAppName}"
Name: "{group}\Adapter Drivers";        Filename: "{app}\drivers";        \
  Comment: "Browse adapter driver files (FTDI, CH340, CP210x)"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}";       \
  IconFilename: "{uninstallexe}"

; ── Desktop ──
Name: "{commondesktop}\{#MyAppName}";  Filename: "{app}\{#MyAppExeName}"; \
  IconFilename: "{app}\fuse.ico";       Tasks: desktopicon

[Run]
; ── 1. Launch app (user checkbox, skipped during silent auto-update) ──
Filename: "{app}\{#MyAppExeName}";     \
  Description: "{cm:LaunchProgram,{#MyAppName}}"; \
  Tasks: launchafter;                   \
  Flags: nowait postinstall skipifsilent skipifdoesntexist

; ── 2. Open drivers folder (optional, user checkbox) ──
Filename: "explorer.exe";              \
  Parameters: """{app}\drivers""";      \
  Description: "Open adapter &drivers folder"; \
  Flags: nowait postinstall skipifsilent unchecked

[Dirs]
Name: "{app}\drivers"

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
Type: files;          Name: "{commondesktop}\{#MyAppName}.lnk"

[InstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function IsSilent: Boolean;
begin
  Result := (Pos('/SILENT', UpperCase(GetCmdTail())) > 0) or
            (Pos('/VERYSILENT', UpperCase(GetCmdTail())) > 0);
end;

// Show welcome info even in silent (it gets skipped automatically)
procedure InitializeWizard;
begin
  // If you have wizard bitmap images, Inno Setup auto-loads them
end;

// Final step — notify user
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    if not IsSilent then
    begin
      // Interactive install completed — Finish page shows
    end;
  end;
end;

// Suppress restart prompt if not needed
function NeedRestart: Boolean;
begin
  Result := False;
end;

// Validate install path doesn't exist with stale files
function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = wpSelectDir then
  begin
    if DirExists(ExpandConstant('{app}')) then
    begin
      if not IsSilent then
      begin
        if MsgBox('Fuse OBD is already installed in this location.' + #13#10 +
                  'Continuing will overwrite the existing installation.' + #13#10#13#10 +
                  'Do you want to continue?', mbConfirmation, MB_YESNO) = IDNO then
        begin
          Result := False;
        end;
      end;
    end;
  end;
end;
