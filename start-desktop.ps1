$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendScripts = Join-Path $projectRoot "backend\.venv\Scripts"
$launcherScript = Join-Path $projectRoot "tools\desktop_launcher.py"
$logDir = Join-Path $projectRoot "logs"
$bootstrapLog = Join-Path $logDir "desktop-bootstrap.log"

if (Test-Path -LiteralPath (Join-Path $backendScripts "pythonw.exe")) {
    $python = Join-Path $backendScripts "pythonw.exe"
} elseif (Test-Path -LiteralPath (Join-Path $backendScripts "python.exe")) {
    $python = Join-Path $backendScripts "python.exe"
} else {
    $python = "python"
}

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

try {
    $launcherArgs = "`"$launcherScript`" --build"
    Start-Process `
        -FilePath $python `
        -ArgumentList $launcherArgs `
        -WorkingDirectory $projectRoot `
        -WindowStyle Hidden
} catch {
    $message = "Failed to start AI Interpreter desktop launcher: $($_.Exception.Message)"
    Add-Content -LiteralPath $bootstrapLog -Value $message

    try {
        $shell = New-Object -ComObject WScript.Shell
        $shell.Popup("$message`n`nSee log:`n$bootstrapLog", 0, "AI Interpreter startup failed", 16) | Out-Null
    } catch {
        Add-Content -LiteralPath $bootstrapLog -Value "Unable to show startup failure popup."
    }

    exit 1
}
