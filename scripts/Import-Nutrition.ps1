param(
    [Parameter(Mandatory=$true)][ValidateSet('dev', 'test')][string]$Target,
    [Parameter(Mandatory=$true)][string]$Source
)
. "$PSScriptRoot\Common.ps1"
& (Join-Path $ProjectRoot '.venv\Scripts\python.exe') (Join-Path $PSScriptRoot 'import_nutrition_catalog.py') --source $Source --target $Target
if ($LASTEXITCODE -ne 0) { throw '영양 자료 가져오기에 실패했습니다. 기존 자료는 유지됩니다.' }
