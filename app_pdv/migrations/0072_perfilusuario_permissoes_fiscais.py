from django.db import migrations, models


TELAS_FISCAIS_TODAS = [
    'hub', 'matriz', 'produtos', 'avulsa', 'documentos', 'nfce', 'lote', 'nfe',
    'contabilidade', 'relatorios', 'webhooks', 'contingencia', 'arquivos',
    'reforma', 'inutilizacao', 'manifestacao',
]


def preencher_permissoes_fiscais(apps, schema_editor):
    PerfilUsuario = apps.get_model('app_pdv', 'PerfilUsuario')
    Loja = apps.get_model('app_pdv', 'Loja')
    PerfilUsuario.objects.filter(perm_fiscal=True).update(perm_fiscal_telas=TELAS_FISCAIS_TODAS)
    gerente_ids = list(
        Loja.objects.exclude(gerente_id=None).values_list('gerente_id', flat=True)
    )
    if gerente_ids:
        PerfilUsuario.objects.filter(user_id__in=gerente_ids).update(
            usuario_padrao_loja=True,
            perm_fiscal_config=True,
            perm_fiscal=True,
            perm_fiscal_telas=TELAS_FISCAIS_TODAS,
        )


def noop_reverse(apps, schema_editor):
    return None


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0071_loja_assistente_habilitado'),
    ]

    operations = [
        migrations.AddField(
            model_name='perfilusuario',
            name='perm_fiscal_config',
            field=models.BooleanField(
                default=False,
                help_text='Libera os botões Integração API e Config. Também vale para o usuário padrão da loja e para root.',
                verbose_name='Alterar Integração API e Config fiscal',
            ),
        ),
        migrations.AddField(
            model_name='perfilusuario',
            name='perm_fiscal_telas',
            field=models.JSONField(
                blank=True,
                default=list,
                help_text='Lista de chaves das telas operacionais liberadas (Hub, Produtos, Avulsa, etc.).',
                verbose_name='Telas do módulo fiscal',
            ),
        ),
        migrations.AddField(
            model_name='perfilusuario',
            name='usuario_padrao_loja',
            field=models.BooleanField(
                default=False,
                help_text='Criado automaticamente ao cadastrar a loja. Tem Integração API, Config e todas as telas fiscais.',
                verbose_name='Usuário padrão da loja',
            ),
        ),
        migrations.RunPython(preencher_permissoes_fiscais, noop_reverse),
    ]
