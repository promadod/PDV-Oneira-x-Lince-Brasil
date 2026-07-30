# Exporta SQLite de produção → JSON (após alinhar schema).
# Pré-requisito: .env com SECRET_KEY; venv com deps instaladas.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

New-Item -ItemType Directory -Force -Path "data\exports", "backups" | Out-Null

if (-not (Test-Path "db.sqlite3")) {
    Write-Error "db.sqlite3 não encontrado em $Root"
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
Copy-Item "db.sqlite3" "backups\db_producao_$Stamp.sqlite3"
Copy-Item "db.sqlite3" "data\exports\db_work.sqlite3" -Force
Write-Host "Backup: backups\db_producao_$Stamp.sqlite3"
Write-Host "Cópia de trabalho: data\exports\db_work.sqlite3"

$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "Alinhando django_migrations (fake até 0053) + migrate 0054 se necessário..."
# Se o SQLite já estiver no schema atual, estes comandos são idempotentes o suficiente
# para reexport. Em banco legado sem registro de migrations, faça:
#   python manage.py migrate app_pdv 0053 --fake --settings=setup.settings_sqlite_export
#   python manage.py migrate --settings=setup.settings_sqlite_export --noinput
python manage.py migrate --settings=setup.settings_sqlite_export --noinput

Write-Host "Exportando dumpdata..."
python manage.py dumpdata `
  --settings=setup.settings_sqlite_export `
  --natural-foreign `
  --natural-primary `
  -e contenttypes `
  -e auth.Permission `
  -e sessions.Session `
  --indent 2 `
  -o "data\exports\sqlite_dump.json"

Write-Host "OK: data\exports\sqlite_dump.json"
Get-Item "data\exports\sqlite_dump.json" | Select-Object FullName, Length
Write-Host "Depois, com o Docker no ar: docker compose ... exec web python manage.py loaddata_safe data/exports/sqlite_dump.json"
