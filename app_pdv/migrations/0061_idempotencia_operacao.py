from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('app_pdv', '0060_troco_recebido_conferencia_loja'),
    ]

    operations = [
        migrations.CreateModel(
            name='IdempotenciaOperacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('endpoint', models.CharField(max_length=80)),
                ('chave', models.CharField(max_length=64)),
                ('resposta', models.JSONField(blank=True, default=dict)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('loja', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='idempotencias', to='app_pdv.loja')),
                ('usuario', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='idempotencias', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'Idempotência de operação',
                'verbose_name_plural': 'Idempotências de operação',
            },
        ),
        migrations.AddIndex(
            model_name='idempotenciaoperacao',
            index=models.Index(fields=['criado_em'], name='app_pdv_idem_criado_idx'),
        ),
        migrations.AddConstraint(
            model_name='idempotenciaoperacao',
            constraint=models.UniqueConstraint(fields=('loja', 'endpoint', 'chave'), name='idempotencia_unica_loja_endpoint_chave'),
        ),
    ]
