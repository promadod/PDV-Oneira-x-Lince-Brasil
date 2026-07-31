#!/usr/bin/env bash
# Deploy rápido na Contabo (pull develop + build + migrate).
# Uso no servidor: bash /opt/pdv/app/deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."

echo "==> Atualizando código (develop)..."
git fetch origin
git checkout develop
git pull origin develop

echo "==> Subindo stack produção..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

echo "==> Migrations..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web \
  python manage.py migrate --noinput

echo "==> Status..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

echo "==> Health..."
curl -sf https://oneirasistemas.com.br/health/ || curl -sf http://127.0.0.1/health/ || true
echo
echo "Deploy OK"
