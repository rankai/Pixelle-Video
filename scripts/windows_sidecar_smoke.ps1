#requires -Version 7.0
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Sidecar,
    [string]$Output = "windows-sidecar-smoke.json",
    [int]$Port = 18080,
    [int]$TimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"

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

function Get-SafeErrorCode {
    param([object]$ErrorRecord)

    $message = [string]$ErrorRecord.Exception.Message
    if ($message -in @(
        "sidecar_missing",
        "sidecar_suffix_invalid",
        "artifact_invalid",
        "port_query_failed",
        "port_preoccupied",
        "process_start_failed"
    )) {
        return $message
    }
    if ($message -match "^sidecar_exit_(-?\d+)$") {
        return "sidecar_exit_$($Matches[1])"
    }
    return $message -like "health_timeout" ? "health_timeout" : "sidecar_smoke_failed"
}

function Wait-PortReleased {
    param([int]$TargetPort, [int]$Seconds = 30)

    $deadline = (Get-Date).AddSeconds($Seconds)
    do {
        if ((Get-ListeningPids -TargetPort $TargetPort).Count -eq 0) {
            return $true
        }
        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)
    return $false
}

$outputPath = [IO.Path]::GetFullPath($Output)
$runnerTempRoot = ([IO.Path]::GetFullPath(($env:RUNNER_TEMP ?? $env:TEMP))).TrimEnd([char[]]@("\", "/"))
$runtimeRoot = Join-Path $runnerTempRoot "Pixelle Sidecar Smoke"
$stdoutPath = Join-Path $runtimeRoot "sidecar.stdout.log"
$stderrPath = Join-Path $runtimeRoot "sidecar.stderr.log"
$result = [ordered]@{
    schema_version = 1
    stage = "PROGRAM-ROLLOUT"
    batch = "windows-sidecar-smoke"
    platform = "windows"
    status = "running"
    sidecar_executable = $null
    port = $Port
    process_started = $false
    health = "not_run"
    process_exit_code = $null
    stdout_present = $false
    stderr_present = $false
    external_actions = 0
    final_publish_clicks = 0
    started_at = [DateTime]::UtcNow.ToString("o")
}
$process = $null
$previousEnvironment = @{}

try {
    if (-not (Test-Path -LiteralPath $Sidecar -PathType Leaf)) {
        throw "sidecar_missing"
    }
    if ([IO.Path]::GetExtension($Sidecar).ToLowerInvariant() -ne ".exe") {
        throw "sidecar_suffix_invalid"
    }
    $file = Get-Item -LiteralPath $Sidecar
    if ($file.Length -le 0) {
        throw "artifact_invalid"
    }
    $result.sidecar_executable = $file.Name
    $baseline = @(Get-ListeningPids -TargetPort $Port)
    if ($baseline.Count -gt 0) {
        throw "port_preoccupied"
    }
    New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
    foreach ($name in @("PIXELLE_DESKTOP_MODE", "PIXELLE_DESKTOP_TOKEN", "PIXELLE_DESKTOP_ORIGIN", "PIXELLE_VIDEO_ROOT", "PIXELLE_CONFIG_PATH", "PIXELLE_ASSET_CENTER_V2", "PIXELLE_ASSET_CENTER_SMB_UX")) {
        $previousEnvironment[$name] = [Environment]::GetEnvironmentVariable($name)
    }
    $env:PIXELLE_DESKTOP_MODE = "1"
    $env:PIXELLE_DESKTOP_TOKEN = "windows-sidecar-smoke"
    $env:PIXELLE_DESKTOP_ORIGIN = "tauri://localhost"
    $env:PIXELLE_VIDEO_ROOT = $runtimeRoot
    $env:PIXELLE_CONFIG_PATH = Join-Path $runtimeRoot "config.yaml"
    $env:PIXELLE_ASSET_CENTER_V2 = "1"
    $env:PIXELLE_ASSET_CENTER_SMB_UX = "0"
    $process = Start-Process -FilePath $Sidecar -ArgumentList @("--host", "127.0.0.1", "--port", "$Port") -WorkingDirectory $runtimeRoot -RedirectStandardOutput $stdoutPath -RedirectStandardError $stderrPath -PassThru
    $result.process_started = $true
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if ($process.HasExited) {
            $result.process_exit_code = [int]$process.ExitCode
            throw "sidecar_exit_$($process.ExitCode)"
        }
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 3
            if ($health.status -eq "healthy") {
                $result.health = "passed"
                break
            }
        } catch {
            # Bounded startup retry; the final result is written below.
        }
        Start-Sleep -Milliseconds 1000
    } while ((Get-Date) -lt $deadline)
    if ($result.health -ne "passed") {
        throw "health_timeout"
    }
    $result.status = "passed_with_boundary"
} catch {
    $result.status = "failed"
    $result.error_code = Get-SafeErrorCode -ErrorRecord $_
} finally {
    try {
        if ($null -ne $process -and -not $process.HasExited) {
            & taskkill.exe /PID $process.Id /T /F | Out-Null
        }
    } catch {
        $result.cleanup_error = "process_cleanup_failed"
        $result.status = "failed"
    }
    try {
        $result.port_released = Wait-PortReleased -TargetPort $Port -Seconds 30
        if (-not $result.port_released) {
            $result.status = "failed"
            $result.cleanup_error = "port_not_released"
        }
    } catch {
        $result.status = "failed"
        $result.port_released = $false
        $result.cleanup_error = "port_cleanup_probe_failed"
    }
    $result.stdout_present = Test-Path -LiteralPath $stdoutPath -PathType Leaf
    $result.stderr_present = Test-Path -LiteralPath $stderrPath -PathType Leaf
    $result.finished_at = [DateTime]::UtcNow.ToString("o")
    $result | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $outputPath -Encoding UTF8
    Write-Output ($result | ConvertTo-Json -Depth 10 -Compress)
    foreach ($name in $previousEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $previousEnvironment[$name])
    }
}

if ($result.status -eq "failed") {
    exit 1
}
