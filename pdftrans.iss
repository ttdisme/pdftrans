; PDFTrans 安装包脚本（Inno Setup 6）
; 编译：ISCC.exe pdftrans.iss
; 产物：dist\PDFTrans-Setup-<版本>.exe

#define AppName "PDF 论文翻译"
#define AppNameEn "PDFTrans"
#define AppVersion "1.0.0"
#define AppExe "PDFTrans.exe"
#define AppRepo "https://github.com/ttdisme/pdftrans"

[Setup]
AppId={{9C1F2E7A-3B4D-4E8F-9A2C-7D5E6B1F0A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=ttdisme
AppPublisherURL={#AppRepo}
AppSupportURL={#AppRepo}/issues
AppUpdatesURL={#AppRepo}/releases
VersionInfoVersion=1.0.0.0
VersionInfoCompany=PDFTrans
VersionInfoDescription={#AppName} 安装程序
VersionInfoProductName={#AppName}
VersionInfoProductVersion=1.0.0.0

; 装到当前用户目录（%LOCALAPPDATA%\Programs），不需要管理员权限
PrivilegesRequired=lowest
DefaultDirName={autopf}\{#AppNameEn}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
UsePreviousAppDir=yes

LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=PDFTrans-Setup-{#AppVersion}
SetupIconFile=assets\app.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
AllowNoIcons=yes

[Languages]
Name: "zh"; MessagesFile: "tools\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式(&D)"; GroupDescription: "附加任务:"; Flags: checkedonce

[Files]
; 排除便携用的快捷方式脚本和运行时数据目录
Source: "dist\{#AppNameEn}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "创建桌面快捷方式.bat,创建桌面快捷方式.ps1,data\*"
Source: "assets\app.ico"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion isreadme
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\app.ico"; Comment: "多标签 PDF 阅读 + 划词翻译"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; IconFilename: "{app}\app.ico"; Comment: "多标签 PDF 阅读 + 划词翻译"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "立即运行 {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}\data"
