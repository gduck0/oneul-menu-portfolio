. "$PSScriptRoot\Common.ps1"
Push-Location (Join-Path $ProjectRoot 'backend')
try {
    & (Join-Path $ProjectRoot '.venv\Scripts\python.exe') -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw '백엔드 검증에 실패했습니다.' }
} finally { Pop-Location }
