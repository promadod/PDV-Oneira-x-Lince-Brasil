#!/bin/sh
set -eu

OUT="/etc/alertmanager/alertmanager.yml"

SMTP_HOST="${SMTP_HOST:-}"
SMTP_PORT="${SMTP_PORT:-587}"
SMTP_USER="${SMTP_USER:-}"
SMTP_PASSWORD="${SMTP_PASSWORD:-}"
SMTP_FROM="${SMTP_FROM:-alertas@oneirasistemas.com.br}"
ALERT_EMAIL_TO="${ALERT_EMAIL_TO:-}"
SMTP_REQUIRE_TLS="${SMTP_REQUIRE_TLS:-true}"

# YAML: aspas simples — escapar ' como ''
esc_sq() {
  printf '%s' "$1" | sed "s/'/''/g"
}

if [ -n "$SMTP_HOST" ] && [ -n "$ALERT_EMAIL_TO" ]; then
  echo "Alertmanager: e-mail ativo -> $ALERT_EMAIL_TO via $SMTP_HOST:$SMTP_PORT"
  cat > "$OUT" <<EOF
global:
  resolve_timeout: 5m
  smtp_smarthost: '$(esc_sq "$SMTP_HOST"):$(esc_sq "$SMTP_PORT")'
  smtp_from: '$(esc_sq "$SMTP_FROM")'
  smtp_auth_username: '$(esc_sq "$SMTP_USER")'
  smtp_auth_password: '$(esc_sq "$SMTP_PASSWORD")'
  smtp_require_tls: ${SMTP_REQUIRE_TLS}

route:
  receiver: 'email'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'email'
    email_configs:
      - to: '$(esc_sq "$ALERT_EMAIL_TO")'
        send_resolved: true
        headers:
          Subject: '[PDV Contabo] {{ .Status | toUpper }} {{ .CommonLabels.alertname }}'
EOF
else
  echo "Alertmanager: SMTP/ALERT_EMAIL_TO não configurados — alertas em modo noop (sem e-mail)."
  cat > "$OUT" <<'EOF'
global:
  resolve_timeout: 5m

route:
  receiver: 'noop'
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h

receivers:
  - name: 'noop'
EOF
fi

exec /bin/alertmanager \
  --config.file="$OUT" \
  --storage.path=/alertmanager \
  --web.listen-address=:9093
