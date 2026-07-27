from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0048_produto_kit'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='trabalha_com_leitor_codigo_barras',
            field=models.BooleanField(
                default=False,
                help_text='Ativo: na tela de vendas, leituras USB selecionam o produto automaticamente. Cadastre o código de barras em cada produto.',
                verbose_name='Trabalha com leitor de código de barras?',
            ),
        ),
        migrations.AddField(
            model_name='produto',
            name='codigo_barras',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Lido pelo leitor USB na tela de vendas (quando a loja usa leitor de código de barras).',
                max_length=50,
                verbose_name='Código de barras (EAN/GTIN)',
            ),
        ),
        migrations.AddConstraint(
            model_name='produto',
            constraint=models.UniqueConstraint(
                condition=~Q(codigo_barras=''),
                fields=('loja', 'codigo_barras'),
                name='produto_codigo_barras_unico_por_loja',
            ),
        ),
    ]
