# Honest QA: lint + types + tests (fails hard on any non-zero exit)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
$env:PYTHONPATH = "."

function Invoke-Checked {
    param([string]$Name, [scriptblock]$Command)
    Write-Host "==> $Name"
    & $Command
    if ($null -ne $LASTEXITCODE -and $LASTEXITCODE -ne 0) {
        throw "QA FAILED at step: $Name (exit $LASTEXITCODE)"
    }
}

Invoke-Checked "pip install QA deps" {
    python -m pip install -q ruff black isort flake8 mypy types-redis types-aiofiles pytest pytest-asyncio
}
Invoke-Checked "ruff" { python -m ruff check app tests }
# black may write emoji to stderr; do not treat that as failure
Invoke-Checked "black --check" {
    python -m black --check app tests 2>&1 | Out-Host
}
Invoke-Checked "isort --check-only" { python -m isort --check-only app tests }
Invoke-Checked "flake8" {
    python -m flake8 app tests --max-line-length=100 --extend-ignore=E501,E203,E402
}
Invoke-Checked "mypy" { python -m mypy app --ignore-missing-imports }
Invoke-Checked "pytest" { python -m pytest -q --tb=short }
Write-Host "QA OK"
