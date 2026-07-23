#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Installer,
    [string]$Output = "windows-installer-smoke.json",
    [string]$InstallRoot = $(Join-Path ($env:RUNNER_TEMP ?? $env:TEMP) "Pixelle Video Smoke"),
    [int]$Port = 8000,
    [int]$TimeoutSeconds = 90,
    [int]$InstallerTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

function Get-FileRecord {
    param([string]$Path)

    $file = Get-Item -LiteralPath $Path
    if (-not $file.PSIsContainer -and $file.Length -gt 0) {
        $hash = Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256
        return [ordered]@{
            name = $file.Name
            size_bytes = [int64]$file.Length
            sha256 = $hash.Hash.ToLowerInvariant()
        }
    }
    throw "artifact_invalid"
}

function Get-ListeningPids {
    param([int]$TargetPort)

    if (-not (Get-Command Get-NetTCPConnection -ErrorAction SilentlyContinue)) {
        throw "port_query_failed"
    }
    try {
        return @(
            Get-NetTCPConnection -State Listen -ErrorAction Stop |
                Where-Object {
                    $_.LocalAddress -eq "127.0.0.1" -and [int]$_.LocalPort -eq $TargetPort
                } |
                Select-Object -ExpandProperty OwningProcess -Unique
        )
    } catch {
        throw "port_query_failed"
    }
}

function Get-ListeningProcessRecords {
    param([int]$TargetPort)

    $records = @()
    foreach ($ownedPid in (Get-ListeningPids -TargetPort $TargetPort)) {
        try {
            $process = Get-Process -Id $ownedPid -ErrorAction Stop
            $executable = $process.ProcessName
            if ($process.Path) {
                $executable = Split-Path -Leaf $process.Path
            }
            $records += [ordered]@{
                pid = [int]$ownedPid
                name = $process.ProcessName
                executable = $executable
            }
        } catch {
            throw "process_query_failed"
        }
    }
    return $records
}

function Wait-Health {
    param([int]$TargetPort, [int]$Seconds)

    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$TargetPort/health" -TimeoutSec 3
            if ($health.status -eq "healthy") {
                $listeners = @(Get-ListeningProcessRecords -TargetPort $TargetPort)
                $sidecars = @(
                    $listeners | Where-Object {
                        $_.executable.ToLowerInvariant().StartsWith("pixelle-api")
                    }
                )
                if ($sidecars.Count -eq 0) {
                    throw "health_owner_invalid"
                }
                return [ordered]@{
                    passed = $true
                    listeners = $listeners
                }
            }
        } catch {
            if ($_.Exception.Message -eq "health_owner_invalid" -or $_.Exception.Message -eq "port_query_failed" -or $_.Exception.Message -eq "process_query_failed") {
                throw $_.Exception.Message
            }
            # The sidecar may still be starting; retry within the bounded window.
        }
        Start-Sleep -Milliseconds 1000
    } while ((Get-Date) -lt $deadline)
    return [ordered]@{
        passed = $false
        listeners = @()
    }
}

function Wait-PortReleased {
    param([int]$TargetPort, [int]$Seconds)

    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if ((Get-ListeningPids -TargetPort $TargetPort).Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

function Resolve-InstalledApp {
    param([string]$Root)

    $candidates = @(
        (Join-Path $Root "Pixelle Video.exe"),
        (Join-Path $Root "pixelle-video.exe"),
        (Join-Path $Root "pixelle_video.exe"),
        (Join-Path $Root "pixelle-video-desktop.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    $discovered = Get-ChildItem -Path $Root -Filter "*.exe" -File -Recurse -ErrorAction SilentlyContinue |
        Where-Object {
            $_.Name -in @("Pixelle Video.exe", "pixelle-video.exe", "pixelle_video.exe", "pixelle-video-desktop.exe")
        } |
        Select-Object -First 1
    if ($null -ne $discovered) {
        return $discovered.FullName
    }
    throw "installed_app_not_found"
}

function Stop-AppTree {
    param([System.Diagnostics.Process]$Process)

    if ($null -eq $Process) {
        return "not_started"
    }
    try {
        $Process.Refresh()
        if ($Process.HasExited) {
            return "already_exited"
        }
        if ($Process.CloseMainWindow() -and $Process.WaitForExit(30000)) {
            return "graceful"
        }
    } catch {
        # Fall through to a bounded process-tree stop so the port can be checked.
    }
    & taskkill.exe /PID $Process.Id /T /F | Out-Null
    if ($LASTEXITCODE -ne 0) {
        throw "process_tree_stop_failed"
    }
    return "process_tree_terminated"
}

function Stop-OwnSidecars {
    param([int]$TargetPort)

    $stopped = @()
    foreach ($listener in (Get-ListeningProcessRecords -TargetPort $TargetPort)) {
        if ($listener.executable.ToLowerInvariant().StartsWith("pixelle-api")) {
            Stop-Process -Id $listener.pid -Force -ErrorAction Stop
            $stopped += $listener.pid
        }
    }
    return $stopped
}

function Redact-ListenerRecords {
    param([object[]]$Records)

    return @(
        $Records | ForEach-Object {
            [ordered]@{
                name = $_.name
                executable = $_.executable
            }
        }
    )
}

function Get-SafeErrorCode {
    param([object]$ErrorRecord)

    $message = [string]$ErrorRecord.Exception.Message
    $known = @(
        "installer_missing",
        "installer_suffix_invalid",
        "artifact_invalid",
        "install_root_invalid",
        "installer_timeout",
        "installed_app_not_found",
        "port_preoccupied",
        "port_query_failed",
        "process_query_failed",
        "health_owner_invalid",
        "process_tree_stop_failed"
    )
    foreach ($code in $known) {
        if ($message -eq $code) {
            return $code
        }
    }
    if ($message -match "^installer_exit_(-?\d+)$") {
        return "installer_exit_$($Matches[1])"
    }
    if ($message -match "^(health_timeout|port_not_released)_cycle_[12]$") {
        return $message
    }
    return "smoke_failed"
}

$outputPath = [IO.Path]::GetFullPath($Output)
$startedAt = [DateTime]::UtcNow
$result = [ordered]@{
    schema_version = 1
    stage = "PROGRAM-ROLLOUT"
    batch = "windows-installer-smoke"
    platform = "windows"
    status = "running"
    installer = $null
    install = [ordered]@{ status = "not_run" }
    cycles = @()
    external_actions = 0
    final_publish_clicks = 0
    started_at = $startedAt.ToString("o")
}
$appProcess = $null
$passed = $false

try {
    $runnerTempRoot = ([IO.Path]::GetFullPath(($env:RUNNER_TEMP ?? $env:TEMP))).TrimEnd([char[]]@("\", "/"))
    $installRootFull = [IO.Path]::GetFullPath($InstallRoot)
    if ($installRootFull.Equals($runnerTempRoot, [StringComparison]::OrdinalIgnoreCase) -or
        -not $installRootFull.StartsWith("$runnerTempRoot\", [StringComparison]::OrdinalIgnoreCase)) {
        throw "install_root_invalid"
    }
    if (-not (Test-Path -LiteralPath $Installer -PathType Leaf)) {
        throw "installer_missing"
    }
    if ([IO.Path]::GetExtension($Installer).ToLowerInvariant() -ne ".exe") {
        throw "installer_suffix_invalid"
    }
    $result.installer = Get-FileRecord -Path $Installer

    $baselineListeners = @(Get-ListeningProcessRecords -TargetPort $Port)
    $result.preflight = [ordered]@{
        port = $Port
        listener_processes = Redact-ListenerRecords -Records $baselineListeners
        port_listening = $baselineListeners.Count -gt 0
    }
    if ($baselineListeners.Count -gt 0) {
        throw "port_preoccupied"
    }

    if (Test-Path -LiteralPath $installRootFull) {
        Remove-Item -LiteralPath $installRootFull -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $installRootFull | Out-Null
    $installProcess = Start-Process -FilePath $Installer -ArgumentList @("/S", "/D=$installRootFull") -PassThru
    if (-not $installProcess.WaitForExit($InstallerTimeoutSeconds * 1000)) {
        & taskkill.exe /PID $installProcess.Id /T /F | Out-Null
        throw "installer_timeout"
    }
    $result.install_process = [ordered]@{
        exit_code = [int]$installProcess.ExitCode
        timeout_seconds = $InstallerTimeoutSeconds
    }
    if ($installProcess.ExitCode -ne 0) {
        throw "installer_exit_$($installProcess.ExitCode)"
    }
    $appPath = Resolve-InstalledApp -Root $installRootFull
    $result.install = [ordered]@{
        status = "passed"
        mode = "nsis_silent"
        app_executable = [IO.Path]::GetFileName($appPath)
        app_path = "runner_temp/Pixelle Video Smoke/$([IO.Path]::GetFileName($appPath))"
    }

    foreach ($cycle in 1..2) {
        $appProcess = Start-Process -FilePath $appPath -PassThru
        $healthProbe = Wait-Health -TargetPort $Port -Seconds $TimeoutSeconds
        $healthPassed = [bool]$healthProbe.passed
        $cycleRecord = [ordered]@{
            cycle = $cycle
            process_started = $true
            health = if ($healthPassed) { "passed" } else { "failed" }
            listener_processes = Redact-ListenerRecords -Records $healthProbe.listeners
            listener_owner_verified = $healthPassed
            close = "not_run"
            port_released = $false
        }
        if (-not $healthPassed) {
            $result.cycles += ,$cycleRecord
            throw "health_timeout_cycle_$cycle"
        }
        $cycleRecord.close = Stop-AppTree -Process $appProcess
        $cycleRecord.port_released = Wait-PortReleased -TargetPort $Port -Seconds 30
        $result.cycles += ,$cycleRecord
        $appProcess = $null
        if (-not $cycleRecord.port_released) {
            throw "port_not_released_cycle_$cycle"
        }
    }
    $result.status = "passed_with_boundary"
    $passed = $true
} catch {
    $result.status = "failed"
    $result.error_code = Get-SafeErrorCode -ErrorRecord $_
} finally {
    try {
        if ($null -ne $appProcess) {
            $result.cleanup = Stop-AppTree -Process $appProcess
        }
    } catch {
        $result.cleanup_error = "process_cleanup_failed"
        $result.status = "failed"
        $passed = $false
    }
    try {
        $result.cleanup_sidecars = @(Stop-OwnSidecars -TargetPort $Port)
    } catch {
        $result.cleanup_error = "sidecar_cleanup_failed"
        $result.status = "failed"
        $passed = $false
    }
    try {
        $result.cleanup_port_released = Wait-PortReleased -TargetPort $Port -Seconds 30
        if (-not $result.cleanup_port_released) {
            $result.status = "failed"
            $passed = $false
        }
    } catch {
        $result.cleanup_error = "port_cleanup_probe_failed"
        $result.cleanup_port_released = $false
        $result.status = "failed"
        $passed = $false
    }
    $result.finished_at = [DateTime]::UtcNow.ToString("o")
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outputPath -Encoding UTF8
    Write-Output ($result | ConvertTo-Json -Depth 10 -Compress)
}

if (-not $passed) {
    exit 1
}
