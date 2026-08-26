# Install Python/Node deps preferring Chabokan mirrors (Iran).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "==> pip (Chabokan mirror first)"
$pipArgs = @(
  "install", "-r", "backend/requirements.txt",
  "-i", "https://mirror2.chabokan.net/pypi/simple/",
  "--trusted-host", "mirror2.chabokan.net"
)
try {
  python -m pip @pipArgs
} catch {
  Write-Host "Chabokan pip failed; falling back to PyPI"
  python -m pip install -r backend/requirements.txt
}

Write-Host "==> pip pc_client"
try {
  python -m pip install -r pc_client/requirements.txt -i https://mirror2.chabokan.net/pypi/simple/ --trusted-host mirror2.chabokan.net
} catch {
  python -m pip install -r pc_client/requirements.txt
}

Write-Host "==> npm web (Chabokan registry first)"
Set-Location "$Root\web"
if (-not (Test-Path .npmrc)) {
  "registry=https://mirror2.chabokan.net/npm/" | Out-File -Encoding utf8 .npmrc
}
try {
  npm install
} catch {
  Write-Host "Chabokan npm failed; falling back to registry.npmjs.org"
  npm install --registry=https://registry.npmjs.org/
}

Write-Host "Done."
