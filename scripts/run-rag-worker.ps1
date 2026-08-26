# Run ARQ rag-worker against local Redis/Postgres
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
$env:PYTHONPATH = "."
if (-not $env:RAG_INGEST_MODE) { $env:RAG_INGEST_MODE = "arq" }
python -m arq app.workers.rag.WorkerSettings
