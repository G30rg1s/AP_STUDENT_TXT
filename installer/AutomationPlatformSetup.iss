
#define MyAppName "Automation Platform"
#define MyAppVersion "1.0.1"
#define MyAppPublisher "Automation Platform"
#define MyAppExeName "AutomationPlatformLauncher.exe"

; ============================================
; WINDOWS SETUP - TEST BUILD
; Source: dist-test
; ============================================

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

; Keep the previous installer untouched.
OutputDir=..\installer-output-test
OutputBaseFilename=AutomationPlatform-Setup-Test

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


; ============================================
; APPLICATION FILES
; ============================================

[Files]

; Install the complete NEW PyInstaller build.
;
; PyInstaller was configured with:
; contents_directory="."
;
; Therefore the executable, Python runtime,
; compose.yaml, icon and Docker files are all
; included in the same distribution tree.
;
; Do not copy the developer's .env file.

Source: "..\dist-test\AutomationPlatformLauncher\*"; DestDir: "{app}"; Excludes: ".env"; Flags: ignoreversion recursesubdirs createallsubdirs


; ============================================
; SHORTCUTS
; ============================================

[Icons]

; Main Launcher - Start Menu
Name: "{autoprograms}\Automation Platform Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AutomationPlatform.ico"

; Main Launcher - Desktop
Name: "{autodesktop}\Automation Platform Launcher"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\AutomationPlatform.ico"


; ============================================
; RUN AFTER INSTALLATION
; ============================================

[Run]

Filename: "{app}\{#MyAppExeName}"; Description: "Launch Automation Platform"; Flags: nowait postinstall skipifsilent


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

  { Windows cryptographically secure random generator }
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

  { Never overwrite configuration from an earlier installation. }
  if FileExists(EnvFile) then
  begin
    Log('Existing .env preserved.');
    Exit;
  end;

  Content :=
    '# Automation Platform - Student Configuration' + #13#10 +
    '# Automatically generated during installation' + #13#10 +
        '# Do not publish this file' + #13#10#13#10 +
        'JWT_SECRET=' + GenerateJwtSecret() + #13#10 +
    'MYSQL_PASSWORD=1234' + #13#10 +
    'MYSQL_ROOT_PASSWORD=1234' + #13#10 +
    'APP_PORT=8080' + #13#10;

  if not SaveStringToFile(EnvFile, Content, False) then
  begin
    RaiseException(
      'Unable to create the application .env file.'
    );
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
