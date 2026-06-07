$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendScripts = Join-Path $projectRoot "backend\.venv\Scripts"
$launcherScript = Join-Path $projectRoot "tools\desktop_launcher.py"
$logDir = Join-Path $projectRoot "logs"
$bootstrapLog = Join-Path $logDir "web-bootstrap.log"

if (Test-Path -LiteralPath (Join-Path $backendScripts "python.exe")) {
    $python = Join-Path $backendScripts "python.exe"
} else {
    $python = "python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

try {
    & $python $launcherScript --build --mode web --no-splash
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        $message = "AI Interpreter web launcher exited with code $exitCode."
        Add-Content -LiteralPath $bootstrapLog -Value $message
        Write-Host $message
        Write-Host "See log: $bootstrapLog"
        Read-Host "Press Enter to close"
        exit $exitCode
    }
} catch {
    $message = "Failed to start AI Interpreter web launcher: $($_.Exception.Message)"
    Add-Content -LiteralPath $bootstrapLog -Value $message
    Write-Host $message
    Write-Host "See log: $bootstrapLog"
    Read-Host "Press Enter to close"
    exit 1
}
