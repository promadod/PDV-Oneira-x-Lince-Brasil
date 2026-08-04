# Guia — Observabilidade (Prometheus + Grafana + logs JSON + alertas)

Stack no Contabo: **6 vCPU / 11 GB RAM** — cabe com folga (~1 GB usados pelo PDV).

Serviços adicionais (rede Docker + portas só em `127.0.0.1`):

| Serviço | Porta local | Função |
|---------|-------------|--------|
| Grafana | 3000 | Dashboards (CPU, RAM, latência API) |
| Prometheus | 9090 | Métricas e regras de alerta |
| Alertmanager | 9093 | Envio de e-mail (quando SMTP configurado) |
| node-exporter | 9100 (interno) | CPU/RAM/disco do host |
| cAdvisor | 8080 (interno) | RAM/CPU dos containers |
| Django `/metrics` | só rede Docker | Latência e RPS da API |

**Não** ficam públicos na internet (nginx bloqueia `/metrics`; Grafana/Prometheus só em localhost).

---

## 1. Subir no Contabo

No servidor (`/opt/pdv/app`), após o merge em `develop`:

```bash
bash /opt/pdv/app/deploy/update.sh
```

Ou manualmente:

```bash
cd /opt/pdv/app
chmod +x deploy/observability/alertmanager-entrypoint.sh
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d --build
```

---

## 2. Acessar Grafana (túnel SSH)

No **seu PC** (PowerShell):

```powershell
ssh -L 3000:127.0.0.1:3000 -L 9090:127.0.0.1:9090 root@207.244.248.73
```

Com o túnel aberto, no navegador:

1. Abra http://127.0.0.1:3000  
2. Login: user/senha do `.env` (`GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD`)  
   - Se não definiu ainda: `admin` / `troque-esta-senha` (**troque no `.env` e suba de novo o Grafana**)  
3. Menu **Dashboards** → pasta **PDV** → **PDV Contabo — Overview**

Prometheus: http://127.0.0.1:9090  
Alertas: http://127.0.0.1:9090/alerts  

---

## 3. Definir senha do Grafana (recomendado)

No Contabo, edite `/opt/pdv/app/.env`:

```env
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=uma-senha-forte
```

```bash
cd /opt/pdv/app
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d grafana
```

---

## 4. Ativar alerta por e-mail (CPU > 80%)

O alerta **HighHostCPU** dispara se a CPU média ficar **acima de 80% por 5 minutos**.

No `.env` do Contabo:

```env
SMTP_HOST=smtp.seudominio.com
SMTP_PORT=587
SMTP_USER=seu-usuario
SMTP_PASSWORD=sua-senha-ou-app-password
SMTP_FROM=alertas@oneirasistemas.com.br
SMTP_REQUIRE_TLS=true
ALERT_EMAIL_TO=seu-email@exemplo.com
```

Reinicie o Alertmanager:

```bash
cd /opt/pdv/app
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml up -d alertmanager
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml logs alertmanager --tail 30
```

Sem SMTP, o Alertmanager sobe em modo **noop** (não envia e-mail; regras do Prometheus continuam aparecendo na UI).

Teste de e-mail (opcional): em Prometheus → **Alerts** → quando a regra dispara, o Alertmanager deve logar o envio.

---

## 5. Logs JSON (por que está lento?)

Em produção, `LOG_JSON` padrão é ligado (`DEBUG=False`).

Ver requests com duração:

```bash
cd /opt/pdv/app
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml logs -f web
```

Exemplo de linha:

```json
{"ts":"...","level":"INFO","logger":"app_pdv.request","message":"request","request_id":"a1b2c3","method":"GET","path":"/relatorios/","status_code":200,"duration_ms":842.5,"user":"admin"}
```

Filtrar lentos (Linux):

```bash
docker compose ... logs web --tail 2000 | grep duration_ms | grep -E '"duration_ms": [0-9]{4,}'
```

Cada resposta HTTP também leva header `X-Request-ID` (para cruzar com o log).

---

## 6. Queries lentas no Postgres

Com o compose de observabilidade, o Postgres loga statements **≥ 500 ms**.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml -f docker-compose.observability.yml logs db --tail 100 | grep duration
```

---

## 7. Checklist “CPU 100% — e agora?”

1. Túnel SSH → Grafana Overview (CPU / containers / latência).  
2. Prometheus → Alerts (HighHostCPU ativo?).  
3. `docker stats` no servidor.  
4. Logs JSON do `web` (path + `duration_ms`).  
5. Logs do `db` (duration ≥ 500 ms).  

---

## 8. Impacto de recursos (estimado)

| Extra | RAM aproximada |
|-------|----------------|
| Prometheus | 200–400 MB |
| Grafana | 150–250 MB |
| Alertmanager | ~50 MB |
| node-exporter + cAdvisor | 100–200 MB |
| **Total** | **~0,6–1 GB** |

Servidor: **11 GB**, PDV atual ~350 MB → sobra folga.

Retenção Prometheus: **15 dias**.
