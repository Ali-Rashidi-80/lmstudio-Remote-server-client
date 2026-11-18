# Honest QA: lint + types + pylint + compileall + tests (fails hard on any non-zero exit)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
$env:PYTHONPATH = "."

$Py = Join-Path $Root "backend\.venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python"
}

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "==> $Name"
    & $Command
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "QA FAILED at step: $Name (exit $LASTEXITCODE)"
    }
}

Invoke-Checked "ruff" { & $Py -m ruff check app tests ..\pc_client\main.py ..\pc_client\cipher_utils.py ..\cipher_utils.py }
# black writes summary to stderr; convert ErrorRecords to strings before Out-Host
Invoke-Checked "black --check" {
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $Py -m black --check app tests 2>&1 | ForEach-Object { "$_" } | Out-Host
    $ErrorActionPreference = $prevEap
}
Invoke-Checked "isort --check-only" { & $Py -m isort --check-only app tests }
Invoke-Checked "flake8" {
    & $Py -m flake8 app tests --max-line-length=100 --extend-ignore=E501,E203,E402
}
Invoke-Checked "mypy" { & $Py -m mypy app --ignore-missing-imports }
Invoke-Checked "pylint" { & $Py -m pylint app }
Invoke-Checked "compileall" { & $Py -m compileall -q app tests ..\pc_client }
Invoke-Checked "pytest" { & $Py -m pytest -q --tb=short }
Write-Host "QA OK"
