#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "==> pip (Chabokan mirror first)"
if ! python -m pip install -r backend/requirements.txt \
  -i https://mirror2.chabokan.net/pypi/simple/ \
  --trusted-host mirror2.chabokan.net; then
  echo "Chabokan pip failed; falling back to PyPI"
  python -m pip install -r backend/requirements.txt
fi

echo "==> pip pc_client"
python -m pip install -r pc_client/requirements.txt \
  -i https://mirror2.chabokan.net/pypi/simple/ \
  --trusted-host mirror2.chabokan.net || \
  python -m pip install -r pc_client/requirements.txt

echo "==> npm web"
cd "$ROOT/web"
printf 'registry=https://mirror2.chabokan.net/npm/\n' > .npmrc
npm install || npm install --registry=https://registry.npmjs.org/
echo "Done."
