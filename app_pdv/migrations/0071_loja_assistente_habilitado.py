from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app_pdv', '0070_logauditoria_acao_admin'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='loja',
                    name='assistente_habilitado',
                    field=models.BooleanField(
                        default=False,
                        help_text='Liga o chat/assistente por loja. Sem chave de API, o modo offline usa os guias do PDV.',
                        verbose_name='Assistente da loja habilitado?',
                    ),
                ),
            ],
            database_operations=[
                migrations.RunSQL(
                    sql="""
                    ALTER TABLE app_pdv_loja
                    ADD COLUMN IF NOT EXISTS assistente_habilitado boolean;
                    UPDATE app_pdv_loja
                    SET assistente_habilitado = false
                    WHERE assistente_habilitado IS NULL;
                    ALTER TABLE app_pdv_loja
                    ALTER COLUMN assistente_habilitado SET DEFAULT false;
                    ALTER TABLE app_pdv_loja
                    ALTER COLUMN assistente_habilitado SET NOT NULL;
                    """,
                    reverse_sql="""
                    ALTER TABLE app_pdv_loja
                    DROP COLUMN IF EXISTS assistente_habilitado;
                    """,
                ),
            ],
        ),
    ]
