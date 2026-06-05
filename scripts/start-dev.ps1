param(
    [string]$PythonPath = "",
    [string]$HostAddress = "127.0.0.1",
    [int]$ApiPort = 8000,
    [int]$FrontendPort = 5173,
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$backendDir = Join-Path $repoRoot "backend"
$frontendDir = Join-Path $repoRoot "frontend"

function Resolve-PythonPath {
    if ($PythonPath) {
        return $PythonPath
    }
    if ($env:COMPETITOR_AGENT_PYTHON) {
        return $env:COMPETITOR_AGENT_PYTHON
    }
    $knownPath = "D:\Anaconda\envs\competitor-agent\python.exe"
    if (Test-Path $knownPath) {
        return $knownPath
    }
    return "python"
}

function Quote-PowerShellLiteral {
    param([string]$Value)
    return "'" + $Value.Replace("'", "''") + "'"
}

function Test-PortListening {
    param([int]$Port)
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $listeners
}

function Start-ForegroundWindow {
    param(
        [string]$Title,
        [string]$WorkingDirectory,
        [string]$CommandLine,
        [string]$Url = ""
    )

    $quotedTitle = Quote-PowerShellLiteral $Title
    $quotedWorkingDirectory = Quote-PowerShellLiteral $WorkingDirectory
    $urlLine = if ($Url) { "Write-Host 'URL: $Url'" } else { "" }
    $command = @"
`$ErrorActionPreference = 'Stop'
`$Host.UI.RawUI.WindowTitle = $quotedTitle
Set-Location -LiteralPath $quotedWorkingDirectory
Write-Host ''
Write-Host '== $Title =='
$urlLine
Write-Host 'Working directory: $WorkingDirectory'
Write-Host ''
$CommandLine
Write-Host ''
Write-Host 'Process exited. Press Enter to close this window.'
Read-Host | Out-Null
"@

    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    Start-Process `
        -FilePath "powershell.exe" `
        -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", $encoded) `
        -WindowStyle Normal
}

if (-not (Test-Path $backendDir)) {
    throw "Backend directory not found: $backendDir"
}
if (-not (Test-Path $frontendDir)) {
    throw "Frontend directory not found: $frontendDir"
}

$python = Resolve-PythonPath
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if (-not $npmCommand) {
    $npmCommand = Get-Command npm -ErrorAction SilentlyContinue
}
if (-not $npmCommand) {
    throw "npm was not found in PATH. Install Node.js before starting the frontend."
}

$quotedPython = Quote-PowerShellLiteral $python
$quotedNpm = Quote-PowerShellLiteral $npmCommand.Source

Write-Host ""
Write-Host "Starting Competitive Agent dev services in foreground windows..."
Write-Host "Repository : $repoRoot"
Write-Host ""

if (Test-PortListening -Port $ApiPort) {
    Write-Warning "FastAPI port $ApiPort is already listening. Run .\stop-dev.bat or change -ApiPort."
} else {
    $reloadArg = if ($NoReload) { "" } else { " --reload" }
    Start-ForegroundWindow `
        -Title "Competitive Agent - FastAPI" `
        -WorkingDirectory $backendDir `
        -CommandLine "& $quotedPython -m uvicorn app.main:app --host $HostAddress --port $ApiPort$reloadArg" `
        -Url "http://$HostAddress`:$ApiPort"
}

Start-ForegroundWindow `
    -Title "Competitive Agent - Celery" `
    -WorkingDirectory $backendDir `
    -CommandLine "& $quotedPython -m celery -A app.worker worker --loglevel=info --pool=solo"

if (Test-PortListening -Port $FrontendPort) {
    Write-Warning "Vue dev server port $FrontendPort is already listening. Run .\stop-dev.bat or change -FrontendPort."
} else {
    Start-ForegroundWindow `
        -Title "Competitive Agent - Vue" `
        -WorkingDirectory $frontendDir `
        -CommandLine "& $quotedNpm run dev -- --host $HostAddress --port $FrontendPort" `
        -Url "http://$HostAddress`:$FrontendPort"
}

Write-Host "Started visible service windows."
Write-Host "- FastAPI : http://$HostAddress`:$ApiPort"
Write-Host "- API docs: http://$HostAddress`:$ApiPort/docs"
Write-Host "- Vue     : http://$HostAddress`:$FrontendPort"
Write-Host ""
Write-Host "Stop services with Ctrl+C in each service window, by closing those windows, or by running .\stop-dev.bat."
