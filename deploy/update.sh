#!/usr/bin/env bash
# Deploy rápido na Contabo (pull develop + build + migrate + observabilidade).
# Uso no servidor: bash /opt/pdv/app/deploy/update.sh
set -euo pipefail

cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml)

echo "==> Atualizando código (develop)..."
git fetch origin
git checkout develop
git pull origin develop

chmod +x deploy/observability/alertmanager-entrypoint.sh || true

echo "==> Subindo stack produção + observabilidade..."
"${COMPOSE[@]}" up -d --build

echo "==> Migrations..."
"${COMPOSE[@]}" exec -T web python manage.py migrate --noinput

# Nginx resolve o IP de "web" na subida; após recreate do web, reinicia para evitar 502.
echo "==> Recarregando nginx (DNS upstream)..."
"${COMPOSE[@]}" restart nginx

echo "==> Status..."
"${COMPOSE[@]}" ps

echo "==> Health..."
sleep 2
curl -sf https://oneirasistemas.com.br/health/ || curl -sf http://127.0.0.1/health/ || true
echo
echo "Deploy OK"
echo "Grafana (túnel SSH): http://127.0.0.1:3000  |  Prometheus: http://127.0.0.1:9090"
echo "Ver guia: GUIA_OBSERVABILIDADE.md"
