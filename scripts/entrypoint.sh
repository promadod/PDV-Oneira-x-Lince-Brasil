#!/bin/sh
set -e

echo "Aguardando PostgreSQL em ${POSTGRES_HOST:-db}:${POSTGRES_PORT:-5432}..."
python <<'PY'
import os, socket, time
host = os.getenv("POSTGRES_HOST", "db")
port = int(os.getenv("POSTGRES_PORT", "5432"))
for i in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print("PostgreSQL disponível.")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit("Timeout aguardando PostgreSQL")
PY

echo "Aplicando migrations..."
python manage.py migrate --noinput

echo "Coletando static files..."
python manage.py collectstatic --noinput

echo "Iniciando: $*"
exec "$@"
