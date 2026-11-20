from django.db import migrations, models


def marcar_lojas_piloto_padrao(apps, schema_editor):
    Loja = apps.get_model('app_pdv', 'Loja')
    # Sacolão / Mercadinho da Cris
    Loja.objects.filter(pk=15).update(segmento='mercadinho', loja_piloto=True)
    # Massini — revenda/depósito/distribuidora de gás
    Loja.objects.filter(pk=16).update(segmento='revenda_gas', loja_piloto=True)


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0072_perfilusuario_permissoes_fiscais'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='segmento',
            field=models.CharField(
                blank=True,
                choices=[
                    ('', '— Não informado'),
                    ('mercadinho', 'Mercadinho'),
                    ('revenda_gas', 'Revenda / Depósito / Distribuidora de gás'),
                ],
                default='',
                help_text='Usado no cadastro para sugerir importação de produtos da loja piloto do mesmo segmento.',
                max_length=20,
                verbose_name='Segmento da loja',
            ),
        ),
        migrations.AddField(
            model_name='loja',
            name='loja_piloto',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Marque para esta loja aparecer no select de importação de produtos/parâmetros fiscais '
                    'ao criar uma nova loja no Django Admin.'
                ),
                verbose_name='Loja piloto?',
            ),
        ),
        migrations.RunPython(marcar_lojas_piloto_padrao, noop_reverse),
    ]
