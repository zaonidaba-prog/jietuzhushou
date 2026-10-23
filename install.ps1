$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $proj "dist\JieTuZhuShou"
$target = Join-Path $env:LOCALAPPDATA "Programs\JieTuZhuShou"

if (-not (Test-Path (Join-Path $source "JieTuZhuShou.exe"))) {
    throw "请先运行 build.ps1 完成打包。"
}

if (Test-Path $target) {
    Remove-Item -LiteralPath $target -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $target | Out-Null
Copy-Item -Path (Join-Path $source "*") -Destination $target -Recurse -Force

$exe = Join-Path $target "JieTuZhuShou.exe"
$shell = New-Object -ComObject WScript.Shell

# Build the Chinese shortcut name from code points so this script stays encoding-safe.
$appName = [string]([char]0x622A) + [char]0x56FE + [char]0x52A9 + [char]0x624B
$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = Join-Path $desktop ($appName + ".lnk")
$shortcut = $shell.CreateShortcut($lnk)
$shortcut.TargetPath = $exe
$shortcut.WorkingDirectory = $target
$shortcut.IconLocation = "$exe,0"
$shortcut.Description = "截图识字 + 本地剪贴板历史"
$shortcut.Save()

$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Item -ItemType Directory -Force -Path $startMenu | Out-Null
$startLnk = Join-Path $startMenu ($appName + ".lnk")
$shortcut2 = $shell.CreateShortcut($startLnk)
$shortcut2.TargetPath = $exe
$shortcut2.WorkingDirectory = $target
$shortcut2.IconLocation = "$exe,0"
$shortcut2.Description = "截图识字 + 本地剪贴板历史"
$shortcut2.Save()

Write-Host "已安装到：$target"
Write-Host "桌面快捷方式：$lnk"
Write-Host "开始菜单快捷方式：$startLnk"
