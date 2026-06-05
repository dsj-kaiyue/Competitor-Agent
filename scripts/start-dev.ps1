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
$logDir = Join-Path $repoRoot "logs\dev"
$stamp = Get-Date -Format "yyyyMMdd-HHmmss"

New-Item -ItemType Directory -Force -Path $logDir | Out-Null

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

function Test-PortListening {
    param([int]$Port)
    $listeners = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $listeners
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    $process = Get-Process -Id $ProcessId -ErrorAction SilentlyContinue
    if ($process) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Start-DevProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$Arguments,
        [string]$WorkingDirectory,
        [string]$Url
    )

    $stdout = Join-Path $logDir "$Name-$stamp.out.log"
    $stderr = Join-Path $logDir "$Name-$stamp.err.log"

    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $Arguments `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $stdout `
        -RedirectStandardError $stderr `
        -WindowStyle Hidden `
        -PassThru

    [PSCustomObject]@{
        Name = $Name
        Process = $process
        Url = $Url
        StdOut = $stdout
        StdErr = $stderr
        ReportedExit = $false
    }
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
    throw "npm was not found in PATH. Install Node.js dependencies before starting the frontend."
}

$services = @()

Write-Host ""
Write-Host "Starting Competitive Agent dev services..."
Write-Host "Repository : $repoRoot"
Write-Host "Logs       : $logDir"
Write-Host ""

if (Test-PortListening -Port $ApiPort) {
    Write-Warning "FastAPI port $ApiPort is already listening. Skipping FastAPI startup."
} else {
    $apiArgs = @("-m", "uvicorn", "app.main:app", "--host", $HostAddress, "--port", "$ApiPort")
    if (-not $NoReload) {
        $apiArgs += "--reload"
    }
    $services += Start-DevProcess `
        -Name "fastapi" `
        -FilePath $python `
        -Arguments $apiArgs `
        -WorkingDirectory $backendDir `
        -Url "http://$HostAddress`:$ApiPort"
}

$services += Start-DevProcess `
    -Name "celery" `
    -FilePath $python `
    -Arguments @("-m", "celery", "-A", "app.worker", "worker", "--loglevel=info", "--pool=solo") `
    -WorkingDirectory $backendDir `
    -Url ""

if (Test-PortListening -Port $FrontendPort) {
    Write-Warning "Vue dev server port $FrontendPort is already listening. Skipping Vue startup."
} else {
    $services += Start-DevProcess `
        -Name "vue" `
        -FilePath $npmCommand.Source `
        -Arguments @("run", "dev", "--", "--host", $HostAddress, "--port", "$FrontendPort") `
        -WorkingDirectory $frontendDir `
        -Url "http://$HostAddress`:$FrontendPort"
}

Write-Host "Started services:"
foreach ($service in $services) {
    $urlText = if ($service.Url) { " | $($service.Url)" } else { "" }
    Write-Host ("- {0} pid={1}{2}" -f $service.Name, $service.Process.Id, $urlText)
    Write-Host ("  stdout: {0}" -f $service.StdOut)
    Write-Host ("  stderr: {0}" -f $service.StdErr)
}

Write-Host ""
Write-Host "Open:"
Write-Host "- Frontend : http://$HostAddress`:$FrontendPort"
Write-Host "- FastAPI  : http://$HostAddress`:$ApiPort"
Write-Host "- API docs : http://$HostAddress`:$ApiPort/docs"
Write-Host ""
Write-Host "Keep this window open. Press Ctrl+C to stop services started by this script."

try {
    while ($true) {
        foreach ($service in $services) {
            $service.Process.Refresh()
            if ($service.Process.HasExited -and -not $service.ReportedExit) {
                $service.ReportedExit = $true
                Write-Warning ("{0} exited with code {1}. Check stderr: {2}" -f $service.Name, $service.Process.ExitCode, $service.StdErr)
            }
        }
        Start-Sleep -Seconds 2
    }
}
finally {
    Write-Host ""
    Write-Host "Stopping dev services..."
    foreach ($service in $services) {
        $service.Process.Refresh()
        if (-not $service.Process.HasExited) {
            Write-Host ("Stopping {0} pid={1}" -f $service.Name, $service.Process.Id)
            Stop-ProcessTree -ProcessId $service.Process.Id
        }
    }
    Write-Host "Done."
}
