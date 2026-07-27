from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0046_taxa_servico'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='divide_produtos_por_grupos',
            field=models.BooleanField(
                default=False,
                help_text='Ativo: estoque e produtos organizados em grupos (ex.: Bebidas, Petiscos). Recibo de fechamento de caixa agrupa as saídas por grupo.',
                verbose_name='Dividir produtos por grupos?',
            ),
        ),
        migrations.CreateModel(
            name='GrupoProduto',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100)),
                ('ordem', models.PositiveIntegerField(default=0)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grupos_produto', to='app_pdv.loja')),
            ],
            options={
                'verbose_name': 'Grupo de Produto',
                'verbose_name_plural': 'Grupos de Produto',
                'ordering': ['ordem', 'nome'],
                'unique_together': {('loja', 'nome')},
            },
        ),
        migrations.AddField(
            model_name='produto',
            name='grupo',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='produtos', to='app_pdv.grupoproduto', verbose_name='Grupo',
            ),
        ),
        migrations.AddField(
            model_name='venda',
            name='eh_avaria',
            field=models.BooleanField(default=False, verbose_name='Venda Avaria?'),
        ),
    ]
