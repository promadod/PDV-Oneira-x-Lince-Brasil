from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0049_codigo_barras'),
    ]

    operations = [
        migrations.AddField(
            model_name='loja',
            name='nome_marca_pdv',
            field=models.CharField(
                blank=True,
                default='',
                help_text='Marca no topo do menu (máx. 22 caracteres). Clique no nome no sistema para alterar.',
                max_length=22,
                verbose_name='Nome exibido no menu lateral',
            ),
        ),
    ]
