from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0050_nome_marca_pdv'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='cnpj',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Exibido no rodapé do PDV. Ex: 00.000.000/0001-00',
                max_length=18,
                verbose_name='CNPJ',
            ),
        ),
    ]
