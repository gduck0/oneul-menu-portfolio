. "$PSScriptRoot\Common.ps1"
Stop-OwnedServers @(Get-ServerState)
Save-ServerState @()
& "$PSScriptRoot\Stop-Database.ps1"
Write-Output '프로젝트 서버를 중지했습니다.'
