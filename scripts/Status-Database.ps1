. "$PSScriptRoot\Common.ps1"
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'db_manage.py') status
if ($LASTEXITCODE -ne 0) { throw 'DB 상태 확인에 실패했습니다.' }
