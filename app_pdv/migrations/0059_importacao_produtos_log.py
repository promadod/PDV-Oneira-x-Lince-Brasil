from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app_pdv', '0056_balanca_granel_ean'),
    ]

    operations = [
        migrations.AlterField(
            model_name='logauditoria',
            name='acao',
            field=models.CharField(
                choices=[
                    ('CRIAR', 'Criou'),
                    ('EDITAR', 'Editou'),
                    ('EXCLUIR', 'Excluiu'),
                    ('LOGIN', 'Login'),
                    ('LOGOUT', 'Logout'),
                    ('TRANSFERIR', 'Transferiu estoque'),
                    ('VENDA', 'Venda'),
                    ('CAIXA', 'Caixa'),
                    ('ESTOQUE', 'Estoque'),
                    ('SENHA', 'Senha / usuário'),
                    ('CONFIG', 'Configuração'),
                    ('IMPORTACAO', 'Importação'),
                    ('OUTRO', 'Outro'),
                ],
                default='OUTRO',
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name='ImportacaoProdutosLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome_arquivo', models.CharField(max_length=255)),
                ('modo_estoque', models.CharField(
                    choices=[('SOMAR', 'Somar ao estoque existente'), ('SUBSTITUIR', 'Substituir estoque pelo da planilha')],
                    default='SOMAR',
                    max_length=12,
                )),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('produtos_criados', models.PositiveIntegerField(default=0)),
                ('produtos_atualizados', models.PositiveIntegerField(default=0)),
                ('linhas_processadas', models.PositiveIntegerField(default=0)),
                ('revertida_em', models.DateTimeField(blank=True, null=True)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='importacoes_produtos', to='app_pdv.loja')),
                ('revertida_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='importacoes_produtos_revertidas', to=settings.AUTH_USER_MODEL)),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='importacoes_produtos', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Importação de produtos',
                'verbose_name_plural': 'Importações de produtos',
                'ordering': ['-criado_em'],
            },
        ),
        migrations.CreateModel(
            name='ImportacaoProdutosItemSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome_item', models.CharField(max_length=150)),
                ('estoque_antes', models.DecimalField(decimal_places=3, default=0, max_digits=10)),
                ('estoque_depois', models.DecimalField(decimal_places=3, default=0, max_digits=10)),
                ('item_criado', models.BooleanField(default=False)),
                ('importacao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='itens_snapshot', to='app_pdv.importacaoprodutoslog')),
                ('item_estoque', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='snapshots_importacao', to='app_pdv.itemestoque')),
            ],
            options={
                'verbose_name': 'Snapshot item (importação)',
                'verbose_name_plural': 'Snapshots item (importação)',
            },
        ),
        migrations.CreateModel(
            name='ImportacaoProdutosProdutoSnapshot',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome_venda', models.CharField(max_length=150)),
                ('linha_planilha', models.PositiveIntegerField(default=0)),
                ('produto_criado', models.BooleanField(default=False)),
                ('preco_compra_antes', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('preco_venda_antes', models.DecimalField(blank=True, decimal_places=2, max_digits=10, null=True)),
                ('quantidade_baixa_antes', models.DecimalField(blank=True, decimal_places=3, max_digits=10, null=True)),
                ('codigo_barras_antes', models.CharField(blank=True, default='', max_length=50)),
                ('grupo_id_antes', models.PositiveIntegerField(blank=True, null=True)),
                ('ativo_antes', models.BooleanField(blank=True, null=True)),
                ('importacao', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='produtos_snapshot', to='app_pdv.importacaoprodutoslog')),
                ('produto', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='snapshots_importacao', to='app_pdv.produto')),
            ],
            options={
                'verbose_name': 'Snapshot produto (importação)',
                'verbose_name_plural': 'Snapshots produto (importação)',
            },
        ),
    ]
