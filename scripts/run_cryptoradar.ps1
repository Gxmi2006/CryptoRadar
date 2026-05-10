param(
    [switch]$Mock
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir

Set-Location $ProjectRoot

Write-Host "CryptoRadar auto pipeline"
Write-Host "Project: $ProjectRoot"
Write-Host "Press Ctrl+C to stop."

if (Test-Path ".\.venv\Scripts\Activate.ps1") {
    . ".\.venv\Scripts\Activate.ps1"
} else {
    Write-Host "No .venv found. Using the current Python environment."
}

$ArgsList = @("main.py", "--auto-pipeline")
if ($Mock) {
    $ArgsList += "--mock"
}

python @ArgsList
