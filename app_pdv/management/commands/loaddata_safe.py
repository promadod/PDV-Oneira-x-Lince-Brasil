from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.models.signals import post_delete, post_save, pre_save

from app_pdv.models import (
    ItemVenda,
    Loja,
    Venda,
    blindagem_edicao_item,
    blindagem_exclusao_item,
    blindagem_novo_item,
    blindagem_status_venda,
    criar_formas_pagamento_nova_loja,
    criar_perfil_usuario,
    processar_fidelidade_ao_finalizar,
    salvar_perfil_usuario,
)


class Command(BaseCommand):
    help = "loaddata com signals desligados + reset de sequences (migração SQLite→Postgres)"

    def add_arguments(self, parser):
        parser.add_argument("fixture", nargs="?", default="data/exports/sqlite_dump.json")

    def handle(self, *args, **options):
        fixture = options["fixture"]

        pairs = [
            (post_save, criar_perfil_usuario, User),
            (post_save, salvar_perfil_usuario, User),
            (post_save, criar_formas_pagamento_nova_loja, Loja),
            (post_save, processar_fidelidade_ao_finalizar, Venda),
            (post_save, blindagem_novo_item, ItemVenda),
            (post_delete, blindagem_exclusao_item, ItemVenda),
            (pre_save, blindagem_status_venda, Venda),
            (pre_save, blindagem_edicao_item, ItemVenda),
        ]

        for signal, receiver, sender in pairs:
            signal.disconnect(receiver, sender=sender)

        try:
            call_command("loaddata", fixture, verbosity=1)
        finally:
            for signal, receiver, sender in pairs:
                signal.connect(receiver, sender=sender)

        if connection.vendor == "postgresql":
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DO $$
                    DECLARE r record;
                    BEGIN
                      FOR r IN (
                        SELECT
                          format('%I.%I', n.nspname, c.relname) AS seq,
                          format('%I.%I', tn.nspname, t.relname) AS tbl
                        FROM pg_class c
                        JOIN pg_namespace n ON n.oid = c.relnamespace
                        JOIN pg_depend d ON d.objid = c.oid AND d.deptype = 'a'
                        JOIN pg_class t ON t.oid = d.refobjid
                        JOIN pg_namespace tn ON tn.oid = t.relnamespace
                        WHERE c.relkind = 'S' AND n.nspname = 'public'
                      ) LOOP
                        EXECUTE format(
                          'SELECT setval(%L, COALESCE((SELECT MAX(id) FROM %s), 1))',
                          r.seq, r.tbl
                        );
                      END LOOP;
                    END $$;
                    """
                )
            self.stdout.write(self.style.SUCCESS("Sequences Postgres ajustadas."))

        self.stdout.write(self.style.SUCCESS(f"Import concluído: {fixture}"))
