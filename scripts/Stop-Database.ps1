. "$PSScriptRoot\Common.ps1"
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'db_manage.py') stop
if ($LASTEXITCODE -ne 0) { throw 'DB 중지에 실패했습니다.' }
