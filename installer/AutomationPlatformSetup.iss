
#define MyAppName "Automation Platform"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Automation Platform"
#define MyAppExeName "AutomationPlatformLauncher.exe"

[Setup]
AppId=AutomationPlatformStudent
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={localappdata}\Programs\Automation Platform
DefaultGroupName=Automation Platform
DisableProgramGroupPage=yes

PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible

OutputDir=..\installer-output
OutputBaseFilename=AutomationPlatform-Setup

SetupIconFile=..\AutomationPlatform.ico
UninstallDisplayIcon={app}\AutomationPlatform.ico

Compression=lzma2
SolidCompression=yes

WizardStyle=modern
WizardResizable=no

CloseApplications=yes
RestartApplications=no

UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
; The executable
Source: "..\dist\AutomationPlatformLauncher\AutomationPlatformLauncher.exe"; DestDir: "{app}"; Flags: ignoreversion

; PyInstaller runtime files
Source: "..\dist\AutomationPlatformLauncher\_internal\*"; DestDir: "{app}\_internal"; Flags: ignoreversion recursesubdirs createallsubdirs

; Our desktop icon
Source: "..\AutomationPlatform.ico"; DestDir: "{app}"; Flags: ignoreversion

; Docker Compose configuration
Source: "..\compose.yaml"; DestDir: "{app}"; Flags: ignoreversion

; MySQL initialization files
Source: "..\docker\mysql\init\*"; DestDir: "{app}\docker\mysql\init"; Flags: ignoreversion recursesubdirs createallsubdirs

; IMPORTANT:
; Never package the developer's .env file.

[Icons]
; Start Menu shortcut
Name: "{autoprograms}\Automation Platform Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AutomationPlatform.ico"

; Desktop shortcut
Name: "{autodesktop}\Automation Platform Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AutomationPlatform.ico"

[Run]
; Launch the application after installation
Filename: "{app}\{#MyAppExeName}"; Description: "Launch Automation Platform"; Flags: nowait postinstall skipifsilent

[Code]
function BCryptGenRandom(
  hAlgorithm: Integer;
  var pbBuffer: Byte;
  cbBuffer: Integer;
  dwFlags: Integer
): Integer;
  external 'BCryptGenRandom@bcrypt.dll stdcall';

function GenerateJwtSecret(): String;
var
  Bytes: array[0..31] of Byte;
  I: Integer;
begin
  Result := '';

  { Use Windows cryptographic random number generator }
  if BCryptGenRandom(0, Bytes[0], 32, 2) <> 0 then
  begin
    RaiseException('Unable to generate a secure JWT secret.');
  end;

  for I := 0 to 31 do
  begin
    Result := Result + Format('%.2x', [Bytes[I]]);
  end;
end;

procedure CreateEnvironmentFile();
var
  EnvFile: String;
  Content: String;
begin
  EnvFile := ExpandConstant('{app}\.env');

  { Never overwrite settings from an existing installation }
  if FileExists(EnvFile) then
  begin
    Log('Existing .env preserved.');
    Exit;
  end;

  Content :=
    '# Automation Platform - Student Configuration' + #13#10 +
    '# Automatically generated during installation' + #13#10 +
    'JWT_SECRET=' + GenerateJwtSecret() + #13#10 +
    'APP_PORT=8080' + #13#10;

  if not SaveStringToFile(EnvFile, Content, False) then
  begin
    RaiseException('Unable to create the application .env file.');
  end;

  Log('Student .env file created.');
end;

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CreateEnvironmentFile();
  end;
end;
