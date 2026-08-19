from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0055_parcela_mercadoria_agendada'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='trabalha_com_balanca_granel',
            field=models.BooleanField(
                default=False,
                help_text='Ativo: o PDV decodifica a etiqueta da Prix 4 Uno / Prix 3 Fit+L42 (código digitado na balança + peso). Use o mesmo código do cadastro na tabela da balança (MGV).',
                verbose_name='Trabalha com balança de granel (etiqueta)?',
            ),
        ),
        migrations.AddField(
            model_name='loja',
            name='balanca_ean_prefixo',
            field=models.CharField(
                default='2',
                help_text='Padrão Toledo/supermercado: 2. Deve ser o mesmo no MGV das duas balanças.',
                max_length=2,
                verbose_name='Prefixo EAN da etiqueta (balança)',
            ),
        ),
        migrations.AddField(
            model_name='loja',
            name='balanca_plu_digitos',
            field=models.PositiveSmallIntegerField(
                choices=[(4, '4 dígitos'), (5, '5 dígitos'), (6, '6 dígitos')],
                default=6,
                help_text='Tamanho do código digitado na balança (4, 5 ou 6). Igual no MGV da Prix 4 Uno e da Prix 3 Fit.',
                verbose_name='Dígitos do código na balança (PLU)',
            ),
        ),
        migrations.AddField(
            model_name='loja',
            name='balanca_ean_variavel',
            field=models.CharField(
                choices=[
                    ('PESO', 'Peso (gramas) na etiqueta'),
                    ('PRECO', 'Preço total (centavos) na etiqueta'),
                ],
                default='PESO',
                help_text='PESO: gramas do produto. PRECO: valor total em centavos. Tem que ser a mesma opção no MGV.',
                max_length=8,
                verbose_name='O que a etiqueta leva além do código',
            ),
        ),
        migrations.AlterField(
            model_name='loja',
            name='trabalha_com_leitor_codigo_barras',
            field=models.BooleanField(
                default=False,
                help_text='Ativo: na tela de vendas, leituras USB selecionam o produto automaticamente. Cadastre o código em cada produto. Necessário também para ler a etiqueta da balança.',
                verbose_name='Trabalha com leitor de código de barras?',
            ),
        ),
        migrations.AlterField(
            model_name='produto',
            name='codigo_barras',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Unidade: EAN do fabricante. Granel: o mesmo código digitado na balança (PLU). Na etiqueta a balança junta este código + peso; o PDV separa na leitura.',
                max_length=50,
                verbose_name='Código do produto (barras / balança)',
            ),
        ),
    ]
