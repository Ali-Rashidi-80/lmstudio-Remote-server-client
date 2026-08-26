# Start Bridge on host port 8010 (avoids clash with other services on :8000)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
$env:PYTHONPATH = "."
if (-not $env:PORT) { $env:PORT = "8010" }
# uvicorn binds HOST:PORT — use 8010 on host by default
python -m uvicorn app.main:app --host 127.0.0.1 --port ([int]$env:PORT)
