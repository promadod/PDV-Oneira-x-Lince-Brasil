from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0059_importacao_produtos_log'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='conferencia_dinheiro_habilitada',
            field=models.BooleanField(
                default=True,
                help_text='Ativo: vendas em dinheiro exigem botão Receber no histórico (útil para delivery/app). '
                           'Desligado: confirmação automática — ideal para lojas só com venda no balcão.',
                verbose_name='Conferência de pagamento em dinheiro?',
            ),
        ),
        migrations.AddField(
            model_name='venda',
            name='valor_recebido_dinheiro',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='Valor recebido em dinheiro',
            ),
        ),
        migrations.AddField(
            model_name='liquidacaovenda',
            name='valor_recebido_dinheiro',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=10,
                null=True,
                verbose_name='Valor recebido em dinheiro',
            ),
        ),
    ]
