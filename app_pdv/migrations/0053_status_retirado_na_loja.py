from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0052_log_auditoria_acoes'),
    ]

    operations = [
        migrations.AlterField(
            model_name='venda',
            name='status',
            field=models.CharField(
                choices=[
                    ('ABERTO', 'Em Aberto (Balcão)'),
                    ('FINALIZADO', 'Finalizado'),
                    ('RETIRADO_NA_LOJA', 'Retirado na loja'),
                    ('ORCAMENTO', 'Orçamento'),
                    ('PENDENTE', 'Aguardando Aprovação'),
                    ('EM_PREPARACAO', 'Em Separação'),
                    ('SAIU_ENTREGA', 'Saiu para Entrega'),
                    ('CANCELADO', 'Cancelado/Recusado'),
                    ('AGUARDANDO_FINALIZAR', 'Pausado / Finalizar Depois'),
                    ('FIADO', 'Fiado (Pagamento Pendente)'),
                ],
                default='ABERTO',
                max_length=20,
            ),
        ),
    ]
