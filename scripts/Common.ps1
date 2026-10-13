$ErrorActionPreference = 'Stop'
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$LocalRoot = Join-Path $ProjectRoot '.local'
$StatePath = Join-Path $LocalRoot 'server-state.json'

function Get-LocalPort($settings, [string]$name, [int]$fallback) {
    if ($null -eq $settings -or $null -eq $settings.PSObject.Properties[$name]) { return $fallback }
    $value = 0
    if (-not [int]::TryParse([string]$settings.$name, [ref]$value) -or $value -lt 1024 -or $value -gt 65535) {
        throw "로컬 포트는 1024~65535 범위의 정수여야 합니다: $name"
    }
    return $value
}

$localSettings = $null
$localSettingsPath = Join-Path $ProjectRoot '.runtime.local.json'
if (Test-Path -LiteralPath $localSettingsPath) { $localSettings = Get-Content -LiteralPath $localSettingsPath -Raw | ConvertFrom-Json }
$BackendPort = Get-LocalPort $localSettings 'backend_port' 18080
$FrontendPort = Get-LocalPort $localSettings 'frontend_port' 15173
if ($BackendPort -eq $FrontendPort) { throw '화면과 API의 포트는 서로 달라야 합니다.' }
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"

function Get-Runtime {
    $settingsPath = Join-Path $ProjectRoot '.runtime.local.json'
    if (Test-Path -LiteralPath $settingsPath) {
        $settings = Get-Content -LiteralPath $settingsPath -Raw | ConvertFrom-Json
    } else {
        $settings = [pscustomobject]@{
            node = (Get-Command node -ErrorAction Stop).Source
            pnpm = (Get-Command pnpm.cmd -ErrorAction Stop).Source
        }
    }
    if (-not (Test-Path -LiteralPath $settings.node)) { throw 'Node 실행 파일을 찾을 수 없습니다.' }
    return $settings
}

function Get-ServerState {
    if (Test-Path -LiteralPath $StatePath) {
        return @(Get-Content -LiteralPath $StatePath -Raw | ConvertFrom-Json)
    }
    return @()
}

function Save-ServerState($entries) {
    New-Item -ItemType Directory -Path $LocalRoot -Force | Out-Null
    ConvertTo-Json -InputObject @($entries) -Depth 4 | Set-Content -LiteralPath $StatePath -Encoding utf8
}

function Get-OwnedProcess($entry) {
    try { $candidate = Get-Process -Id $entry.processId -ErrorAction Stop } catch { return $null }
    if ($candidate.StartTime.ToUniversalTime().Ticks.ToString() -ne $entry.startTicks) { return $null }
    if ($candidate.Path -ne $entry.executable) { return $null }
    return $candidate
}

function Stop-OwnedServers($entries) {
    foreach ($entry in $entries) {
        $owned = Get-OwnedProcess $entry
        if ($null -ne $owned) {
            & taskkill.exe /PID $owned.Id /T /F | Out-Null
            if ($LASTEXITCODE -ne 0) { throw "프로세스를 중지하지 못했습니다: $($entry.name)" }
        }
    }
}

function Wait-ForService([string]$url, [bool]$checkIdentity = $false) {
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        try {
            $response = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
            if ($response.StatusCode -eq 200) {
                if ($checkIdentity) {
                    $body = $response.Content | ConvertFrom-Json
                    if ($body.status -eq 'ok' -and $body.service -eq 'oneul-menu') { return }
                } else { return }
            }
        } catch { }
        Start-Sleep -Milliseconds 250
    }
    throw "서버 응답을 확인하지 못했습니다: $url"
}
