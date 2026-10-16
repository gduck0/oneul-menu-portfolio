. "$PSScriptRoot\Common.ps1"
$testTemp = Join-Path $LocalRoot ('test-files-' + [guid]::NewGuid().ToString('N'))
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & (Join-Path $ProjectRoot '.venv\Scripts\python.exe') -m pytest -q --basetemp $testTemp
    if ($LASTEXITCODE -ne 0) { throw '백엔드 검증에 실패했습니다.' }
} finally { Pop-Location }
