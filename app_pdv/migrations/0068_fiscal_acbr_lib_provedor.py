from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0067_fiscal_acbr_credenciais'),
    ]

    operations = [
        migrations.AddField(
            model_name='fiscalconfig',
            name='provedor_emissao',
            field=models.CharField(
                choices=[('api', 'ACBr API (OAuth HTTP)'), ('lib', 'ACBrLib Pro (SEFAZ direto)')],
                default='api',
                help_text='API = caminho atual. Lib = worker com libacbrnfe64.so.',
                max_length=10,
                verbose_name='Provedor de emissão',
            ),
        ),
        migrations.AddField(
            model_name='fiscalconfig',
            name='acbr_lib_pfx_path',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Relativo ao MEDIA_ROOT ou absoluto no volume compartilhado com o worker.',
                max_length=500,
                verbose_name='Caminho do certificado A1 (PFX)',
            ),
        ),
        migrations.AddField(
            model_name='fiscalconfig',
            name='acbr_lib_pfx_senha',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Armazenada apenas no servidor.',
                max_length=255,
                verbose_name='Senha do certificado A1',
            ),
        ),
    ]
