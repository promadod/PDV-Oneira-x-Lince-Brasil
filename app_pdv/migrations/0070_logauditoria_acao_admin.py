from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0069_fiscalconfig_telefone'),
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
                    ('ADMIN', 'Django Admin'),
                    ('OUTRO', 'Outro'),
                ],
                default='OUTRO',
                max_length=20,
            ),
        ),
    ]
