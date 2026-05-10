param(
    [switch]$Clean,
    [switch]$FullRag
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
}

if ($Clean) {
    Remove-Item -Recurse -Force ".\build", ".\dist" -ErrorAction SilentlyContinue
}

python -m pip install -r requirements.txt

$PyInstallerArgs = @(
    "--noconfirm",
    "--clean",
    "--onefile",
    "--name", "CryptoRadar",
    "main.py"
)

if ($FullRag) {
    $PyInstallerArgs = @(
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name", "CryptoRadar",
        "--collect-all", "chromadb",
        "--collect-all", "sentence_transformers",
        "main.py"
    )
}

python -m PyInstaller @PyInstallerArgs

New-Item -ItemType Directory -Force ".\dist\data", ".\dist\models\model_reports", ".\dist\logs", ".\dist\exports", ".\dist\backups", ".\dist\knowledge" | Out-Null
Copy-Item ".\config.yaml" ".\dist\config.yaml" -Force
Copy-Item ".\.env.example" ".\dist\.env.example" -Force

Write-Host "CryptoRadar EXE created at: $ProjectRoot\dist\CryptoRadar.exe"
Write-Host "Double-clicking the EXE starts the full notification-only automation pipeline."
