#!/bin/sh
set -eu

TPL="/etc/alertmanager/alertmanager.yml.tpl"
OUT="/etc/alertmanager/alertmanager.yml"

SMTP_HOST="${SMTP_HOST:-}"
SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASSWORD="${SMTP_PASSWORD:-}"
SMTP_FROM="${SMTP_FROM:-alertas@oneirasistemas.com.br}"
ALERT_EMAIL_TO="${ALERT_EMAIL_TO:-}"
SMTP_REQUIRE_TLS="${SMTP_REQUIRE_TLS:-true}"

if [ -n "$SMTP_HOST" ] && [ -n "$ALERT_EMAIL_TO" ]; then
  ALERT_RECEIVER="email"
  echo "Alertmanager: e-mail ativo -> $ALERT_EMAIL_TO via $SMTP_HOST:$SMTP_PORT"
else
  ALERT_RECEIVER="noop"
  echo "Alertmanager: SMTP/ALERT_EMAIL_TO não configurados — alertas em modo noop (sem e-mail)."
fi

# Escape simples para senhas com caracteres especiais em sed
esc() {
  printf '%s' "$1" | sed -e 's/[\\/&|]/\\&/g'
}

sed \
  -e "s|\${SMTP_HOST}|$(esc "$SMTP_HOST")|g" \
  -e "s|\${SMTP_PORT}|$(esc "$SMTP_PORT")|g" \
  -e "s|\${SMTP_USER}|$(esc "$SMTP_USER")|g" \
  -e "s|\${SMTP_PASSWORD}|$(esc "$SMTP_PASSWORD")|g" \
  -e "s|\${SMTP_FROM}|$(esc "$SMTP_FROM")|g" \
  -e "s|\${ALERT_EMAIL_TO}|$(esc "$ALERT_EMAIL_TO")|g" \
  -e "s|\${SMTP_REQUIRE_TLS}|$(esc "$SMTP_REQUIRE_TLS")|g" \
  -e "s|\${ALERT_RECEIVER}|$(esc "$ALERT_RECEIVER")|g" \
  "$TPL" > "$OUT"

exec /bin/alertmanager \
  --config.file="$OUT" \
  --storage.path=/alertmanager \
  --web.listen-address=:9093
