# 在桌面创建本程序的快捷方式（文件需保存为 UTF-8 with BOM，否则中文会乱码）
$ErrorActionPreference = 'Stop'

$here = $PSScriptRoot
if (-not $here) { $here = Split-Path -Parent $MyInvocation.MyCommand.Path }

$exe = Join-Path $here 'PDFTrans.exe'
if (-not (Test-Path -LiteralPath $exe)) {
    Write-Host '找不到 PDFTrans.exe。' -ForegroundColor Red
    Write-Host '请把本脚本放在程序目录（和 exe 同一层）再运行。' -ForegroundColor Yellow
    exit 1
}

$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'PDF论文翻译.lnk'

$shell = New-Object -ComObject WScript.Shell
$sc = $shell.CreateShortcut($lnk)
$sc.TargetPath = $exe
$sc.WorkingDirectory = (Split-Path -Parent $exe)
$sc.IconLocation = "$exe,0"
$sc.Description = 'PDF 文献翻译 · 划词即译'
$sc.WindowStyle = 1
$sc.Save()

Write-Host ''
Write-Host '已创建桌面快捷方式：' -NoNewline
Write-Host $lnk -ForegroundColor Green
Write-Host '双击桌面上的「PDF论文翻译」即可启动。'
