. "$PSScriptRoot\Common.ps1"
$runtime = Get-Runtime
$python = Join-Path $ProjectRoot '.venv\Scripts\python.exe'
$vite = Join-Path $ProjectRoot 'frontend\node_modules\vite\bin\vite.js'
if (-not (Test-Path -LiteralPath $python)) { throw 'Python 가상환경을 먼저 준비하세요.' }
if (-not (Test-Path -LiteralPath $vite)) { throw '프론트 의존성을 먼저 설치하세요.' }

$existing = @(Get-ServerState)
$live = @($existing | Where-Object { $null -ne (Get-OwnedProcess $_) })
if ($live.Count -eq 2) {
    Wait-ForService "$BackendUrl/api/health" $true
    Wait-ForService "$FrontendUrl/api/health" $true
    Write-Output "이미 실행 중입니다: $FrontendUrl"
    exit 0
}
Stop-OwnedServers $live
Save-ServerState @()

foreach ($port in @($BackendPort, $FrontendPort)) {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $port)
    try { $listener.Start() } catch { throw "다른 프로그램이 포트 $port 을 사용 중입니다. 기존 프로그램은 변경하지 않습니다." }
    finally { $listener.Stop() }
}

$started = @()
$previousApiPort = [Environment]::GetEnvironmentVariable('ONEUL_API_PORT', 'Process')
$previousFrontendPort = [Environment]::GetEnvironmentVariable('ONEUL_FRONTEND_PORT', 'Process')
try {
    $backend = Start-Process -FilePath $python -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', [string]$BackendPort) -WorkingDirectory (Join-Path $ProjectRoot 'backend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LocalRoot 'backend.out.log') -RedirectStandardError (Join-Path $LocalRoot 'backend.err.log') -PassThru
    $started += [pscustomobject]@{ name = 'backend'; processId = $backend.Id; startTicks = $backend.StartTime.ToUniversalTime().Ticks.ToString(); executable = $python }
    Save-ServerState $started
    Wait-ForService "$BackendUrl/api/health" $true

    [Environment]::SetEnvironmentVariable('ONEUL_API_PORT', [string]$BackendPort, 'Process')
    [Environment]::SetEnvironmentVariable('ONEUL_FRONTEND_PORT', [string]$FrontendPort, 'Process')
    $frontend = Start-Process -FilePath $runtime.node -ArgumentList @(('"' + $vite + '"')) -WorkingDirectory (Join-Path $ProjectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $LocalRoot 'frontend.out.log') -RedirectStandardError (Join-Path $LocalRoot 'frontend.err.log') -PassThru
    $started += [pscustomobject]@{ name = 'frontend'; processId = $frontend.Id; startTicks = $frontend.StartTime.ToUniversalTime().Ticks.ToString(); executable = $runtime.node }
    Save-ServerState $started
    Wait-ForService $FrontendUrl
    Wait-ForService "$FrontendUrl/api/health" $true
    Write-Output "프론트: $FrontendUrl"
    Write-Output "백엔드: $BackendUrl/api/health"
} catch {
    Stop-OwnedServers $started
    Save-ServerState @()
    throw
} finally {
    [Environment]::SetEnvironmentVariable('ONEUL_API_PORT', $previousApiPort, 'Process')
    [Environment]::SetEnvironmentVariable('ONEUL_FRONTEND_PORT', $previousFrontendPort, 'Process')
}
