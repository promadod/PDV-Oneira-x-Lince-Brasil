#!/usr/bin/env bash
# Exporta dados do db.sqlite3 (produção) para JSON.
# Execute na máquina local, com o arquivo db.sqlite3 na raiz do projeto.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p data/exports backups

if [[ ! -f db.sqlite3 ]]; then
  echo "ERRO: db.sqlite3 não encontrado em $ROOT"
  exit 1
fi

STAMP="$(date +%Y%m%d_%H%M%S)"
cp -f db.sqlite3 "backups/db_producao_${STAMP}.sqlite3"
echo "Backup: backups/db_producao_${STAMP}.sqlite3"

echo "Exportando dumpdata..."
python manage.py dumpdata \
  --settings=setup.settings_sqlite_export \
  --natural-foreign \
  --natural-primary \
  -e contenttypes \
  -e auth.Permission \
  -e sessions.Session \
  --indent 2 \
  -o "data/exports/sqlite_dump.json"

echo "OK: data/exports/sqlite_dump.json"
ls -lh data/exports/sqlite_dump.json
