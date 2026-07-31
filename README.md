# Magno Distribuidora / PDV Oneira — Sistema PDV & Delivery (SaaS)

> Solução Full-Stack para gestão de distribuidoras, mercados e delivery: back-office web, PDV e apps móveis.

![Status do Projeto](https://img.shields.io/badge/Status-Em_Desenvolvimento-yellow)
![Python](https://img.shields.io/badge/Backend-Django-green)
![Flutter](https://img.shields.io/badge/Frontend-Flutter-blue)

## Sobre o Projeto

Sistema **SaaS** multi-lojas para varejo e atacado: estoque, financeiro e logística de entregas, com isolamento de dados por estabelecimento.

---

## Funcionalidades Principais

### Back-office & Gestão
* Multi-tenant (várias lojas)
* Estoque com baixa/estorno automático
* Caixa, receitas, despesas e relatórios
* Cupons não-fiscais (impressão térmica)

### Apps Frontend (Flutter)
* App Cliente (vitrine)
* App Motoboy/Entregador
* App PDV

---

## Tecnologias

### Backend
* Python 3.12+ / Django 6.x
* PostgreSQL 16 (Docker) — SQLite só para exportação de legado
* Docker Compose + Gunicorn + Nginx (Contabo)
* Autenticação Django + PerfilUsuario

### Frontend
* Flutter (Web / Android)
* API REST (JSON)

---

## Como executar

Guia completo (Contabo, DNS Registro.br, migração SQLite → Postgres, CI/CD):

**[DEPLOY_CONTABO.md](DEPLOY_CONTABO.md)**

### Pré-requisitos
* Docker Desktop (recomendado) **ou** Python 3.12+ + PostgreSQL
* Git
* Flutter SDK (apps)

### Docker local (igual à Contabo)

```powershell
copy .env.example .env
# Edite SECRET_KEY e POSTGRES_PASSWORD em .env

docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
# http://127.0.0.1:8000/health/
```

### Venv

```bash
git clone https://github.com/promadod/PDV-Oneira-x-Lince-Brasil.git
cd PDV-Oneira-x-Lince-Brasil
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

O banco padrão é **PostgreSQL**. Para migrar o `db.sqlite3` de produção: `scripts/export_sqlite.ps1` e depois `scripts/import_to_postgres.ps1`.
