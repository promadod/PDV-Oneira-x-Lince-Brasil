from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0047_grupos_avaria'),
    ]

    operations = [
        migrations.AddField(
            model_name='produto',
            name='eh_kit',
            field=models.BooleanField(
                default=False,
                help_text='Ao vender, baixa automaticamente vários itens de estoque conforme os componentes do kit.',
                verbose_name='Produto kit / promoção?',
            ),
        ),
        migrations.AlterField(
            model_name='produto',
            name='item_estoque',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name='produtos_venda', to='app_pdv.itemestoque',
                verbose_name='Item do Estoque',
            ),
        ),
        migrations.CreateModel(
            name='ComponenteKit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantidade', models.DecimalField(decimal_places=3, default=1.0, max_digits=10, verbose_name='Qtd por kit vendido')),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('item_estoque', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='kits_que_usam', to='app_pdv.itemestoque', verbose_name='Item de estoque')),
                ('produto_kit', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='componentes_kit', to='app_pdv.produto', verbose_name='Produto kit')),
            ],
            options={
                'verbose_name': 'Componente do kit',
                'verbose_name_plural': 'Componentes do kit',
                'ordering': ['ordem', 'id'],
                'unique_together': {('produto_kit', 'item_estoque')},
            },
        ),
    ]
