#!/usr/bin/env bash
set -euo pipefail
# Usage: DATABASE_URL=postgresql://aiws:pass@localhost:5432/aiworkspace ./scripts/backup-postgres.sh
OUT_DIR="${BACKUP_DIR:-./backups}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILE="$OUT_DIR/aiworkspace-$STAMP.sql"
pg_dump "$DATABASE_URL" > "$FILE"
echo "Wrote $FILE"
