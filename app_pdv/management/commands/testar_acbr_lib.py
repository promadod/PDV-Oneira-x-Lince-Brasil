from django.core.management.base import BaseCommand

from app_pdv.fiscal.acbr_lib_client import AcbrLibClient, AcbrLibError, acbr_lib_habilitada
from app_pdv.fiscal.models import FiscalConfig
from app_pdv.fiscal.services import testar_status_acbr_lib


class Command(BaseCommand):
    help = 'Testa o worker ACBrLib (health e, se houver loja com PFX, StatusServico SEFAZ).'

    def add_arguments(self, parser):
        parser.add_argument('--loja', type=int, default=None, help='ID da loja com PFX configurado')

    def handle(self, *args, **options):
        if not acbr_lib_habilitada():
            self.stderr.write(self.style.WARNING('ACBR_LIB_ENABLED não está ativo.'))
        try:
            health = AcbrLibClient().health()
        except AcbrLibError as exc:
            self.stderr.write(self.style.ERROR(f'Health falhou: {exc}'))
            return
        self.stdout.write(self.style.SUCCESS(f'Worker health: {health}'))

        loja_id = options.get('loja')
        qs = FiscalConfig.objects.exclude(acbr_lib_pfx_path='').select_related('loja')
        if loja_id:
            qs = qs.filter(loja_id=loja_id)
        cfg = qs.first()
        if not cfg:
            self.stdout.write('Nenhuma loja com PFX — pulando StatusServico.')
            return
        try:
            teste = testar_status_acbr_lib(cfg)
        except AcbrLibError as exc:
            self.stderr.write(self.style.ERROR(f'Status SEFAZ falhou (loja {cfg.loja_id}): {exc}'))
            return
        self.stdout.write(self.style.SUCCESS(f'Status SEFAZ loja {cfg.loja_id}: {teste}'))
