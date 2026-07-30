# Deploy Contabo — PDV Oneira / Lince Brasil

Domínio: `oneirasistemas.com.br`  
Servidor: `207.244.248.73`  
Repo: https://github.com/promadod/PDV-Oneira-x-Lince-Brasil

---

## Visão geral

| Ambiente | Comando |
|----------|---------|
| Local (dev) | `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build` |
| Contabo (prod) | `docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build` |

Serviços: **db** (Postgres `pdv`) + **web** (Django/Gunicorn) + **nginx** (só em prod; no dev o nginx fica desligado).

---

## 1. Você — preparação local

### 1.1 Backup do SQLite de produção

```powershell
mkdir c:\dev\backups -Force
copy c:\dev\contabo_pdv\db.sqlite3 c:\dev\backups\pdv_producao_$(Get-Date -Format yyyyMMdd).sqlite3
```

### 1.2 Arquivo `.env` (não vai para o Git)

```powershell
cd c:\dev\contabo_pdv
copy .env.example .env
```

Edite o `.env` e preencha:

| Variável | O que colocar |
|----------|----------------|
| `SECRET_KEY` | Gere com: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"` (com venv ativo) **ou** qualquer string longa aleatória |
| `DEBUG` | `True` no local |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` |
| `CSRF_TRUSTED_ORIGINS` | `http://localhost:8000,http://127.0.0.1:8000` |
| `POSTGRES_DB` | `pdv` |
| `POSTGRES_USER` | `pdv` |
| `POSTGRES_PASSWORD` | senha forte (sua escolha) |
| `POSTGRES_HOST` | `db` (nome do serviço Docker) |
| `POSTGRES_PORT` | `5432` |

### 1.3 Subir stack local

Requisito: **Docker Desktop** aberto.

```powershell
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

Teste: http://127.0.0.1:8000/health/ → `{"status":"ok",...}`

### 1.4 Migrar dados SQLite → Postgres (local)

O SQLite de produção pode estar com `django_migrations` desatualizado em relação ao schema real.
Fluxo validado:

```powershell
# 1) Cópia de trabalho + alinhar schema (fake das migrations já aplicadas no arquivo legado)
copy db.sqlite3 data\exports\db_work.sqlite3
$env:PYTHONIOENCODING="utf-8"
python manage.py migrate app_pdv 0053 --fake --settings=setup.settings_sqlite_export
python manage.py migrate --settings=setup.settings_sqlite_export --noinput

# 2) Export
.\scripts\export_sqlite.ps1
# (ou dumpdata direto — ver script)

# 3) Import no Docker (signals desligados)
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T web `
  python manage.py loaddata_safe data/exports/sqlite_dump.json

# 4) Media
docker compose -f docker-compose.yml -f docker-compose.dev.yml cp .\media\. web:/app/media/
```

Confira login em http://127.0.0.1:8000/accounts/login/ com um usuário real de produção.

---

## 2. Você — Contabo (primeira vez)

### 2.1 SSH e usuário deploy (recomendado)

```bash
ssh root@207.244.248.73
adduser deploy
usermod -aG sudo,docker deploy   # docker após instalar
# Copiar sua chave SSH para /home/deploy/.ssh/authorized_keys
```

Depois prefira: `ssh deploy@207.244.248.73`.

### 2.2 Instalar Docker

```bash
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
apt install -y git
```

### 2.3 Firewall

```bash
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
# NÃO abra 5432
```

### 2.4 Clone e `.env` de produção

```bash
mkdir -p /opt/pdv && chown deploy:deploy /opt/pdv
sudo -u deploy -i
cd /opt/pdv
git clone https://github.com/promadod/PDV-Oneira-x-Lince-Brasil.git app
cd app
cp .env.example .env
nano .env
```

Valores de produção no `.env`:

```env
SECRET_KEY=<outra chave, diferente da local>
DEBUG=False
ALLOWED_HOSTS=oneirasistemas.com.br,www.oneirasistemas.com.br,207.244.248.73
CSRF_TRUSTED_ORIGINS=https://oneirasistemas.com.br,https://www.oneirasistemas.com.br
POSTGRES_DB=pdv
POSTGRES_USER=pdv
POSTGRES_PASSWORD=<senha forte>
POSTGRES_HOST=db
POSTGRES_PORT=5432
CORS_ALLOWED_ORIGINS=https://oneirasistemas.com.br,https://www.oneirasistemas.com.br
SECURE_SSL_REDIRECT=False
```

(`SECURE_SSL_REDIRECT=False` enquanto o HTTPS ainda não estiver na frente do nginx; depois do Certbot pode ligar `True` se o redirect for no Django.)

### 2.5 Subir produção

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

Teste pelo IP: `http://207.244.248.73/health/`

### 2.6 Importar dump + media

No seu PC, envie o dump:

```powershell
scp data\exports\sqlite_dump.json deploy@207.244.248.73:/opt/pdv/app/data/exports/
```

No servidor, copie o dump **para dentro do container** e importe (a imagem de prod não monta o código do host):

```bash
cd /opt/pdv/app
docker compose -f docker-compose.yml -f docker-compose.prod.yml cp \
  ./data/exports/sqlite_dump.json web:/app/data/exports/sqlite_dump.json
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T web \
  python manage.py loaddata_safe data/exports/sqlite_dump.json

# Media (imagens de produtos)
docker compose -f docker-compose.yml -f docker-compose.prod.yml cp \
  ./media/. web:/app/media/
```

(Se a pasta `media` ainda não estiver no servidor, faça `scp -r media deploy@207.244.248.73:/opt/pdv/app/media` antes.)

---

## 3. Você — DNS Registro.br (só depois do app OK no IP)

1. Acesse [Registro.br](https://registro.br)
2. Domínio `oneirasistemas.com.br` → DNS
3. Registros **A**:
   - `@` → `207.244.248.73`
   - `www` → `207.244.248.73`
4. Aguarde propagação e configure SSL (Certbot / Caddy). Enquanto só HTTP na porta 80, o site já responde pelo domínio após o A record.

### SSL (Certbot no host, proxy para nginx — próximo passo)

Documentação oficial Contabo/Ubuntu + Certbot. Opção simples: instalar Caddy na frente ou `certbot --nginx` se o nginx estiver no host. Com nginx **só em Docker**, o caminho usual é:

- Traefik/Caddy como reverse proxy no host, **ou**
- Certificados montados em volume no container nginx (ajuste `deploy/nginx/`).

Peça na próxima sessão Agent para plugar HTTPS quando o DNS já apontar.

---

## 4. Você — secrets do GitHub (CI/CD)

No repo → **Settings → Secrets and variables → Actions**, crie:

| Secret | Valor |
|--------|--------|
| `CONTABO_HOST` | `207.244.248.73` |
| `CONTABO_USER` | `deploy` |
| `CONTABO_SSH_KEY` | conteúdo da chave **privada** do deploy |
| `CONTABO_APP_DIR` | `/opt/pdv/app` |

Push em `main` dispara o workflow `Deploy Contabo`.

---

## 5. Git — branches (prática diária)

```
main      → produção (protegida; só via PR)
develop   → integração
feature/* → trabalho do dia
```

```bash
git checkout -b develop
git push -u origin develop
git checkout -b feature/minha-tarefa
# ... commits ...
# PR → develop → (teste) → PR → main → deploy automático
```

No GitHub: proteja `main` (require PR + CI green).

---

## 6. Checklist go-live

- [ ] Backup `db.sqlite3` fora do PC de trabalho
- [ ] Stack local OK + dados importados
- [ ] Contabo Docker OK + `/health/`
- [ ] `loaddata` + media no servidor
- [ ] Login com usuário real
- [ ] DNS Registro.br
- [ ] HTTPS
- [ ] Apps Flutter apontando para `https://oneirasistemas.com.br`
- [ ] Secrets GitHub + deploy de teste
- [ ] `pg_dump` agendado (cron) no servidor

---

## Comandos úteis

```bash
# Logs
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs -f web

# Shell Django
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec web python manage.py shell

# Backup Postgres
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T db \
  pg_dump -U pdv pdv | gzip > backup_pdv_$(date +%Y%m%d).sql.gz
```
