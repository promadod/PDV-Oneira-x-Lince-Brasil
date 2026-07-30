# Importa data/exports/sqlite_dump.json no Postgres via container web.
# Uso (com stack local no ar):
#   .\scripts\import_to_postgres.ps1

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$Dump = if ($args.Count -gt 0) { $args[0] } else { "data/exports/sqlite_dump.json" }
if (-not (Test-Path $Dump)) {
    Write-Error "Dump não encontrado: $Dump"
}

Write-Host "Migrate + loaddata_safe via container web..."
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T web python manage.py migrate --noinput
docker compose -f docker-compose.yml -f docker-compose.dev.yml exec -T web python manage.py loaddata_safe "$Dump"

Write-Host "OK — dados carregados."
Write-Host "Media (se necessário): docker compose -f docker-compose.yml -f docker-compose.dev.yml cp .\media\. web:/app/media/"
