from decimal import Decimal

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


def preencher_entradas_existentes(apps, schema_editor):
    EntradaEstoque = apps.get_model('app_pdv', 'EntradaEstoque')
    for entrada in EntradaEstoque.objects.all().iterator():
        qtd = Decimal(str(entrada.quantidade or 0))
        preco = Decimal(str(entrada.preco_unitario_compra or 0))
        total = (qtd * preco).quantize(Decimal('0.01'))
        EntradaEstoque.objects.filter(pk=entrada.pk).update(
            valor_total=total,
            valor_pago=total,
            status_pagamento='QUITADO',
            eh_consignado=False,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0053_status_retirado_na_loja'),
        ('auth', '0012_alter_user_first_name_max_length'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='gerencia_pagamento_mercadorias',
            field=models.BooleanField(
                default=False,
                help_text='Ativo: entradas consignadas ficam a pagar; baixas no relatório CMV descontam o meio (Pix/Dinheiro etc.) no caixa do dia.',
                verbose_name='Gerenciar pagamento de mercadorias (CMV)?',
            ),
        ),
        migrations.AddField(
            model_name='entradaestoque',
            name='eh_consignado',
            field=models.BooleanField(
                default=False,
                help_text='Se marcado e a loja gerencia CMV, a entrada fica a pagar até as baixas.',
                verbose_name='Compra consignada (pagar depois)?',
            ),
        ),
        migrations.AddField(
            model_name='entradaestoque',
            name='valor_total',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12,
                verbose_name='Valor total da compra',
            ),
        ),
        migrations.AddField(
            model_name='entradaestoque',
            name='valor_pago',
            field=models.DecimalField(
                decimal_places=2, default=0, max_digits=12,
                verbose_name='Valor já pago',
            ),
        ),
        migrations.AddField(
            model_name='entradaestoque',
            name='status_pagamento',
            field=models.CharField(
                choices=[
                    ('QUITADO', 'Quitado'),
                    ('PENDENTE', 'A pagar'),
                    ('PARCIAL', 'Pago parcial'),
                ],
                default='QUITADO',
                max_length=10,
                verbose_name='Status do pagamento',
            ),
        ),
        migrations.CreateModel(
            name='PagamentoMercadoria',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('valor', models.DecimalField(decimal_places=2, max_digits=12)),
                ('meio_liquidacao', models.CharField(
                    choices=[
                        ('DINHEIRO', 'Dinheiro'),
                        ('PIX', 'Pix'),
                        ('CREDITO', 'Cartão de Crédito'),
                        ('DEBITO', 'Cartão de Débito'),
                        ('CORTESIA', 'Cortesia'),
                    ],
                    default='PIX',
                    max_length=20,
                    verbose_name='Meio de pagamento',
                )),
                ('data_pagamento', models.DateTimeField(default=django.utils.timezone.now)),
                ('observacao', models.CharField(blank=True, default='', max_length=200)),
                ('caixa', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='pagamentos_mercadoria', to='app_pdv.caixa',
                    verbose_name='Turno de caixa',
                )),
                ('entrada', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pagamentos', to='app_pdv.entradaestoque',
                )),
                ('loja', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='pagamentos_mercadoria', to='app_pdv.loja',
                )),
                ('registrado_por', models.ForeignKey(
                    blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                    related_name='pagamentos_mercadoria', to='auth.user',
                )),
            ],
            options={
                'verbose_name': 'Pagamento de mercadoria',
                'verbose_name_plural': 'Pagamentos de mercadorias',
                'ordering': ['-data_pagamento'],
            },
        ),
        migrations.RunPython(preencher_entradas_existentes, migrations.RunPython.noop),
    ]
