#!/usr/bin/env bash
# Emite/renova certificado Let's Encrypt (webroot) para o PDV Contabo.
# Uso no servidor: bash deploy/issue_ssl.sh
set -euo pipefail

cd "$(dirname "$0")/.."
DOMAINS=(-d oneirasistemas.com.br -d www.oneirasistemas.com.br)
EMAIL="${LETSENCRYPT_EMAIL:-admin@oneirasistemas.com.br}"

echo "Garantindo volumes e nginx com ACME..."
mkdir -p deploy/nginx

# Fase HTTP-only para o desafio (se ainda não houver cert)
if [[ ! -f /var/lib/docker/volumes/app_certbot_certs/_data/live/oneirasistemas.com.br/fullchain.pem ]] \
   && ! docker compose -f docker-compose.yml -f docker-compose.prod.yml run --rm --entrypoint test certbot_helper 2>/dev/null; then
  :
fi

# Usa o volume do compose: sobe stack e certbot via docker
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d nginx

echo "Solicitando certificado..."
docker run --rm \
  -v app_certbot_www:/var/www/certbot \
  -v app_certbot_certs:/etc/letsencrypt \
  certbot/certbot certonly --webroot \
  -w /var/www/certbot \
  "${DOMAINS[@]}" \
  --email "$EMAIL" \
  --agree-tos \
  --no-eff-email \
  --non-interactive \
  --keep-until-expiring

echo "Recarregando nginx..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T nginx nginx -s reload || \
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d nginx

echo "OK — certificado emitido/renovado."
