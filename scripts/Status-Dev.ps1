. "$PSScriptRoot\Common.ps1"
foreach ($entry in @(Get-ServerState)) {
    $owned = Get-OwnedProcess $entry
    [pscustomobject]@{ service = $entry.name; running = ($null -ne $owned); processId = $entry.processId }
}
Wait-ForService "$BackendUrl/api/health" $true
Wait-ForService "$FrontendUrl/api/health" $true
Write-Output '백엔드와 프론트의 API 연결이 정상입니다.'
