param(
    [int[]]$Ports = @(8000, 5173)
)

$ErrorActionPreference = "SilentlyContinue"

function Stop-ProcessTree {
    param([int]$ProcessId)

    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $ProcessId"
    foreach ($child in $children) {
        Stop-ProcessTree -ProcessId ([int]$child.ProcessId)
    }

    if ($ProcessId -ne $PID) {
        Stop-Process -Id $ProcessId -Force
    }
}

$targetIds = New-Object System.Collections.Generic.HashSet[int]

foreach ($port in $Ports) {
    $listeners = Get-NetTCPConnection -LocalPort $port -State Listen
    foreach ($listener in $listeners) {
        [void]$targetIds.Add([int]$listener.OwningProcess)
    }
}

$patterns = @(
    "app.main:app",
    "app.worker",
    "start-dev.ps1",
    "vite --host 127.0.0.1 --port",
    "npm run dev"
)

$processes = Get-CimInstance Win32_Process
foreach ($process in $processes) {
    $commandLine = [string]$process.CommandLine
    if (-not $commandLine) {
        continue
    }
    foreach ($pattern in $patterns) {
        if ($commandLine -like "*$pattern*") {
            [void]$targetIds.Add([int]$process.ProcessId)
            break
        }
    }
}

if ($targetIds.Count -eq 0) {
    Write-Host "No Competitive Agent dev processes found."
    exit 0
}

Write-Host "Stopping Competitive Agent dev processes:"
foreach ($processId in $targetIds) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId = $processId"
    if ($process) {
        Write-Host ("- pid={0} name={1} command={2}" -f $process.ProcessId, $process.Name, $process.CommandLine)
    }
}

foreach ($processId in ($targetIds | Sort-Object -Descending)) {
    Stop-ProcessTree -ProcessId ([int]$processId)
}

Write-Host "Done."
