$ErrorActionPreference = "Stop"
$proj = Split-Path -Parent $MyInvocation.MyCommand.Path
$py = Join-Path $proj ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    throw "找不到虚拟环境：$py"
}

Set-Location $proj
& $py -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "JieTuZhuShou" `
    --icon "$proj\assets\icon.ico" `
    --add-data "$proj\assets;assets" `
    --collect-all rapidocr_onnxruntime `
    --collect-all onnxruntime `
    --collect-all cv2 `
    --exclude-module PySide6.QtWebEngineCore `
    --exclude-module PySide6.QtWebEngineWidgets `
    --exclude-module PySide6.QtWebEngineQuick `
    --exclude-module PySide6.QtPdf `
    --exclude-module PySide6.QtPdfWidgets `
    "$proj\app.py"

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller 打包失败，退出码 $LASTEXITCODE"
}

Write-Host ""
Write-Host "打包完成：$proj\dist\JieTuZhuShou\JieTuZhuShou.exe"
