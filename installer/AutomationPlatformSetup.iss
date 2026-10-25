
#define MyAppName "Automation Platform TXT"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "Automation Platform"
#define MyAppExeName "AutomationPlatformTXTLauncher.exe"

; ============================================
; STUDENT TXT - WINDOWS SETUP
; Separate installation from original Student
; ============================================

[Setup]

; UNIQUE APP ID - DO NOT USE OLD STUDENT ID
AppId=AutomationPlatformStudentTXT

AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}

DefaultDirName={localappdata}\Programs\Automation Platform TXT
DefaultGroupName=Automation Platform TXT
DisableProgramGroupPage=yes

PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible

; Dedicated output for new Student TXT installer
OutputDir=..\installer-output-txt
OutputBaseFilename=AutomationPlatformTXT-Setup

SetupIconFile=..\AutomationPlatform.ico
UninstallDisplayIcon={app}\AutomationPlatform.ico

Compression=lzma2
SolidCompression=yes

WizardStyle=modern

CloseApplications=yes
RestartApplications=no

; Never reuse the old Student installation path
UsePreviousAppDir=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"


; ============================================
; APPLICATION FILES
; ============================================

[Files]

; Includes:
; - New Student TXT Launcher
; - Python runtime
; - compose.yaml
; - MySQL initialization scripts
; - Icon
;
; Does NOT bundle:
; - Encrypted application TXT
; - Runner Docker image
; - GitHub tokens
; - Developer .env

Source: "..\dist\AutomationPlatformTXTLauncher\*"; DestDir: "{app}"; Excludes: ".env,.env.*,*.gvm.txt,*.key"; Flags: ignoreversion recursesubdirs createallsubdirs


; ============================================
; SHORTCUTS
; ============================================

[Icons]

; Start Menu
Name: "{autoprograms}\Automation Platform TXT Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AutomationPlatform.ico"

; Desktop
Name: "{autodesktop}\Automation Platform TXT Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AutomationPlatform.ico"


; ============================================
; RUN AFTER INSTALLATION
; ============================================

[Run]

Filename: "{app}\{#MyAppExeName}"; Description: "Launch Automation Platform TXT"; Flags: nowait postinstall skipifsilent


; ============================================
; SECURE ENVIRONMENT CONFIGURATION
; ============================================

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

  if BCryptGenRandom(0, Bytes[0], 32, 2) <> 0 then
  begin
    RaiseException(
      'Unable to generate a secure JWT secret.'
    );
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

  { Preserve existing settings during upgrades }
  if FileExists(EnvFile) then
  begin
    Log('Existing Student TXT .env preserved.');
    Exit;
  end;

  Content :=
    '# Automation Platform TXT Configuration' + #13#10 +
    '# Generated automatically during installation' + #13#10 +
    '# Do not publish this file' + #13#10#13#10 +
    'JWT_SECRET=' + GenerateJwtSecret() + #13#10 +
    'MYSQL_PASSWORD=1234' + #13#10 +
    'MYSQL_ROOT_PASSWORD=1234' + #13#10 +
    'APP_PORT=8080' + #13#10;

  if not SaveStringToFile(EnvFile, Content, False) then
  begin
    RaiseException(
      'Unable to create Student TXT .env file.'
    );
  end;

  Log('Student TXT .env file created.');
end;


procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    CreateEnvironmentFile();
  end;
end;
