param([ValidateSet('dev', 'test')][string]$Target = 'dev')
. "$PSScriptRoot\Common.ps1"
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'db_manage.py') migrate --target $Target
if ($LASTEXITCODE -ne 0) { throw '마이그레이션에 실패했습니다.' }
