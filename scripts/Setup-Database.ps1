. "$PSScriptRoot\Common.ps1"
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'db_manage.py') setup
if ($LASTEXITCODE -ne 0) { throw 'DB 초기화에 실패했습니다. 기존 파일은 보존됩니다.' }
