from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0068_fiscal_acbr_lib_provedor'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiscalconfig',
            name='telefone',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Exibido no cabeçalho do DANFE/NFC-e (tag fone do emitente).',
                max_length=20,
                verbose_name='Telefone (DANFE)',
            ),
        ),
    ]
