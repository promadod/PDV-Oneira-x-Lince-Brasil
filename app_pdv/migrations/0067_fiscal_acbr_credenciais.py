from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0066_natureza_operacao_fiscal'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiscalconfig',
            name='acbr_client_id',
            field=models.CharField(blank=True, default='', max_length=128, verbose_name='ACBr Client ID'),
        ),
        migrations.AddField(
            model_name='fiscalconfig',
            name='acbr_client_secret',
            field=models.CharField(
                blank=True, default='', max_length=512,
                help_text='Credencial OAuth da ACBr API. Armazenada apenas no servidor.',
                verbose_name='ACBr Client Secret',
            ),
        ),
    ]
