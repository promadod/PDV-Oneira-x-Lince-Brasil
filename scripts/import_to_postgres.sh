#!/usr/bin/env bash
# Importa data/exports/sqlite_dump.json no Postgres (já migrado).
# Preferível rodar via: docker compose exec web bash scripts/import_to_postgres.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

DUMP="${1:-data/exports/sqlite_dump.json}"
if [[ ! -f "$DUMP" ]]; then
  echo "ERRO: dump não encontrado: $DUMP"
  exit 1
fi

echo "Aplicando migrate (schema)..."
python manage.py migrate --noinput

echo "Importando $DUMP ..."
python manage.py loaddata "$DUMP"

echo "OK — dados carregados. Verifique login e contagens no admin."
