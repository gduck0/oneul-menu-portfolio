. "$PSScriptRoot\Common.ps1"
foreach ($entry in @(Get-ServerState)) {
    $owned = Get-OwnedProcess $entry
    [pscustomobject]@{ service = $entry.name; running = ($null -ne $owned); processId = $entry.processId }
}
Wait-ForService "$BackendUrl/api/health" $true
Wait-ForService "$FrontendUrl/api/health" $true
Wait-ForService "$FrontendUrl/api/ready" $true
& "$PSScriptRoot\Status-Database.ps1"
Write-Output '백엔드·프론트·DB 연결이 정상입니다.'
