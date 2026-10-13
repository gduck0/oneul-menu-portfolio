. "$PSScriptRoot\Common.ps1"
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'db_manage.py') start
if ($LASTEXITCODE -ne 0) { throw 'DB 시작에 실패했습니다.' }
