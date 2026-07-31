# Guia — desenvolvimento local, branch e deploy Contabo

Referência do fluxo PDV Oneira / Lince Brasil.

- **PC (código):** `c:\dev\contabo_pdv`
- **Contabo (produção):** `/opt/pdv/app`
- **Domínio:** https://oneirasistemas.com.br
- **Repo:** https://github.com/promadod/PDV-Oneira-x-Lince-Brasil
- **Branch de integração:** `develop` (hoje a Contabo também usa `develop`)

---

## 1. Pastas importantes

### No PC

| Item | Caminho |
|------|---------|
| Projeto | `c:\dev\contabo_pdv` |
| Settings | `setup\settings.py` |
| Env local | `.env` (não vai pro Git) |
| Modelo env | `.env.example` |

### No Contabo

| Item | Caminho |
|------|---------|
| Projeto | `/opt/pdv/app` |
| Settings | `/opt/pdv/app/setup/settings.py` |
| Env produção | `/opt/pdv/app/.env` |
| Nginx SSL | `/opt/pdv/app/deploy/nginx/default.conf` |

```bash
ssh root@207.244.248.73
cd /opt/pdv/app
ls
```

---

## 2. Ambiente local (Docker — igual à Contabo)

Pré-requisito: Docker Desktop aberto.

```powershell
cd c:\dev\contabo_pdv
copy .env.example .env
# Edite SECRET_KEY e POSTGRES_PASSWORD no .env

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- App: http://127.0.0.1:8000
- Health: http://127.0.0.1:8000/health/

Em segundo plano:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build
```

Logs:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml logs -f web
```

Parar:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml down
```

Migrations no container:

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec web python manage.py makemigrations
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec web python manage.py migrate
```

---

## 3. Nova feature (branch → teste → merge)

### 3.1 Criar branch

```powershell
cd c:\dev\contabo_pdv
git checkout develop
git pull origin develop
git checkout -b feature/nome-da-feature
```

### 3.2 Desenvolver e testar no Docker local

1. Suba o stack (seção 2).
2. Altere o código.
3. Se mudou models → `makemigrations` + `migrate`.
4. Teste em http://127.0.0.1:8000 com usuário real (dados já migrados do SQLite, se aplicável).

### 3.3 Commit e push

```powershell
git add .
git status
git commit -m "Descreva o porquê da mudança em 1-2 frases."
git push -u origin feature/nome-da-feature
```

**Não commit:** `.env`, `db.sqlite3`, dumps em `data/exports/*.json`.

### 3.4 Pull Request → develop

1. GitHub → Compare & pull request: `feature/...` → `develop`
2. Esperar CI verde (se ativo)
3. Merge

Ou merge local:

```powershell
git checkout develop
git pull origin develop
git merge feature/nome-da-feature
git push origin develop
```

---

## 4. Deploy na Contabo (após merge em develop)

### Opção A — comandos manuais (SSH)

```bash
ssh root@207.244.248.73
cd /opt/pdv/app
git fetch origin
git checkout develop
git pull origin develop
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web python manage.py migrate --noinput
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
curl -s https://oneirasistemas.com.br/health/
```

Teste a feature em: https://oneirasistemas.com.br

### Opção B — script de update

No servidor:

```bash
bash /opt/pdv/app/deploy/update.sh
```

No PC (via SSH):

```powershell
ssh root@207.244.248.73 "bash /opt/pdv/app/deploy/update.sh"
```

> O `.env` do servidor **não** vem do Git. Variável nova → edite `/opt/pdv/app/.env` e rode de novo o update (ou `up -d web`).

---

## 5. Variáveis de ambiente

| Onde | Arquivo |
|------|---------|
| Modelo (Git) | `.env.example` |
| Local | `c:\dev\contabo_pdv\.env` |
| Contabo | `/opt/pdv/app/.env` |

Feature precisa de env nova:

1. Documentar em `.env.example`
2. Colocar no `.env` local e testar
3. Colocar no `.env` Contabo
4. `docker compose ... up -d web` no servidor

---

## 6. HTTPS / SSL (já configurado)

- Certificado: Let's Encrypt → `oneirasistemas.com.br`
- URL: https://oneirasistemas.com.br
- Renovação: cron `/etc/cron.d/pdv-certbot`

Se `www` ganhar DNS A → `207.244.248.73`, reemitir certificado incluindo `www`.

---

## 7. Checklist rápido por feature

- [ ] Branch `feature/...` a partir de `develop`
- [ ] Docker local up + teste em localhost
- [ ] Migrations se necessário
- [ ] Commit + push + PR → `develop`
- [ ] Contabo: `git pull` + compose build + migrate (ou `deploy/update.sh`)
- [ ] Validar em https://oneirasistemas.com.br
- [ ] Apagar branch da feature após merge

---

## 8. Comandos úteis Contabo

```bash
# Logs
cd /opt/pdv/app
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f web

# Shell Django
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py shell

# Backup Postgres
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  pg_dump -U pdv pdv | gzip > /root/backup_pdv_$(date +%Y%m%d).sql.gz
```

---

## 9. Por que local ≈ produção

| | Local | Contabo |
|--|--------|---------|
| Compose | `docker-compose.dev.yml` | `docker-compose.prod.yml` |
| URL | `localhost:8000` | `https://oneirasistemas.com.br` |
| `.env` | `DEBUG=True` | `DEBUG=False` + HTTPS |
| Banco | Postgres 16 (Docker) | Postgres 16 (Docker) |
| Código | mesmo repo / migrations | mesmo repo / migrations |

Teste a feature no Docker local antes do deploy; o comportamento do app tende a ser o mesmo (salvo domínio/HTTPS).
