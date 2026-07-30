#!/usr/bin/env bash
# Bootstrap inicial do VPS Contabo (Ubuntu).
# Execute como root na primeira conexão:
#   curl -fsSL ... | bash
# ou copie este arquivo e: bash bootstrap_contabo.sh
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/pdv/app}"
DEPLOY_USER="${DEPLOY_USER:-deploy}"
REPO_URL="${REPO_URL:-https://github.com/promadod/PDV-Oneira-x-Lince-Brasil.git}"

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get upgrade -y
apt-get install -y git curl ufw ca-certificates

if ! command -v docker >/dev/null 2>&1; then
  curl -fsSL https://get.docker.com | sh
fi

if ! id -u "$DEPLOY_USER" >/dev/null 2>&1; then
  adduser --disabled-password --gecos "" "$DEPLOY_USER"
fi
usermod -aG docker,sudo "$DEPLOY_USER"

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

mkdir -p "$(dirname "$APP_DIR")"
if [[ ! -d "$APP_DIR/.git" ]]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
chown -R "$DEPLOY_USER:$DEPLOY_USER" "$(dirname "$APP_DIR")"

echo
echo "OK. Próximos passos (como $DEPLOY_USER):"
echo "  cd $APP_DIR"
echo "  cp .env.example .env && nano .env"
echo "  docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
echo
echo "Configure a chave SSH em /home/$DEPLOY_USER/.ssh/authorized_keys e deixe de usar root."
