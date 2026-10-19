"""Valida Client ID/Secret da ACBr API (token OAuth + GET /empresas)."""
from django.core.management.base import BaseCommand, CommandError

from app_pdv.fiscal.acbr_client import AcbrApiError
from app_pdv.fiscal.services import testar_conexao_acbr


class Command(BaseCommand):
    help = 'Testa autenticação e listagem de empresas na ACBr API.'

    def handle(self, *args, **options):
        try:
            teste = testar_conexao_acbr()
        except AcbrApiError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS('ACBr API OK'))
        self.stdout.write(f"base: {teste.get('base_url')}")
        self.stdout.write(f"scope: {teste.get('scope')}")
        self.stdout.write(f"empresas: {teste.get('empresas_cadastradas')}")
        self.stdout.write(f"expires_in: {teste.get('expires_in')}")
